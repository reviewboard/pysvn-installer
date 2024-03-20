#!/usr/bin/env python
#
# Simplifies installation of PySVN, working through platform and other
# compatibility differences.
#
# By default, this will install a wheel for the latest version of PySVN.

from __future__ import print_function, unicode_literals

import argparse
import atexit
import getpass
import glob
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from subprocess import CalledProcessError

try:
    # Python 3
    from urllib.error import URLError
    from urllib.request import urlopen, urlretrieve
except ImportError:
    # Python 2
    from urllib import urlretrieve
    from urllib2 import URLError, urlopen

try:
    import pip
except ImportError:
    sys.stderr.write('Install pip for Python %s.%s and try again.\n'
                     % sys.version_info[:2])
    sys.exit(1)

try:
    import wheel
except ImportError:
    sys.stderr.write('Install wheel for Python %s.%s and try again.\n'
                     % sys.version_info[:2])
    sys.exit(1)


INDEX_URL = 'https://sourceforge.net/projects/pysvn/rss?path=/pysvn&limit=10'
DOWNLOAD_URL_MASK = (
    'https://sourceforge.net/projects/pysvn/files/pysvn/V%(version)s/'
    'pysvn-%(version)s.tar.gz/download')
VERSION_RE = \
    re.compile(br'<link>.*/files/pysvn/V(?P<version>[0-9\.-]+)/.*</link>')


cwd = None
temp_path = None
_debug_mode = (os.environ.get('DEBUG_PYSVN_INSTALLER') == '1')


def destroy_temp():
    shutil.rmtree(temp_path)


def debug(msg):
    if _debug_mode:
        sys.stderr.write(msg)


def get_pysvn_version():
    try:
        data = urlopen(INDEX_URL).read()
    except URLError as e:
        sys.stderr.write('Unable to fetch PySVN downloads RSS feed: %s\n' % e)
        sys.stderr.write('Tried to load feed from %s\n' % INDEX_URL)
        sys.exit(1)

    m = VERSION_RE.search(data)

    if not m:
        sys.stderr.write('Unable to find latest PySVN version in RSS feed.\n')
        sys.stderr.write('Please report to support@beanbaginc.com.\n')
        sys.exit(1)

    return m.groups('version')[0].decode('utf-8')


def fetch_pysvn(pysvn_version):
    url = DOWNLOAD_URL_MASK % {
        'version': pysvn_version,
    }

    debug('PySVN URL: %s\n' % url)

    tarball_path = os.path.join(temp_path, 'pysvn.tar.gz')

    try:
        urlretrieve(url, filename=tarball_path)
    except URLError as e:
        sys.stderr.write('Unable to fetch PySVN %s: %s\n' % (pysvn_version, e))
        sys.stderr.write('Please report to support@beanbaginc.com.\n')
        sys.exit(1)

    return tarball_path


def extract_pysvn(tarball_path):
    with tarfile.open(tarball_path) as tar:
        def is_within_directory(directory, target):
            
            abs_directory = os.path.abspath(directory)
            abs_target = os.path.abspath(target)
        
            prefix = os.path.commonprefix([abs_directory, abs_target])
            
            return prefix == abs_directory
        
        def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
        
            for member in tar.getmembers():
                member_path = os.path.join(path, member.name)
                if not is_within_directory(path, member_path):
                    raise Exception("Attempted Path Traversal in Tar File")
        
            tar.extractall(path, members, numeric_owner=numeric_owner) 
            
        
        safe_extract(tar, temp_path)

    try:
        return glob.glob(os.path.join(temp_path, 'pysvn-*'))[0]
    except IndexError:
        sys.stderr.write('Unable to find pysvn-* directory in tarball.\n')
        sys.stderr.write('Please report to support@beanbaginc.com.\n')
        sys.exit(1)


def get_brew_prefix(package):
    try:
        path = (
            subprocess.check_output(['brew', '--prefix', package])
            .strip()
            .decode('utf-8')
        )
        debug('%s was found in brew: %s\n' % (package, path))

        return path
    except CalledProcessError:
        debug('%s was not found in brew\n' % package)
        return None


def get_linux_arch():
    """Return the current multiarch architecture for Linux.

    Returns:
        str:
        The architecture, or ``None`` if it can't be determined.
    """
    try:
        return (
            subprocess.check_output(['gcc', '-dumpmachine'])
            .strip()
            .decode('utf-8')
        )
    except CalledProcessError:
        return None


def get_linux_arch_dirs():
    """Return a list of Linux multiarch library directories.

    These will be based off the current architecture. Only paths that exist
    will be returned.

    Returns:
        list of str:
        The list of multiarch directories.
    """
    linux_arch = get_linux_arch()

    if not linux_arch:
        return []

    return [
        path
        for path in [
            '/usr/lib/%s' % linux_arch,
            '/usr/local/lib/%s' % linux_arch,
        ]
        if os.path.exists(path)
    ]


