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

  # Devices in this testing inventory will have a device name but without any attributes.
  Device = collections.namedtuple('Device', ())

  @classmethod
  def setUpClass(cls):
    super(InventoryBaseTest, cls).setUpClass()
    inventory_base.FLAGS([__file__,])

  def setUp(self):
    super(InventoryBaseTest, self).setUp()
    with mock.patch.object(inventory_base.Inventory, 'LoadDevices'):
      self.inv = inventory_base.Inventory(batch=False)

  def tearDown(self):
    inventory_base.DEVICE_ATTRIBUTES = {}

  def testChangeFilter(self):
    """Tests changing the targets filters."""

    self.inv._GetDevices = mock.Mock(
        return_value={'abc': self.Device(), 'xyz': self.Device()})

    # '^' clears targets.
    self.inv._device_list = ['something']
    self.inv._filters['targets'] = 'something'
    self.assertEqual('', self.inv._ChangeFilter('targets', '^'))
    self.assertIsNone(self.inv._literals_filter['targets'])
    self.assertIsNone(self.inv._compiled_filter['targets'])

    self.assertEqual('abc,^xyz', self.inv._ChangeFilter('targets', 'abc,^xyz'))
    self.assertEqual(['abc'], self.inv._literals_filter['targets'])
    self.assertEqual(['^xyz$'],
                     [x.pattern for x in self.inv._compiled_filter['targets']])

    self.assertEqual('abc,^xyz', self.inv._ChangeFilter('xtargets', 'abc,^xyz'))
    self.assertEqual(['abc'], self.inv._literals_filter['xtargets'])
    self.assertEqual(['^xyz$'],
                     [x.pattern for x in self.inv._compiled_filter['xtargets']])

    # Generate a ValueError.
    self.inv._filters['targets'] = 'something'
    self.assertRaises(
        ValueError,
        self.inv._ChangeFilter, 'targets', 'bogus')
    self.assertEqual('something', self.inv._filters['targets'])

  def testDecomposeFilter(self):
    """Test deriving the compiled/literal filters from the string."""

    (literals, re_match) = self.inv._DecomposeFilter('a,b,^c')
    self.assertEqual(
        (['a', 'b'], ['^c$']),
        (literals, [x.pattern for x in re_match]))
    (literals, re_match) = self.inv._DecomposeFilter('^a.*,b,^c$,d,e')
    self.assertEqual(
        (['b', 'd', 'e'], ['^a.*$', '^c$']),
        (literals, [x.pattern for x in re_match]))

  def testFormatLabelAndValue(self):
    """Tests formatting value display."""

    self.assertEqual('Abc: xyz', self.inv._FormatLabelAndValue('abc', 'xyz', 1))
    self.assertEqual('ABc: xyz', self.inv._FormatLabelAndValue('abc', 'xyz', 2))
    self.assertEqual('ABC: xyz', self.inv._FormatLabelAndValue('abc', 'xyz', 4))

  def testCmdFilterCompleter(self):
    """Tests completer registered to a command."""

    inventory_base.DEVICE_ATTRIBUTES = ['apple', 'pear']
    self.assertEqual(inventory_base.DEVICE_ATTRIBUTES[0],
                     self.inv._CmdFilterCompleter([''], 0))
    self.assertEqual(inventory_base.DEVICE_ATTRIBUTES[1],
                     self.inv._CmdFilterCompleter([''], 1))
    self.assertEqual(
        None, self.inv._CmdFilterCompleter([''], len(inventory_base.DEVICE_ATTRIBUTES)))
    self.assertEqual('pear', self.inv._CmdFilterCompleter(['p'], 0))
    self.assertIsNone(self.inv._CmdFilterCompleter(['p', 'bogus'], 0))

  def testCmdFilter(self):
    """Tests that command handler sets the string value of the filters."""

    self.inv._devices = {
        'abc': self.Device(),
        'xyz': self.Device(),
        'bogus': self.Device()
    }
    # Defaults
    self.assertEqual('Targets: ', self.inv._CmdFilter('targets', []))
    self.assertEqual('XTargets: ', self.inv._CmdFilter('xtargets', []))

    # New values
    self.inv._CmdFilter('targets', ['abc'])
    self.assertEqual('abc', self.inv._filters['targets'])
    self.inv._CmdFilter('targets', ['xyz'], append=True)
    self.assertEqual('abc,xyz', self.inv._filters['targets'])
    # Prepend with an 'x' to update the exclusions.
    self.inv._CmdFilter('xtargets', ['abc'])
    self.assertEqual('abc', self.inv._exclusions['xtargets'])
    self.assertRaises(ValueError, self.inv._CmdFilter, 'bogus', [])

  def testCmdFilter2(self):
    """Tests setting filter via attributes command."""

    self.inv._devices = {
        'abc': self.Device(),
        'xyz': self.Device(),
        'bogus': self.Device()
    }
    # New values
    self.inv._CmdFilter('attributes', ['targets', 'abc'])
    self.assertEqual('abc', self.inv._filters['targets'])
    self.inv._CmdFilter('attributes', ['targets', 'xyz'], append=True)
    self.assertEqual('abc,xyz', self.inv._filters['targets'])
    # Prepend with an 'x' to update the exclusions.
    self.assertEqual('XTargets: ', self.inv._CmdFilter('xtargets', []))
    self.inv._CmdFilter('xattributes', ['targets', 'abc'])
    self.assertEqual('abc', self.inv._exclusions['xtargets'])
    self.assertRaises(ValueError, self.inv._CmdFilter, 'attributes', ['bogus'])

  def testShowEnv(self):
    """Tests basic display of running environment."""

    self.inv._filters = {'targets': ''}
    self.inv._exclusions = {'xtargets': ''}
    self.assertEqual(
        'Inventory:\n'
        '  Max Targets: 50\n'
        '  Filters:\n'
        '    Targets: , XTargets: ',
        self.inv._ShowEnv())

  def testExcluded(self):
    """Tests exclusion logic for filters."""

    dev_attr = collections.namedtuple('dev_attr', ['a', 'b', 'c'])
    self.inv._exclusions = {'xa': 'alpha', 'xb': 'beta', 'xc': 'charlie'}
    with mock.patch.object(self.inv, '_Match', return_value=True) as mock_match:
      self.inv._Excluded('device_a', dev_attr(a='alpha', b='beta', c='charlie'))
      # First match is all that is needed.
      mock_match.assert_called_once_with('xa', 'alpha')

    with mock.patch.object(self.inv,
                           '_Match', return_value=False) as mock_match:
      # Missing non blank attribute 'xb' skipped over.
      dev_attr2 = collections.namedtuple('dev_attr2', ['a'])
      self.assertFalse(self.inv._Excluded(
          'device_a', dev_attr2(a='nomatch')))
      mock_match.assert_has_calls([
          mock.call('xa', 'nomatch'),
      ])

    self.inv._exclusions = {'xtargets': 'abc'}
    with mock.patch.object(self.inv, '_Match') as mock_match:
      self.inv._Excluded('device_a', dev_attr(a='alpha', b='beta', c='charlie'))
      # 'Targets' attribute matched to device name.
      mock_match.assert_called_once_with('xtargets', 'device_a')

  def testIncluded(self):
    """Tests inclusion logic for filters."""

    dev_attr = collections.namedtuple('dev_attr', ['a', 'b', 'c'])
    self.inv._filters = {'a': 'alpha', 'b': 'beta', 'c': ''}
    with mock.patch.object(self.inv, '_Match', return_value=True) as mock_match:
      self.inv._Included('device_a', dev_attr(a='alpha', b='beta', c='charlie'))
      # Compares a Match for each non-blank filter.
      mock_match.assert_has_calls([
          mock.call('a', 'alpha'),
          mock.call('b', 'beta'),
      ])

    # Missing non blank attribute - False.
    dev_attr2 = collections.namedtuple('dev_attr2', ['a'])
    self.assertFalse(self.inv._Included('device_a', dev_attr2(a='alpha')))

    # devicename attribute is checked against the targets.
    self.inv._filters = {'targets': 'abc'}
    with mock.patch.object(self.inv, '_Match') as mock_match:
      self.inv._Included('device_a', dev_attr(a='alpha', b='beta', c='charlie'))
      # 'Targets' attribute matched to device name.
      mock_match.assert_called_once_with('targets', 'device_a')

  def testMatch(self):
    """Test applying the compiled and literal filters to attribute matching."""

    self.inv._literals_filter['fruit'] = ['pear', 'apple']
    self.inv._literals_filter['xfruit'] = None
    self.inv._compiled_filter['shape'] = None
    self.inv._compiled_filter['xshape'] = None
    self.assertTrue(self.inv._Match('fruit', 'apple'))

    self.inv._literals_filter['fruit'] = None
    self.inv._compiled_filter['fruit'] = [re.compile('^apple$')]
    self.assertTrue(self.inv._Match('fruit', 'apple'))

  def testMatch2(self):
    """Tests recursing down a list of attributes."""
    self.inv._literals_filter['fruit'] = ['pear', 'apple']
    self.assertFalse(self.inv._Match('fruit', []))
    self.assertFalse(self.inv._Match('fruit', ['grape', 'orange']))
    self.assertTrue(self.inv._Match('fruit', ['grape', 'apple']))
    self.assertTrue(self.inv._Match('fruit', [['grape'], ['orange', 'apple']]))

  def testBuildDeviceList(self):
    """Tests building a device list from  device dictionary."""

    self.inv._devices = {
        'first': self.Device(),
        'second': self.Device(),
        'third': self.Device()
        }
    self.inv._CmdFilter('targets', ['^f.*,second,^t.ird'])
    self.inv._CmdFilter('xtargets', [''])
    self.inv._device_list = None
    self.assertEqual(set(['first', 'second', 'third']),
                     set(self.inv.device_list))

    self.inv._CmdFilter('targets', ['^f.*'])
    self.inv._device_list = None
    self.assertEqual(['first'], self.inv.device_list)

  def testMaxTargets(self):
    """Tests exceeding the maximum target limit."""

    self.assertEqual('Maxtargets: %s' % inventory_base.DEFAULT_MAXTARGETS,
                     self.inv._CmdMaxTargets('maxtargets', []))
    self.inv._CmdMaxTargets('maxtargets', ['10'])
    self.assertEqual(10, self.inv._maxtargets)

  def testBuildDeviceListWithMaxTargets(self):
    """Tests triggereing maximum target limit."""

    self.inv._maxtargets = 2
    self.inv._devices = {
        'first': self.Device(),
        'second': self.Device(),
        'third': self.Device()}
    self.inv._CmdFilter('targets', ['^f.*,second,^t.ird'])
    self.inv._CmdFilter('xtargets', [''])
    self.inv._device_list = None
    self.assertRaises(ValueError, self.inv._BuildDeviceList)

  def testTargets(self):
    """Tests setting targets value and resultant device lists."""

    # Test targets are four devices - device_a|b|c and 'bogus'.
    self.inv._devices = {
        'device_a': self.Device(), 'device_b': self.Device(),
        'device_c': self.Device(), 'bogus': self.Device()}

    # Initial state, confirm there no targets or excluded targets.
    self.assertEqual('Targets: ', self.inv._CmdFilter('targets', []))
    self.assertEqual('XTargets: ', self.inv._CmdFilter('xtargets', []))

    # A single device as target.
    self.inv._CmdFilter('targets', ['device_c'])
    self.assertEqual(['device_c'], self.inv.device_list)

    # Nonexistant host - rejected. Retains existing targets.
    self.assertRaises(ValueError, self.inv._CmdFilter,
                      'targets', ['nonexistant'])
    self.assertEqual(['device_c'], self.inv.device_list)

    # Two devices as targets. Filer is unordered but device_list is.
    self.inv._CmdFilter('targets', ['device_c,device_a'])
    self.assertEqual(['device_a', 'device_c'], self.inv.device_list)

    # Appending additional target.
    self.inv._CmdFilter('targets', ['device_b'], True)
    self.assertEqual(['device_a', 'device_b', 'device_c'], self.inv.device_list)

    # Clear targets then append two targets to a blank target list.
    self.inv._CmdFilter('targets', ['^'])
    self.inv._CmdFilter('targets', ['device_c,device_a'], True)
    self.assertEqual(['device_a', 'device_c'], self.inv.device_list)

    # Blank targets command leaves existing targets in place.
    self.assertEqual('Targets: device_c,device_a',
                     self.inv._CmdFilter('targets', []))

    # Target list is cleared with '^' argument.
    self.inv._CmdFilter('targets', ['^'])
    self.assertEqual(self.inv.device_list, [])

   # Target list is cleared with '^$' argument.
    self.inv._CmdFilter('targets', ['device_c'])
    self.inv._CmdFilter('targets', ['^$'])
    self.assertEqual(self.inv.device_list, [])

  def testXtargets(self):
    """Tests setting exclusions for the device targets."""

    # Test targets are four devices - device_a|b|c and 'bogus'.
    self.inv._devices = {
        'device_a': self.Device(), 'device_b': self.Device(),
        'device_c': self.Device(), 'bogus': self.Device()}

    # Initial state, confirm there no excluded targets.
    self.assertEqual('XTargets: ',
                     self.inv._CmdFilter('xtargets', []))

    # A single device as target.
    self.inv._CmdFilter('targets', ['device_c'])

    # Single target with disjoint exclusion.
    self.inv._CmdFilter('xtargets', ['device_a'])
    self.assertEqual(['device_c'], self.inv.device_list)

    # Single target with identical exclusion.
    self.inv._CmdFilter('xtargets', ['device_c'])
    self.assertEqual([], self.inv.device_list)

    # Exclusion list is cleared with '^' argument.
    self.inv._CmdFilter('xtargets', ['^'])
    self.assertEqual(['device_c'], self.inv.device_list)

    # Two devices as targets.
    self.inv._CmdFilter('targets', ['device_c,device_a'])

    # Exclude all targets with wildcard matching.
    self.inv._CmdFilter('xtargets', ['^.*'])
    self.assertEqual([], self.inv.device_list)

    # Exclude one target with a partial match.
    self.inv._CmdFilter('xtargets', ['^.*_c'])
    self.assertEqual(['device_a'], self.inv.device_list)

    # Append new exclusion rule to exclude the second target.
    self.inv._CmdFilter('xtargets', ['^.*_a'], True)
    self.assertEqual([], self.inv.device_list)


if __name__ == '__main__':
  unittest.main()
