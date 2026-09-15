"""Controller-side UCI preflight and rename-only migration; no Python on OpenWrt."""
import json
import os
import re
import shlex
import tempfile
from pathlib import Path

from ansible.plugins.action import ActionBase

ID = re.compile(r'^[A-Za-z0-9_]+$')


def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError('UCI package and section IDs must contain only letters, digits and underscores')
    return value


def parse_export(data, package, section_ids):
    """Parse UCI export, retaining list/scalar distinction and section order."""
    lexer = shlex.shlex(data, posix=True, punctuation_chars='\n')
    lexer.whitespace = ' \t\r'
    lexer.whitespace_split = True
    records, record = [], []
    for token in lexer:
        if token and set(token) == {'\n'}:
            if record:
                records.append(record)
                record = []
        else:
            record.append(token)
    if record:
        records.append(record)
    sections = []
    for record in records:
        op, *args = record
        if op == 'package' and args == [package]:
            continue
        if op == 'config' and len(args) in (1, 2):
            sections.append({'type': args[0], 'name': args[1] if len(args) == 2 else None,
                             'options': {}})
        elif op in ('option', 'list') and len(args) == 2 and sections:
            key, value = args
            options = sections[-1]['options']
            if op == 'list':
                if key in options and not isinstance(options[key], list):
                    raise ValueError('Mixed UCI option/list declarations; inspect configuration')
                options.setdefault(key, []).append(value)
            else:
                options[key] = value
        else:
            raise ValueError('Unsupported UCI export syntax; inspect configuration privately')
    if len(sections) != len(section_ids):
        raise ValueError('Configuration changed during discovery; retry after other writers finish')
    for section, (old_id, kind) in zip(sections, section_ids):
        identifier(old_id)
        if section['type'] != kind or section['name'] not in (None, old_id):
            raise ValueError('Configuration changed during discovery')
        section['id'] = old_id
    return sections


def show_ids(data, package):
    # -X uses persistent cfg IDs, never positional @type[index] selectors.
    result = []
    pattern = re.compile(r'^' + re.escape(package) + r'\.([A-Za-z0-9_]+)=([^\n]+)$', re.M)
    for match in pattern.finditer(data):
        kind = shlex.split(match[2])
        if len(kind) != 1:
            raise ValueError('Invalid section type in UCI discovery')
        result.append((match[1], kind[0]))
    return result


def desired_sections(groups):
    desired = []
    for group in groups:
        for entry in group.get('entries', []):
            identity = entry.get('find')
            if identity is None and 'identity' in group:
                identity = {key: entry[key] for key in group['identity']}
            desired.append({'id': identifier(entry['id']), 'type': group['type'],
                            'find': identity, 'state': entry.get('state', 'present')})
    return desired


def plan_package(sections, desired):
    """Reject ambiguous identities/occupied IDs before returning any renames."""
    by_id = {section['id']: section for section in sections}
    reserved, claimed, renames = set(), {}, []
    for entry in desired:
        name = identifier(entry['id'])
        if name in reserved:
            raise ValueError(f'Duplicate desired section ID: {name}')
        reserved.add(name)
        if entry['state'] not in ('present', 'absent'):
            raise ValueError(f'Invalid desired state for {name}')
    for entry in desired:
        name, kind, identity = entry['id'], entry['type'], entry['find']
        destination = by_id.get(name)
        if destination and destination['type'] != kind:
            raise ValueError(f'Destination {name} belongs to another section type')
        matches = [] if identity is None else [s for s in sections if s['type'] == kind and
                   all(s['options'].get(k) == v for k, v in identity.items())]
        if len(matches) > 1:
            raise ValueError(f'Ambiguous identity for {name}; resolve duplicate sections first')
        match = matches[0] if matches else None
        if destination and match and destination['id'] != match['id']:
            raise ValueError(f'Destination {name} and its semantic identity refer to different sections')
        # Existing canonical IDs may change values (e.g. SANs or SSID). An
        # occupied ID must never hide a *different* matching legacy section.
        source = destination or match
        if not source:
            continue  # missing present: reconciliation creates it; absent: noop
        if source['id'] in claimed:
            raise ValueError(f'Two desired sections claim {source["id"]}')
        claimed[source['id']] = name
        if source['id'] != name or source['name'] is None:
            renames.append({'from': source['id'], 'to': name, 'type': kind, 'reason': 'managed'})
    occupied = set(by_id) | reserved
    for section in sections:
        if section['name'] is not None or section['id'] in claimed:
            continue
        # Retain unlisted stock sections. Prefer descriptive names; fall back
        # to the persistent opaque UCI ID, never its position in the package.
        label = section['options'].get('name', section['options'].get('interface', section['id']))
        if not isinstance(label, str):
            label = section['id']
        label = re.sub('[^a-z0-9_]+', '_', label.lower()).strip('_')[:48] or section['id']
        kind = re.sub('[^a-z0-9_]+', '_', section['type'].lower())
        name = f'retained_{kind}_{label}'
        if name in occupied:
            name += '_' + section['id']
        if name in occupied:
            raise ValueError('Retained section name collision; supply an explicit identity')
        occupied.add(name)
        renames.append({'from': section['id'], 'to': name, 'type': section['type'], 'reason': 'retained'})
    return renames


