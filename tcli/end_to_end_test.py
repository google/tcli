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

"""End to end system test of TCLI, includes dependency on libraries."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import importlib
import os
from absl import flags
from absl.testing import absltest as unittest
import mock
from tcli import tcli_lib as tcli


tcli.inventory = importlib.import_module('tcli.inventory_csv')
FLAGS = flags.FLAGS

# Test outputs.
HEADER = '#!# cat %s #!#'
OUTPUT_A = ('Host, ColAa, ColAb\n'
            'device_a, hello, world\n'
            'device_b, HELLO, WORLD\n')
OUTPUT_B = ('Host, ColBa, ColBb\n'
            'device_a, foo, bar\n'
            'device_b, FOO, BAR\n')


class UnitTestTCLIEndToEnd(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    super(UnitTestTCLIEndToEnd, cls).setUpClass()
    tcli.FLAGS([__file__,])
    # Stub out as little as possible.
    tcli.command_response.tqdm = mock.MagicMock()
    tcli.TCLI._PrintWarning = mock.Mock()
    tcli.TCLI._PrintSystem = mock.Mock()

  @classmethod
  def tearDownClass(cls):
    super(UnitTestTCLIEndToEnd, cls).tearDownClass()

  def setUp(self):
    super(UnitTestTCLIEndToEnd, self).setUp()
    tcli.FLAGS.color = False
    tcli.FLAGS.interactive = False
    tcli.FLAGS.display = 'csv'
    tcli.FLAGS.sorted = True
    tcli.FLAGS.cmds = None
    tcli.FLAGS.template_dir = os.path.join(
        os.path.dirname(__file__), 'testdata')
    # Read some runtime commands from there.
    tcli.FLAGS.config_file = os.path.join(
        os.path.dirname(__file__), 'testdata', 'rc_file')

  def testSendReceiveCommand(self):

    # Mock the class method as an inline object is created dynamically.
    with mock.patch.object(tcli.TCLI, '_PrintOutput') as mock_tcli_out:
      gcl_obj = tcli.TCLI()
      gcl_obj.StartUp(None, False)

      # RC script sets log buffer.
      self.assertEqual('abuffer', gcl_obj.log)

      # Safe mode starts on in interactive mode, toggle it off here.
      gcl_obj.ParseCommands('/S')
      # Revert the format to 'raw' and test setting it to 'csv' inline.
      gcl_obj.ParseCommands('/D raw')
      # Issue some commands interactively.
      gcl_obj.ParseCommands('/T device_a,device_b')
      gcl_obj.ParseCommands('/X ^')
      gcl_obj.ParseCommands('cat a //D csv\ncat b //D csv')

      mock_tcli_out.assert_has_calls([
          mock.call(HEADER % 'a', title=True),
          mock.call(OUTPUT_A),
          mock.call(HEADER % 'b', title=True),
          mock.call(OUTPUT_B)])

    self.assertEqual('raw', gcl_obj.display)

  def testSendReceiveCommandBatch(self):

    tcli.FLAGS.targets = 'device_a,device_b'
    tcli.FLAGS.xtargets = ''
    # Mock the class as commands are executed before the object is returned.
    with mock.patch.object(tcli.TCLI, '_PrintOutput') as mock_tcli_out:
      gcl_obj = tcli.TCLI()
      gcl_obj.StartUp('cat a\ncat b', False)

      mock_tcli_out.assert_has_calls([
          mock.call(HEADER % 'a', title=True),
          mock.call(OUTPUT_A),
          mock.call(HEADER % 'b', title=True),
          mock.call(OUTPUT_B)])

    # RC script ignored.
    self.assertEqual(None, gcl_obj.log)


if __name__ == '__main__':
  unittest.main()
