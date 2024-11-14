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

"""Tests for tcli.inventory_csv."""

import os
import typing
import unittest
from io import StringIO    # pylint: disable=g-importing-member
from unittest import mock

from tcli import inventory_csv as inventory


class UnitTestCSVInventory(unittest.TestCase):
  """Test the CSV inventory class."""

  def _ClearFilters(self, inv_obj):
    """Clear all filters for targets etc."""
    for x in inv_obj._inclusions: inv_obj._inclusions[x] = ''
    for y in inv_obj._exclusions: inv_obj._exclusions[y] = ''

  @classmethod
  def setUpClass(cls):
    super(UnitTestCSVInventory, cls).setUpClass()

  def setUp(self):
    super(UnitTestCSVInventory, self).setUp()
    self.dev_inv_orig = inventory.inventory_base.DEVICE_ATTRIBUTES
    # Trigger FLAGS initialisation before referencing maxtargets flag.
    inventory.FLAGS([__file__,])
    self.inv = inventory.Inventory()
    # Clear all filters for targets etc.
    self._ClearFilters(self.inv)
    
  def tearDown(self):
    inventory.inventory_base.DEVICE_ATTRIBUTES = self.dev_inv_orig

  def testParseDevicesFromCsv(self):
    """Tests parsing valid CSV data from string buffer."""
  
    csv_text = ('# comment at start\n'
                'device, bb, ccc, flags\n'
                '# between header and rows\n'
                '# variable amounts of white space between fields.\n'
                'device_a,B ,  C , f1,f2, f3\n'
                '# comment between rows\n'
                '\n'
                'device_b, , CC, fx, fy, fz')
    result = self.inv._ParseDevicesFromCsv(StringIO(csv_text))
    # Row matches dictionary key
    self.assertEqual(result['device_a'].bb, 'B')    # type: ignore
    # Spaces trim from entries.
    self.assertEqual(result['device_a'].ccc, 'C')   # type: ignore
    # Flags are a list.
    self.assertEqual(result['device_a'].flags, ['f1', 'f2', 'f3'])# type: ignore
    # Last entry is present and null column respected.
    self.assertEqual(result['device_b'].ccc, 'CC')  # type: ignore

  def testParseDevicesFromCsvFail(self):
    """Tests parsing invalid CSV data."""

    # Data without 'device' column."""
    csv_text = ('bogus, bb, ccc, flags\n'
                'device_a, B , C ,flag_1,flag_2,flag_3\n'
                'device_b,,CC,flag_x,flag_yy,flag_zzz')
    # First column of header should be 'device'.
    self.assertRaises(ValueError, self.inv._ParseDevicesFromCsv,
                      StringIO(csv_text))

    # Data without 'flag' column.
    csv_text = ('device,bb,ccc,bogus\n'
                'device_a,B , C ,flag_1,flag_2,flag_3\n'
                'device_b,,CC,flag_x,flag_yy,flag_zzz')
    # Last column of header should be 'flags'.
    self.assertRaises(ValueError, self.inv._ParseDevicesFromCsv,
                      StringIO(csv_text))
    # Data from empty buffer.
    csv_text = ('')
    # Empty buffer
    self.assertRaises(ValueError, self.inv._ParseDevicesFromCsv,
                      StringIO(csv_text))

    # Data from empty table.
    csv_text = ('device,bb,ccc,flags\n')
    # Empty table
    result = self.inv._ParseDevicesFromCsv(StringIO(csv_text))
    self.assertEqual(result, {})

  def testFetchDevices(self):
    """Tests directly loading device inventory from CSV file."""
    self.inv._devices = {}
    self.inv._FetchDevices()
    self.assertTrue(self.inv._devices)

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

    self.inv.SendRequests([(request, callback),])
    callback.assert_called_with(
      inventory.inventory_base.CmdResponse(
        uid=0, device_name=target, command=command, data='',
        error='Failure to retrieve response from device ' +
         f'"{target}", for command "{command}".'
      )
    )

    # Result is pulled from file for valid device and command.
    target = 'device_a'
    request = requestObject(target, command)
    file_result = os.path.join(inventory.DEFAULT_RESPONSE_DIRECTORY, 
                             f'{target}_{command}'.replace(' ', '_'))
    with open(file_result) as fp:
      data = fp.read()
    callback = mock.MagicMock()

    self.inv.SendRequests([(request, callback),])
    callback.assert_called_with(
      inventory.inventory_base.CmdResponse(
        uid=0, device_name=target, command=command,
        data=data,
        error=''
      )
    )

if __name__ == '__main__':
  unittest.main()
