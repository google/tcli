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

"""Unittest for tcli script."""

import collections
import copy
import os
import unittest
from unittest import mock

from absl import flags

from tcli import command_register
from tcli import inventory_base as inventory
from tcli import tcli_lib as tcli
from tcli.tcli_textfsm import clitable


APPEND = tcli.command_parser.APPEND
FLAGS = flags.FLAGS


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

  def __exit__(self, *args, **kwargs):
    pass

  def __enter__(self, *args, **kwargs):
    pass


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


class UnitTestTCLI(unittest.TestCase):
  """Tests the TCLI class."""

  @classmethod
  def setUpClass(cls):
    cls.flags_orig = copy.deepcopy(tcli.FLAGS)
    tcli.command_response.threading.Event = mock.MagicMock()
    tcli.command_response.threading.Lock = mock.MagicMock()
    tcli.command_response.tqdm = mock.MagicMock()
    tcli.FLAGS.template_dir = os.path.join(
      os.path.dirname(__file__), 'testdata')
    return super().setUpClass()

  @classmethod
  def tearDownClass(cls):
    tcli.FLAGS = cls.flags_orig
    return super().tearDownClass()

  def setUp(self):
    # Instantiate FLAGS global var.
    tcli.FLAGS([__file__,])
    # Turn off looking for .tclirc
    tcli.FLAGS.color = False
    tcli.FLAGS.config_file = 'none'
    tcli.FLAGS.display = 'raw'
    tcli.FLAGS.filter = None

    self.orig_terminal_size = tcli.terminal.TerminalSize
    tcli.terminal.TerminalSize = lambda: (10, 20)
    self.orig_dev_attr = tcli.inventory.DEVICE_ATTRIBUTES
    tcli.inventory.DEVICE_ATTRIBUTES = {}

    with mock.patch.object(tcli.inventory, 'Inventory'):
      self.tcli_obj = tcli.TCLI(interactive=False)
    # pylance: ignore
    self.tcli_obj.inventory.device_list = ['a', 'b', 'c']                       # type: ignore
    dev_attr = collections.namedtuple('dev_attr', [])
    self.tcli_obj.inventory.devices = {                                         # type: ignore
      'a': dev_attr(), 'b': dev_attr(), 'c': dev_attr()}   
    self.tcli_obj.inventory.targets = ''                                        # type: ignore
    # type: ignore
    self.tcli_obj._Print = mock.Mock()

    command_register.RegisterCommands(self.tcli_obj, self.tcli_obj.cli_parser)
    self.tcli_obj.cli_parser.RegisterCommand(
        'somecommand', 'somecommand help', append=True, regexp=True,
        handler=lambda command, args, append: (command, args, append))

    self.tcli_obj.verbose = True
    self.tcli_obj.linewrap = True
    self.tcli_obj.timeout = 1
    return super().setUp()

  def tearDown(self):
    tcli.terminal.TerminalSize = self.orig_terminal_size
    tcli.inventory.DEVICE_ATTRIBUTES = self.orig_dev_attr
    return super().tearDown()

  def testInlineOnly(self):
    """Tests that only inline supported commands are ruin when inline."""
    #TODO(harro): Add tests here.
    pass

  def testCopy(self):
    # TODO(harro): Tests for extended commands?
    self.tcli_obj.buffers.Append('label', 'content')
    self.tcli_obj.record = ''
    inline_tcli = copy.copy(self.tcli_obj)
    inline_tcli.cli_parser.InlineOnly()
    self.assertEqual('content', self.tcli_obj.buffers.GetBuffer('label'))
    self.assertFalse(self.tcli_obj.record)
    # Change parent.
    self.tcli_obj.buffers.Append('label', 'more')
    self.tcli_obj.record = 'label'
    # Change copy.
    inline_tcli.record = 'anotherlabel'

    # Test the parent.
    self.assertEqual('content\nmore', self.tcli_obj.buffers.GetBuffer('label'))
    self.assertEqual('label', self.tcli_obj.record)
    # Test the child.
    self.assertEqual('content\nmore',
                     inline_tcli.buffers.GetBuffer('label'))
    self.assertEqual('anotherlabel', inline_tcli.record)

  def testSetDefaults(self):
    """Tests setup of default commands from Flags."""

    # Change some values around
    self.tcli_obj.color = not tcli.FLAGS.color
    self.tcli_obj.timeout = 30

    command_register.SetFlagDefaults(self.tcli_obj.cli_parser)
    self.assertEqual(tcli.FLAGS.color, self.tcli_obj.color)
    self.assertEqual(tcli.FLAGS.timeout, self.tcli_obj.timeout)

  def testCallback(self):
    """Tests async callback."""

    self.tcli_obj._FormatRow = mock.Mock()

    # self.tcli_obj.Callback(
    #   inventory.Response(99, "device_name", "command", "data", "error"))
    # # Test that nonexistant uid trigger early return.
    # self.assertFalse(self.tcli_obj.cmd_response._response_count)

    self.tcli_obj.cmd_response.InitCommandRow(0, '')
    self.tcli_obj.cmd_response.InitCommandRow(1, '')

    self.tcli_obj.cmd_response.SetRequest(0, 1)
    self.tcli_obj.cmd_response.SetRequest(0, 2)
    self.tcli_obj.cmd_response.SetRequest(1, 3)
    self.tcli_obj.cmd_response.SetRequest(1, 4)
    self.tcli_obj.cmd_response._row_response[0] = []

    self.tcli_obj.inventory.device_list = set(['device_a', 'device_b'])         # type: ignore
    self.tcli_obj.command_list = ['cat alpha', 'cat beta']                      # type: ignore

    # Call with valid uid and check response count increments.
    self.tcli_obj._Callback(
      inventory.Response(1, 'device_a', 'cat alpha', 'data', 'error'))

    self.assertTrue(self.tcli_obj.cmd_response._response_count)
    self.assertEqual(self.tcli_obj.cmd_response._row_response[0], [1])
    # Should still point at first (0) row.
    self.assertFalse(self.tcli_obj.cmd_response._current_row)

    # Second call for last argument of first row.
    self.tcli_obj._Callback(
      inventory.Response(2, 'device_b', 'cat alpha', 'data', 'error'))

    self.assertEqual(self.tcli_obj.cmd_response._row_response[0], [1, 2])
    self.assertFalse(self.tcli_obj.cmd_response._row_response[1])
    # Should point at next row (1).
    self.assertEqual(self.tcli_obj.cmd_response._current_row, 1)

    self.tcli_obj.cmd_response._current_row = 0
    self.tcli_obj.cmd_response._response_count = 0
    self.tcli_obj.cmd_response._row_response[0] = []

    # Test populating the second row before the first.
    self.tcli_obj._Callback(
      inventory.Response(4, 'device_b', 'cat beta', 'data', 'error'))
    self.tcli_obj._Callback(
      inventory.Response(3, 'device_a', 'cat beta', 'data', 'error'))

    self.assertFalse(self.tcli_obj.cmd_response._row_response[0])
    self.assertEqual(self.tcli_obj.cmd_response._row_response[1], [4, 3])

    # Once first row gets fully pop'd then both should be reported and cleared.
    self.tcli_obj._Callback(
      inventory.Response(1, 'device_a', 'cat alpha', 'data', 'error'))
    self.tcli_obj._Callback(
      inventory.Response(2, 'device_b', 'cat alpha', 'data', 'error'))

    self.assertEqual(self.tcli_obj.cmd_response._row_response[0], [1, 2])
    self.assertEqual(self.tcli_obj.cmd_response._row_response[1], [4, 3])
    # Should point at next row (2).
    self.assertEqual(self.tcli_obj.cmd_response._current_row, 2)

  def testDisplayRaw(self):
    """Test display of raw output."""

    with mock.patch.object(self.tcli_obj, '_Print') as mock_print:
      self.tcli_obj._DisplayRaw(
          inventory.Response(
              device_name='device1', command='time of day',
              data='a random\nmulti line\nstring.', error='', uid=''))
      mock_print.assert_has_calls([
          mock.call('#!# device1:time of day #!#', 'title'),
          mock.call('a random\nmulti line\nstring.')
      ])

    self.tcli_obj.cmd_response._results[1] = inventory.Response(
        uid=1, device_name='device_1', data='hello world\n',
        command='c alpha', error='')
    self.tcli_obj.cmd_response._results[2] = inventory.Response(
        uid=2, device_name='device_2', data='quick fox\n',
        command='c alpha', error='')

    self.tcli_obj.display = 'raw'
    self.tcli_obj.inventory._devices = {                                        # type: ignore
        'device_1': {'Vendor', 'Asterix'},
        'device_2': {'Vendor', 'Asterix'},
    }

    # Raw headers.
    header = '#!# %s:%s #!#' % ('device_1', 'c alpha')

    with mock.patch.object(self.tcli_obj, '_Print') as mock_print:
      # Single entry, raw output.
      self.tcli_obj._FormatRow([1])
      mock_print.assert_has_calls([
          mock.call(header, 'title'),
          mock.call('hello world\n')
      ])

    header2 = '#!# %s:%s #!#' % ('device_2', 'c alpha')
    # Multiple ActionRequest objects, differing content.
    with mock.patch.object(self.tcli_obj, '_Print') as mock_print:
      self.tcli_obj._FormatRow([1, 2])
      mock_print.assert_has_calls([
          mock.call(header, 'title'),
          mock.call('hello world\n'),
          mock.call(header2, 'title'),
          mock.call('quick fox\n')
      ])

    # Multiple action request objects, same content.
    with mock.patch.object(self.tcli_obj, '_Print') as mock_print:
      self.tcli_obj._FormatRow([1, 1])
      mock_print.assert_has_calls([
          mock.call(header, 'title'),
          mock.call('hello world\n'),
          mock.call(header, 'title'),
          mock.call('hello world\n')
      ])

  def _CannedResponse(self):      # pylint: disable=invalid-name
    """Setup some canned commands and responses."""

    self.tcli_obj.inventory.attributes = {                                      # type: ignore
        'vendor': tcli.inventory.inventory_base.Attribute(                      # type: ignore
            'vendor', '', None, '', display_case='title')}
    # Initialise the textfsm engine in TCLI.
    self.tcli_obj.filter = 'default_index'
    self.tcli_obj.filter_engine = clitable.CliTable(self.tcli_obj.filter,
                                                    tcli.FLAGS.template_dir)
    self.tcli_obj.display = 'raw'
    dev_attr = collections.namedtuple('dev_attr', ['vendor'])
    self.tcli_obj.inventory.devices = {                                         # type: ignore
        'device_1': dev_attr(vendor='asterix'),
        'device_2': dev_attr(vendor='asterix'),
        'device_3': dev_attr(vendor='asterix'),
        'device_4': dev_attr(vendor='obelix')
    }

    self.tcli_obj.cmd_response._results[1] = inventory.Response(
        uid='1', device_name='device_1', error='',
        command='c alpha', data='hello world\n')
    self.tcli_obj.cmd_response._results[2] = inventory.Response(
        uid='2', device_name='device_2', error='',
        command='c alpha', data='quick fox\n')
    self.tcli_obj.cmd_response._results[3] = inventory.Response(
        uid=3, device_name='device_3', error='',
        command='cat epsilon', data='jumped over\n')
    self.tcli_obj.cmd_response._results[4] = inventory.Response(
        uid=4, device_name='device_4', error='',
        command='cat epsilon', data='the wall\n')

  def testFormatResponse(self):
    """Tests display of command results - Single entry, csv format."""

    self._CannedResponse()

    # CSV formatted.
    self.tcli_obj.display = 'csv'

    header = '#!# c alpha #!#'
    # Single entry, csv format.
    with mock.patch.object(self.tcli_obj, '_Print') as mock_print:
      self.tcli_obj._FormatRow([1])
      mock_print.assert_has_calls([
          mock.call(header, 'title'),
          mock.call('Host, ColAa, ColAb\ndevice_1, hello, world\n')
      ])

  def testFormatResponseCSV1(self):
    """Tests display of command results - Multiple entries, csv format."""

    self._CannedResponse()

    # CSV formatted.
    self.tcli_obj.display = 'csv'

    header = '#!# c alpha #!#'
    # Multiple entries.
    with mock.patch.object(self.tcli_obj, '_Print') as mock_print:
      self.tcli_obj._FormatRow([1, 2])
      mock_print.assert_has_calls([
          mock.call(header, 'title'),
          mock.call('Host, ColAa, ColAb\n'
                    'device_1, hello, world\n'
                    'device_2, quick, fox\n')
      ])

  def testFormatResponseCSV2(self):
    """Tests display of command results."""

    self._CannedResponse()

    # CSV formatted.
    self.tcli_obj.display = 'csv'

    header = '#!# cat epsilon #!#'
    # Single entry - by Vendor.
    with mock.patch.object(self.tcli_obj, '_Print') as mock_print:
      self.tcli_obj._FormatRow([3])
      mock_print.assert_has_calls([
          mock.call(header, 'title'),
          mock.call('Host, ColCa, ColCb\n'
                    'device_3, jumped, over\n')
      ])

  def testFormatResponseCSV3(self):
    """Tests display of command results - Multiple entries and Vendors."""

    self._CannedResponse()

    # CSV formatted.
    self.tcli_obj.display = 'csv'

    header = '#!# cat epsilon #!#'
    # Multiple entry - Vendor 'Asterix'.
    with mock.patch.object(self.tcli_obj, '_Print') as mock_print:
      self.tcli_obj._FormatRow([3, 3])
      mock_print.assert_has_calls([
          mock.call(header, 'title'),
          mock.call('Host, ColCa, ColCb\n'
                    'device_3, jumped, over\n'
                    'device_3, jumped, over\n')
      ])

    # Multiple entry - Vendor 'Obelix'.
    with mock.patch.object(self.tcli_obj, '_Print') as mock_print:
      self.tcli_obj._FormatRow([4, 4])
      mock_print.assert_has_calls([
          mock.call(header, 'title'),
          mock.call('Host, ColDa, ColDb\n'
                    'device_4, the, wall\n'
                    'device_4, the, wall\n')
      ])

    # Multiple entry - Mixed vendors.
    with mock.patch.object(self.tcli_obj, '_Print') as mock_print:
      self.tcli_obj._FormatRow([3, 4, 3, 4])
      mock_print.assert_has_calls([
          mock.call(header, 'title'),
          mock.call('Host, ColCa, ColCb\n'
                    'device_3, jumped, over\n'
                    'device_3, jumped, over\n'),
          mock.call('Host, ColDa, ColDb\n'
                    'device_4, the, wall\n'
                    'device_4, the, wall\n')
      ])

  def testFormatResponseVarz(self):
    """Tests display of command results - Varz format."""

    self._CannedResponse()

    # VARZ formatted.
    self.tcli_obj.display = 'nvp'
    nvp_label = '# LABEL Host'

    header = '#!# c alpha #!#'
    # Single entry, nvp format.
    with mock.patch.object(self.tcli_obj, '_Print') as mock_print:
      self.tcli_obj._FormatRow([1])
      # Column header, nvp label and data rows.
      mock_print.assert_has_calls([
          mock.call(header, 'title'),
          mock.call(
              nvp_label + '\n'
              + 'device_1.ColAa hello\n'
              'device_1.ColAb world\n')
      ])

  def testFormatResponseGsh(self):
    """Tests display of command results - Gsh format."""

    # GSH formatted.
    self.tcli_obj.display = 'tbl'
    tcli.terminal.TerminalSize = lambda: (24, 10)
    with mock.patch.object(self.tcli_obj, '_Print') as mock_print:
      # Displays warning if width too narrow.
      self.tcli_obj._FormatRow([1])
      mock_print.assert_called_once()

  def testColor(self):
    self.tcli_obj.color = False
    self.tcli_obj._TCLICmd('color on')
    self.assertTrue(self.tcli_obj.color)
    self.tcli_obj.color = False
    self.tcli_obj._TCLICmd('color On')
    self.assertTrue(self.tcli_obj.color)
    self.tcli_obj.color = False
    self.tcli_obj._TCLICmd('color True')
    self.assertTrue(self.tcli_obj.color)
    self.tcli_obj.color = False
    self.tcli_obj._TCLICmd('color')
    self.assertTrue(self.tcli_obj.color)
    self.tcli_obj._TCLICmd('color')
    self.assertEqual(False, self.tcli_obj.color)

    self.tcli_obj.color = True
    self.tcli_obj._Print = mock.Mock()

    self.tcli_obj.system_color = ''
    self.tcli_obj.warning_color = ''
    self.tcli_obj.title_color = ''
    self.tcli_obj._CmdColorScheme('color_scheme', ['dark'])
    self.assertEqual(tcli.DARK_SYSTEM_COLOR, self.tcli_obj.system_color)
    self.assertEqual(tcli.DARK_WARNING_COLOR, self.tcli_obj.warning_color)
    self.assertEqual(tcli.DARK_TITLE_COLOR, self.tcli_obj.title_color)

    self.tcli_obj._CmdColorScheme('color_scheme', ['light'])
    self.assertEqual(tcli.LIGHT_SYSTEM_COLOR, self.tcli_obj.system_color)
    self.assertEqual(tcli.LIGHT_WARNING_COLOR, self.tcli_obj.warning_color)
    self.assertEqual(tcli.LIGHT_TITLE_COLOR, self.tcli_obj.title_color)

    self.assertRaises(ValueError, self.tcli_obj._CmdColorScheme,
                      'color_scheme', ['noscheme'])

    self.tcli_obj.color = False
    self.tcli_obj._CmdColorScheme('color_scheme', ['light'])
    self.assertEqual('', self.tcli_obj.system_color)
    self.assertEqual('', self.tcli_obj.warning_color)
    self.assertEqual('', self.tcli_obj.title_color)

  def testParseCommands(self):
    """Tests that commands are supplied to CmdRequests."""

    #TODO(harro): Better tests here.
    with mock.patch.object(self.tcli_obj, '_CmdRequests') as mock_request:
      # Single command.
      self.tcli_obj._ParseCommands('cat alpha')
      mock_request.assert_called_once_with(
          self.tcli_obj.device_list, ['cat alpha'])

    with mock.patch.object(self.tcli_obj, '_CmdRequests') as mock_request:
      # Multiple commands.
      self.tcli_obj._ParseCommands('cat alpha\ncat alpha\ncat beta')
      mock_request.assert_called_once_with(
          self.tcli_obj.device_list,
          ['cat alpha', 'cat alpha', 'cat beta'])

    # Multiple commands, with extra whitespace.
    with mock.patch.object(self.tcli_obj, '_CmdRequests') as mock_request:
      self.tcli_obj._ParseCommands(' cat alpha\n\n\ncat alpha  \ncat beta  ')
      mock_request.assert_called_once_with(
          self.tcli_obj.device_list,
          ['cat alpha', 'cat alpha', 'cat beta'])

    # Mixed commands some for the device some TCLI commands.
    with mock.patch.object(self.tcli_obj, '_CmdRequests') as mock_request:
      self.tcli_obj._ParseCommands(' cat alpha \n  %shelp \n\n\n%scolor  ' %
                                  (tcli.SLASH, tcli.SLASH))
      mock_request.assert_called_once_with(
          self.tcli_obj.device_list,
          ['cat alpha'])

    # Mixed commands with some inline TCLI commands.
    with mock.patch.object(self.tcli_obj, '_CmdRequests') as mock_request:
      self.tcli_obj._ParseCommands(' cat alpha\n%scolor\n\nc alpha  ' %
                                  tcli.SLASH)
      mock_request.assert_has_calls([
          mock.call(self.tcli_obj.device_list, ['cat alpha']),
          mock.call(self.tcli_obj.device_list, ['c alpha'])
          ])

  def testBufferInUse(self):
    """Tests _BufferInUse function."""
    # Ensure logging is clear
    self.tcli_obj.record = ''
    self.tcli_obj.recordall = ''
    self.tcli_obj.logall = ''
    self.tcli_obj.log = ''

    self.assertFalse(self.tcli_obj._BufferInUse('hello'))

    self.tcli_obj.record = 'hello'
    self.tcli_obj.recordall = 'world'
    self.tcli_obj.logall = 'hi'
    self.tcli_obj.log = 'there'

    self.assertTrue(self.tcli_obj._BufferInUse('hello'))
    self.assertTrue(self.tcli_obj._BufferInUse('world'))
    self.assertTrue(self.tcli_obj._BufferInUse('hi'))
    self.assertTrue(self.tcli_obj._BufferInUse('there'))

    self.assertFalse(self.tcli_obj._BufferInUse('not_in_use'))

  def testNumberofArgs(self):

    with mock.patch.object(self.tcli_obj, '_Print') as mock_print:
      self.tcli_obj._TCLICmd('help badarg')
      mock_print.assert_called_once_with(
          'Invalid number of arguments, found: 1.', msgtype='warning')

      self.tcli_obj._TCLICmd('buffer boo badarg')
      mock_print.assert_called_with(
          'Invalid number of arguments, found: 2.', msgtype='warning')

  def testTCLIExit(self):

    self.assertRaises(EOFError, self.tcli_obj._TCLICmd, 'exit')
    self.assertRaises(EOFError, self.tcli_obj._TCLICmd, 'quit')

  def testTCLIColor(self):

    self.tcli_obj.color = False
    self.tcli_obj.color_scheme = 'light'

    # Color toggles on and off.
    self.assertFalse(self.tcli_obj.color)
    self.tcli_obj._TCLICmd('color on')
    self.assertTrue(self.tcli_obj.color)
    self.tcli_obj._TCLICmd('color off')
    self.assertFalse(self.tcli_obj.color)
    self.tcli_obj._TCLICmd('color')
    self.assertTrue(self.tcli_obj.color)
    # Invalid bool rejected.
    with mock.patch.object(self.tcli_obj, '_Print') as mock_print:
      self.tcli_obj._TCLICmd('color bogus')
      mock_print.assert_called_once_with(
          "Error: Argument must be 'on' or 'off'.", msgtype='warning')
    # Valid color_scheme accepted
    self.tcli_obj._TCLICmd('color_scheme light')
    self.assertEqual('light', self.tcli_obj.color_scheme)
    self.tcli_obj._TCLICmd('color_scheme dark')
    self.assertEqual('dark', self.tcli_obj.color_scheme)

    # Invalid color scheme rejected
    with mock.patch.object(self.tcli_obj, '_Print') as mock_print:
      self.tcli_obj._TCLICmd('color_scheme bogus')
      mock_print.assert_called_once_with(
          "Error: Unknown color scheme: 'bogus'", msgtype='warning')

  def testSafeMode(self):
    """Tests safemode toggle."""

    self.tcli_obj.safemode = False
    self.tcli_obj._TCLICmd('safemode on')
    self.assertTrue(self.tcli_obj.safemode)
    self.tcli_obj._TCLICmd('safemode')
    self.assertFalse(self.tcli_obj.safemode)

  def testVerbose(self):
    """Tests verbose toggle."""

    self.tcli_obj.verbose = False
    self.tcli_obj._TCLICmd('verbose on')
    self.assertTrue(self.tcli_obj.verbose)
    self.tcli_obj._TCLICmd('verbose')
    self.assertFalse(self.tcli_obj.verbose)

  def testLineWrap(self):
    """Tests linewrap toggle."""

    self.tcli_obj.linewrap = False
    self.tcli_obj._TCLICmd('linewrap on')
    self.assertTrue(self.tcli_obj.linewrap)
    self.tcli_obj._TCLICmd('linewrap')
    self.assertFalse(self.tcli_obj.linewrap)

  def testTCLIDisplay(self):

    self.tcli_obj.display = 'raw'

    # Invalid display rejected.
    self.tcli_obj._TCLICmd('display boo')
    self.assertEqual('raw', self.tcli_obj.display)
    self.tcli_obj._TCLICmd('display tsvboo')
    self.assertEqual('raw', self.tcli_obj.display)

    # Valid display accepted.
    self.tcli_obj._TCLICmd('display csv')
    self.assertEqual('csv', self.tcli_obj.display)

    # Valid short command display accepted.
    self.tcli_obj._TCLICmd('D raw')
    self.assertEqual('raw', self.tcli_obj.display)

  def testTCLIMode(self):

    self.tcli_obj.mode = 'cli'

    # Invalid mode rejected.
    self.tcli_obj._TCLICmd('mode boo')
    self.assertEqual('cli', self.tcli_obj.mode)
    self.tcli_obj._TCLICmd('mode clishell')
    self.assertEqual('cli', self.tcli_obj.mode)

    # Valid mode accepted.
    self.tcli_obj._TCLICmd('mode shell')
    self.assertEqual('shell', self.tcli_obj.mode)

    # Valid short command display accepted.
    self.tcli_obj._TCLICmd('M gated')
    self.assertEqual('gated', self.tcli_obj.mode)

  def testTCLICmd(self):
    """b/2303768 Truncation of characters in /command."""

    self.tcli_obj.inventory.targets = ''                                        # type: ignore
    self.tcli_obj.inventory.device_list = set()                                 # type: ignore
    cmd = 'cat bogus'
    with mock.patch.object(self.tcli_obj, '_CmdRequests') as mock_request:
      self.tcli_obj._TCLICmd('command %s' % cmd)
      mock_request.assert_called_once_with(set(), ['cat bogus'], True)

  def testDisplayBadTable(self):

    # A bad format.
    self.tcli_obj.display = 'notaformat'
    self.assertRaises(tcli.TcliCmdError,
                      self.tcli_obj._DisplayFormatted, 'boo')

  def testAlphaNumBuffer(self):

    # Use 'buffer' as test command as it accepts and argument
    with mock.patch.object(self.tcli_obj, '_Print') as mock_print:
      self.tcli_obj._TCLICmd('buffer a.b')
      # Argument to buffer must be an alphanum.
      mock_print.assert_called_once_with(
          'Arguments with alphanumeric characters only.', msgtype='warning')

  def testTCLIFilter(self):
    """Tests setting filter via cli."""

    self.tcli_obj.filter_engine = None
    self.tcli_obj._TCLICmd('filter default_index')
    self.assertTrue(self.tcli_obj.filter_engine)

    self.tcli_obj.filter_engine.template_dir = tcli.FLAGS.template_dir          # type: ignore
    self.tcli_obj.filter_engine.ReadIndex('default_index')                      # type: ignore

    self.tcli_obj.filter_engine.ParseCmd(                                       # type: ignore
      'two words',  attributes={'Command': 'cat eps', 'Vendor': 'Asterix'})
    self.assertEqual(
      'ColCa, ColCb\ntwo, words\n', self.tcli_obj.filter_engine.table)          # type: ignore

    # Bad filter value.
    with mock.patch.object(self.tcli_obj, '_Print') as mock_print:
      self.tcli_obj._TCLICmd('filter not_a_valid_filter')
      mock_print.assert_called_once_with(
          "Invalid filter 'not_a_valid_filter'.", msgtype='warning')

  def testTCLIBufferAsignment(self):

    # Ensure logging is clear
    self.tcli_obj.record = ''
    self.tcli_obj.recordall = ''
    self.tcli_obj.logall = ''
    self.tcli_obj.log = ''

    self.tcli_obj._TCLICmd('record boo')
    self.assertEqual('boo', self.tcli_obj.record)
    self.tcli_obj._TCLICmd('recordall hoo')
    self.assertEqual('hoo', self.tcli_obj.recordall)

    self.tcli_obj._TCLICmd('log boo2')
    self.assertEqual('boo2', self.tcli_obj.log)
    self.tcli_obj._TCLICmd('logall hoo2')
    self.assertEqual('hoo2', self.tcli_obj.logall)

    self.tcli_obj._TCLICmd('recordstop boo')
    self.assertIsNone(self.tcli_obj.record)
    self.tcli_obj._TCLICmd('recordstop hoo')
    self.assertIsNone(self.tcli_obj.recordall)

    # Clears log but not logall.
    self.tcli_obj._TCLICmd('logstop boo2')
    self.assertIsNone(self.tcli_obj.log)
    self.assertEqual('hoo2', self.tcli_obj.logall)

    self.tcli_obj._TCLICmd('logstop hoo2')
    self.assertIsNone(self.tcli_obj.logall)

    self.tcli_obj.record = ''
    self.tcli_obj.recordall = ''
    self.tcli_obj.logall = ''
    self.tcli_obj.log = ''

    self.tcli_obj._TCLICmd('record hello')
    self.tcli_obj._TCLICmd('recordall world')
    self.tcli_obj._TCLICmd('recordall hello')
    self.assertEqual('hello', self.tcli_obj.record)
    self.assertEqual('world', self.tcli_obj.recordall)
    self.tcli_obj._TCLICmd('logstop hello')
    self.assertIsNone(self.tcli_obj.record)
    self.assertEqual('world', self.tcli_obj.recordall)

    self.tcli_obj.record = ''
    self.tcli_obj.recordall = ''
    self.tcli_obj.logall = ''
    self.tcli_obj.log = ''

    self.tcli_obj._TCLICmd('log hello')
    self.tcli_obj._TCLICmd('logall world')
    self.tcli_obj._TCLICmd('logall hello')
    self.tcli_obj._TCLICmd('recordall hello')
    self.assertEqual('hello', self.tcli_obj.log)
    self.assertEqual('world', self.tcli_obj.logall)
    self.assertEqual(self.tcli_obj.recordall, '')
    self.tcli_obj._TCLICmd('logstop hello')
    self.assertIsNone(self.tcli_obj.log)
    self.assertEqual('world', self.tcli_obj.logall)

    self.tcli_obj.record = ''
    self.tcli_obj.recordall = ''
    self.tcli_obj.logall = ''
    self.tcli_obj.log = ''

    # Buffer allocation with append should be the same
    self.tcli_obj._TCLICmd('record{} hello'.format(APPEND))
    self.tcli_obj._TCLICmd('recordall{} world'.format(APPEND))
    self.tcli_obj._TCLICmd('recordall{} hello'.format(APPEND))
    self.assertEqual('hello', self.tcli_obj.record)
    self.assertEqual('world', self.tcli_obj.recordall)
    self.tcli_obj._TCLICmd('logstop hello')
    self.assertIsNone(self.tcli_obj.record)
    self.assertEqual('world', self.tcli_obj.recordall)

    self.tcli_obj.record = ''
    self.tcli_obj.recordall = ''
    self.tcli_obj.logall = ''
    self.tcli_obj.log = ''

    self.tcli_obj._TCLICmd('log{} hello'.format(APPEND))
    self.tcli_obj._TCLICmd('logall{} world'.format(APPEND))
    self.tcli_obj._TCLICmd('logall{} hello'.format(APPEND))
    self.tcli_obj._TCLICmd('recordall{} hello'.format(APPEND))
    self.assertEqual('hello', self.tcli_obj.log)
    self.assertEqual('world', self.tcli_obj.logall)
    self.assertEqual(self.tcli_obj.recordall, '')
    self.tcli_obj._TCLICmd('logstop hello')
    self.assertIsNone(self.tcli_obj.log)
    self.assertEqual('world', self.tcli_obj.logall)

  def testTCLIBufferRecord(self):
    """Test writing to buffers."""

    # Record commands but not escape commands.
    with mock.patch.object(self.tcli_obj, '_Print') as mock_print:
      self.tcli_obj._TCLICmd('record hello')
      self.tcli_obj._ParseCommands('A test')
      self.tcli_obj._ParseCommands('A two\nline test')
      self.tcli_obj._TCLICmd('an invalid escape cmd')
      # A valid SLASH command.
      self.tcli_obj._TCLICmd('help')
      self.assertEqual(
          'A test\nA two\nline test',
          self.tcli_obj.buffers.GetBuffer('hello'))
      mock_print.assert_any_call("Invalid escape command 'an'.",
                                   msgtype='warning')

    # Record and append.
    self.tcli_obj.record = ''
    self.tcli_obj._TCLICmd('record{} hello'.format(APPEND))
    self.tcli_obj._ParseCommands('Append test')
    self.tcli_obj._ParseCommands('Append again\non two lines')
    self.assertEqual(
        'A test\nA two\nline test\nAppend test\nAppend again\non two lines',
        self.tcli_obj.buffers.GetBuffer('hello'))

    # Stop and restart recording. Buffer should be cleared.
    self.tcli_obj._TCLICmd('logstop hello')
    self.tcli_obj._TCLICmd('record hello')
    self.assertEqual('hello', self.tcli_obj.record)
    # Haven't written yet, so there is no buffer.
    self.assertRaises(AttributeError, self.tcli_obj.buffers.GetBuffer, 'hello')

    # Record to the newly cleared buffer.
    self.tcli_obj._ParseCommands('A test')
    self.tcli_obj._TCLICmd('logstop hello')
    self.tcli_obj._TCLICmd('record{} hello'.format(APPEND))
    self.assertEqual('A test', self.tcli_obj.buffers.GetBuffer('hello'))

    self.tcli_obj.record = self.tcli_obj.recordall = ''
    self.tcli_obj.log = self.tcli_obj.logall = ''

    # Record command and escape commands.
    self.tcli_obj._TCLICmd('recordall hello')
    self.tcli_obj._ParseCommands('A test')
    self.tcli_obj._ParseCommands('A two\nline test')
    self.tcli_obj._TCLICmd('an invalid escape cmd')
    # A valid SLASH command.
    self.tcli_obj._TCLICmd('buffer hello')
    self.assertEqual(
        'A test\nA two\nline test\n%sbuffer hello' % tcli.SLASH,
        self.tcli_obj.buffers.GetBuffer('hello'))

    self.tcli_obj.record = self.tcli_obj.recordall = ''
    self.tcli_obj.log = self.tcli_obj.logall = ''

    # Record command and escape commands with logstop.
    self.tcli_obj._TCLICmd('recordall hello')
    self.tcli_obj._TCLICmd('logall world')
    self.tcli_obj._ParseCommands('A test')
    self.tcli_obj._TCLICmd('logstop hello')
    self.assertIsNone(self.tcli_obj.recordall)
    self.tcli_obj._ParseCommands('A two\nline test')
    self.assertEqual(
        '%slogall world\nA test' % tcli.SLASH,
        self.tcli_obj.buffers.GetBuffer('hello'))
    self.assertEqual(
        'A test\n%slogstop hello\nA two\nline test' % tcli.SLASH,
        self.tcli_obj.buffers.GetBuffer('world'))
    self.assertEqual('world', self.tcli_obj.logall)

    self.tcli_obj.record = self.tcli_obj.recordall = ''
    self.tcli_obj.log = self.tcli_obj.logall = ''

    # Record to buffer already in use
    self.tcli_obj.logall = 'hello'
    self.tcli_obj._TCLICmd('record hello')
    self.assertEqual(self.tcli_obj.record, '')
    self.tcli_obj._TCLICmd('recordall hello')
    self.assertEqual(self.tcli_obj.recordall, '')
    self.tcli_obj._TCLICmd('log hello')
    self.assertEqual(self.tcli_obj.log, '')
    self.tcli_obj.logall = ''
    self.tcli_obj.record = 'hello'
    self.tcli_obj._TCLICmd('logall hello')
    self.assertEqual(self.tcli_obj.logall, '')

  def testTCLIBufferLog(self):
    """Tests logging of commands to a buffer."""

    with mock.patch.object(self.tcli_obj, '_Print') as mock_print:
      # Record commands but not escape commands.
      self.tcli_obj._TCLICmd('log hello')
      self.tcli_obj._ParseCommands('A test')
      self.tcli_obj._ParseCommands('A two\nline test')
      self.tcli_obj._TCLICmd('an invalid escape cmd')
      # A valid SLASH command.
      self.tcli_obj._TCLICmd('color')
      self.assertEqual(
          'A test\nA two\nline test',
          self.tcli_obj.buffers.GetBuffer('hello'))
      mock_print.assert_called_once_with("Invalid escape command 'an'.",
                                           msgtype='warning')

    self.tcli_obj.record = ''
    self.tcli_obj.recordall = ''
    self.tcli_obj.logall = ''
    self.tcli_obj.log = ''

    # Record both commands and escape commands.
    self.tcli_obj._TCLICmd('logall hello')
    self.tcli_obj._ParseCommands('A test')
    self.tcli_obj._ParseCommands('A two\nline test')
    # exit, quit & help are not logged
    self.tcli_obj._TCLICmd('help')
    self.tcli_obj._TCLICmd('color')
    self.assertEqual(
        'A test\nA two\nline test\n%scolor' % tcli.SLASH,
        self.tcli_obj.buffers.GetBuffer('hello'))

  def testDisplayBufname(self):
    """Tests that buffer name is displayed with logall."""

    with mock.patch.object(self.tcli_obj, '_Print') as mock_print:
      self.tcli_obj.logall = 'hello'
      self.tcli_obj._TCLICmd('logall')
      mock_print.assert_called_once_with("'logall' buffer is 'hello'",
                                        msgtype='system')

  def testTCLITimeout(self):
    """Tests setting the timeout value."""

    self.tcli_obj._TCLICmd('timeout 10')
    self.assertEqual(10, self.tcli_obj.timeout)

    # Rejects invalid data
    with mock.patch.object(self.tcli_obj, '_Print') as mock_print:
      self.tcli_obj._TCLICmd('timeout a')
      self.assertEqual(10, self.tcli_obj.timeout)
      mock_print.assert_called_once_with("Invalid timeout value 'a'.",
                                           msgtype='warning')

    # Accepts only positive whole integers
    self.tcli_obj._TCLICmd('timeout 15.1')
    self.assertEqual(10, self.tcli_obj.timeout)
    self.tcli_obj._TCLICmd('timeout -15')
    self.assertEqual(10, self.tcli_obj.timeout)

  def testTCLIBufferPlay(self):
    """Tests that buffer contents 'plays' out as commands."""

    with mock.patch.object(self.tcli_obj, '_ParseCommands') as mock_parse:
      self.tcli_obj.buffers.Append('boo', 'hello\nworld')
      self.tcli_obj._TCLICmd('play boo')
      mock_parse.assert_called_once_with('hello\nworld')

      # Non existing buffer so ParseCommand is still only called once..
      self.tcli_obj._TCLICmd('play non_exist')
      mock_parse.assert_called_once_with('hello\nworld')

  def testTCLIBufferRecursivePlay0(self):
    """Sanity check that buffer plays out."""
    with mock.patch.object(self.tcli_obj, '_ParseCommands') as mock_parse:
      self.tcli_obj.buffers.Append('boo', '%scolor' % tcli.SLASH)
      self.tcli_obj._TCLICmd('play boo')
      mock_parse.assert_called_once_with('%scolor' % tcli.SLASH)

  def testTCLIBufferRecursivePlay1(self):
    """Cannot make recursive or infinite calls to play out buffer."""
    with mock.patch.object(self.tcli_obj, '_Print') as mock_print:
      self.tcli_obj.buffers.Append('boo', '%splay boo' % tcli.SLASH)
      self.tcli_obj._TCLICmd('play boo')
      mock_print.assert_called_once_with(
          'Recursive call of "play" rejected.', msgtype='warning')

  def testTCLIBufferRecursivePlay2(self):
    """Cannot assign buffer while playing out the content."""
    with mock.patch.object(self.tcli_obj, '_Print') as mock_print:
      self.tcli_obj.buffers.Append('boo', '%srecordall boo\n%scolor' % (
          tcli.SLASH, tcli.SLASH))
      self.tcli_obj._TCLICmd('play boo')
      mock_print.assert_called_once_with(
          "Buffer: 'boo', already open by 'play' command.", msgtype='warning')
      self.assertEqual(self.tcli_obj.recordall, '')

  def testTCLIBufferRecursivePlay3(self):
    """Cannot play from a buffer that is being recorded to."""
    with mock.patch.object(self.tcli_obj, '_Print') as mock_print:
      self.tcli_obj.recordall = 'boo'
      self.tcli_obj.buffers.Append('boo', '%scolor' % tcli.SLASH)
      self.tcli_obj._TCLICmd('play boo')
      mock_print.assert_called_once_with(
          "Buffer: 'boo', already open for writing.", msgtype='warning')

  def testTCLIBufferRecursivePlay4(self):
    """Tests we are able log to a different buffer to what we play out from."""
    with mock.patch.object(self.tcli_obj, '_Print') as mock_print:
      self.tcli_obj.color = True
      self.tcli_obj.recordall = 'hoo'
      self.tcli_obj.buffers.Append('boo', '%scolor' % tcli.SLASH)
      self.tcli_obj._TCLICmd('play boo')
      self.assertEqual('%splay boo\n%scolor' % (tcli.SLASH, tcli.SLASH),
                       self.tcli_obj.buffers.GetBuffer('hoo'))
      # Color value was toggled.
      self.tcli_obj.color = False
      mock_print.assert_has_calls([])

  def testTCLIBuffer(self):
    with mock.patch.object(self.tcli_obj, '_Print') as mock_print:
      # Populate and test that content is returned.
      self.tcli_obj.buffers.Append('boo', 'hello\nworld')
      self.tcli_obj._TCLICmd('buffer boo')

      mock_print.assert_has_calls([
        mock.call('#! BUFFER boo !#', msgtype='warning'),
        mock.call('hello\nworld', msgtype='system'),
        mock.call('#! ENDBUFFER !#', msgtype='warning')])

      # Invalid buffer name displays null content.
      mock_print.reset_mock()
      self.tcli_obj._TCLICmd('buffer non_exist')
      mock_print.assert_called_once_with('Invalid buffer name "non_exist".',
                                         msgtype='warning')

  def testTCLIClear(self):
    """Tests that buffer contents are cleared."""

    self.tcli_obj.buffers.Append('boo', 'hello\nworld')
    self.tcli_obj._TCLICmd('clear boo')
    self.assertRaises(AttributeError, self.tcli_obj.buffers.GetBuffer, 'boo')

    # Clearing a nonexistant buffer fails silently.
    self.tcli_obj._TCLICmd('clear non_exist')


  def testTCLIExpandTargets(self):
    """Tests target expansion."""

    with mock.patch.object(self.tcli_obj, '_Print') as mock_print:
      self.tcli_obj.inventory.device_list = ['device_a', 'device_b']            # type: ignore
      self.tcli_obj._TCLICmd('expandtargets')
      mock_print.assert_called_once_with('device_a,device_b', msgtype='system')

  def testAdvancedRegexpTargets(self):
    """b/2725704 tcli fails to parse regexes."""

    # pylint: disable=anomalous-backslash-in-string
    self.assertEqual(
        ('somecommand', [r'^br\d{2}.*'], False),
        self.tcli_obj.cli_parser.ParseCommandLine(r"somecommand '^br\d{2}.*'"))

    # Complex TCLI commands targets/xtargets must be quoted.
    # pylint: disable=anomalous-backslash-in-string
    self.assertEqual(
        ('somecommand', [r'^brd{2}.*'], False),
        self.tcli_obj.cli_parser.ParseCommandLine(r'somecommand ^br\d{2}.*'))


if __name__ == '__main__':
  unittest.main()
