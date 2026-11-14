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
"""Ensure test fixtures release their process-wide state after cleanup."""

import subprocess
import sys
import unittest

_PROBE = r"""
import importlib
import sys
import threading
from absl import flags
from tcli import accessor_base, command_response, inventory_base, tcli_lib

module_name, class_name = {
    'response': ('tcli.command_response_test', 'UnitTestCmdResponse'),
    'inventory': ('tcli.inventory_base_test', 'InventoryBaseTest'),
    'tcli': ('tcli.tcli_test', 'UnitTestTCLI'),
    'end_to_end': ('tcli.end_to_end_test', 'UnitTestTCLIEndToEnd'),
}[sys.argv[1]]
original = {
    'lock': threading.Lock,
    'event': threading.Event,
    'fetch': inventory_base.Inventory._FetchDevices,
    'send': accessor_base.SendRequests,
    'tqdm': command_response.tqdm,
    'flags': flags.FLAGS,
    'inventory_module': tcli_lib.inventory,
    'accessor_module': tcli_lib.accessor,
}
flag_values = {
    name: flags.FLAGS[name].value
    for name in ('template_dir', 'color', 'config_file', 'display', 'filter')
    if name in flags.FLAGS
}
fixture = getattr(importlib.import_module(module_name), class_name)
fixture.setUpClass()
try:
    case = fixture()
    try:
        case.setUp()
        if getattr(case, 'inv', None) is not None:
            assert case.inv._loaded.wait(2), 'Inventory did not finish loading'
        case.tearDown()
    finally:
        case.doCleanups()
finally:
    try:
        fixture.tearDownClass()
    finally:
        fixture.doClassCleanups()

leaks = []
for name, actual in {
    'lock': threading.Lock,
    'event': threading.Event,
    'fetch': inventory_base.Inventory._FetchDevices,
    'send': accessor_base.SendRequests,
    'tqdm': command_response.tqdm,
    'flags': tcli_lib.FLAGS,
    'inventory_module': tcli_lib.inventory,
    'accessor_module': tcli_lib.accessor,
}.items():
    if actual is not original[name]:
        leaks.append(name)
for name, value in flag_values.items():
    if flags.FLAGS[name].value != value:
        leaks.append('flag value: ' + name)
assert not leaks, 'Fixture leaked process state: ' + ', '.join(leaks)

# An unrelated caller can still use the real synchronization primitives.
event = threading.Event()
worker = threading.Thread(target=event.set)
worker.start()
worker.join(2)
assert not worker.is_alive() and event.is_set()
"""


class FixtureIsolationTest(unittest.TestCase):

  def assertFixtureIsolated(self, name):
    result = subprocess.run(
        [sys.executable, '-c', _PROBE, name],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    self.assertEqual(0, result.returncode, result.stdout + result.stderr)

  def testCommandResponseFixture(self):
    self.assertFixtureIsolated('response')

  def testInventoryFixture(self):
    self.assertFixtureIsolated('inventory')

  def testTcliFixture(self):
    self.assertFixtureIsolated('tcli')

  def testEndToEndFixture(self):
    self.assertFixtureIsolated('end_to_end')


if __name__ == '__main__':
  unittest.main()
