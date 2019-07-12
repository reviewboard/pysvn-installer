===============
PySVN Installer
===============

PySVN_ is a tricky package to install, and is often problematic for most
users. This installer simplifies this, making it easy to get PySVN up and
running on most systems and within a Python virtual environment.

*Please note that we do not maintain PySVN. We only maintain this installer.*


.. _PySVN: https://pysvn.sourceforge.io/


Installation - The Short Version
================================

PySVN requires Python development headers and Subversion development libraries.
You can get these from your package packager, or through XCode on macOS. This
is covered in more detail below.

To install::

    $ curl https://pysvn.reviewboard.org | python

This will pull down our `installer
<https://raw.githubusercontent.com/reviewboard/pysvn-installer/master/install.py>`_
and build/install a Python Wheel for the latest version of PySVN.

If you need to install for a different version of Python, use the appropriate
``pythonX.Y`` binary.


Installation - The Longer Version
=================================

Getting the Development Packages
--------------------------------

This will vary based on your system.

For Ubuntu Linux (or other Debian-based systems)::

    $ sudo apt-get install python-dev
    $ sudo apt-get build-dep python-svn


On RHEL/CentOS::

    $ sudo yum install python-devel subversion-devel


On macOS::

    $ xcode-select --install


(If these instructions are incomplete for your system, let us know.)


Installation Options
--------------------

You can use this script to install a specific version of PySVN, to install
from a downloaded PySVN source tarball, or to build a Python Wheel without
installing.

You will need to `download the installer
<https://raw.githubusercontent.com/reviewboard/pysvn-installer/master/install.py>`_
and run it directly to use these arguments.

Here are your options:

``--pysvn-version=<X.Y.Z>``:
    The specific version of PySVN to download and install. Note that this is
    dependent on the version being hosted by the PySVN maintainers,

``--file=<path>``:
    The path to a downloaded PySVN source tarball to install. Useful if you're
    installing on multiple versions of Python and don't want to re-download
    each time.

``--build-only``:
    If specified, this will build a Python Wheel in the current directory,
    but won't install it. Note that Wheels for PySVN are fairly tied to the
    platform and environment they were built on.