def rename_script(plans):
    packages = [identifier(p) for p, changes in plans.items() if changes]
    if not packages:
        return ''
    lines = ['set -eu', 'umask 077', 'mkdir /var/lock/ansible-uci-migration.lock',
             'backup=""', 'done_ok=0',
             'cleanup() { rc=$?; trap - EXIT HUP INT TERM; '
             'if [ "$done_ok" = 0 ] && [ -n "$backup" ]; then '
             'for p in ' + ' '.join(packages) + '; do '
             'if [ -f "$backup/$p" ]; then uci -q revert "$p" || true; '
             'cp -p "$backup/$p" "/etc/config/$p"; fi; done; fi; '
             'rmdir /var/lock/ansible-uci-migration.lock; exit "$rc"; }',
             'trap cleanup EXIT', 'trap "exit 1" HUP INT TERM']
    for package in packages:
        lines.append(f'test -z "$(uci changes {package})"')
    lines.append('backup=$(mktemp -d /tmp/ansible-uci-migration.XXXXXX)')
    for package in packages:
        lines.append(f'cp -p /etc/config/{package} "$backup/{package}"')
    for package in packages:
        for rename in plans[package]:
            old, new = identifier(rename['from']), identifier(rename['to'])
            lines.append(f'uci rename {package}.{old}={new}')
    if 'firewall' in packages:
        lines.append('fw4 check >/dev/null 2>&1')
    for package in packages:
        lines.append(f'uci commit {package}')
        lines.append(f'test -z "$(uci changes {package})"')
    lines.extend(['done_ok=1', 'printf "%s\\n" "$backup"'])
    return '\n'.join(lines)


class ActionModule(ActionBase):
    TRANSFERS_FILES = False
    _supports_check_mode = True
    _supports_async = False

    def _read(self, command):
        response = self._low_level_execute_command(command)
        if response.get('rc', 1):
            # Never return raw output: exports and errors can contain secrets.
            raise ValueError('Remote UCI discovery/migration failed; inspect the device privately')
        return response.get('stdout', '')

    def run(self, tmp=None, task_vars=None):
        result = super().run(tmp, task_vars)
        try:
            args = self._task.args
            mode = args.get('mode', 'plan')
            if mode not in ('plan', 'apply'):
                raise ValueError('mode must be plan or apply')
            packages = args.get('packages', {})
            plans, snapshots = {}, {}
            # Validate the complete desired catalogue even for missing packages.
            desired = {identifier(p): desired_sections(groups) for p, groups in packages.items()}
            for package, entries in desired.items():
                plan_package([], entries)
                if self._read(f'if test -f /etc/config/{package}; then echo present; fi').strip() != 'present':
                    plans[package] = []
                    continue
                if self._read(f'uci changes {package}').strip():
                    raise ValueError(f'Uncommitted changes in {package}; back up and resolve them before retrying')
                exported = self._read(f'uci -N export {package}')
                ids = show_ids(self._read(f'uci -X show {package}'), package)
                sections = parse_export(exported, package, ids)
                plans[package] = plan_package(sections, entries)
                snapshots[package] = exported
            manifest = {'host': task_vars['inventory_hostname'], 'packages': plans,
                        'mode': mode, 'check_mode': self._task.check_mode}
            directory = args.get('manifest_dir')
            if directory:
                directory = Path(os.path.expanduser(directory))
                directory.mkdir(parents=True, exist_ok=True, mode=0o700)
                host = re.sub('[^A-Za-z0-9_.-]', '_', task_vars['inventory_hostname'])
                target = directory / (host + '--' + '-'.join(sorted(packages)) + '.json')
                fd, temporary = tempfile.mkstemp(dir=directory)
                try:
                    with os.fdopen(fd, 'w') as output:
                        json.dump(manifest, output, indent=2)
                        output.write('\n')
                    os.replace(temporary, target)
                finally:
                    if os.path.exists(temporary):
                        os.unlink(temporary)
                result['manifest_path'] = str(target)
            result['renames'] = plans
            result['changed'] = any(plans.values())
            if mode == 'apply' and not self._task.check_mode and result['changed']:
                for package, snapshot in snapshots.items():
                    if self._read(f'uci -N export {package}') != snapshot:
                        raise ValueError('Configuration changed after preflight; no migration attempted')
                result['backup_path'] = self._read(rename_script(plans)).strip()
            return result
        except (ValueError, KeyError, TypeError, OSError):
            # These exceptions must not include parser values or task arguments.
            import sys
            exc = sys.exc_info()[1]
            message = str(exc) if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError) else 'Invalid migration input or unavailable manifest directory'
            result.update(failed=True, changed=False, msg=message)
            return result
