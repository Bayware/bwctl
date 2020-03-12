"""
bwctl packaging setup script
"""
import os

from setuptools import setup


def read(filename):
    """Read file's content"""
    try:
        with open(os.path.join(os.path.dirname(__file__), filename)) as f:
            return f.read()
    except IOError as err:
        print("I/O error while reading {0!r} ({1!s}): {2!s}".format(filename, err.errno, err.strerror))
        return "0.0.1"


requires = [
    'boto3==1.9.180',
    'Click==7.0',
    'click-repl==0.1.6',
    'jinja2==2.10.1',
    'pid==2.2.5',
    'psutil==5.6.6',
    'pyyaml==5.1',
    'requests==2.21.0',
    'sh==1.12.14'
]

setup(
    name='bwctl',
    version=read('bwctl/version.txt').strip(),
    author='Bayware',
    author_email='bwctl@bayware.io',
    description='Bayware Command Line Toolkit',
    long_description=read('README.md'),
    license="Apache License 2.0",
    url='https://www.bayware.io',
    platforms='Posix;',
    install_requires=requires,
    packages=['bwctl', 'bwctl.actions', 'bwctl.commands', 'bwctl.session', 'bwctl.utils', 'bwctl.templates'],
    package_data={'bwctl': ['version_family.txt', 'version.txt'], 'bwctl.templates': ['*', '*/*']},
    entry_points='''
        [console_scripts]
        bwctl=bwctl.bwctl:main
    '''
)
