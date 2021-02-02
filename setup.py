#!/usr/bin/env python3

from setuptools import find_packages, setup

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name='python-presence',
    author='Joerg Mechnich',
    author_email='joerg.mechnich@gmail.com',
    description='Python library providing a QSystemTrayIcon wrapper',
    long_description=long_description,
    long_description_content_type="text/markdown",
    url ='https://github.com/jmechnich/python-presence',
    packages=['presence'],
    scripts=['examples/presence-minimal'],
    use_scm_version={"local_scheme": "no-local-version"},
    setup_requires=['setuptools_scm'],
    install_requires=["python-daemon"],
    python_requires='>=3.6',
)
