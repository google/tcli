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

"""Tests for tcli.inventory_base."""

import collections
import re
import unittest
from unittest import mock

from tcli import inventory_base


class InventoryBaseTest(unittest.TestCase):

  def _ClearFilters(self, inv_obj):
    """Clear all filters for targets etc."""
    for x in inv_obj._inclusions: inv_obj._inclusions[x] = ''
    for y in inv_obj._exclusions: inv_obj._exclusions[y] = ''

  @classmethod
  def setUpClass(cls):
    super(InventoryBaseTest, cls).setUpClass()
    inventory_base.FLAGS([__file__,])
    def _FetchDevicesStub(self):
      # Fake inventory data, same columns as the CSV file.
      _d = collections.namedtuple('Device', ('pop', 'realm', 'vendor', 'flags'))
      self._devices = {
        'device01': _d(vendor='juniper', realm='prod', pop='abc01', flags=['f1']),
        'device02': _d(vendor='cisco', realm='prod', pop='xyz01', flags=['f1', 'f2']),
        'device03': _d(vendor='juniper', realm='lab', pop='abc01', flags=[]), 
        'device04': _d(vendor='juniper', realm='lab', pop='abc02', 
                      flags=['f1', 'f2'])}
      return
    inventory_base.Inventory._FetchDevices = _FetchDevicesStub

  @classmethod
  def tearDownClass(cls):
    super(InventoryBaseTest, cls).tearDownClass()

  def setUp(self):
    super(InventoryBaseTest, self).setUp()
    self.dev_inv_orig = inventory_base.DEVICE_ATTRIBUTES
    self.inv = inventory_base.Inventory()
    self._ClearFilters(self.inv)

  def tearDown(self):
    inventory_base.DEVICE_ATTRIBUTES = self.dev_inv_orig

  ############################################################################
  # Thread safe public methods and properties.                               #
  ############################################################################
  
  def testCmdRequestPresentation(self):
    """Test building commands requests to send to device connection service."""

    inventory_base.CmdRequest.UID = 0
    request = inventory_base.CmdRequest('device01', 'show vers', 'cli')
    self.assertEqual('device01', request.target)
    self.assertEqual('show vers', request.command)
    self.assertEqual('cli', request.mode)
    self.assertEqual(1, request.uid)
    request = inventory_base.CmdRequest('device02', 'show vers', 'shell')
    self.assertEqual('device02', request.target)
    self.assertEqual('shell', request.mode)

  def testGetDevices(self):
    """Test building dict of Device objects."""

    self.assertListEqual(
      list(self.inv.devices.keys()), 
      ['device01', 'device02', 'device03', 'device04'])

  def testGetDeviceList(self):
    """Tests returning a list of Device names."""

    # Default filter matches no devices.
    self.assertListEqual(self.inv.device_list, [])

  def testReformatCmdResponse(self):
    # Tested in child module.
    pass

  def testRegisterCommands(self):
    # Tested in the main module.
    pass

  def testShowEnv(self):
    self.assertEqual(self.inv.ShowEnv(),
                     ('Inventory:\n'
                      '  Max Targets: 50\n'
                      '  Filters:\n'
                      '    Pop: , XPop: \n'
                      '    Realm: , XRealm: \n'
                      '    Targets: , XTargets: \n'
                      '    Vendor: , XVendor: \n'))
  
  ############################################################################
  # Methods related to registering/executing TCLI CLI command extensions.    #
  ############################################################################
  
  def testCmdFilterCompleter(self):
    """Test command completion list for valid attribute completions."""

    # Completer matches against the global device attributes.
    self.inv._attributes = {'apple': {},
                             'pear': {}}
    # A blank word will match all entries, state 0 and state 1.
    self.assertEqual(self.inv._CmdFilterCompleter([''], 0), 'apple')
    self.assertEqual(self.inv._CmdFilterCompleter([''], 1), 'pear')
    # An empty word list gives a 'None' result.
    self.assertEqual(
      self.inv._CmdFilterCompleter([''], len(self.inv._attributes)),
      None)
    # Valid single match.
    self.assertEqual(self.inv._CmdFilterCompleter(['p'], 0), 'pear')
    self.assertEqual(self.inv._CmdFilterCompleter(['pe'], 0), 'pear')
    # A non-match.
    self.assertIsNone(self.inv._CmdFilterCompleter(['ph'], 0))
    # Two words, so also a non-match.
    self.assertIsNone(self.inv._CmdFilterCompleter(['p', 'bogus'], 0))

  def testMaxTargets(self):
    """Tests displaying and updating the maximum target limit."""

    command = 'maxtargets'
    # Display
    self.assertEqual(self.inv._CmdMaxTargets(command, []),
                     f'Maxtargets: {inventory_base.DEFAULT_MAXTARGETS}')
    # Update
    self.inv._CmdMaxTargets(command, ['10'])
    self.assertEqual(self.inv._maxtargets, 10)
    self.assertRaises(ValueError, self.inv._CmdMaxTargets, command, ['-10'])
    # Error

  def testBuildDeviceListWithMaxTargets(self):
    """Tests triggereing maximum target limit."""

    self.inv._CmdFilter('targets', ['^device.*'])
    # Limit not triggered by changing the value.
    self.inv._maxtargets = 2
    # Limit triggered next time we update a filter.
    self.assertRaises(ValueError, self.inv._CmdFilter, 'targets', ['^device.*'])

  def testCmdHandlers(self):
    """Tests the extended handler."""

    # Defaults
    self.assertEqual(self.inv._CmdFilter('realm', [], False), 'Realm: ')
    self.assertEqual(self.inv._CmdFilter('vendor', [], False), 'Vendor: ')

    # New values
    # Changing realm or vendor updates the appropriate filter.
    self.inv._CmdFilter('realm', ['lab'], False)
    self.assertEqual(self.inv._inclusions['realm'], 'lab')
    self.assertEqual(self.inv._filters['realm'].filters[0], ['lab'])

    self.inv._CmdFilter('vendor', ['juniper'], False)
    self.assertEqual(self.inv._inclusions['vendor'], 'juniper')
    self.assertEqual(self.inv._filters['vendor'].filters[0], ['juniper'])

    # prepend with an 'x' to update the exclusions.
    self.inv._CmdFilter('xvendor', ['cisco'], False)
    self.assertEqual(self.inv._exclusions['xvendor'], 'cisco')
    self.assertEqual(self.inv._filters['xvendor'].filters[0], ['cisco'])

  def testChangeDeviceList(self):
    """Tests changing specific filters."""

    # Realm filter / unfilter.
    self.inv._CmdFilter('targets', ['^device0.'])
    self.inv._CmdFilter('realm', ['prod'])
    self.assertEqual(self.inv.device_list, ['device01', 'device02'])

    self.inv._CmdFilter('realm', ['lab'])
    self.assertEqual(self.inv.device_list, ['device03', 'device04'])

    # Invalid causes us to retain prior filter (new v2 behavior).
    self.assertRaises(ValueError, self.inv._CmdFilter, 'bogus', ['bogus'])
    self.assertEqual(self.inv.device_list, ['device03', 'device04'])

    self.inv._inclusions['realm'] = ''
    # Vendor filter / unfilter.
    self.inv._CmdFilter('vendor', ['cisco'])
    self.assertEqual(self.inv.device_list, ['device02'])

    self.inv._CmdFilter('vendor', ['juniper'])
    self.assertEqual(self.inv.device_list, ['device01', 'device03', 'device04'])

    self.inv._CmdFilter('vendor', ['cisco,juniper'])
    self.assertEqual(self.inv.device_list,
                     ['device01', 'device02', 'device03', 'device04'])

    # Realm and vendor filters.
    self.inv._CmdFilter('realm', ['prod'])
    self.inv._CmdFilter('vendor', ['cisco'])
    self.assertEqual(self.inv.device_list, ['device02'])

  def testChangeDeviceListMatches(self):
    """Tests matching logic of various filter combinations."""

    # Realm filter / unfilter.
    self.inv._CmdFilter('targets', ['^device0.'])
    self.inv._CmdFilter('realm', ['prod'])
    self.assertListEqual(self.inv.device_list, ['device01', 'device02'])

    self.inv._CmdFilter('realm', ['^$'])
    self.assertListEqual(self.inv.device_list, 
                     ['device01', 'device02', 'device03', 'device04'])
    
    # Remove one device with xtargets.
    self.inv._CmdFilter('xtargets', ['device02'])
    self.assertListEqual(self.inv.device_list, 
                         ['device01', 'device03', 'device04'])

    # Remove another device with additoinal xtargets.
    # Add some whitespace, which should be ignored.
    self.inv._CmdFilter('xtargets', ['  device02  ,  device03  '])
    self.assertListEqual(self.inv.device_list, ['device01', 'device04'])

    # Remove two with regular matching and 
    # two more (overlapping) via a regexp.
    self.inv._CmdFilter('xtargets', ['device02, device03, ^.*0[34]$'])
    self.assertListEqual(self.inv.device_list, ['device01'])
    
    # Set the realm to "lab" - there are no matches.
    self.inv._CmdFilter('realm', ['lab'])
    self.assertListEqual(self.inv.device_list, [])

    # Resetting target filter value, no matches.
    self.inv._CmdFilter('targets', ['^$'])
    self.assertListEqual(self.inv.device_list, [])

    self._ClearFilters(self.inv)
    self.inv._CmdFilter('targets', ['^.*'])
    self.inv._CmdFilter('realm', ['^prod|lab'])
    self.assertListEqual(self.inv.device_list, 
                         ['device01', 'device02', 'device03', 'device04'])
    
    # Use the attributes indirect command rather than the 'targets' et al.
    self._ClearFilters(self.inv)
    self.inv._AttributeFilter('attributes', ['targets', 'device01'])
    self.assertListEqual(self.inv.device_list, ['device01'])

    # Match based on "pop" attribute.
    self.inv._AttributeFilter('attributes', ['targets', '^.*$'])
    self.inv._AttributeFilter('attributes', ['pop', 'abc01'])
    self.assertListEqual(self.inv.device_list, ['device01', 'device03'])
    # Remove both these devices based on vendor.
    self.inv._AttributeFilter('xattributes', ['vendor', 'juniper'])
    self.assertListEqual(self.inv.device_list, [])

  def testFormatLabelAndValue(self):
    """Tests formatting attribute: value'' displayed."""

    self.assertEqual(self.inv._FormatLabelAndValue('abc', 'xyz', 1), 'Abc: xyz')
    self.assertEqual(self.inv._FormatLabelAndValue('abc', 'xyz', 2), 'ABc: xyz')
    self.assertEqual(self.inv._FormatLabelAndValue('abc', 'xyz', 4), 'ABC: xyz')

