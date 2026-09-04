This is Python version 3.12.3
=============================

.. image:: https://github.com/python/cpython/workflows/Tests/badge.svg
   :alt: CPython build status on GitHub Actions
   :target: https://github.com/python/cpython/actions

.. image:: https://dev.azure.com/python/cpython/_apis/build/status/Azure%20Pipelines%20CI?branchName=main
   :alt: CPython build status on Azure DevOps
   :target: https://dev.azure.com/python/cpython/_build/latest?definitionId=4&branchName=main

.. image:: https://img.shields.io/badge/discourse-join_chat-brightgreen.svg
   :alt: Python Discourse chat
   :target: https://discuss.python.org/


Historical package store prototype
----------------------------------

.. warning::

   This branch is an experimental proof of concept based on CPython 3.12.3.
   It is not an official Python feature or a production package-management
   system.

This branch prototypes deterministic, metadata-driven imports from a permanent
package store. Package releases coexist under paths of the following form::

    ~/.python/packages/<distribution>/<version>/

Projects continue to use normal Python syntax, for example
``import requests``. The interpreter discovers the project's dependency
metadata and selects a compatible distribution release; no version syntax is
added to Python source code.

Motivation
^^^^^^^^^^

A conventional installation places one selected release of a distribution in
an environment. Updating that release can invalidate an older application,
while maintaining a separate environment for every application duplicates
packages and moves dependency selection outside the program's metadata.

This prototype explores an additive alternative: retain historical releases
side-by-side, let each project state what it requires, and select a stored
release without replacing versions needed by other projects. Existing imports
remain unchanged when no project metadata is present.

Selection model
^^^^^^^^^^^^^^^

For each absolute import, the prototype:

1. Finds project metadata by walking upward from the main script until it sees
   ``pylock.toml`` or ``pyproject.toml``. Embedded hosts and ``python -c`` can
   instead set ``PYTHONHISTORICALPROJECT`` to a project directory or directly
   to either metadata file.
2. Uses a compatible ``pylock.toml`` with ``lock-version = "1.0"`` when one is
   present. Otherwise, it reads ``[project].dependencies`` from
   ``pyproject.toml``.
3. Leaves normal import resolution in place when the ordinarily installed
   distribution satisfies the requirement.
4. Otherwise selects the exact requested release, or the highest compatible
   release, from ``~/.python/packages/<distribution>/<version>/``.
5. Loads either ``<import-name>/__init__.py`` or a single-file
   ``<import-name>.py`` while preserving the module's ordinary public name.

Distribution names and import names may differ. For example, metadata can name
``Pillow`` while the application imports ``PIL``. If metadata selects a
dependency but no compatible stored release is available, import fails with a
version-specific ``ModuleNotFoundError`` rather than silently using an
incompatible release.

Minimal example
^^^^^^^^^^^^^^^

Given this project::

    example/
        pyproject.toml
        app.py

with ``pyproject.toml`` containing::

    [project]
    name = "historical-store-example"
    version = "0.1"
    dependencies = ["testpkg==1.0"]

and ``app.py`` containing::

    import testpkg
    print(testpkg.VERSION)

place the package at::

    ~/.python/packages/testpkg/1.0/testpkg/__init__.py

with the following content::

    VERSION = "1.0"

Running ``app.py`` with this interpreter prints ``1.0``. For an embedded host,
select the same metadata explicitly::

    PYTHONHISTORICALPROJECT=/path/to/example ./python -c \
        'import testpkg; print(testpkg.VERSION)'

The interpreter only consumes metadata and imports installed content. Package
installation and store-management commands belong to the companion
experimental pip implementation and are not part of this repository.

Implementation and tests
^^^^^^^^^^^^^^^^^^^^^^^^

The implementation is intentionally isolated in ``Lib/_historical_store.py``
and small import-bootstrap hooks. Its focused regression suite covers exact and
ranged requirements, lock-file precedence, ordinary-distribution precedence,
missing-version errors, differing distribution/import names, single-file
modules, embedded-project discovery, and unchanged legacy imports.

