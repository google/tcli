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

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import collections
from io import StringIO    # pylint: disable=g-importing-member
from absl.testing import absltest as unittest
import mock
from tcli import inventory_csv as inventory


class UnitTestCSVInventory(unittest.TestCase):
  """Test the CSV inventory class."""

  @classmethod
  def setUpClass(cls):
    super(UnitTestCSVInventory, cls).setUpClass()
    inventory.FLAGS([__file__,])
    # Stub out thread related byproduct of base class.
    inventory.inventory_base.threading.Thread = mock.MagicMock()
    inventory.inventory_base.threading.Event = mock.MagicMock()
    inventory.inventory_base.threading.Lock = mock.MagicMock()

  @classmethod
  def tearDownClass(cls):
    super(UnitTestCSVInventory, cls).tearDownClass()

  def setUp(self):
    super(UnitTestCSVInventory, self).setUp()
    inventory.FLAGS.realm = 'lab'
    with mock.patch.object(inventory.Inventory, 'LoadDevices'):
      self.inv = inventory.Inventory()
    self.inv._filters['targets'] = ''
    self.inv._exclusions['xtargets'] = ''

  def testParseDevicesFromCsv(self):
    """Tests parsing valid CSV data from string buffer."""
    csv_text = ('device,bb,ccc,flags\n'
                'device_a,B , C ,flag_1,flag_2,flag_3\n'
                'device_b,,CC,flag_x,flag_yy,flag_zzz')
    result = self.inv._ParseDevicesFromCsv(StringIO(csv_text))
    # Row matches dictionary key
    self.assertEqual(result['device_a'].bb, 'B')
    # Last entry is present and null column respected.
    self.assertEqual(result['device_b'].ccc, 'CC')
    # Spaces trim from entries.
    self.assertEqual(result['device_a'].ccc, 'C')
    # Flags are a list.
    self.assertEqual(result['device_a'].flags[1], 'flag_2')

  def testParseDevicesFromCsv2(self):
    """Tests parsing valid CSV data with comments and whitespace."""
    csv_text = ('# comment at start\n'
                'device,bb,ccc,flags\n'
                '# between header and rows\n'
                'device_a,B , C ,flag_1,flag_2,flag_3\n'
                '# comment between rows\n'
                '\n'
                'device_b,,CC,flag_x,flag_yy,flag_zzz')
    result = self.inv._ParseDevicesFromCsv(StringIO(csv_text))
    # Row matches dictionary key
    self.assertEqual(result['device_a'].bb, 'B')
    # Last entry is present and null column respected.
    self.assertEqual(result['device_b'].ccc, 'CC')
    # Spaces trim from entries.
    self.assertEqual(result['device_a'].ccc, 'C')
    # Flags are a list.
    self.assertEqual(result['device_a'].flags[1], 'flag_2')

  def testParseDevicesFromCsv3(self):
    """Tests parsing invalid CSV data without 'device' column."""
    csv_text = ('bogus,bb,ccc,flags\n'
                'device_a,B , C ,flag_1,flag_2,flag_3\n'
                'device_b,,CC,flag_x,flag_yy,flag_zzz')
    # First column of header should be 'device'.
    self.assertRaises(ValueError, self.inv._ParseDevicesFromCsv,
                      StringIO(csv_text))

  def testParseDevicesFromCsv4(self):
    """Tests parsing invalid CSV data without 'flag' column."""
    csv_text = ('device,bb,ccc,bogus\n'
                'device_a,B , C ,flag_1,flag_2,flag_3\n'
                'device_b,,CC,flag_x,flag_yy,flag_zzz')
    # Last column of header should be 'flags'.
    self.assertRaises(ValueError, self.inv._ParseDevicesFromCsv,
                      StringIO(csv_text))

  def testParseDevicesFromCsv5(self):
    """Tests parsing CSV data from empty table."""
    csv_text = ('device,bb,ccc,flags\n')
    # Empty table
    result = self.inv._ParseDevicesFromCsv(StringIO(csv_text))
    self.assertEqual({}, result)

  def testParseDevicesFromCsv6(self):
    """Tests parsing CSV data from empty buffer."""
    csv_text = ('')
    # Empty buffer
    self.assertRaises(ValueError, self.inv._ParseDevicesFromCsv,
                      StringIO(csv_text))

  def testFetchDevices(self):
    """Tests directly loading device inventory from CSV file."""
    self.inv._FetchDevices()
    devices = self.inv.devices.keys()
    self.assertCountEqual(['device_a', 'device_b', 'device_c'], devices)

  def testDeviceList(self):
    """Tests loading inventory from CSV file."""
    inv = inventory.Inventory()
    inv._FetchDevices()
    inv._CmdFilter('targets', ['^.*'])
    self.assertListEqual(['device_a', 'device_b', 'device_c'], inv.device_list)

  def testChangeFilter(self):
    """Tests making changes to filters."""
    # '^' clears vendor.
    self.assertEqual('', self.inv._ChangeFilter('vendor', '^'))

    self.assertEqual('lab,^xyz',
                     self.inv._ChangeFilter('realm', 'lab,^xyz'))
    self.assertEqual('cisco,^xyz',
                     self.inv._ChangeFilter('xvendor', 'cisco,^xyz'))
    self.assertRaises(ValueError, self.inv._ChangeFilter,
                      'xvendor', 'bogus,^xyz')

  def testChangeAttribFilter(self):
    """Tests updating arbitrary filters."""

    dev_attr = collections.namedtuple('dev_attr', ['pop'])
    self.inv._GetDevices = mock.Mock(
        return_value={'abc': dev_attr(pop='abc'),
                      'xyz': dev_attr(pop='xyz')})

    self.assertEqual('', self.inv._ChangeFilter('pop', '^'))
    self.assertEqual('abc,^xyz',
                     self.inv._ChangeFilter('pop', 'abc,^xyz'))

  def testCmdFilter(self):
    """Tests that handler sets the string value of the attribute filters."""
    dev_attr = collections.namedtuple('dev_attr', ['pop'])
    self.inv._devices = {
        'abc': dev_attr(pop='abc'),
        'xyz': dev_attr(pop='xyz'),
        'bogus': dev_attr(pop='')
        }
    # Defaults
    self.assertEqual('Pop: ', self.inv._CmdFilter('pop', []))
    self.assertEqual('XPop: ', self.inv._CmdFilter('xpop', []))

    # New values
    self.inv._CmdFilter('pop', ['abc'])
    self.assertEqual('abc', self.inv._filters['pop'])
    self.inv._CmdFilter('pop', ['xyz'], append=True)
    self.assertEqual('abc,xyz', self.inv._filters['pop'])
    # Prepend with an 'x' to update the exclusions.
    self.inv._CmdFilter('xpop', ['abc'])
    self.assertEqual('abc', self.inv._exclusions['xpop'])

  def testCreateCmdRequest(self):
    """Test building commands requests to send to device connection service."""

    self.inv.Request.UID = 0
    request = self.inv._CreateCmdRequest('abc', 'show vers', 'cli')
    self.assertEqual('abc', request.target)
    self.assertEqual('show vers', request.command)
    self.assertEqual('cli', request.mode)
    self.assertEqual(1, request.uid)
    request = self.inv._CreateCmdRequest('xyz', 'show vers', 'shell')
    self.assertEqual('xyz', request.target)
    self.assertEqual('shell', request.mode)

  def testCmdHandlers(self):
    """Tests the extended handler support of TCLI."""

    # Defaults
    self.assertEqual('Realm: ', self.inv._CmdFilter('realm', [], False))
    self.assertEqual('Vendor: ', self.inv._CmdFilter('vendor', [], False))

    # New values
    # Changing realm or vendor updates the appropriate filter.
    self.inv._CmdFilter('realm', ['lab'], False)
    self.assertEqual('lab', self.inv._filters['realm'])
    self.assertEqual(['lab'], self.inv._literals_filter['realm'])
    self.inv._CmdFilter('vendor', ['juniper'], False)
    self.assertEqual('juniper', self.inv._filters['vendor'])
    self.assertEqual(['juniper'], self.inv._literals_filter['vendor'])
    # prepend with an 'x' to update the exclusions.
    self.inv._CmdFilter('xvendor', ['cisco'], False)
    self.assertEqual('cisco', self.inv._exclusions['xvendor'])
    self.assertEqual(['cisco'], self.inv._literals_filter['xvendor'])

  def testShowEnv(self):
    self.assertEqual(('Inventory:\n'
                      '  Max Targets: 50\n'
                      '  Filters:\n'
                      '    Pop: , XPop: \n'
                      '    Realm: , XRealm: \n'
                      '    Targets: , XTargets: \n'
                      '    Vendor: , XVendor: \n'), self.inv.ShowEnv())

  def testChangeDeviceList(self):
    """Tests changing specific filters."""

    # pylint: disable=invalid-name
    Device = collections.namedtuple(
        'Device', ('pop', 'realm', 'vendor', 'flags'))
    d1 = Device(vendor='juniper', realm='prod', pop='abc01', flags=['active'])
    d2 = Device(vendor='cisco', realm='prod', pop='xyz01', flags=[])
    d3 = Device(vendor='juniper', realm='lab', pop='abc01', flags=[])
    d4 = Device(vendor='juniper', realm='lab', pop='abc02', flags=[])
    self.inv._devices = collections.OrderedDict([
        ('device01', d1), ('device02', d2),
        ('device03', d3), ('device04', d4)])
    self.inv._filters['targets'] = ''
    self.inv._filters['realm'] = ''
    self.inv._filters['vendor'] = ''

    # Realm filter / unfilter.
    self.inv._CmdFilter('targets', ['^device0.'])
    self.inv._CmdFilter('realm', ['prod'])
    self.assertEqual(
        ['device01', 'device02'], self.inv.device_list)
    self.inv._CmdFilter('realm', ['lab'])
    self.assertEqual(['device03', 'device04'], self.inv.device_list)
    # Invalid causes us to retain prior filter (new v2 behavior).
    self.assertRaises(ValueError, self.inv._CmdFilter, 'realm', ['bogus'])
    self.assertEqual(['device03', 'device04'], self.inv.device_list)

    self.inv._filters['realm'] = ''
    # Vendor filter / unfilter.
    self.inv._CmdFilter('vendor', ['cisco'])
    self.assertEqual(['device02'], self.inv.device_list)
    self.inv._CmdFilter('vendor', ['juniper'])
    self.assertEqual(['device01', 'device03', 'device04'],
                     self.inv.device_list)
    self.inv._CmdFilter('vendor', ['cisco,juniper'])
    self.assertEqual(['device01', 'device02', 'device03', 'device04'],
                     self.inv.device_list)

    # Realm and vendor filters.
    self.inv._CmdFilter('realm', ['prod'])
    self.inv._CmdFilter('vendor', ['cisco'])
    self.assertEqual(['device02'], self.inv.device_list)


if __name__ == '__main__':
  unittest.main()