def build_pysvn(src_path, install=True):
    system = platform.system()
    debug('System = %s\n' % system)
    debug('Machine = %s\n' % platform.machine())
    debug('Processor = %s\n' % platform.processor())

    os.chdir(src_path)

    # Locate the PyCXX Import version, so we can force its usage during
    # setup.py.
    import_path = os.path.join(src_path, 'Import')

    try:
        pycxx_dirname = glob.glob(os.path.join(import_path, 'pycxx*'))[0]
    except IndexError:
        sys.stderr.write('PySVN seems to be missing an Import/pycxx* '
                         'directory\n')
        sys.stderr.write('Please report to support@beanbaginc.com.\n')
        sys.exit(1)

    pycxx_path = os.path.join(import_path, pycxx_dirname)

    # We need to patch setup.py to specify the --pycxx-dir parameter.
    setup_py_path = os.path.join(src_path, 'setup.py')

    with open(setup_py_path, 'r') as fp:
        setup_py = fp.read()

    config_token = 'setup.py configure'

    if config_token not in setup_py:
        sys.stderr.write("PySVN's setup.py can no longer be patched.\n")
        sys.stderr.write('Please report to support@beanbaginc.com.\n')
        sys.exit(1)

    config_args = ['--pycxx-dir="%s"' % pycxx_path]

    extra_apr_include_paths = []
    extra_apr_lib_paths = []
    extra_apu_include_paths = []
    extra_svn_bin_paths = []
    extra_svn_include_paths = []
    extra_svn_lib_paths = []

    apr_config_path = None
    apu_config_path = None

    libsvn_client_filename = None
    libapr_filename = None

    if system == 'Darwin':
        debug('Enabling macOS framework support\n')

        libapr_filename = 'libapr-1.dylib'
        libsvn_client_filename = 'libsvn_client-1.a'

        config_args.append('--link-python-framework-via-dynamic-lookup')

        # We want to include a few additional places to look for headers
        # and libraries. We'll start by seeing if Homebrew has some
        # information, and we'll then proceed to including the XCode versions.
        brew_svn_path = get_brew_prefix('subversion')
        brew_apr_path = get_brew_prefix('apr')
        brew_apr_util_path = get_brew_prefix('apr-util')

        if brew_apr_path:
            apr_config_path = os.path.join(brew_apr_path, 'bin',
                                           'apr-1-config')

        if brew_apr_util_path:
            apu_config_path = os.path.join(brew_apr_util_path, 'bin',
                                           'apu-1-config')

        if brew_svn_path and os.path.exists(brew_svn_path):
            # If SVN is installed from brew, we'll want to use those paths.
            extra_svn_bin_paths.append(os.path.join(brew_svn_path, 'bin'))
            extra_svn_include_paths.append(os.path.join(brew_svn_path,
                                                        'include',
                                                        'subversion-1'))
            extra_svn_lib_paths.append(os.path.join(brew_svn_path, 'lib'))

        # XCode bundle both APU directories under the same path.
        xcode_apr_path = (
            '/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk'
            '/usr/include/apr-1')
        extra_apr_include_paths.append(xcode_apr_path)
        extra_apu_include_paths.append(xcode_apr_path)
    elif system == 'Linux':
        libapr_filename = 'libapr-1.so'
        libsvn_client_filename = 'libsvn_client-1.so'

        if getpass.getuser() == 'bitnami':
            debug('Installing for Bitnami\n')

            apr_config_path = '/opt/bitnami/apache/bin/apr-1-config'
            apu_config_path = '/opt/bitnami/apache/bin/apu-1-config'
            extra_svn_bin_paths.append('/opt/bitnami/subversion/bin')
            extra_svn_lib_paths.append('/opt/bitnami/subversion/lib')
            extra_svn_include_paths.append(
                '/opt/bitnami/subversion/include/subversion-1')
        else:
            linux_arch_dirs = get_linux_arch_dirs()
            debug('Linux arch directories: %r\n' % linux_arch_dirs)

            extra_apr_lib_paths += linux_arch_dirs
            extra_svn_lib_paths += linux_arch_dirs

    # Scan for any directories based on the apu-1-config/apr-1-config tools.
    # We'll prefer these paths over any others.
    if apr_config_path and os.path.exists(apr_config_path):
        extra_apr_include_paths.insert(
            0,
            subprocess.check_output([apr_config_path, '--includedir'])
            .decode('utf-8').strip())

        apr_prefix = (
            subprocess.check_output([apr_config_path, '--prefix'])
            .decode('utf-8').strip()
        )

        extra_apr_lib_paths.append(os.path.join(apr_prefix, 'lib'))

    if apu_config_path and os.path.exists(apu_config_path):
        extra_apu_include_paths.insert(
            0,
            subprocess.check_output([apu_config_path, '--includedir'])
            .decode('utf-8').strip())

    debug('Extra APR include paths: %r\n' % (extra_apr_include_paths,))
    debug('Extra APR lib paths: %r\n' % (extra_apr_lib_paths,))
    debug('Extra APU include paths: %r\n' % (extra_apu_include_paths,))
    debug('Extra SVN bin paths: %r\n' % (extra_svn_bin_paths,))
    debug('Extra SVN include paths: %r\n' % (extra_svn_include_paths,))
    debug('Extra SVN lib paths: %r\n' % (extra_svn_lib_paths,))

    for path in extra_apr_include_paths:
        if os.path.exists(os.path.join(path, 'apr.h')):
            config_args.append('--apr-inc-dir="%s"' % path)
            break

    if libapr_filename:
        for path in extra_apr_lib_paths:
            if os.path.exists(os.path.join(path, libapr_filename)):
                config_args.append('--apr-lib-dir="%s"' % path)
                break

    for path in extra_apu_include_paths:
        if os.path.exists(os.path.join(path, 'apu.h')):
            config_args.append('--apu-inc-dir="%s"' % path)
            break

    for path in extra_svn_bin_paths:
        if os.path.exists(os.path.join(path, 'svn')):
            config_args.append('--svn-bin-dir="%s"' % path)
            break

    for path in extra_svn_include_paths:
        if os.path.exists(os.path.join(path, 'svn_client.h')):
            config_args.append('--svn-inc-dir="%s"' % path)
            break

    if libsvn_client_filename:
        for path in extra_svn_lib_paths:
            if os.path.exists(os.path.join(path, libsvn_client_filename)):
                config_args.append('--svn-lib-dir="%s"' % path)
                break

    debug('Using configuration arguments: %r\n' % (config_args,))

    setup_py = setup_py.replace(config_token,
                                '%s %s' % (config_token,
                                           ' '.join(config_args)))

    with open(setup_py_path, 'w') as fp:
        fp.write(setup_py)

    if install:
        cmd_args = ['-m', 'pip', 'install', src_path]
    else:
        cmd_args = ['setup.py', 'bdist_wheel', '--dist-dir', cwd]

    result = subprocess.call([sys.executable] + cmd_args)
    debug('Exit code = %s\n' % result)

    return result


