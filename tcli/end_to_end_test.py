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

import importlib
import os
import unittest
from unittest import mock

from absl import flags

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


#TODO(harro): Expand tests here to make this an automated UAT.


class UnitTestTCLIEndToEnd(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    super(UnitTestTCLIEndToEnd, cls).setUpClass()
    tcli.FLAGS([__file__,])
    # Stub out as little as possible.
    tcli.command_response.tqdm = mock.MagicMock()

  @classmethod
  def tearDownClass(cls):
    super(UnitTestTCLIEndToEnd, cls).tearDownClass()

  def setUp(self):
    super(UnitTestTCLIEndToEnd, self).setUp()
    tcli.FLAGS.template_dir = os.path.join(
      os.path.dirname(__file__), 'testdata')
    # Read some runtime commands from there.
    tcli.FLAGS.config_file = os.path.join(
      os.path.dirname(__file__), 'testdata', 'rc_file')

  def testSendReceiveCommandInteractive(self):

    # Mock the class method as an inline object is created dynamically.
    with mock.patch.object(tcli.TCLI, '_Print') as mock_print:
      tcli_obj = tcli.TCLI(interactive=True)
      # RC script sets log buffer.
      self.assertEqual('abuffer', tcli_obj.log)
      # Safe mode starts on in interactive mode, toggle it off here.
      self.assertTrue(tcli_obj.safemode)
      tcli_obj.ParseCommands('/S')
      self.assertFalse(tcli_obj.safemode)
      tcli_obj.ParseCommands('/D csv')
      self.assertEqual('csv', tcli_obj.display)
      # Issue some commands interactively.
      tcli_obj.ParseCommands('/T ^device_.*')
      tcli_obj.ParseCommands('/X device_c')
      self.assertListEqual(['device_a', 'device_b'], tcli_obj.device_list)
      tcli_obj.ParseCommands('cat a')
      tcli_obj.ParseCommands('/X ^')
      self.assertListEqual(['device_a', 'device_b', 'device_c'],
                           tcli_obj.device_list)

      mock_print.assert_has_calls([
          mock.call("Invalid escape command 'bogus'.", msgtype='warning'),
          mock.call(HEADER % 'a', 'title'),
          mock.call(OUTPUT_A)])

  def testSendReceiveCommandNonInteractive(self):

    tcli.FLAGS.targets = 'device_a,device_b'
    tcli.FLAGS.xtargets = ''

    with mock.patch.object(tcli.TCLI, '_Print') as mock_print:
      tcli_obj = tcli.TCLI(interactive=False, commands='/display csv\ncat a')

      mock_print.assert_has_calls([
          mock.call(HEADER % 'a', 'title'), mock.call(OUTPUT_A)])

      # RC script ignored. Logging would be on otherwise.
      self.assertEqual(tcli_obj.log, '')

    # Commands as an arg of the TCLI object.
    with mock.patch.object(tcli.TCLI, '_Print') as mock_print:
      tcli_obj = tcli.TCLI(interactive=False,
                           commands='/display csv\ncat a\ncat b')

      mock_print.assert_has_calls([
          mock.call(HEADER % 'a', 'title'), mock.call(OUTPUT_A),
          mock.call(HEADER % 'b', 'title'), mock.call(OUTPUT_B)])

    # With inline TCLI commands.
    with mock.patch.object(tcli.TCLI, '_Print') as mock_print:
      tcli_obj = tcli.TCLI(interactive=False,
                           commands='/display raw\ncat a //D csv')

      mock_print.assert_has_calls([
          mock.call(HEADER % 'a', 'title'),
          mock.call(OUTPUT_A)])


if __name__ == '__main__':
  unittest.main()
