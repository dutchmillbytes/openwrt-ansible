import copy
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault('ANSIBLE_LOCAL_TEMP', '/tmp/ansible-tests')
spec = importlib.util.spec_from_file_location('uci_migrate', Path(__file__).resolve().parents[1] / 'plugins/action/uci_migrate.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def section(name, identity, kind='device', anonymous=False):
    return {'id': name, 'name': None if anonymous else name, 'type': kind, 'options': identity}


def desired(name='dev_br_lan', identity=None, kind='device', state='present'):
    return {'id': name, 'find': {'name': 'br-lan'} if identity is None else identity, 'type': kind, 'state': state}


class PlannerTests(unittest.TestCase):
    def test_occupied_destination_cannot_mask_legacy_match(self):
        with self.assertRaisesRegex(ValueError, 'different sections'):
            m.plan_package([section('dev_br_lan', {'name':'wrong'}), section('cfg001', {'name':'br-lan'}, anonymous=True)], [desired()])

    def test_wrong_destination_type(self):
        with self.assertRaisesRegex(ValueError, 'another section type'):
            m.plan_package([section('dev_br_lan', {}, 'interface')], [desired()])

    def test_duplicate_identity(self):
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            m.plan_package([section('one', {'name':'br-lan'}),section('two', {'name':'br-lan'})],[desired()])

    def test_cross_type_desired_id_collision(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate desired'):
            m.plan_package([], [desired(), desired(kind='interface')])

    def test_two_desired_entries_claim_same_section(self):
        with self.assertRaisesRegex(ValueError, 'Two desired'):
            m.plan_package([section('old', {'name':'br-lan'})],[desired(),desired('second')])

    def test_empty_singleton_is_type_identity(self):
        self.assertEqual(m.plan_package([section('cfg001', {}, 'system',True)], [desired('main',{},'system')])[0]['to'],'main')

    def test_absent_missing_does_not_create(self):
        self.assertEqual(m.plan_package([], [desired(state='absent')]), [])

    def test_canonical_value_change_is_allowed(self):
        self.assertEqual(m.plan_package([section('dev_br_lan',{'name':'old'})], [desired()]), [])

    def test_named_ids_only(self):
        for value in ['@device[0]', '', 'a.b', 'a;reboot', 'br-lan']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                m.plan_package([], [desired(value)])

    def test_renames_do_not_mutate_options_or_order(self):
        sections=[section('cfg001',{'name':'br-lan','ports':['lan','wan']},anonymous=True),section('cfg002',{'name':'Stock Rule'},'rule',True)]
        before=copy.deepcopy(sections)
        plan=m.plan_package(sections,[desired()])
        self.assertEqual(before,sections)
        self.assertEqual(plan[1]['to'],'retained_rule_stock_rule')

    def test_list_type_and_multiline_quoted_values(self):
        value="package network\nconfig device\n option name 'br-lan'\n list ports 'lan:u*'\n list ports 'wan:t'\n option note 'first\nsecond'\n"
        parsed=m.parse_export(value,'network',[('cfg001','device')])
        self.assertEqual(parsed[0]['options']['ports'],['lan:u*','wan:t'])
        self.assertEqual(parsed[0]['options']['note'],'first\nsecond')


@unittest.skipUnless(os.environ.get('UCI_TEST_BIN'), 'Set UCI_TEST_BIN to run tests against the real OpenWrt CLI')
class RealUCITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        for name in ['config','deltas','overrides','lock','bin','backups']:
            (self.root/name).mkdir()
        binary=shlex.quote(os.environ['UCI_TEST_BIN'])
        wrapper=f'#!/bin/sh\nexec {binary} -c {self.root}/config -C {self.root}/overrides -t {self.root}/deltas "$@"\n'
        (self.root/'bin/uci').write_text(wrapper);(self.root/'bin/uci').chmod(0o700)
        (self.root/'bin/fw4').write_text('#!/bin/sh\nexit 1\n');(self.root/'bin/fw4').chmod(0o700)
        self.env=dict(os.environ,PATH=str(self.root/'bin')+':'+os.environ['PATH'])
        self.commands=[]

    def tearDown(self):
        self.temp.cleanup()

    def read(self,command):
        self.commands.append(command)
        command=command.replace('/etc/config',str(self.root/'config')).replace('/var/lock',str(self.root/'lock')).replace('/tmp/ansible-uci-migration.',str(self.root/'backups/migration.'))
        proc=subprocess.run(['/bin/sh','-c',command],env=self.env,text=True,capture_output=True)
        if proc.returncode:
            raise ValueError('Remote UCI discovery/migration failed; inspect the device privately')
        return proc.stdout

    def run_action(self,packages,check=False,mode='apply'):
        action=object.__new__(m.ActionModule)
        action._task=SimpleNamespace(args={'packages':packages,'mode':mode,'manifest_dir':str(self.root/'manifests')},check_mode=check)
        action._read=self.read
        with patch.object(m.ActionBase,'run',return_value={}):
            return action.run(task_vars={'inventory_hostname':'fixture.test'})

    def network(self):
        (self.root/'config/network').write_text("config device\n option name 'br-lan'\n list ports 'lan:u*'\n list ports 'wan:t'\n option password 'test-only-do-not-log'\nconfig interface 'lan'\n option proto 'dhcp'\nconfig rule\n option name 'Preserve Stock'\n option priority '100'\n")
        return {'network':[{'type':'device','identity':['name'],'entries':[{'id':'dev_br_lan','name':'br-lan'}]}]}

    def test_real_rename_preserves_values_lists_order_and_is_idempotent(self):
        packages=self.network()
        before=m.parse_export(self.read('uci -N export network'),'network',m.show_ids(self.read('uci -X show network'),'network'))
        result=self.run_action(packages)
        self.assertNotIn('failed',result,result)
        self.assertTrue(result['changed'])
        after=m.parse_export(self.read('uci -N export network'),'network',m.show_ids(self.read('uci -X show network'),'network'))
        self.assertEqual([(s['type'],s['options']) for s in before],[(s['type'],s['options']) for s in after])
        self.assertTrue(all(s['name'] for s in after))
        self.assertEqual(self.read('uci changes network'),'')
        self.assertFalse(self.run_action(packages)['changed'])
        manifest=Path(result['manifest_path'])
        self.assertEqual(manifest.stat().st_mode & 0o777,0o600)
        self.assertNotIn('test-only-do-not-log',manifest.read_text())

    def test_check_mode_and_plan_write_no_device_changes(self):
        for check,mode in [(True,'apply'),(False,'plan')]:
            packages=self.network();before=(self.root/'config/network').read_bytes()
            self.commands=[]
            result=self.run_action(packages,check,mode)
            self.assertNotIn('failed',result,result)
            self.assertTrue(result['changed'])
            self.assertEqual(before,(self.root/'config/network').read_bytes())
            self.assertFalse(any('uci rename' in c or 'uci commit' in c for c in self.commands))

    def test_dirty_configuration_fails_without_disclosing_delta(self):
        packages=self.network()
        self.read('uci set network.lan.password=test-only-pending-secret')
        result=self.run_action(packages)
        self.assertTrue(result['failed'])
        self.assertIn('Uncommitted',result['msg'])
        self.assertNotIn('test-only-pending-secret',json.dumps(result))
        self.assertIn('password',self.read('uci changes network'))

    def test_all_packages_checked_before_first_write(self):
        packages=self.network()
        (self.root/'config/firewall').write_text("config zone 'wan'\n option name 'wrong'\nconfig zone\n option name 'wan'\n")
        packages['firewall']=[{'type':'zone','identity':['name'],'entries':[{'id':'wan','name':'wan'}]}]
        before=(self.root/'config/network').read_bytes()
        result=self.run_action(packages)
        self.assertTrue(result['failed'])
        self.assertEqual(before,(self.root/'config/network').read_bytes())
        self.assertFalse(any('uci rename' in c for c in self.commands))

    def test_firewall_validation_failure_restores_packages(self):
        packages=self.network()
        (self.root/'config/firewall').write_text("config zone\n option name 'wan'\n")
        packages['firewall']=[{'type':'zone','identity':['name'],'entries':[{'id':'wan','name':'wan'}]}]
        before={p:(self.root/'config'/p).read_bytes() for p in packages}
        result=self.run_action(packages)
        self.assertTrue(result['failed'])
        for p,data in before.items():
            self.assertEqual(data,(self.root/'config'/p).read_bytes())
            self.assertEqual(self.read('uci changes '+p),'')
        self.assertFalse((self.root/'lock/ansible-uci-migration.lock').exists())

    def test_missing_package_still_checks_desired_id_collisions(self):
        result=self.run_action({'network':[{'type':'device','entries':[{'id':'same'},{'id':'same'}]}]})
        self.assertTrue(result['failed'])

    def test_absent_entry_only_renames_in_migration(self):
        packages=self.network()
        packages['network'][0]['entries'][0]['state']='absent'
        result=self.run_action(packages)
        self.assertNotIn('failed',result,result)
        self.assertEqual(self.read('uci get network.dev_br_lan.name').strip(),'br-lan')


if __name__ == '__main__':
    unittest.main()