From a CPython build directory, run the focused tests with::

    ./python -m test test_historical_package_store

A real embedded-application integration is available in the
`FreeCAD historical-store branch
<https://github.com/JustTryingToGetSomeWorkDone/FreeCAD/tree/historical-python-store-test>`_.

Prototype boundaries
^^^^^^^^^^^^^^^^^^^^^

This branch does not download packages, resolve or install dependencies,
replace pip, remove ``site-packages``, provide lock-file authoring, or support
simultaneous releases of the same import name in one process. It does not solve
native-extension ABI or shared-library compatibility. The store root and
``PYTHONHISTORICALPROJECT`` name are prototype interfaces and may change.

When PyPA's ``packaging`` library is unavailable, the bootstrap-safe fallback
accepts only final versions made from decimal components and a limited set of
comparison operators. The prototype has not been performance-optimized; in
particular, project metadata is currently rediscovered and parsed during
imports.

This is the end of the prototype explanation.
----------------------------------------------------------------------------


Copyright © 2001-2024 Python Software Foundation.  All rights reserved.

See the end of this file for further copyright and license information.

.. contents::

General Information
-------------------

- Website: https://www.python.org
- Source code: https://github.com/python/cpython
- Issue tracker: https://github.com/python/cpython/issues
- Documentation: https://docs.python.org
- Developer's Guide: https://devguide.python.org/

Contributing to CPython
-----------------------

For more complete instructions on contributing to CPython development,
see the `Developer Guide`_.

.. _Developer Guide: https://devguide.python.org/

Using Python
------------

Installable Python kits, and information about using Python, are available at
`python.org`_.

.. _python.org: https://www.python.org/

Build Instructions
------------------

On Unix, Linux, BSD, macOS, and Cygwin::

    ./configure
    make
    make test
    sudo make install

This will install Python as ``python3``.

You can pass many options to the configure script; run ``./configure --help``
to find out more.  On macOS case-insensitive file systems and on Cygwin,
the executable is called ``python.exe``; elsewhere it's just ``python``.

Building a complete Python installation requires the use of various
additional third-party libraries, depending on your build platform and
configure options.  Not all standard library modules are buildable or
useable on all platforms.  Refer to the
`Install dependencies <https://devguide.python.org/getting-started/setup-building.html#build-dependencies>`_
section of the `Developer Guide`_ for current detailed information on
dependencies for various Linux distributions and macOS.

On macOS, there are additional configure and build options related
to macOS framework and universal builds.  Refer to `Mac/README.rst
<https://github.com/python/cpython/blob/main/Mac/README.rst>`_.

On Windows, see `PCbuild/readme.txt
<https://github.com/python/cpython/blob/main/PCbuild/readme.txt>`_.

If you wish, you can create a subdirectory and invoke configure from there.
For example::

    mkdir debug
    cd debug
    ../configure --with-pydebug
    make
    make test

(This will fail if you *also* built at the top-level directory.  You should do
a ``make clean`` at the top-level first.)

To get an optimized build of Python, ``configure --enable-optimizations``
before you run ``make``.  This sets the default make targets up to enable
Profile Guided Optimization (PGO) and may be used to auto-enable Link Time
Optimization (LTO) on some platforms.  For more details, see the sections
below.

Profile Guided Optimization
^^^^^^^^^^^^^^^^^^^^^^^^^^^

PGO takes advantage of recent versions of the GCC or Clang compilers.  If used,
either via ``configure --enable-optimizations`` or by manually running
``make profile-opt`` regardless of configure flags, the optimized build
process will perform the following steps:

The entire Python directory is cleaned of temporary files that may have
resulted from a previous compilation.

An instrumented version of the interpreter is built, using suitable compiler
flags for each flavor. Note that this is just an intermediary step.  The
binary resulting from this step is not good for real-life workloads as it has
profiling instructions embedded inside.

After the instrumented interpreter is built, the Makefile will run a training
workload.  This is necessary in order to profile the interpreter's execution.
Note also that any output, both stdout and stderr, that may appear at this step
is suppressed.

