# UCI migration

Controller-side preflight and rename-only migration for Python-free OpenWrt.
When using roles from a checkout, add `plugins/action` to `action_plugins` in
Ansible configuration. Reconciliation uses `community.openwrt.uci`; the migration
action uses the connection directly and does not need the init role or a target
Python interpreter. Other configuration roles initialize `community.openwrt.init`
as a dependency before their remote module calls.

`uci_migration_selected_packages` selects owned packages from
`uci_migration_catalog`. Each group declares a UCI type, desired entries and
optional identity keys. An entry's `find` mapping overrides those keys; an empty
mapping identifies a singleton by type. Stable-ID-only entries omit identity.
The catalogue can be overridden to name additional retained sections explicitly.

`uci_migration_mode: plan` is read-only remotely. The default `apply` honors
Ansible check mode. `uci_migration_manifest_dir` defaults to the transient
controller path `/tmp/ansible-uci-migration-manifests` and receives private JSON
diagnostics containing only names/types/rename reasons. A plan reports `changed`
when renames would be needed. Missing desired sections are left to configuration
roles. Even `absent` entries are only renamed here; normal reconciliation deletes
them.

A successful apply records selected packages in the host fact
`uci_migration_prepared_packages`. Configuration roles skip their local
preflight when a fleet-wide preflight already prepared that package. Standalone
role use still performs its own preflight. Plan mode does not record packages,
because a later non-check-mode reconciliation would still require pending
renames to be applied.

All selected packages are validated before the first write. Dirty UCI state,
ambiguous identities, occupied destinations and duplicate desired IDs fail closed.
An existing canonical ID with no conflicting legacy match may change mutable
values during reconciliation. Unlisted anonymous sections are retained and named,
using their descriptive name or persistent cfg ID, never an index selector.

Rename apply backs up each affected package to a private `/tmp` directory, holds
a migration lock, validates firewall syntax, commits packages separately and
restores the original files on failure. It changes no option values or list types,
reorders no sections, and reloads no services. External/manual UCI writers must
remain idle during a run. A failed normal configuration run may leave staged
changes; back up and resolve those explicitly before retrying.

Runtime assumptions: BusyBox-compatible shell, UCI CLI with `-N` and `-X`, and
`fw4 check` for firewall migration. Package reads and errors may contain secrets;
the role suppresses invocation output and exposes sanitized failure messages only.
