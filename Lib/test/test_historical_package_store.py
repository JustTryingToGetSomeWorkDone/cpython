import os
import sys
import unittest

from test.support import os_helper
from test.support import script_helper


class HistoricalPackageStoreTests(unittest.TestCase):
    def setUp(self):
        self.home = self.enterContext(os_helper.temp_dir())
        self.project = self.enterContext(os_helper.temp_dir())
        self.main = os.path.join(self.project, 'src', 'main.py')
        os.makedirs(os.path.dirname(self.main))
        self.write_main('testpkg')

    def write_main(self, import_name):
        with open(self.main, 'w', encoding='utf-8') as file:
            file.write(
                f'import {import_name}\n'
                f'print({import_name}.VERSION)\n')

    def write_project(self, dependency):
        with open(os.path.join(self.project, 'pyproject.toml'),
                  'w', encoding='utf-8') as file:
            file.write(
                '[project]\n'
                'name = "version-store-test"\n'
                'version = "0.1"\n'
                f'dependencies = ["{dependency}"]\n')

    def write_lock(self, version, lock_version='1.0'):
        with open(os.path.join(self.project, 'pylock.toml'),
                  'w', encoding='utf-8') as file:
            file.write(
                f'lock-version = "{lock_version}"\n'
                '[[packages]]\n'
                'name = "testpkg"\n'
                f'version = "{version}"\n')

    def write_store(self, version, value=None, *, distribution='testpkg',
                    import_name='testpkg'):
        package = os.path.join(
            self.home, '.python', 'packages', distribution, version,
            import_name)
        os.makedirs(package)
        with open(os.path.join(package, '__init__.py'),
                  'w', encoding='utf-8') as file:
            file.write(f'VERSION = {(value or version)!r}\n')

    def write_ambient(self, value):
        ambient = self.enterContext(os_helper.temp_dir())
        package = os.path.join(ambient, 'testpkg')
        os.makedirs(package)
        with open(os.path.join(package, '__init__.py'),
                  'w', encoding='utf-8') as file:
            file.write(f'VERSION = {value!r}\n')
        return ambient

    def run_main(self, *, ambient=None, expect_success=True):
        env = {'HOME': self.home, '__isolated': False}
        if sys.platform == 'win32':
            env['USERPROFILE'] = self.home
        if ambient is not None:
            env['PYTHONPATH'] = ambient
        run = (script_helper.assert_python_ok if expect_success else
               script_helper.assert_python_failure)
        return run(self.main, **env)

    def test_changing_exact_project_requirement_changes_version(self):
        self.write_store('1.0')
        self.write_store('2.0')

        self.write_project('testpkg==1.0')
        _, stdout, _ = self.run_main()
        self.assertEqual(stdout, b'1.0\n')

        self.write_project('testpkg==2.0')
        _, stdout, _ = self.run_main()
        self.assertEqual(stdout, b'2.0\n')

    def test_range_selects_highest_compatible_version(self):
        for version in ('1.0', '1.5', '2.0', '3.0'):
            self.write_store(version)
        self.write_project('testpkg>=1.0,<3.0')

        _, stdout, _ = self.run_main()

        self.assertEqual(stdout, b'2.0\n')

    def test_lock_takes_priority_over_project_dependencies(self):
        self.write_store('1.0')
        self.write_store('2.0')
        self.write_project('testpkg==1.0')
        self.write_lock('2.0')

        _, stdout, _ = self.run_main()

        self.assertEqual(stdout, b'2.0\n')

    def test_incompatible_lock_falls_back_to_project_dependencies(self):
        self.write_store('1.0')
        self.write_store('2.0')
        self.write_project('testpkg==1.0')
        self.write_lock('2.0', lock_version='2.0')

        _, stdout, _ = self.run_main()

        self.assertEqual(stdout, b'1.0\n')

    def test_metadata_selection_overrides_ambient_package(self):
        self.write_store('1.0', 'from historical store')
        self.write_project('testpkg==1.0')
        ambient = self.write_ambient('from sys.path')

        _, stdout, _ = self.run_main(ambient=ambient)

        self.assertEqual(stdout, b'from historical store\n')

    def test_no_metadata_preserves_legacy_import(self):
        ambient = self.write_ambient('legacy import')

        _, stdout, _ = self.run_main(ambient=ambient)

        self.assertEqual(stdout, b'legacy import\n')

    def test_missing_compatible_version_has_specific_error(self):
        self.write_store('1.0')
        self.write_project('testpkg>=2.0,<3.0')

        _, _, stderr = self.run_main(expect_success=False)

        self.assertIn(
            b'testpkg requires >=2.0,<3.0 but no compatible stored version '
            b'is available', stderr)

    def test_distribution_to_import_name_mapping(self):
        self.write_main('PIL')
        self.write_project('Pillow==10.0')
        self.write_store(
            '10.0', distribution='Pillow', import_name='PIL')

        _, stdout, _ = self.run_main()

        self.assertEqual(stdout, b'10.0\n')


if __name__ == '__main__':
    unittest.main()
