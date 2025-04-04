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

import unittest
from unittest import mock

from tcli import inventory_base as inventory
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
    self.cmd_response.InitCommandRow(0, 'boohoo')
    self.cmd_response.InitCommandRow(1, 'testing')
    self.assertFalse(self.cmd_response._row_index[0])
    self.assertEqual([], self.cmd_response._row_index[1])
    self.assertEqual([], self.cmd_response._row_response[1])
    self.assertEqual('boohoo', self.cmd_response._pipe[0])
    self.assertEqual('testing', self.cmd_response._pipe[1])

  def testSetRequest(self):
    """Tests SetReq method."""

    self.cmd_response.InitCommandRow(0, 'boohoo')
    self.cmd_response.InitCommandRow(1, 'testing')

    self.cmd_response.SetRequest(1, 1)

    self.assertEqual([], self.cmd_response._row_index[0])
    self.assertEqual(1, self.cmd_response._uid_index[1])
    self.assertEqual([1], self.cmd_response._row_index[1])
    self.assertCountEqual([1], self.cmd_response._results)

    self.cmd_response.SetRequest(1, 2)
    self.assertEqual([1, 2], self.cmd_response._row_index[1])

  def testAddResponse(self):
    """Tests AddResponse method."""

    self.assertFalse(
      self.cmd_response.AddResponse(
        inventory.Response(1, 'device_name', 'command', 'data', 'error')))

    self.cmd_response.InitCommandRow(0, 'boohoo')
    self.cmd_response.InitCommandRow(1, 'testing')

    self.cmd_response.SetRequest(1, 1)
    self.cmd_response.SetRequest(1, 2)

    self.assertFalse(self.cmd_response._response_count)
    self.assertTrue(self.cmd_response.AddResponse(
      inventory.Response(1, 'device_name', 'command', 'data', 'error')))
    self.assertTrue(self.cmd_response._results[1])
    self.assertEqual([1], self.cmd_response._row_response[1])
    self.assertEqual(1, self.cmd_response._response_count)
    self.assertTrue(self.cmd_response.AddResponse(
      inventory.Response(2, 'device_name', 'command', 'data', 'error')))
    self.assertFalse(self.cmd_response.AddResponse(
      inventory.Response(3, 'device_name', 'command', 'data', 'error')))
    self.assertEqual(2, self.cmd_response._response_count)
    self.assertEqual([1, 2],
                     self.cmd_response._row_response[1])
    # pylint: disable=g-generic-assert
    self.assertEqual(2, len(self.cmd_response._row_index))

  def testGetRow(self):
    """Tests GetRow method."""

    # Two rows, two commands for devices.
    self.cmd_response.InitCommandRow(0, 'boohoo')
    self.cmd_response.InitCommandRow(1, 'testing')

    # Two devices, so two responses for each of the two rows.
    # Hence four requet IDs: 1-4.
    self.cmd_response.SetRequest(1, 1)
    self.cmd_response.SetRequest(1, 2)
    # Responses for the first command have the higher IDs ... just because.
    self.cmd_response.SetRequest(0, 3)
    self.cmd_response.SetRequest(0, 4)

    self.assertEqual(self.cmd_response.GetRow(), ([], ''))

    # Responses are added against the request IDs.
    self.cmd_response.AddResponse(
      inventory.Response(1, 'device_name', 'command', 'data', 'error'))
    self.cmd_response.AddResponse(
      inventory.Response(2, 'device_name', 'command', 'data', 'error'))
    self.cmd_response.AddResponse(
      inventory.Response(3, 'device_name', 'command', 'data', 'error'))
    self.cmd_response.AddResponse(
      inventory.Response(4, 'device_name', 'command', 'data', 'error'))

    self.assertFalse(self.cmd_response._current_row)
    self.assertFalse(self.cmd_response.done.is_set())
    # First row is first command request and the response IDs 3 & 4.
    self.assertEqual(self.cmd_response.GetRow(), ([3, 4], 'boohoo'))
    self.assertFalse(self.cmd_response.done.is_set())
    self.assertEqual(self.cmd_response.GetRow(), ([1, 2], 'testing'))
    self.assertFalse(self.cmd_response.done.is_set())
    self.assertEqual(self.cmd_response._current_row, 2)
    self.assertEqual(self.cmd_response.GetRow(), ([], ''))
    self.assertEqual(self.cmd_response._current_row, 2)
    self.assertTrue(self.cmd_response.done.is_set())


if __name__ == '__main__':
  unittest.main()
