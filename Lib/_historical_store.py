"""Resolve project dependencies from an experimental historical store.

Project metadata is normally discovered by walking upward from the main
script.  Embedded hosts and ``python -c`` may set ``PYTHONHISTORICALPROJECT``
to an explicit project directory (or a metadata file inside it).  The first
directory containing ``pylock.toml`` or ``pyproject.toml`` is the project root.
A compatible lock file takes priority over ``[project].dependencies``.

This is a deliberately small prototype.  It uses PyPA's ``packaging`` library
when available.  Stock CPython does not include that library, so a fallback
supports final releases made of decimal components and the comparison
operators needed by the prototype.
"""

import os
import re
import sys
import tomllib


try:
    from packaging.markers import Marker as _PackagingMarker
    from packaging.requirements import Requirement as _PackagingRequirement
    from packaging.version import InvalidVersion as _InvalidPackagingVersion
    from packaging.version import Version as _PackagingVersion
except ImportError:
    _PackagingMarker = None
    _PackagingRequirement = None
    _InvalidPackagingVersion = ValueError
    _PackagingVersion = None


_NAME_PATTERN = re.compile(
    r"^\s*([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)"
    r"(?:\[[^]]+\])?\s*(.*?)\s*$")
_SPECIFIER_PATTERN = re.compile(
    r"^(~=|==|!=|<=|>=|<|>)\s*([0-9]+(?:\.[0-9]+)*)$")
_VERSION_PATTERN = re.compile(r"^[0-9]+(?:\.[0-9]+)*$")