The final step is to build the actual interpreter, using the information
collected from the instrumented one.  The end result will be a Python binary
that is optimized; suitable for distribution or production installation.


Link Time Optimization
^^^^^^^^^^^^^^^^^^^^^^

Enabled via configure's ``--with-lto`` flag.  LTO takes advantage of the
ability of recent compiler toolchains to optimize across the otherwise
arbitrary ``.o`` file boundary when building final executables or shared
libraries for additional performance gains.


What's New
----------

We have a comprehensive overview of the changes in the `What's New in Python
3.12 <https://docs.python.org/3.12/whatsnew/3.12.html>`_ document.  For a more
detailed change log, read `Misc/NEWS
<https://github.com/python/cpython/tree/main/Misc/NEWS.d>`_, but a full
accounting of changes can only be gleaned from the `commit history
<https://github.com/python/cpython/commits/main>`_.

If you want to install multiple versions of Python, see the section below
entitled "Installing multiple versions".


Documentation
-------------

`Documentation for Python 3.12 <https://docs.python.org/3.12/>`_ is online,
updated daily.

It can also be downloaded in many formats for faster access.  The documentation
is downloadable in HTML, PDF, and reStructuredText formats; the latter version
is primarily for documentation authors, translators, and people with special
formatting requirements.

For information about building Python's documentation, refer to `Doc/README.rst
<https://github.com/python/cpython/blob/main/Doc/README.rst>`_.


Testing
-------

To test the interpreter, type ``make test`` in the top-level directory.  The
test set produces some output.  You can generally ignore the messages about
skipped tests due to optional features which can't be imported.  If a message
is printed about a failed test or a traceback or core dump is produced,
something is wrong.

By default, tests are prevented from overusing resources like disk space and
memory.  To enable these tests, run ``make testall``.

If any tests fail, you can re-run the failing test(s) in verbose mode.  For
example, if ``test_os`` and ``test_gdb`` failed, you can run::

    make test TESTOPTS="-v test_os test_gdb"

If the failure persists and appears to be a problem with Python rather than
your environment, you can `file a bug report
<https://github.com/python/cpython/issues>`_ and include relevant output from
that command to show the issue.

See `Running & Writing Tests <https://devguide.python.org/testing/run-write-tests.html>`_
for more on running tests.

Installing multiple versions
----------------------------

On Unix and Mac systems if you intend to install multiple versions of Python
using the same installation prefix (``--prefix`` argument to the configure
script) you must take care that your primary python executable is not
overwritten by the installation of a different version.  All files and
directories installed using ``make altinstall`` contain the major and minor
version and can thus live side-by-side.  ``make install`` also creates
``${prefix}/bin/python3`` which refers to ``${prefix}/bin/python3.X``.  If you
intend to install multiple versions using the same prefix you must decide which
version (if any) is your "primary" version.  Install that version using ``make
install``.  Install all other versions using ``make altinstall``.

For example, if you want to install Python 2.7, 3.6, and 3.12 with 3.12 being the
primary version, you would execute ``make install`` in your 3.12 build directory
and ``make altinstall`` in the others.


Release Schedule
----------------

See :pep:`693` for Python 3.12 release details.


Copyright and License Information
---------------------------------


Copyright © 2001-2024 Python Software Foundation.  All rights reserved.

Copyright © 2000 BeOpen.com.  All rights reserved.

Copyright © 1995-2001 Corporation for National Research Initiatives.  All
rights reserved.

Copyright © 1991-1995 Stichting Mathematisch Centrum.  All rights reserved.

See the `LICENSE <https://github.com/python/cpython/blob/main/LICENSE>`_ for
information on the history of this software, terms & conditions for usage, and a
DISCLAIMER OF ALL WARRANTIES.

This Python distribution contains *no* GNU General Public License (GPL) code,
so it may be used in proprietary projects.  There are interfaces to some GNU
code but these are entirely optional.

All trademarks referenced herein are property of their respective holders.
