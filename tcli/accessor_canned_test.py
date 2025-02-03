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
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied. See the License for the specific language governing
# permissions and limitations under the License.

"""Tests for tcli.accessor_files."""

import os
import unittest

from unittest import mock

from tcli import accessor_canned as accessor
from tcli import inventory_base as inventory

class UnitTestCannedFileAccessor(unittest.TestCase):
  """Test the CSV inventory class."""

  def testSendRequests(self):
    """Tests command requests are pulled from file."""
    
    class requestObject(inventory.CmdRequest):
      uid = 0
      def __init__(self, target, command):
        self.target = target
        self.command = command
        self.uid += requestObject.uid

    # Invalid target or command results in error.
    target = 'bogus'
    command = 'show version'
    request = requestObject(target, command)
    callback = mock.MagicMock()

    accessor.SendRequests([(request, callback),])
    callback.assert_called_with(
      inventory.Response(
        uid=0, device_name=target, command=command, data='',
        error='Failure to retrieve response from device '
        + f'"{target}", for command "{command}".'
      )
    )

    # Result is pulled from file for valid device and command.
    target = 'device_a'
    request = requestObject(target, command)
    file_result = os.path.join(accessor.DEFAULT_RESPONSE_DIRECTORY, 
                             f'{target}_{command}'.replace(' ', '_'))
    with open(file_result) as fp:
      data = fp.read()
    callback = mock.MagicMock()

    accessor.SendRequests([(request, callback),])
    callback.assert_called_with(
      inventory.Response(
        uid=0, device_name=target, command=command,
        data=data,
        error=''
      )
    )

if __name__ == '__main__':
  unittest.main()