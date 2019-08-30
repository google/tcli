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

"""Unittest for textfsm module."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from io import StringIO    # pylint: disable=g-importing-member
from absl import flags
from absl.testing import absltest as unittest
from tcli.tcli_textfsm import textfsm


FLAGS = flags.FLAGS


class UnitTestFSM(unittest.TestCase):
  """Tests the FSM engine."""

  def testKey(self):

    tplt = ('Value Required boo (on.)\n'
            'Value Required,Key hoo (on.)\n\n'
            'Start\n  ^$boo -> Continue\n  ^$hoo -> Record')

    # Explicit default.
    t = textfsm.TextFSM(StringIO(tplt))
    self.assertIn('Key', t._GetValue('hoo').OptionNames())
    self.assertNotIn('Key', t._GetValue('boo').OptionNames())

    tplt = ('Value Required boo (on.)\n'
            'Value Verbose,Key hoo (on.)\n\n'
            'Start\n  ^$boo -> Continue\n  ^$hoo -> Record')
    self.assertRaises(textfsm.textfsm.TextFSMTemplateError, textfsm.TextFSM,
                      StringIO(tplt))

  def testVerbose(self):

    # Suppress second column.
    tplt = ('Value Required boo (on.)\n'
            'Value Filldown,Required,Verbose hoo (on.)\n\n'
            'Start\n  ^$boo -> Continue\n  ^$hoo -> Record')

    t = textfsm.TextFSM(StringIO(tplt), verbose=False)
    data = 'one\non0'
    result = t.ParseText(data)
    self.assertEqual(str(result), ("[['one'], ['on0']]"))
    # The headers displayed is less too.
    self.assertEqual(t.header, ['boo'])

    # Explicit default.
    t = textfsm.TextFSM(StringIO(tplt), verbose=True)
    data = 'one\non0'
    result = t.ParseText(data)
    self.assertEqual(str(result), ("[['one', 'one'], ['on0', 'on0']]"))

    # Required Verbose fields still apply.
    tplt = ('Value Required boo (on.)\n'
            'Value Required,Verbose hoo (tw.)\n\n'
            'Start\n  ^$boo -> Continue\n  ^$hoo -> Record')

    t = textfsm.TextFSM(StringIO(tplt), verbose=False)
    data = 'one\non0'
    result = t.ParseText(data)
    self.assertEqual(result, [])

  def testBlank(self):

    # Value may be matched by 'boo' but are never retained.
    tplt = ('Value Required boo (one)\n'
            'Value Blank hoo (two)\n\n'
            'Start\n  ^$boo $hoo -> Record')

    t = textfsm.TextFSM(StringIO(tplt))
    data = 'one two'
    result = t.ParseText(data)
    self.assertEqual(str(result), ("[['one', '']]"))
    # The headers displayed is for both.
    self.assertEqual(t.header, ['boo', 'hoo'])

    # Blank values can have no other options
    tplt = ('Value Required boo (one)\n'
            'Value Blank,Verbose hoo (two)\n\n'
            'Start\n  ^$boo $hoo -> Record')
    self.assertRaises(textfsm.textfsm.TextFSMTemplateError, textfsm.TextFSM,
                      StringIO(tplt))

  def testError(self):

    tplt = ('Value Required boo (on.)\n'
            'Value Filldown,Required hoo (on.)\n\n'
            'Start\n  ^$boo -> Continue\n  ^$hoo -> Error')

    t = textfsm.TextFSM(StringIO(tplt))
    data = 'one'
    # Exception should look local i.e. not from textfsm_os.
    self.assertRaises(textfsm.TextFSMError, t.ParseText, data)

  def testDump(self):
    tplt = ('Value Required boo (on.)\n'
            'Value Required hoo (of.)\n\n'
            'Start\n  ^${boo}\n  ^${hoo} -> Record')

    data = 'one\noff\n'
    t = textfsm.TextFSM(StringIO(tplt))
    t.ParseText(data)
    self.assertMultiLineEqual('["boo","hoo"]\n["one","off"]', t.Dump())


if __name__ == '__main__':
  unittest.main()
