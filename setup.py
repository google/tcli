#!/usr/bin/python3
#
# Copyright 2019 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Setup script."""

# To use a consistent encoding
from codecs import open  # pylint: disable=redefined-builtin,g-importing-member
from os import path
from setuptools import setup

__version__ = '1.0.0'
here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, 'README.md'), encoding='utf8') as f:
  long_description = f.read()

setup(
    name='tcli',
    maintainer='Google',
    maintainer_email='tcli-dev@googlegroups.com',
    version=__version__,
    description=(
        'CLI for interacting with multiple devices and structuring the output.'
        ),
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/google/tcli',
    license='Apache License, Version 2.0',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Operations',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3'],
    requires=['absl', 'mock', 'textfsm', 'tqdm'],
    packages=['tcli'],
    include_package_data=True,
    setup_requires=['pytest-runner'],
    tests_require=['pytest'],
    )
