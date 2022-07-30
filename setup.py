#!/usr/bin/env python3

from setuptools import find_packages, setup

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name='python-presence',
    author='Joerg Mechnich',
    author_email='joerg.mechnich@gmail.com',
    license='GNU GPLv3',
    description='minimal implementation of a serverless XMPP client',
    long_description=long_description,
    long_description_content_type="text/markdown",
    url ='https://github.com/jmechnich/python-presence',
    packages=['presence'],
    scripts=['python-presence'],
    use_scm_version={"local_scheme": "no-local-version"},
    setup_requires=['setuptools_scm'],
    install_requires=["pidfile", "psutil", "python-daemon"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: POSIX :: Linux",
    ],
    python_requires='>=3.6',
)
