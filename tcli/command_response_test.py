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

"""Tests for tcli.command_response."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from absl.testing import absltest as unittest
import mock
from tcli import command_response


class FakeLock(object):
  """Fake lock with locking conflict indicator."""

  locked = False
  conflict = False
  was_locked = False

  def acquire(self):                        # pylint: disable=g-bad-name
    if self.locked:
      self.conflict = True
    else:
      self.locked = True
      self.was_locked = True

  def release(self):                        # pylint: disable=g-bad-name
    self.locked = False


class FakeEvent(object):
  """Fake async event handler."""

  # Disable a few lint warning for out stubbed class.
  # We don't have the luxury of choosing the method names.
  # pylint: disable=unused-argument
  def wait(self, timeout):  # pylint: disable=g-bad-name
    return

  def set(self):  # pylint: disable=g-bad-name
    pass

  def isSet(self):  # pylint: disable=g-bad-name
    return True

  def clear(self):  # pylint: disable=g-bad-name
    pass


class FakeCmdResponse(command_response.CmdResponse):
  """Fake CmdResponse object."""

  lock = FakeLock()
  done = FakeEvent()

  def __init__(self, uid=''):
    super(FakeCmdResponse, self).__init__()
    if uid:
      self.uid = uid


class UnitTestCmdResponse(unittest.TestCase):
  """Tests the CmdResponse class."""

  def setUp(self):
    super(UnitTestCmdResponse, self).setUp()
    command_response.threading.Lock = mock.MagicMock()
    self.cmd_response = command_response.CmdResponse()
    # Set class variables to defaults.
    self.cmd_response.__init__()

  def testSetCommandRow(self):
    """Tests SetCommandRow method."""

    self.cmd_response._row_index[0] = ['content']
    self.cmd_response.SetCommandRow(0, 'boohoo')
    self.cmd_response.SetCommandRow(1, 'testing')
    self.assertFalse(self.cmd_response._row_index[0])
    self.assertEqual([], self.cmd_response._row_index[1])
    self.assertEqual([], self.cmd_response._row_response[1])
    self.assertEqual('boohoo', self.cmd_response._pipe[0])
    self.assertEqual('testing', self.cmd_response._pipe[1])

  def testSetRequest(self):
    """Tests SetReq method."""

    self.cmd_response.SetCommandRow(0, 'boohoo')
    self.cmd_response.SetCommandRow(1, 'testing')

    self.cmd_response.SetRequest(1, 'first_uid')

    self.assertEqual([], self.cmd_response._row_index[0])
    self.assertEqual(1, self.cmd_response._uid_index['first_uid'])
    self.assertEqual(['first_uid'], self.cmd_response._row_index[1])
    self.assertCountEqual(['first_uid'], self.cmd_response._results)

    self.cmd_response.SetRequest(1, 'second_uid')
    self.assertEqual(['first_uid', 'second_uid'],
                     self.cmd_response._row_index[1])

  def testAddResponse(self):
    """Tests AddResponse method."""

    class FakeResponse(object):

      def __init__(self, uid):
        self.uid = uid or None

    self.assertFalse(self.cmd_response.AddResponse(FakeResponse('first_uid')))

    self.cmd_response.SetCommandRow(0, 'boohoo')
    self.cmd_response.SetCommandRow(1, 'testing')

    self.cmd_response.SetRequest(1, 'first_uid')
    self.cmd_response.SetRequest(1, 'second_uid')

    self.assertFalse(self.cmd_response._response_count)
    self.assertTrue(self.cmd_response.AddResponse(FakeResponse('first_uid')))
    self.assertTrue(self.cmd_response._results['first_uid'])
    self.assertEqual(['first_uid'], self.cmd_response._row_response[1])
    self.assertEqual(1, self.cmd_response._response_count)
    self.assertTrue(self.cmd_response.AddResponse(FakeResponse('second_uid')))
    self.assertFalse(self.cmd_response.AddResponse(FakeResponse('bogus_uid')))
    self.assertEqual(2, self.cmd_response._response_count)
    self.assertEqual(['first_uid', 'second_uid'],
                     self.cmd_response._row_response[1])
    # pylint: disable=g-generic-assert
    self.assertEqual(2, len(self.cmd_response._row_index))

  def testGetRow(self):
    """Tests GetRow method."""

    self.cmd_response.SetCommandRow(0, 'boohoo')
    self.cmd_response.SetCommandRow(1, 'testing')

    self.cmd_response.SetRequest(1, 'first_uid')
    self.cmd_response.SetRequest(1, 'second_uid')
    self.cmd_response.SetRequest(0, 'third_uid')
    self.cmd_response.SetRequest(0, 'forth_uid')

    self.assertFalse(self.cmd_response.GetRow())

    self.cmd_response.AddResponse(FakeCmdResponse('first_uid'))
    self.cmd_response.AddResponse(FakeCmdResponse('second_uid'))
    self.cmd_response.AddResponse(FakeCmdResponse('third_uid'))
    self.cmd_response.AddResponse(FakeCmdResponse('forth_uid'))

    self.assertFalse(self.cmd_response._current_row)
    self.assertFalse(self.cmd_response.done.isSet())
    self.assertEqual((['third_uid', 'forth_uid'], 'boohoo'),
                     self.cmd_response.GetRow())
    self.assertFalse(self.cmd_response.done.isSet())
    self.assertEqual((['first_uid', 'second_uid'], 'testing'),
                     self.cmd_response.GetRow())
    self.assertFalse(self.cmd_response.done.isSet())
    self.assertEqual(2, self.cmd_response._current_row)
    self.assertFalse(self.cmd_response.GetRow())
    self.assertEqual(2, self.cmd_response._current_row)
    self.assertTrue(self.cmd_response.done.isSet())


if __name__ == '__main__':
  unittest.main()