class AttributeFilterTest(unittest.TestCase):
  def testDecomposeFilter(self):
    """Test deriving the compiled/literal filters from the string."""

    (literals, re_match) = inventory_base.FilterMatch('a,b,^c').filters
    # Filtering is split into literals and regexp entries
    self.assertEqual((literals, [x.pattern for x in re_match]),
                     (['a', 'b'], ['^c$']))
    (literals, re_match) = inventory_base.FilterMatch(
      '^a.*,b,^c$,d,e').filters
    self.assertEqual((literals, [x.pattern for x in re_match]),
                     (['b', 'd', 'e'], ['^a.*$', '^c$']))
    (literals, re_match) = inventory_base.FilterMatch(
      '^a.*,b,  ^c$, d , "e"').filters
    self.assertEqual((literals, [x.pattern for x in re_match]),
                     (['b', 'd', '"e"'], ['^a.*$', '^c$']))
    (literals, re_match) = inventory_base.FilterMatch(
      '^A.*,B,  ^C$, D , "E"').filters
    # Ignorecase, literals are changed to lowercase. Regexp are unchanged.
    self.assertEqual((literals, [x.pattern for x in re_match]),
                     (['b', 'd', '"e"'], ['^A.*$', '^C$']))
    # Bogus regular expressions raise an error.
    self.assertRaises(ValueError, inventory_base.FilterMatch, '^A.**')
    self.assertRaises(ValueError, inventory_base.FilterMatch, '^[A')

  def testMatch(self):
    """Tests matching logic against filter substrings."""

    _filter = inventory_base.FilterMatch('hello, World, ^b.*')
    self.assertTrue(_filter.Match('hello'))
    self.assertTrue(_filter.Match('world'))   # Cononical form is lowercase.
    self.assertFalse(_filter.Match('World'))  # Match on only lowercase.
    self.assertTrue(_filter.Match('beehive'))
    self.assertTrue(_filter.Match('Beehive')) # Regexp case insensitive

    # Flip the ignorecase logic.
    _filter = inventory_base.FilterMatch('hello, World, ^b.*', False)
    self.assertTrue(_filter.Match('hello'))
    self.assertFalse(_filter.Match('world'))  # No cononical form, match as is.
    self.assertTrue(_filter.Match('World'))
    self.assertTrue(_filter.Match('beehive'))
    self.assertFalse(_filter.Match('Beehive'))  # Case matters.

    _filter = inventory_base.FilterMatch('f1, ^d.*')
    self.assertTrue(_filter.Match(['f1', 'f2', 'f3']))
    self.assertFalse(_filter.Match(['a', 'b', 'c']))
    self.assertTrue(_filter.Match(['d1', 'd2', 'd3']))

if __name__ == '__main__':
  unittest.main()