#!/usr/bin/env python
try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

setup(name='egulden',
      version='2.6.11',
      description='Python Egulden Tools',
      author='simcity fork of Vitalik Buterin',
      author_email='vbuterin@gmail.com',
      url='https://github.com/Electronic-Gulden-Foundation/pybitcointools',
      packages=['egulden'],
      scripts=['pyefltool'],
      include_package_data=True,
      data_files=[("", ["LICENSE"])],
      )
