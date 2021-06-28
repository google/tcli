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

# Lint as: python3

"""Unittest for tcli script."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import collections
import copy
import os
from absl import flags
from absl.testing import absltest as unittest
import mock
from tcli import tcli_lib as tcli
from tcli.tcli_textfsm import clitable


APPEND = tcli.command_parser.APPEND
FLAGS = flags.FLAGS


class FakeDev(object):
  """Fake device as received from Chipmunk."""

  def __init__(self, vendor, realm):
    self._vendor = vendor
    self._realm = realm

  def vendor(self):  # pylint: disable=g-bad-name
    return self._vendor

  def realm(self):  # pylint: disable=g-bad-name
    return self._realm


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


ResponseTuple = collections.namedtuple(
    'ResponseTuple', ['device_name', 'error', 'uid', 'command', 'data'])


class FakeCmdResponse(tcli.command_response.CmdResponse):
  """Fake CmdResponse object."""

  _lock = FakeLock()
  done = FakeEvent()

  def __init__(self, uid='', device_name='', command='', data='', error=''):
    super(FakeCmdResponse, self).__init__()
    if uid:
      self.uid = uid

  def StartIndicator(self, message=''):
    pass


class FakeActionRequest(object):

  def __init__(self, uid):
    self.uid = uid


class UnitTestTCLI(unittest.TestCase):
  """Tests the TCLI class."""

  @classmethod
  def setUpClass(cls):
    super(UnitTestTCLI, cls).setUpClass()
    cls.flags_orig = copy.deepcopy(tcli.FLAGS)
    tcli.command_response.threading.Event = mock.MagicMock()
    tcli.command_response.threading.Lock = mock.MagicMock()
    tcli.command_response.tqdm = mock.MagicMock()
    tcli.FLAGS.template_dir = os.path.join(os.path.dirname(__file__),
                                           'testdata')

  @classmethod
  def tearDownClass(cls):
    super(UnitTestTCLI, cls).tearDownClass()
    tcli.FLAGS = cls.flags_orig

  def setUp(self):
    super(UnitTestTCLI, self).setUp()
    # Turn off looking for .tclirc
    tcli.FLAGS.color = False
    tcli.FLAGS.config_file = 'none'
    tcli.FLAGS.interactive = False
    tcli.FLAGS.cmds = None
    tcli.FLAGS.display = 'raw'
    tcli.FLAGS.filter = None

    self.orig_terminal_size = tcli.terminal.TerminalSize
    tcli.terminal.TerminalSize = lambda: (10, 20)

    self.orig_dev_attr = tcli.inventory.DEVICE_ATTRIBUTES
    tcli.inventory.DEVICE_ATTRIBUTES = {}

    self.tcli_obj = tcli.TCLI()

    self.tcli_obj.inventory = mock.MagicMock()
    self.tcli_obj.inventory.device_list = ['a', 'b', 'c']
    dev_attr = collections.namedtuple('dev_attr', [])
    self.tcli_obj.inventory.devices = {'a': dev_attr(),
                                       'b': dev_attr(),
                                       'c': dev_attr()}
    self.tcli_obj.inventory.targets = ''
    self.tcli_obj.inventory.CreateCmdRequest.return_value = FakeCmdResponse(
        '123')

    self.tcli_obj._PrintWarning = mock.Mock()
    self.tcli_obj._PrintOutput = mock.Mock()
    self.tcli_obj._PrintSystem = mock.Mock()

    self.tcli_obj.RegisterCommands(self.tcli_obj.cli_parser)
    self.tcli_obj.cli_parser.RegisterCommand(
        'somecommand', 'somecommand help', append=True, regexp=True,
        handler=lambda command, args, append: (command, args, append))

    self.tcli_obj.verbose = True
    self.tcli_obj.linewrap = True
    self.tcli_obj.color = False
    self.tcli_obj.timeout = 1

  def tearDown(self):
    super(UnitTestTCLI, self).tearDown()
    tcli.terminal.TerminalSize = self.orig_terminal_size
    tcli.inventory.DEVICE_ATTRIBUTES = self.orig_dev_attr

  def testCopy(self):
    # TODO(harro): Tests for extended commands?
    self.tcli_obj.buffers.Append('label', 'content')
    self.tcli_obj.record = None
    self.tcli_obj.inline_tcli = copy.copy(self.tcli_obj)
    self.assertEqual('content', self.tcli_obj.buffers.GetBuffer('label'))
    self.assertFalse(self.tcli_obj.record)
    # Change parent.
    self.tcli_obj.buffers.Append('label', 'more')
    self.tcli_obj.record = 'label'
    # Change child.
    self.tcli_obj.inline_tcli.record = 'anotherlabel'

    # Test the parent.
    self.assertEqual('content\nmore', self.tcli_obj.buffers.GetBuffer('label'))
    self.assertEqual('label', self.tcli_obj.record)
    # Test the child.
    self.assertEqual('content\nmore',
                     self.tcli_obj.inline_tcli.buffers.GetBuffer('label'))
    self.assertEqual('anotherlabel', self.tcli_obj.inline_tcli.record)

  def testSetDefaults(self):
    """Tests setup of default commands from Flags."""

    # Change some values around
    self.tcli_obj.color = not tcli.FLAGS.color
    self.tcli_obj.timeout = 30

    self.tcli_obj.SetDefaults()
    self.assertEqual(tcli.FLAGS.color, self.tcli_obj.color)
    self.assertEqual(tcli.FLAGS.timeout, self.tcli_obj.timeout)

  def testStartUp(self):
    """Tests flag setup and run commands."""

    # Sanity check defaults.
    assert (
        tcli.FLAGS.display == 'raw' and
        tcli.FLAGS.filter is None)

    # Don't read from a .tclirc file.
    tcli.FLAGS.config_file = 'none'

    with mock.patch.object(self.tcli_obj, 'ParseCommands'):
      with mock.patch.object(self.tcli_obj, '_InitInventory'):
        with mock.patch.object(self.tcli_obj, 'SetDefaults') as mock_parse:
          self.tcli_obj.StartUp(None, False)
          # Without target or cmds, interactive is set to True.
          self.assertTrue(self.tcli_obj.interactive)
          mock_parse.assert_has_calls([mock.call(), mock.call()])

        with mock.patch.object(self.tcli_obj, 'SetDefaults') as mock_parse:
          self.tcli_obj.StartUp('bogus', False)
          # Without target or cmds, interactive is set to True.
          self.assertFalse(self.tcli_obj.interactive)
          mock_parse.assert_called_once_with()

  def testTildeCompleter(self):

    self.assertEqual(
        '/record', self.tcli_obj._TildeCompleter('/reco', 0))
    self.assertEqual(
        '/record{}'.format(APPEND), self.tcli_obj._TildeCompleter('/reco', 1))
    self.assertEqual(
        '/recordall', self.tcli_obj._TildeCompleter('/reco', 2))
    self.assertEqual(
        '/recordall{}'.format(APPEND),
        self.tcli_obj._TildeCompleter('/reco', 3))
    self.assertEqual(
        '/recordstop', self.tcli_obj._TildeCompleter('/reco', 4))
    self.assertEqual(
        None, self.tcli_obj._TildeCompleter('/reco', 5))

  def testCmdCompleter(self):
    self.tcli_obj = tcli.TCLI()
    self.tcli_obj.filter = 'default'
    clitable.CliTable.INDEX = {}
    self.tcli_obj.filter_engine = clitable.CliTable(
        'default_index', template_dir=tcli.FLAGS.template_dir)
    self.tcli_obj._PrintWarning = mock.Mock()
    self.tcli_obj._PrintOutput = mock.Mock()
    self.tcli_obj._PrintSystem = mock.Mock()

    self.assertEqual('show', self.tcli_obj._CmdCompleter('', 0))
    self.assertEqual('cat', self.tcli_obj._CmdCompleter('', 1))
    self.assertEqual(None, self.tcli_obj._CmdCompleter('', 2))

    self.assertEqual('cat', self.tcli_obj._CmdCompleter('c', 0))
    self.assertEqual(None, self.tcli_obj._CmdCompleter('c', 1))

    self.assertEqual('alpha', self.tcli_obj._CmdCompleter('c ', 0))
    self.assertEqual('beta', self.tcli_obj._CmdCompleter('c ', 1))
    self.assertEqual('epsilon', self.tcli_obj._CmdCompleter('c ', 2))
    self.assertEqual(None, self.tcli_obj._CmdCompleter('c ', 3))

    self.assertEqual(
        'alpha', self.tcli_obj._CmdCompleter('c al', 0))
    self.assertEqual(None, self.tcli_obj._CmdCompleter('c al', 1))

  def testCallback(self):
    """Tests async callback."""

    self.tcli_obj._FormatResponse = mock.Mock()
    self.tcli_obj.inventory.ReformatCmdResponse = lambda r: r

    self.tcli_obj.Callback(FakeActionRequest('non_exist_uid'))
    # Test that nonexistant uid trigger early return.
    self.assertFalse(self.tcli_obj.cmd_response._response_count)

    self.tcli_obj.cmd_response.SetCommandRow(0, '')
    self.tcli_obj.cmd_response.SetCommandRow(1, '')

    self.tcli_obj.cmd_response.SetRequest(0, 'valid_uid')
    self.tcli_obj.cmd_response.SetRequest(0, 'another_valid_uid')
    self.tcli_obj.cmd_response.SetRequest(1, '2nd_row_uid_a')
    self.tcli_obj.cmd_response.SetRequest(1, '2nd_row_uid_b')
    self.tcli_obj.cmd_response._row_response[0] = []

    self.tcli_obj.inventory.device_list = set(['host_a', 'host_b'])
    self.tcli_obj.command_list = ['cat alpha', 'cat beta']

    # Call with valid uid and check response count increments.
    self.tcli_obj.Callback(FakeActionRequest('valid_uid'))

    self.assertTrue(self.tcli_obj.cmd_response._response_count)
    self.assertEqual(['valid_uid'], self.tcli_obj.cmd_response._row_response[0])
    # Should still point at first (0) row.
    self.assertFalse(self.tcli_obj.cmd_response._current_row)

    # Second call for last argument of first row.
    self.tcli_obj.Callback(FakeActionRequest('another_valid_uid'))

    self.assertEqual(['valid_uid', 'another_valid_uid'],
                     self.tcli_obj.cmd_response._row_response[0])
    self.assertFalse(self.tcli_obj.cmd_response._row_response[1])
    # Should point at next row (1).
    self.assertEqual(1, self.tcli_obj.cmd_response._current_row)

    self.tcli_obj.cmd_response._current_row = 0
    self.tcli_obj.cmd_response._response_count = 0
    self.tcli_obj.cmd_response._row_response[0] = []

    # Test populating the second row before the first.
    self.tcli_obj.Callback(FakeActionRequest('2nd_row_uid_b'))
    self.tcli_obj.Callback(FakeActionRequest('2nd_row_uid_a'))

    self.assertFalse(self.tcli_obj.cmd_response._row_response[0])
    self.assertEqual(['2nd_row_uid_b', '2nd_row_uid_a'],
                     self.tcli_obj.cmd_response._row_response[1])

    # Once first row gets fully pop'd then both should be reported and cleared.
    self.tcli_obj.Callback(FakeActionRequest('valid_uid'))
    self.tcli_obj.Callback(FakeActionRequest('another_valid_uid'))

    self.assertEqual(['valid_uid', 'another_valid_uid'],
                     self.tcli_obj.cmd_response._row_response[0])
    self.assertEqual(['2nd_row_uid_b', '2nd_row_uid_a'],
                     self.tcli_obj.cmd_response._row_response[1])
    # Should point at next row (2).
    self.assertEqual(2, self.tcli_obj.cmd_response._current_row)

  def testFormatRaw(self):
    """Test display of raw output."""

    with mock.patch.object(self.tcli_obj, '_PrintOutput') as mock_output:
      self.tcli_obj._FormatRaw(
          ResponseTuple(
              device_name='device1', command='time of day',
              data='a random\nmulti line\nstring.', error='', uid=''))
      mock_output.assert_has_calls([
          mock.call('#!# device1:time of day #!#', title=True),
          mock.call('a random\nmulti line\nstring.')
      ])

  def testFormatRawResponse(self):
    """Tests display of raw command results."""

    self.tcli_obj.cmd_response._results['beef'] = ResponseTuple(
        uid='beef', device_name='device_1', data='hello world\n',
        command='c alpha', error='')
    self.tcli_obj.cmd_response._results['feed'] = ResponseTuple(
        uid='feed', device_name='device_2', data='quick fox\n',
        command='c alpha', error='')

    self.tcli_obj.display = 'raw'
    self.tcli_obj.inventory._devices = {
        'device_1': collections.OrderedDict([('Vendor', 'Asterix')]),
        'device_2': collections.OrderedDict([('Vendor', 'Asterix')]),
    }

    # Raw headers.
    header = '#!# %s:%s #!#' % ('device_1', 'c alpha')

    with mock.patch.object(self.tcli_obj, '_PrintOutput') as mock_output:
      # Single entry, raw output.
      self.tcli_obj._FormatResponse(['beef'])
      mock_output.assert_has_calls([
          mock.call(header, title=True),
          mock.call('hello world\n')
      ])

    header2 = '#!# %s:%s #!#' % ('device_2', 'c alpha')
    # Multiple ActionRequest objects, differing content.
    with mock.patch.object(self.tcli_obj, '_PrintOutput') as mock_output:
      self.tcli_obj._FormatResponse(['beef', 'feed'])
      mock_output.assert_has_calls([
          mock.call(header, title=True),
          mock.call('hello world\n'),
          mock.call(header2, title=True),
          mock.call('quick fox\n')
      ])

    # Multiple action request objects, same content.
    with mock.patch.object(self.tcli_obj, '_PrintOutput') as mock_output:
      self.tcli_obj._FormatResponse(['beef', 'beef'])
      mock_output.assert_has_calls([
          mock.call(header, title=True),
          mock.call('hello world\n'),
          mock.call(header, title=True),
          mock.call('hello world\n')
      ])

  def _CannedResponse(self):      # pylint: disable=invalid-name
    """Setup some canned commands and responses."""

    tcli.inventory.DEVICE_ATTRIBUTES = {
        'vendor': tcli.inventory.inventory_base.DeviceAttribute(
            'vendor', '', None, '', display_case='title', command_flag=False)}
    # Initialise the textfsm engine in TCLI.
    self.tcli_obj.filter = 'default_index'
    self.tcli_obj.filter_engine = clitable.CliTable(self.tcli_obj.filter,
                                                    tcli.FLAGS.template_dir)
    self.tcli_obj.display = 'raw'
    dev_attr = collections.namedtuple('dev_attr', ['vendor'])
    self.tcli_obj.inventory.devices = {
        'device_1': dev_attr(vendor='asterix'),
        'device_2': dev_attr(vendor='asterix'),
        'device_3': dev_attr(vendor='asterix'),
        'device_4': dev_attr(vendor='obelix')
    }

    self.tcli_obj.cmd_response._results['beef'] = ResponseTuple(
        uid='beef', device_name='device_1', error='',
        command='c alpha', data='hello world\n')
    self.tcli_obj.cmd_response._results['feed'] = ResponseTuple(
        uid='feed', device_name='device_2', error='',
        command='c alpha', data='quick fox\n')
    self.tcli_obj.cmd_response._results['deed'] = ResponseTuple(
        uid='deed', device_name='device_3', error='',
        command='cat epsilon', data='jumped over\n')
    self.tcli_obj.cmd_response._results['dead'] = ResponseTuple(
        uid='dead', device_name='device_4', error='',
        command='cat epsilon', data='the wall\n')

  def testFormatResponse(self):
    """Tests display of command results - Single entry, csv format."""

    self._CannedResponse()

    # CSV formatted.
    self.tcli_obj.display = 'csv'

    header = '#!# c alpha #!#'
    # Single entry, csv format.
    with mock.patch.object(self.tcli_obj, '_PrintOutput') as mock_output:
      self.tcli_obj._FormatResponse(['beef'])
      mock_output.assert_has_calls([
          mock.call(header, title=True),
          mock.call('Host, ColAa, ColAb\ndevice_1, hello, world\n')
      ])

  def testFormatResponseCSV1(self):
    """Tests display of command results - Multiple entries, csv format."""

    self._CannedResponse()

    # CSV formatted.
    self.tcli_obj.display = 'csv'

    header = '#!# c alpha #!#'
    # Multiple entries.
    with mock.patch.object(self.tcli_obj, '_PrintOutput') as mock_output:
      self.tcli_obj._FormatResponse(['beef', 'feed'])
      mock_output.assert_has_calls([
          mock.call(header, title=True),
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
    with mock.patch.object(self.tcli_obj, '_PrintOutput') as mock_output:
      self.tcli_obj._FormatResponse(['deed'])
      mock_output.assert_has_calls([
          mock.call(header, title=True),
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
    with mock.patch.object(self.tcli_obj, '_PrintOutput') as mock_output:
      self.tcli_obj._FormatResponse(['deed', 'deed'])
      mock_output.assert_has_calls([
          mock.call(header, title=True),
          mock.call('Host, ColCa, ColCb\n'
                    'device_3, jumped, over\n'
                    'device_3, jumped, over\n')
      ])

    # Multiple entry - Vendor 'Obelix'.
    with mock.patch.object(self.tcli_obj, '_PrintOutput') as mock_output:
      self.tcli_obj._FormatResponse(['dead', 'dead'])
      mock_output.assert_has_calls([
          mock.call(header, title=True),
          mock.call('Host, ColDa, ColDb\n'
                    'device_4, the, wall\n'
                    'device_4, the, wall\n')
      ])

    # Multiple entry - Mixed vendors.
    with mock.patch.object(self.tcli_obj, '_PrintOutput') as mock_output:
      self.tcli_obj._FormatResponse(['deed', 'deed', 'dead', 'dead'])
      mock_output.assert_has_calls([
          mock.call(header, title=True),
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
    with mock.patch.object(self.tcli_obj, '_PrintOutput') as mock_output:
      self.tcli_obj._FormatResponse(['beef'])
      # Column header, nvp label and data rows.
      mock_output.assert_has_calls([
          mock.call(header, title=True),
          mock.call(
              nvp_label + '\n' +
              'device_1.ColAa hello\n'
              'device_1.ColAb world\n')
      ])

  def testFormatResponseGsh(self):
    """Tests display of command results - Gsh format."""

    # GSH formatted.
    self.tcli_obj.display = 'tbl'
    tcli.terminal.TerminalSize = lambda: (24, 10)
    with mock.patch.object(self.tcli_obj, '_PrintWarning') as mock_warn:
      # Displays warning if width too narrow.
      self.tcli_obj._FormatResponse(['beef'])
      mock_warn.called_once_with('Width too narrow to display table.')

  def testColor(self):
    self.tcli_obj.color = False
    self.tcli_obj.TildeCmd('color on')
    self.assertTrue(self.tcli_obj.color)
    self.tcli_obj.color = False
    self.tcli_obj.TildeCmd('color On')
    self.assertTrue(self.tcli_obj.color)
    self.tcli_obj.color = False
    self.tcli_obj.TildeCmd('color True')
    self.assertTrue(self.tcli_obj.color)
    self.tcli_obj.color = False
    self.tcli_obj.TildeCmd('color')
    self.assertTrue(self.tcli_obj.color)
    self.tcli_obj.TildeCmd('color')
    self.assertEqual(False, self.tcli_obj.color)

    self.tcli_obj.color = True
    self.tcli_obj._PrintWarning = mock.Mock()

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

  def testExtractInlineCommands(self):

    # Reasonably complex command with piping but no inlines.
    cmd_base = 'cat alpha | grep abc || grep xyz'

    # Command without inlines returns original command line.
    cmd = cmd_base
    (new_cmd, _) = self.tcli_obj._ExtractInlineCommands(cmd)
    self.assertEqual(cmd, new_cmd)

    # Command with invalid inlines returns original command line.
    cmd = '{} {}bogus'.format(cmd_base, tcli.TILDE*2)
    (new_cmd, _) = self.tcli_obj._ExtractInlineCommands(cmd)
    self.assertEqual(cmd, new_cmd)

    # The tilde must be preceded by a space.
    cmd = '{}{}log bogus'.format(cmd_base, tcli.TILDE*2)
    (new_cmd, _) = self.tcli_obj._ExtractInlineCommands(cmd)
    self.assertEqual(cmd, new_cmd)

    # Command with simple inline in short form.
    cmd = '{} {}D csv'.format(cmd_base, tcli.TILDE*2)
    (new_cmd, tcli_object) = self.tcli_obj._ExtractInlineCommands(cmd)
    self.assertEqual(cmd_base, new_cmd)
    self.assertEqual('csv', tcli_object.display)

    # Multiple inline commands are supported.
    cmd = ('{0} {1}display csv {1}log logfile').format(cmd_base, tcli.TILDE*2)
    (new_cmd, inline_tcli) = self.tcli_obj._ExtractInlineCommands(cmd)
    self.assertEqual(cmd_base, new_cmd)
    self.assertEqual('logfile', inline_tcli.log)
    self.assertEqual('csv', inline_tcli.display)

    # Invalid inline commands are assumed to be part of the commandline.
    cmd = 'cat alpha{0}log {0}bogus {0}log filelist'.format(tcli.TILDE*2)
    (new_cmd, inline_tcli) = self.tcli_obj._ExtractInlineCommands(cmd)
    self.assertEqual('cat alpha{0}log {0}bogus'.format(tcli.TILDE*2), new_cmd)
    self.assertEqual('filelist', inline_tcli.log)

  def testExtractInlineExit(self):

    # Stops accidental parsing of command data.
    cmd = 'cat alpha {}exit'.format(tcli.TILDE*2)
    (new_cmd, inline_tcli) = self.tcli_obj._ExtractInlineCommands(cmd)
    self.assertEqual('cat alpha', new_cmd)

    # Stops accidental parsing of command data.
    cmd = 'show {0}color {0}exit'.format(tcli.TILDE*2)
    (new_cmd, inline_tcli) = self.tcli_obj._ExtractInlineCommands(cmd)
    self.assertEqual('show {}color'.format(tcli.TILDE*2), new_cmd)

    # inlines to the right of the exit are still parsed.
    cmd = 'cat alpha {0}log boo {0}exit {0}log hoo'.format(tcli.TILDE*2)
    (new_cmd, inline_tcli) = self.tcli_obj._ExtractInlineCommands(cmd)
    self.assertEqual('cat alpha {}log boo'.format(tcli.TILDE*2), new_cmd)
    self.assertEqual('hoo', inline_tcli.log)

  def testExtractPipe(self):
    """Tests parsing of command pipes."""

    cmd = 'cat alpha | grep abc || grep xyz || grep -v "||"'
    self.assertEqual(
        ('cat alpha | grep abc', '| grep xyz | grep -v "||"'),
        self.tcli_obj._ExtractPipe(cmd))

    cmd = "cat alpha '||' || grep xyz || grep -v .   "
    self.assertEqual(
        ("cat alpha '||'", '| grep xyz | grep -v .'),
        self.tcli_obj._ExtractPipe(cmd))

    cmd = 'cat alpha   || grep xyz || grep -v "||"'
    self.assertEqual(
        ('cat alpha', '| grep xyz | grep -v "||"'),
        self.tcli_obj._ExtractPipe(cmd))

    cmd = "cat alpha | grep '||'"
    self.assertEqual(
        ("cat alpha | grep '||'", ''),
        self.tcli_obj._ExtractPipe(cmd))

  def testParseCommands(self):
    """Tests that commands destined for are supplied to CmdRequests."""

    with mock.patch.object(self.tcli_obj, 'CmdRequests') as mock_request:
      # Single command.
      self.tcli_obj.ParseCommands('cat alpha')
      mock_request.assert_called_once_with(
          self.tcli_obj.device_list, ['cat alpha'])

    with mock.patch.object(self.tcli_obj, 'CmdRequests') as mock_request:
      # Multiple commands.
      self.tcli_obj.ParseCommands('cat alpha\ncat alpha\ncat beta')
      mock_request.assert_called_once_with(
          self.tcli_obj.device_list,
          ['cat alpha', 'cat alpha', 'cat beta'])

    # Multiple commands, with extra whitespace.
    with mock.patch.object(self.tcli_obj, 'CmdRequests') as mock_request:
      self.tcli_obj.ParseCommands(' cat alpha\n\n\ncat alpha  \ncat beta  ')
      mock_request.assert_called_once_with(
          self.tcli_obj.device_list,
          ['cat alpha', 'cat alpha', 'cat beta'])

    # Mixed commands some for the device some tilde commands.
    with mock.patch.object(self.tcli_obj, 'TildeCmd'):
      with mock.patch.object(self.tcli_obj, 'CmdRequests') as mock_request:
        self.tcli_obj.ParseCommands(' cat alpha \n  %shelp \n\n\n%scolor  ' %
                                    (tcli.TILDE, tcli.TILDE))
        mock_request.assert_called_once_with(
            self.tcli_obj.device_list,
            ['cat alpha'])

      with mock.patch.object(self.tcli_obj, 'CmdRequests') as mock_request:
        self.tcli_obj.ParseCommands(' cat alpha\n%scolor\n\nc alpha  ' %
                                    tcli.TILDE)
        mock_request.assert_has_calls([
            mock.call(self.tcli_obj.device_list, ['cat alpha']),
            mock.call(self.tcli_obj.device_list, ['c alpha'])
            ])

      # Mix of valid and invalid commands.
      with mock.patch.object(self.tcli_obj, 'CmdRequests') as mock_request:
        self.tcli_obj.ParseCommands(
            'cat alpha\n\n bat alpha %sverbose on\n%scolor off\n\n'
            'cat theta  %slog buf\n\nc alpha' %
            (tcli.TILDE*2, tcli.TILDE, tcli.TILDE*2))
        mock_request.assert_has_calls([
            mock.call(self.tcli_obj.device_list, ['cat alpha']),
            mock.call(self.tcli_obj.device_list, ['c alpha'])
            ])

  def testBufferInUse(self):
    """Tests _BufferInUse function."""
    # Ensure logging is clear
    self.tcli_obj.record = None
    self.tcli_obj.recordall = None
    self.tcli_obj.logall = None
    self.tcli_obj.log = None

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

    with mock.patch.object(self.tcli_obj, '_PrintWarning') as mock_warning:
      self.tcli_obj.TildeCmd('help badarg')
      mock_warning.assert_called_once_with(
          'Invalid number of arguments, found "1".')

      self.tcli_obj.TildeCmd('buffer boo badarg')
      mock_warning.assert_called_with(
          'Invalid number of arguments, found "2".')

  def testTildeExit(self):

    self.assertRaises(EOFError, self.tcli_obj.TildeCmd, 'exit')
    self.assertRaises(EOFError, self.tcli_obj.TildeCmd, 'quit')

  def testTildeColor(self):

    self.tcli_obj.color = False
    self.tcli_obj.color_scheme = 'light'

    # Color toggles on and off.
    self.assertFalse(self.tcli_obj.color)
    self.tcli_obj.TildeCmd('color on')
    self.assertTrue(self.tcli_obj.color)
    self.tcli_obj.TildeCmd('color off')
    self.assertFalse(self.tcli_obj.color)
    self.tcli_obj.TildeCmd('color')
    self.assertTrue(self.tcli_obj.color)
    # Invalid bool rejected.
    with mock.patch.object(self.tcli_obj, '_PrintWarning') as mock_warning:
      self.tcli_obj.TildeCmd('color bogus')
      mock_warning.assert_called_once_with(
          "Error: Argument must be 'on' or 'off'.")
    # Valid color_scheme accepted
    self.tcli_obj.TildeCmd('color_scheme light')
    self.assertEqual('light', self.tcli_obj.color_scheme)
    self.tcli_obj.TildeCmd('color_scheme dark')
    self.assertEqual('dark', self.tcli_obj.color_scheme)

    # Invalid color scheme rejected
    with mock.patch.object(self.tcli_obj, '_PrintWarning') as mock_warning:
      self.tcli_obj.TildeCmd('color_scheme bogus')
      mock_warning.assert_called_once_with(
          'Error: Unknown color scheme: bogus')

  def testSafeMode(self):
    """Tests safemode toggle."""

    self.tcli_obj.safemode = False
    self.tcli_obj.TildeCmd('safemode on')
    self.assertTrue(self.tcli_obj.safemode)
    self.tcli_obj.TildeCmd('safemode')
    self.assertFalse(self.tcli_obj.safemode)

  def testVerbose(self):
    """Tests verbose toggle."""

    self.tcli_obj.verbose = False
    self.tcli_obj.TildeCmd('verbose on')
    self.assertTrue(self.tcli_obj.verbose)
    self.tcli_obj.TildeCmd('verbose')
    self.assertFalse(self.tcli_obj.verbose)

  def testLineWrap(self):
    """Tests linewrap toggle."""

    self.tcli_obj.linewrap = False
    self.tcli_obj.TildeCmd('linewrap on')
    self.assertTrue(self.tcli_obj.linewrap)
    self.tcli_obj.TildeCmd('linewrap')
    self.assertFalse(self.tcli_obj.linewrap)

  def testTildeDisplay(self):

    self.tcli_obj.display = 'raw'

    # Invalid display rejected.
    self.tcli_obj.TildeCmd('display boo')
    self.assertEqual('raw', self.tcli_obj.display)
    self.tcli_obj.TildeCmd('display tsvboo')
    self.assertEqual('raw', self.tcli_obj.display)

    # Valid display accepted.
    self.tcli_obj.TildeCmd('display csv')
    self.assertEqual('csv', self.tcli_obj.display)

    # Valid short command display accepted.
    self.tcli_obj.TildeCmd('D raw')
    self.assertEqual('raw', self.tcli_obj.display)

  def testTildeMode(self):

    self.tcli_obj.mode = 'cli'

    # Invalid mode rejected.
    self.tcli_obj.TildeCmd('mode boo')
    self.assertEqual('cli', self.tcli_obj.mode)
    self.tcli_obj.TildeCmd('mode clishell')
    self.assertEqual('cli', self.tcli_obj.mode)

    # Valid mode accepted.
    self.tcli_obj.TildeCmd('mode shell')
    self.assertEqual('shell', self.tcli_obj.mode)

    # Valid short command display accepted.
    self.tcli_obj.TildeCmd('M gated')
    self.assertEqual('gated', self.tcli_obj.mode)

  def testTildeCmd(self):
    """b/2303768 Truncation of characters in /command."""

    self.tcli_obj.inventory.targets = ''
    self.tcli_obj.inventory.device_list = set()
    cmd = 'cat bogus'
    with mock.patch.object(self.tcli_obj, 'CmdRequests') as mock_request:
      self.tcli_obj.TildeCmd('command %s' % cmd)
      mock_request.assert_called_once_with(set(), ['cat bogus'], True)

  def testDisplayBadTable(self):

    # A bad format.
    self.tcli_obj.display = 'notaformat'
    self.assertRaises(tcli.TcliCmdError,
                      self.tcli_obj._DisplayTable, 'boo')

  def testAlphaNumBuffer(self):

    # Use 'buffer' as test command as it accepts and argument
    with mock.patch.object(self.tcli_obj, '_PrintWarning') as mock_warning:
      self.tcli_obj.TildeCmd('buffer a.b')
      # Argument to buffer must be an alphanum.
      mock_warning.assert_called_once_with(
          'Arguments with alphanumeric characters only.')

  def testTildeFilter(self):
    """Tests setting filter via cli."""

    self.tcli_obj.filter_engine = None
    self.tcli_obj.TildeCmd('filter default_index')
    self.assertTrue(self.tcli_obj.filter_engine)

    self.tcli_obj.filter_engine.template_dir = tcli.FLAGS.template_dir
    self.tcli_obj.filter_engine.ReadIndex('default_index')

    self.tcli_obj.filter_engine.ParseCmd('two words',
                                         attributes={'Command': 'cat eps',
                                                     'Vendor': 'Asterix'})
    self.assertEqual(
        'ColCa, ColCb\ntwo, words\n',
        self.tcli_obj.filter_engine.table)

    # Bad filter value.
    with mock.patch.object(self.tcli_obj, '_PrintWarning') as mock_warning:
      self.tcli_obj.TildeCmd('filter not_a_valid_filter')
      mock_warning.assert_called_once_with(
          "Invalid filter 'not_a_valid_filter'.")

  def testTildeBufferAsignment(self):

    # Ensure logging is clear
    self.tcli_obj.record = None
    self.tcli_obj.recordall = None
    self.tcli_obj.logall = None
    self.tcli_obj.log = None

    self.tcli_obj.TildeCmd('record boo')
    self.assertEqual('boo', self.tcli_obj.record)
    self.tcli_obj.TildeCmd('recordall hoo')
    self.assertEqual('hoo', self.tcli_obj.recordall)

    self.tcli_obj.TildeCmd('log boo2')
    self.assertEqual('boo2', self.tcli_obj.log)
    self.tcli_obj.TildeCmd('logall hoo2')
    self.assertEqual('hoo2', self.tcli_obj.logall)

    self.tcli_obj.TildeCmd('recordstop boo')
    self.assertEqual(None, self.tcli_obj.record)
    self.tcli_obj.TildeCmd('recordstop hoo')
    self.assertEqual(None, self.tcli_obj.recordall)

    # Clears log but not logall.
    self.tcli_obj.TildeCmd('logstop boo2')
    self.assertEqual(None, self.tcli_obj.log)
    self.assertEqual('hoo2', self.tcli_obj.logall)

    self.tcli_obj.TildeCmd('logstop hoo2')
    self.assertEqual(None, self.tcli_obj.logall)

    self.tcli_obj.record = None
    self.tcli_obj.recordall = None
    self.tcli_obj.logall = None
    self.tcli_obj.log = None

    self.tcli_obj.TildeCmd('record hello')
    self.tcli_obj.TildeCmd('recordall world')
    self.tcli_obj.TildeCmd('recordall hello')
    self.assertEqual('hello', self.tcli_obj.record)
    self.assertEqual('world', self.tcli_obj.recordall)
    self.tcli_obj.TildeCmd('logstop hello')
    self.assertEqual(None, self.tcli_obj.record)
    self.assertEqual('world', self.tcli_obj.recordall)

    self.tcli_obj.record = None
    self.tcli_obj.recordall = None
    self.tcli_obj.logall = None
    self.tcli_obj.log = None

    self.tcli_obj.TildeCmd('log hello')
    self.tcli_obj.TildeCmd('logall world')
    self.tcli_obj.TildeCmd('logall hello')
    self.tcli_obj.TildeCmd('recordall hello')
    self.assertEqual('hello', self.tcli_obj.log)
    self.assertEqual('world', self.tcli_obj.logall)
    self.assertEqual(None, self.tcli_obj.recordall)
    self.tcli_obj.TildeCmd('logstop hello')
    self.assertEqual(None, self.tcli_obj.log)
    self.assertEqual('world', self.tcli_obj.logall)

    self.tcli_obj.record = None
    self.tcli_obj.recordall = None
    self.tcli_obj.logall = None
    self.tcli_obj.log = None

    # Buffer allocation with append should be the same
    self.tcli_obj.TildeCmd('record{} hello'.format(APPEND))
    self.tcli_obj.TildeCmd('recordall{} world'.format(APPEND))
    self.tcli_obj.TildeCmd('recordall{} hello'.format(APPEND))
    self.assertEqual('hello', self.tcli_obj.record)
    self.assertEqual('world', self.tcli_obj.recordall)
    self.tcli_obj.TildeCmd('logstop hello')
    self.assertEqual(None, self.tcli_obj.record)
    self.assertEqual('world', self.tcli_obj.recordall)

    self.tcli_obj.record = None
    self.tcli_obj.recordall = None
    self.tcli_obj.logall = None
    self.tcli_obj.log = None

    self.tcli_obj.TildeCmd('log{} hello'.format(APPEND))
    self.tcli_obj.TildeCmd('logall{} world'.format(APPEND))
    self.tcli_obj.TildeCmd('logall{} hello'.format(APPEND))
    self.tcli_obj.TildeCmd('recordall{} hello'.format(APPEND))
    self.assertEqual('hello', self.tcli_obj.log)
    self.assertEqual('world', self.tcli_obj.logall)
    self.assertEqual(None, self.tcli_obj.recordall)
    self.tcli_obj.TildeCmd('logstop hello')
    self.assertEqual(None, self.tcli_obj.log)
    self.assertEqual('world', self.tcli_obj.logall)

  def testTildeBufferRecord(self):
    """Test writing to buffers."""

    # A null device list prevents sending of commands to backend.
    self.tcli_obj.inventory.device_list = []

    # Record commands but not escape commands.
    with mock.patch.object(self.tcli_obj, '_PrintWarning') as mock_warning:
      self.tcli_obj.TildeCmd('record hello')
      self.tcli_obj.ParseCommands('A test')
      self.tcli_obj.ParseCommands('A two\nline test')
      self.tcli_obj.TildeCmd('an invalid escape cmd')
      # A valid TILDE command.
      self.tcli_obj.TildeCmd('help')
      self.assertEqual(
          'A test\nA two\nline test',
          self.tcli_obj.buffers.GetBuffer('hello'))
      mock_warning.assert_called_once_with("Invalid escape command 'an'.")

    # Record and append.
    self.tcli_obj.record = None
    self.tcli_obj.TildeCmd('record{} hello'.format(APPEND))
    self.tcli_obj.ParseCommands('Append test')
    self.tcli_obj.ParseCommands('Append again\non two lines')
    self.assertEqual(
        'A test\nA two\nline test\nAppend test\nAppend again\non two lines',
        self.tcli_obj.buffers.GetBuffer('hello'))

    # Stop and restart recording. Buffer should be cleared.
    self.tcli_obj.TildeCmd('logstop hello')
    self.tcli_obj.TildeCmd('record hello')
    self.assertEqual('hello', self.tcli_obj.record)
    self.assertEqual(None, self.tcli_obj.buffers.GetBuffer('hello'))

    # Record to the newly cleared buffer.
    self.tcli_obj.ParseCommands('A test')
    self.tcli_obj.TildeCmd('logstop hello')
    self.tcli_obj.TildeCmd('record{} hello'.format(APPEND))
    self.assertEqual('A test', self.tcli_obj.buffers.GetBuffer('hello'))

    self.tcli_obj.record = None
    self.tcli_obj.recordall = None
    self.tcli_obj.logall = None
    self.tcli_obj.log = None

    # Record command and escape commands.
    self.tcli_obj.TildeCmd('recordall hello')
    self.tcli_obj.ParseCommands('A test')
    self.tcli_obj.ParseCommands('A two\nline test')
    self.tcli_obj.TildeCmd('an invalid escape cmd')
    # A valid TILDE command.
    self.tcli_obj.TildeCmd('buffer hello')
    self.assertEqual(
        'A test\nA two\nline test\n%sbuffer hello' % tcli.TILDE,
        self.tcli_obj.buffers.GetBuffer('hello'))

    self.tcli_obj.record = None
    self.tcli_obj.recordall = None
    self.tcli_obj.logall = None
    self.tcli_obj.log = None

    # Record command and escape commands with logstop.
    self.tcli_obj.TildeCmd('recordall hello')
    self.tcli_obj.TildeCmd('logall world')
    self.tcli_obj.ParseCommands('A test')
    self.tcli_obj.TildeCmd('logstop hello')
    self.assertEqual(None, self.tcli_obj.recordall)
    self.tcli_obj.ParseCommands('A two\nline test')
    self.assertEqual(
        '%slogall world\nA test' % tcli.TILDE,
        self.tcli_obj.buffers.GetBuffer('hello'))
    self.assertEqual(
        'A test\n%slogstop hello\nA two\nline test' % tcli.TILDE,
        self.tcli_obj.buffers.GetBuffer('world'))
    self.assertEqual('world', self.tcli_obj.logall)

    self.tcli_obj.record = None
    self.tcli_obj.recordall = None
    self.tcli_obj.logall = None
    self.tcli_obj.log = None

    # Record to buffer already in use
    self.tcli_obj.logall = 'hello'
    self.tcli_obj.TildeCmd('record hello')
    self.assertEqual(None, self.tcli_obj.record)
    self.tcli_obj.TildeCmd('recordall hello')
    self.assertEqual(None, self.tcli_obj.recordall)
    self.tcli_obj.TildeCmd('log hello')
    self.assertEqual(None, self.tcli_obj.log)
    self.tcli_obj.logall = None
    self.tcli_obj.record = 'hello'
    self.tcli_obj.TildeCmd('logall hello')
    self.assertEqual(None, self.tcli_obj.logall)

  def testTildeBufferLog(self):
    """Tests logging of commands to a buffer."""

    # A null device list prevents sending of commands to backend.
    self.tcli_obj.inventory.device_list = []

    with mock.patch.object(self.tcli_obj, '_PrintWarning') as mock_warning:
      # Record commands but not escape commands.
      self.tcli_obj.TildeCmd('log hello')
      self.tcli_obj.ParseCommands('A test')
      self.tcli_obj.ParseCommands('A two\nline test')
      self.tcli_obj.TildeCmd('an invalid escape cmd')
      # A valid TILDE command.
      self.tcli_obj.TildeCmd('color')
      self.assertEqual(
          'A test\nA two\nline test',
          self.tcli_obj.buffers.GetBuffer('hello'))
      mock_warning.assert_called_once_with("Invalid escape command 'an'.")

    self.tcli_obj.record = None
    self.tcli_obj.recordall = None
    self.tcli_obj.logall = None
    self.tcli_obj.log = None

    # Record both commands and escape commands.
    self.tcli_obj.TildeCmd('logall hello')
    self.tcli_obj.ParseCommands('A test')
    self.tcli_obj.ParseCommands('A two\nline test')
    # exit, quit & help are not logged
    self.tcli_obj.TildeCmd('help')
    self.tcli_obj.TildeCmd('color')
    self.assertEqual(
        'A test\nA two\nline test\n%scolor' % tcli.TILDE,
        self.tcli_obj.buffers.GetBuffer('hello'))

  def testDisplayBufname(self):
    """Tests that buffer name is displayed with logall."""

    with mock.patch.object(self.tcli_obj, '_PrintSystem') as mock_print:
      self.tcli_obj.logall = 'hello'
      self.tcli_obj.TildeCmd('logall')
      mock_print.assert_called_once_with("'logall' buffer is 'hello'")

  def testTildeTimeout(self):
    """Tests setting the timeout value."""

    self.tcli_obj.TildeCmd('timeout 10')
    self.assertEqual(10, self.tcli_obj.timeout)

    # Rejects invalid data
    with mock.patch.object(self.tcli_obj, '_PrintWarning') as mock_warning:
      self.tcli_obj.TildeCmd('timeout a')
      self.assertEqual(10, self.tcli_obj.timeout)
      mock_warning.assert_called_once_with("Invalid timeout value 'a'.")

    # Accepts only positive whole integers
    self.tcli_obj.TildeCmd('timeout 15.1')
    self.assertEqual(10, self.tcli_obj.timeout)
    self.tcli_obj.TildeCmd('timeout -15')
    self.assertEqual(10, self.tcli_obj.timeout)

  def testCmdDefaults(self):
    """Tests setting commands back to default."""

    self.tcli_obj.color_scheme = 'cstring'
    self.tcli_obj.display = 'dstring'
    self.tcli_obj.mode = 'estring'

    # Sanity check defaults.
    assert (
        not tcli.FLAGS.interactive and
        tcli.FLAGS.cmds is None and
        tcli.FLAGS.display == 'raw' and
        tcli.FLAGS.filter is None)

    # Check that reseting 'display', resets this (and only this) variable.
    self.tcli_obj._CmdDefaults('defaults', ['display'])
    self.assertEqual('estring', self.tcli_obj.mode)

    self.tcli_obj.display = 'dstring'
    # Check that reseting 'mode', resets this (and only this) variable.
    self.tcli_obj._CmdDefaults('defaults', ['mode'])
    self.assertEqual(tcli.DEFAULT_CMDS['mode'], self.tcli_obj.mode)
    self.assertEqual('dstring', self.tcli_obj.display)

    self.tcli_obj.mode = 'estring'
    # Reset all values.
    self.tcli_obj._CmdDefaults('defaults', ['all'])
    self.assertEqual(tcli.FLAGS.display, self.tcli_obj.display)
    self.assertEqual(tcli.FLAGS.mode, self.tcli_obj.mode)
    # Raise exception for invalid value.
    self.assertRaises(
        ValueError, self.tcli_obj._CmdDefaults, 'defaults', ['allall'])

  def testTildeBufferPlay(self):
    """Tests that buffer contents 'plays' out as commands."""

    with mock.patch.object(self.tcli_obj, 'ParseCommands') as mock_parse:
      self.tcli_obj.buffers.Append('boo', 'hello\nworld')
      self.tcli_obj.TildeCmd('play boo')
      mock_parse.assert_called_once_with('hello\nworld')

      # Non existing buffer triggers command with no imput.
      self.tcli_obj.TildeCmd('play non_exist')
      mock_parse.assert_has_calls([mock.call('hello\nworld'),
                                   mock.call(None)])

  def testTildeBufferRecursivePlay0(self):
    """Sanity check that buffer plays out."""
    with mock.patch.object(self.tcli_obj, 'ParseCommands') as mock_parse:
      self.tcli_obj.buffers.Append('boo', '%scolor' % tcli.TILDE)
      self.tcli_obj.TildeCmd('play boo')
      mock_parse.assert_called_once_with('%scolor' % tcli.TILDE)

  def testTildeBufferRecursivePlay1(self):
    """Cannot make recursive or infinite calls to play out buffer."""
    with mock.patch.object(self.tcli_obj, '_PrintWarning') as mock_warning:
      self.tcli_obj.buffers.Append('boo', '%splay boo' % tcli.TILDE)
      self.tcli_obj.TildeCmd('play boo')
      mock_warning.assert_called_once_with(
          'Recursive call of "play" rejected.')

  def testTildeBufferRecursivePlay2(self):
    """Cannot assign buffer while playing out the content."""
    with mock.patch.object(self.tcli_obj, '_PrintWarning') as mock_warning:
      self.tcli_obj.buffers.Append('boo', '%srecordall boo\n%scolor' % (
          tcli.TILDE, tcli.TILDE))
      self.tcli_obj.TildeCmd('play boo')
      mock_warning.assert_called_once_with(
          "Buffer: boo, already open by 'play' command.")
      self.assertEqual(None, self.tcli_obj.recordall)

  def testTildeBufferRecursivePlay3(self):
    """Cannot play from a buffer that is being recorded to."""
    with mock.patch.object(self.tcli_obj, '_PrintWarning') as mock_warning:
      self.tcli_obj.recordall = 'boo'
      self.tcli_obj.buffers.Append('boo', '%scolor' % tcli.TILDE)
      self.tcli_obj.TildeCmd('play boo')
      mock_warning.assert_called_once_with(
          "Buffer: 'boo', already open for writing.")

  def testTildeBufferRecursivePlay4(self):
    """Tests we are able log to a different buffer to what we play out from."""
    with mock.patch.object(self.tcli_obj, '_PrintWarning') as mock_warning:
      self.tcli_obj.color = True
      self.tcli_obj.recordall = 'hoo'
      self.tcli_obj.buffers.Append('boo', '%scolor' % tcli.TILDE)
      self.tcli_obj.TildeCmd('play boo')
      self.assertEqual('%splay boo\n%scolor' % (tcli.TILDE, tcli.TILDE),
                       self.tcli_obj.buffers.GetBuffer('hoo'))
      # Color value was toggled.
      self.tcli_obj.color = False
      mock_warning.assert_has_calls([])

  def testTildeBuffer(self):
    with mock.patch.object(self.tcli_obj, '_PrintSystem') as mock_print:
      with mock.patch.object(self.tcli_obj, '_PrintWarning') as mock_warning:
        # Populate and test that content is returned.
        self.tcli_obj.buffers.Append('boo', 'hello\nworld')
        self.tcli_obj.TildeCmd('buffer boo')

        mock_print.assert_has_calls([mock.call('hello\nworld'),
                                     mock.call(None)])
        mock_warning.assert_has_calls([mock.call('#! BUFFER boo !#'),
                                       mock.call('#! ENDBUFFER !#')])

        # Invalid buffer name displays null content.
        mock_print.reset_mock()
        mock_warning.reset_mock()
        self.tcli_obj.TildeCmd('buffer non_exist')
        mock_warning.assert_called_once_with('Invalid buffer name "non_exist".')

  def testTildeClear(self):
    """Tests that buffer contents are cleared."""

    self.tcli_obj.buffers.Append('boo', 'hello\nworld')
    self.tcli_obj.TildeCmd('clear boo')
    self.assertEqual(None, self.tcli_obj.buffers.GetBuffer('boo'))

    # Clearing a nonexistant buffer fails silently.
    self.tcli_obj.TildeCmd('clear non_exist')

  def testPipe(self):
    """Tests _Pipe escape function."""

    # Default - no piped function.
    self.tcli_obj.pipe = None
    self.assertEqual('boo\nboo', self.tcli_obj._Pipe('boo\nboo'))

    # Piped function greps for 'boo' in supplied argument.
    self.tcli_obj.pipe = '/bin/grep boo'
    self.assertEqual('boo\nboo\n', self.tcli_obj._Pipe('boo\nboo'))
    self.tcli_obj.pipe = '/bin/grep boo'
    self.assertEqual('boo\n', self.tcli_obj._Pipe('boo\nhoo'))

    # Tests that pipes are supported within the piping function.
    self.tcli_obj.pipe = '/bin/grep boo | /bin/grep -v hoo'
    self.assertEqual('boo\n', self.tcli_obj._Pipe('boo\nhoo'))
    self.tcli_obj.pipe = '/bin/grep boo | /bin/grep -v boo'
    self.assertEqual('', self.tcli_obj._Pipe('boo\nhoo'))

  def testTildeExpandTargets(self):
    """Tests target expansion."""

    with mock.patch.object(self.tcli_obj, '_PrintSystem') as mock_print:
      self.tcli_obj.inventory.device_list = ['device_a', 'device_b']
      self.tcli_obj.TildeCmd('expandtargets')
      mock_print.assert_called_once_with('device_a,device_b')

  def testAdvancedRegexpTargets(self):
    """b/2725704 tcli fails to parse regexes."""

    # pylint: disable=anomalous-backslash-in-string
    self.assertEqual(
        ('somecommand', [r'^br\d{2}.*'], False),
        self.tcli_obj.cli_parser.ParseCommandLine(r"somecommand '^br\d{2}.*'"))

    # Complex tilde commands targets/xtargets must be quoted.
    # pylint: disable=anomalous-backslash-in-string
    self.assertEqual(
        ('somecommand', [r'^brd{2}.*'], False),
        self.tcli_obj.cli_parser.ParseCommandLine(r'somecommand ^br\d{2}.*'))


if __name__ == '__main__':
  unittest.main()
