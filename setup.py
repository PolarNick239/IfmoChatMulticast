#
# Copyright (c) 2015, Nikolay Polyarnyi
# All rights reserved.
#

from setuptools import setup, find_packages


setup(name='ifmochat',
      version='0.1',
      packages=find_packages('src'),
      package_dir={'': 'src'},
      install_requires=[
          'netifaces>=0.10.4',
          'PyYAML>=3.11',
          'aiohttp>=0.18.3',
          ],
      scripts=[
          "ifmochat_client.py",
          ])