def main():
    global cwd
    global temp_path

    parser = argparse.ArgumentParser()
    parser.add_argument('--pysvn-version',
                        default=os.environ.get('PYSVN_INSTALLER_VERSION'),
                        help='A specific version of PySVN to install.')
    parser.add_argument('--file',
                        default=os.environ.get('PYSVN_INSTALLER_SRC_FILE'),
                        help='A specific PySVN source tarball to install.')
    parser.add_argument('--build-only',
                        action='store_true',
                        default=os.environ.get('PYSVN_INSTALLER_BUILD_ONLY',
                                               False),
                        help="Build a wheel, but don't install it. The "
                             "wheel will be stored in the current directory.")

    args = parser.parse_args()

    cwd = os.getcwd()

    temp_path = tempfile.mkdtemp(suffix='.pysvn-install')
    atexit.register(destroy_temp)

    if args.file:
        tarball_path = args.file

        if not os.path.exists(tarball_path):
            sys.stderr.write('The provided PySVN tarball does not exist.\n')
            sys.exit(1)
    else:
        if args.pysvn_version:
            pysvn_version = args.pysvn_version
        else:
            print('Looking up latest PySVN version...')
            pysvn_version = get_pysvn_version()

            if pysvn_version == '1.9.13':
                pysvn_version = '1.9.12'

            debug('PySVN %s\n' % pysvn_version)

        print('Downloading PySVN %s...' % pysvn_version)
        tarball_path = fetch_pysvn(pysvn_version)

    print('Building PySVN...')
    src_path = extract_pysvn(tarball_path)
    retcode = build_pysvn(src_path, install=not args.build_only)

    if retcode == 0:
        print()

        if args.build_only:
            print('PySVN is built. The wheel is in the current directory.')
        else:
            print('PySVN is installed.')
    else:
        sys.stderr.write('\n')
        sys.stderr.write('PySVN failed to install. You might be missing some '
                         'dependencies.\n')

        system = platform.system()

        if system == 'Darwin':
            sys.stderr.write('On macOS, run:\n')
            sys.stderr.write('\n')
            sys.stderr.write('    $ xcode-select --install\n')
            sys.stderr.write('    $ brew install subversion\n')
            sys.stderr.write('\n')
            sys.stderr.write('Note that you will need to install Homebrew '
                             'from https://brew.sh/\n')
        elif system == 'Linux':
            if sys.version_info[0] == 3:
                pkg_prefix = 'python3'
            else:
                pkg_prefix = 'python'

            sys.stderr.write('On Linux, you will need Python development '
                             'headers and\n')
            sys.stderr.write('Subversion development libraries.\n')
            sys.stderr.write('\n')
            sys.stderr.write('For Ubuntu:\n')
            sys.stderr.write('\n')
            sys.stderr.write('    $ sudo apt-get install %s-dev\n'
                             % pkg_prefix)
            sys.stderr.write('    $ sudo apt-get build-dep %s-svn\n'
                             % pkg_prefix)
            sys.stderr.write('\n')
            sys.stderr.write('For RHEL/CentOS:\n')
            sys.stderr.write('\n')
            sys.stderr.write('    $ sudo yum install %s-devel '
                             'subversion-devel\n'
                             % pkg_prefix)

        sys.exit(1)


if __name__ == '__main__':
    main()
