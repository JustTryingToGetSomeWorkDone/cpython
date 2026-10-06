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
        self.store_root = os.path.join(
            self.home,
            '.python',
            f'python{sys.version_info[0]}{sys.version_info[1]}',
            'packages')
        os.makedirs(os.path.dirname(self.main))
        self.write_main('testpkg')

    def write_main(self, import_name):
        with open(self.main, 'w', encoding='utf-8') as file:
            file.write(
                f'import {import_name}\n'
                f'print({import_name}.VERSION)\n')

    def write_project(self, *dependencies):
        dependencies = ', '.join(f'"{item}"' for item in dependencies)
        with open(os.path.join(self.project, 'pyproject.toml'),
                  'w', encoding='utf-8') as file:
            file.write(
                '[project]\n'
                'name = "version-store-test"\n'
                'version = "0.1"\n'
                f'dependencies = [{dependencies}]\n')

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
            self.store_root, distribution, version,
            import_name)
        os.makedirs(package)
        with open(os.path.join(package, '__init__.py'),
                  'w', encoding='utf-8') as file:
            file.write(f'VERSION = {(value or version)!r}\n')

    def write_store_module(self, version, value=None, *,
                           distribution='testpkg', import_name='testpkg'):
        directory = os.path.join(
            self.store_root, distribution, version)
        os.makedirs(directory)
        with open(os.path.join(directory, import_name + '.py'),
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

    def write_ambient_distribution(self, version, value=None):
        ambient = self.write_ambient(value or version)
        metadata = os.path.join(ambient, f'testpkg-{version}.dist-info')
        os.makedirs(metadata)
        with open(os.path.join(metadata, 'METADATA'),
                  'w', encoding='utf-8') as file:
            file.write(
                'Metadata-Version: 2.1\n'
                'Name: testpkg\n'
                f'Version: {version}\n')
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

    def run_embedded(self, *, metadata_file=False, ambient=None,
                     expect_success=True,
                     code='import testpkg; print(testpkg.VERSION)'):
        project = (os.path.join(self.project, 'pyproject.toml')
                   if metadata_file else self.project)
        env = {
            'HOME': self.home,
            'PYTHONHISTORICALPROJECT': project,
            '__isolated': False,
        }
        if sys.platform == 'win32':
            env['USERPROFILE'] = self.home
        if ambient is not None:
            env['PYTHONPATH'] = ambient
        run = (script_helper.assert_python_ok if expect_success else
               script_helper.assert_python_failure)
        return run('-c', code, **env)

    def test_store_root_uses_python_version(self):
        import _historical_store

        with os_helper.EnvironmentVarGuard() as env:
            env['HOME'] = self.home
            expected = os.path.join(
                self.home,
                '.python',
                f'python{sys.version_info[0]}{sys.version_info[1]}',
                'packages')
            self.assertEqual(_historical_store._store_root(), expected)

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

    def test_compatible_ordinary_distribution_precedes_store(self):
        self.write_store('2.4', 'from historical store')
        self.write_project('testpkg>=2.0,<3.0')
        ambient = self.write_ambient_distribution(
            '2.5', 'from ordinary distribution')

        _, stdout, _ = self.run_main(ambient=ambient)

        self.assertEqual(stdout, b'from ordinary distribution\n')

    def test_incompatible_ordinary_distribution_uses_store(self):
        self.write_store('2.4', 'from historical store')
        self.write_project('testpkg>=2.0,<3.0')
        ambient = self.write_ambient_distribution('3.0')

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

    def test_single_file_module(self):
        self.write_main('singlemod')
        self.write_project('single-dist==1.0')
        self.write_store_module(
            '1.0', distribution='single-dist', import_name='singlemod')

        _, stdout, _ = self.run_main()

        self.assertEqual(stdout, b'1.0\n')

    def test_explicit_project_supports_embedded_import(self):
        self.write_project('testpkg==1.0')
        self.write_store('1.0', 'from explicit project')
        ambient = self.write_ambient('from sys.path')

        _, stdout, _ = self.run_embedded(ambient=ambient)

        self.assertEqual(stdout, b'from explicit project\n')

    def test_explicit_metadata_file_supports_embedded_import(self):
        self.write_project('testpkg==1.0')
        self.write_store('1.0')

        _, stdout, _ = self.run_embedded(metadata_file=True)

        self.assertEqual(stdout, b'1.0\n')

    def test_selected_package_keeps_normal_module_identity(self):
        self.write_project('testpkg==1.0')
        self.write_store('1.0')

        _, stdout, _ = self.run_embedded(code=(
            'import sys, testpkg; '
            'print(testpkg.__name__); '
            'print(sys.modules["testpkg"] is testpkg)'))

        self.assertEqual(stdout, b'testpkg\nTrue\n')

    def test_concurrent_imports_resolve_independently(self):
        self.write_project('pkgone==1.0', 'pkgtwo==1.0')
        self.write_store(
            '1.0', distribution='pkgone', import_name='pkgone')
        self.write_store(
            '1.0', distribution='pkgtwo', import_name='pkgtwo')

        _, stdout, _ = self.run_embedded(code='''
import _historical_store
import threading

original_resolve = _historical_store.resolve
barrier = threading.Barrier(2)

def synchronized_resolve(name, *args):
    if name in {'pkgone', 'pkgtwo'}:
        barrier.wait(timeout=5)
    return original_resolve(name, *args)

_historical_store.resolve = synchronized_resolve
errors = []

def load(name):
    try:
        __import__(name)
    except BaseException as error:
        errors.append(error)

threads = [threading.Thread(target=load, args=(name,))
           for name in ('pkgone', 'pkgtwo')]
for thread in threads:
    thread.start()
for thread in threads:
    thread.join()
if errors:
    raise errors[0]

_historical_store.resolve = original_resolve
import pkgone, pkgtwo
print(pkgone.VERSION, pkgtwo.VERSION)
''')

        self.assertEqual(stdout, b'1.0 1.0\n')


if __name__ == '__main__':
    unittest.main()
