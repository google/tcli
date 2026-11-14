# Copyright 2026 Google Inc. All Rights Reserved.
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
"""Regressions for inventories containing only the mandatory device column."""

from io import StringIO
import unittest

from tcli import inventory_csv


class MinimalInventoryTest(unittest.TestCase):

  def parse(self, text):
    # Parsing is independent of asynchronous inventory loading and CLI flags.
    inventory = object.__new__(inventory_csv.Inventory)
    return inventory._ParseDevicesFromCsv(StringIO(text))

  def testDeviceColumnOnly(self):
    devices = self.parse('device\nrouter_a\nrouter_b\n')
    self.assertEqual(['router_a', 'router_b'], list(devices))
    self.assertEqual((), devices['router_a']._fields)
    self.assertEqual((), tuple(devices['router_b']))

  def testDeviceColumnWithWhitespaceAndComments(self):
    devices = self.parse('# inventory\n device \n\n router_a \n# ignored\n')
    self.assertEqual(['router_a'], list(devices))

  def testHeaderWithoutRows(self):
    self.assertEqual({}, self.parse('device\n'))

  def testAttributeColumnStillParsed(self):
    devices = self.parse('device,vendor\nrouter_a,cisco\n')
    self.assertEqual('cisco', devices['router_a'].vendor)

  def testOptionalFlagsColumnStillCollectsValues(self):
    devices = self.parse('device,flags\nrouter_a,one,two\n')
    self.assertEqual(['one', 'two'], devices['router_a'].flags)


if __name__ == '__main__':
  unittest.main()