def _normalize_name(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def _discover_project(script, explicit_project=None):
    if explicit_project:
        directory = os.path.abspath(os.path.expanduser(explicit_project))
        if os.path.basename(directory) in {'pylock.toml', 'pyproject.toml'}:
            directory = os.path.dirname(directory)
        lock_path = os.path.join(directory, 'pylock.toml')
        project_path = os.path.join(directory, 'pyproject.toml')
        if os.path.isfile(lock_path) or os.path.isfile(project_path):
            return lock_path, project_path
        return None
    if not script or script.startswith('<'):
        return None
    directory = os.path.dirname(os.path.abspath(script))
    while True:
        lock_path = os.path.join(directory, 'pylock.toml')
        project_path = os.path.join(directory, 'pyproject.toml')
        if os.path.isfile(lock_path) or os.path.isfile(project_path):
            return lock_path, project_path
        parent = os.path.dirname(directory)
        if parent == directory:
            return None
        directory = parent


def _read_toml(path):
    try:
        with open(path, 'rb') as file:
            return tomllib.load(file)
    except (OSError, tomllib.TOMLDecodeError):
        return None


def _fallback_specifiers(specifier):
    if not specifier:
        return []
    clauses = []
    for text in specifier.split(','):
        match = _SPECIFIER_PATTERN.fullmatch(text.strip())
        if match is None:
            return None
        clauses.append(match.groups())
    return clauses


def _make_requirement(name, specifier, raw=None):
    if _PackagingRequirement is not None:
        try:
            requirement = _PackagingRequirement(f'{name}{specifier}')
        except ValueError:
            return None
        exact = None
        specs = list(requirement.specifier)
        if (len(specs) == 1 and specs[0].operator == '==' and
                not specs[0].version.endswith('.*')):
            exact = specs[0].version
        return {
            'name': requirement.name,
            'specifier': str(requirement.specifier),
            'parsed': requirement.specifier,
            'exact': exact,
            'raw': raw or f'{requirement.name}{requirement.specifier}',
        }

    clauses = _fallback_specifiers(specifier)
    if clauses is None:
        return None
    exact = None
    if len(clauses) == 1 and clauses[0][0] == '==':
        exact = clauses[0][1]
    return {
        'name': name,
        'specifier': specifier.replace(' ', ''),
        'parsed': clauses,
        'exact': exact,
        'raw': raw or f'{name}{specifier}',
    }


def _parse_dependency(text):
    if not isinstance(text, str):
        return None
    if _PackagingRequirement is not None:
        try:
            requirement = _PackagingRequirement(text)
        except ValueError:
            return None
        if requirement.url is not None:
            return None
        if requirement.marker is not None and not requirement.marker.evaluate():
            return None
        return _make_requirement(
            requirement.name, str(requirement.specifier), raw=text)

    if ';' in text or '@' in text:
        return None
    match = _NAME_PATTERN.fullmatch(text)
    if match is None:
        return None
    name, specifier = match.groups()
    return _make_requirement(name, specifier, raw=text)


def _lock_is_compatible(data):
    if data.get('lock-version') != '1.0':
        return False
    requires_python = data.get('requires-python')
    if requires_python:
        current = '.'.join(str(value) for value in sys.version_info[:3])
        requirement = _make_requirement('python', requires_python)
        if requirement is None or not _matches(current, requirement):
            return False
    environments = data.get('environments')
    if environments:
        if _PackagingMarker is None:
            return False
        try:
            if not any(_PackagingMarker(marker).evaluate()
                       for marker in environments):
                return False
        except (TypeError, ValueError):
            return False
    return True


def _lock_requirements(path):
    data = _read_toml(path)
    if data is None or not _lock_is_compatible(data):
        return None
    requirements = {}
    for package in data.get('packages', ()):
        if not isinstance(package, dict):
            return None
        marker = package.get('marker')
        if marker:
            if _PackagingMarker is None:
                return None
            try:
                if not _PackagingMarker(marker).evaluate():
                    continue
            except (TypeError, ValueError):
                return None
        name = package.get('name')
        version = package.get('version')
        if not isinstance(name, str) or not isinstance(version, str):
            continue
        requirement = _make_requirement(
            name, f'=={version}', raw=f'{name}=={version}')
        if requirement is None:
            return None
        normalized = _normalize_name(name)
        previous = requirements.get(normalized)
        if previous is not None and previous['exact'] != version:
            return None
        requirements[normalized] = requirement
    return requirements


def _project_requirements(path):
    data = _read_toml(path)
    if data is None:
        return {}
    dependencies = data.get('project', {}).get('dependencies', ())
    if not isinstance(dependencies, list):
        return {}
    requirements = {}
    for text in dependencies:
        requirement = _parse_dependency(text)
        if requirement is not None:
            requirements[_normalize_name(requirement['name'])] = requirement
    return requirements


def _requirements_for_project(script, explicit_project=None):
    discovered = _discover_project(script, explicit_project)
    if discovered is None:
        return None
    lock_path, project_path = discovered
    if os.path.isfile(lock_path):
        requirements = _lock_requirements(lock_path)
        if requirements is not None:
            return requirements
    if os.path.isfile(project_path):
        return _project_requirements(project_path)
    return {}


def _release(version):
    if not _VERSION_PATTERN.fullmatch(version):
        raise ValueError(f'unsupported version: {version}')
    return tuple(int(part) for part in version.split('.'))


def _compare(left, right):
    size = max(len(left), len(right))
    left += (0,) * (size - len(left))
    right += (0,) * (size - len(right))
    return (left > right) - (left < right)


def _fallback_matches(version, clauses):
    try:
        candidate = _release(version)
    except ValueError:
        return False
    for operator, required_text in clauses:
        required = _release(required_text)
        comparison = _compare(candidate, required)
        if operator == '==' and comparison != 0:
            return False
        if operator == '!=' and comparison == 0:
            return False
        if operator == '<=' and comparison > 0:
            return False
        if operator == '>=' and comparison < 0:
            return False
        if operator == '<' and comparison >= 0:
            return False
        if operator == '>' and comparison <= 0:
            return False
        if operator == '~=':
            upper = ((required[0] + 1,) if len(required) == 1 else
                     required[:-2] + (required[-2] + 1,))
            if comparison < 0 or _compare(candidate, upper) >= 0:
                return False
    return True


def _matches(version, requirement):
    if _PackagingVersion is not None:
        try:
            parsed = _PackagingVersion(version)
        except _InvalidPackagingVersion:
            return False
        return requirement['parsed'].contains(parsed, prereleases=None)
    return _fallback_matches(version, requirement['parsed'])


def _version_key(version):
    if _PackagingVersion is not None:
        return _PackagingVersion(version)
    return _release(version)


def _store_root():
    return os.path.join(os.path.expanduser('~'), '.python', 'packages')


def _distribution_directory(store, distribution):
    normalized = _normalize_name(distribution)
    try:
        entries = sorted(os.scandir(store), key=lambda entry: entry.name)
    except OSError:
        return None
    for entry in entries:
        if entry.is_dir() and _normalize_name(entry.name) == normalized:
            return entry.path
    return None


def _provides_import(distribution_path, import_name):
    try:
        versions = os.scandir(distribution_path)
    except OSError:
        return False
    with versions:
        return any(
            entry.is_dir() and
            os.path.isfile(os.path.join(
                entry.path, import_name, '__init__.py'))
            for entry in versions)


def _requirement_for_import(import_name, requirements, store):
    normalized_import = import_name.casefold()
    for requirement in requirements.values():
        default_import = _normalize_name(
            requirement['name']).replace('-', '_')
        if default_import == normalized_import:
            return requirement
    for requirement in requirements.values():
        distribution_path = _distribution_directory(
            store, requirement['name'])
        if (distribution_path is not None and
                _provides_import(distribution_path, import_name)):
            return requirement
    try:
        from importlib.metadata import packages_distributions
        providers = packages_distributions().get(import_name, ())
    except (ImportError, OSError):
        providers = ()
    for distribution in providers:
        requirement = requirements.get(_normalize_name(distribution))
        if requirement is not None:
            return requirement
    return None


def _select_version(requirement, import_name, store):
    distribution_path = _distribution_directory(store, requirement['name'])
    if distribution_path is None:
        return None
    versions = []
    try:
        entries = os.scandir(distribution_path)
    except OSError:
        return None
    with entries:
        for entry in entries:
            if (entry.is_dir() and
                    os.path.isfile(os.path.join(
                        entry.path, import_name, '__init__.py')) and
                    _matches(entry.name, requirement)):
                versions.append(entry.name)
    exact = requirement['exact']
    if exact is not None:
        return exact if exact in versions else None
    try:
        return max(versions, key=_version_key)
    except (ValueError, _InvalidPackagingVersion):
        return None


def _ordinary_version(requirement):
    try:
        from importlib.metadata import PackageNotFoundError, version
        installed = version(requirement['name'])
    except (ImportError, OSError, PackageNotFoundError):
        return None
    return installed if _matches(installed, requirement) else None


def _encoded_name(import_name, distribution, version, suffix):
    distribution_hex = distribution.encode('utf-8').hex()
    version_hex = version.encode('utf-8').hex()
    head = f'{import_name}@{distribution_hex}:{version_hex}'
    return f'{head}.{suffix}' if suffix else head


def resolve(name, script=None, explicit_project=None):
    """Return an internal import name selected by project metadata."""
    import_name, separator, suffix = name.partition('.')
    if not import_name.isidentifier():
        return name
    requirements = _requirements_for_project(script, explicit_project)
    if not requirements:
        return name
    store = _store_root()
    requirement = _requirement_for_import(import_name, requirements, store)
    if requirement is None:
        return name
    if _ordinary_version(requirement) is not None:
        return name
    version = _select_version(requirement, import_name, store)
    if version is None:
        specifier = requirement['specifier'] or 'any version'
        raise ModuleNotFoundError(
            f"{requirement['name']} requires {specifier} but no compatible "
            "stored version is available")
    distribution_path = _distribution_directory(store, requirement['name'])
    distribution = os.path.basename(distribution_path)
    return _encoded_name(import_name, distribution, version,
                         suffix if separator else '')
