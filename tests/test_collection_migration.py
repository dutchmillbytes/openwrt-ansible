"""Guard the Python-free execution boundary and native UCI return contract."""
from pathlib import Path
import unittest
import yaml

ROOT=Path(__file__).resolve().parents[1]
BUILTIN_CONTROLLER={'ansible.builtin.assert','ansible.builtin.debug','ansible.builtin.fail',
                    'ansible.builtin.include_tasks','ansible.builtin.include_role',
                    'ansible.builtin.import_role','ansible.builtin.set_fact','ansible.builtin.meta'}


def tasks(items):
    for task in items or []:
        yield task
        for key in ('block','rescue','always'):
            yield from tasks(task.get(key,[]))


class CollectionMigrationTests(unittest.TestCase):
    def test_roles_use_explicit_python_free_remote_modules(self):
        for path in (ROOT/'roles').rglob('*.yml'):
            if not {'tasks','handlers'}.intersection(path.parts):continue
            for task in tasks(yaml.safe_load(path.read_text())):
                for key in task:
                    with self.subTest(path=path,task=task.get('name'),key=key):
                        self.assertNotIn(key,{'uci','opkg','ansible.bultin.command'})
                        if key.startswith('ansible.builtin.'):
                            self.assertIn(key,BUILTIN_CONTROLLER)

    def test_role_dependencies_use_the_collection_init(self):
        for path in (ROOT/'roles').glob('*/meta/main.yml'):
            data=yaml.safe_load(path.read_text())
            self.assertIn({'role':'community.openwrt.init'},data.get('dependencies',[]),str(path))

    def test_find_all_guards_use_the_new_list_contract(self):
        for path in (ROOT/'roles').glob('*/tasks/*.yml'):
            text=path.read_text()
            if 'command: "find_all"' in text:
                self.assertIn('named_section_matches.result_list is defined',text,str(path))
                self.assertNotIn('named_section_matches.result |',text,str(path))

    def test_collection_dependency_matches_find_all_support(self):
        data=yaml.safe_load((ROOT/'galaxy.yml').read_text())
        self.assertEqual(data['dependencies']['community.openwrt'],'>=1.7.0,<2.0.0')

    def test_role_migration_preflights_skip_prepared_packages(self):
        role_packages = {
            'system/tasks/main.yml': 'system',
            'network/tasks/main.yml': 'network',
            'wireless/tasks/main.yml': 'wireless',
            'dhcp/tasks/main.yml': 'dhcp',
            'dropbear/tasks/main.yml': 'dropbear',
            'firewall/tasks/main.yml': 'firewall',
            'acme/tasks/main.yml': 'acme',
            'acme/tasks/uhttpd.yml': 'uhttpd',
        }
        for relative, package in role_packages.items():
            task = yaml.safe_load((ROOT/'roles'/relative).read_text())[0]
            with self.subTest(role=relative):
                self.assertEqual(task['ansible.builtin.include_role']['name'], 'uci_migration')
                self.assertIn(f"'{package}' not in", task['when'])
                self.assertIn('uci_migration_prepared_packages', task['when'])

    def test_migration_apply_records_prepared_packages(self):
        tasks_data = yaml.safe_load((ROOT/'roles/uci_migration/tasks/main.yml').read_text())
        record = next(task for task in tasks_data if task.get('name') == 'Record packages prepared during this play')
        self.assertIn('uci_migration_prepared_packages', record['ansible.builtin.set_fact'])
        self.assertIn("uci_migration_mode == 'apply'", record['when'])

if __name__=='__main__':unittest.main()
