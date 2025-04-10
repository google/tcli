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

"""TCLI - Tokenised CLI for accessing command driven devices.

This librray handles initialising the inventory, executing the RC file,
parsing the command inputs supplied by the user, forwarding to the accessor
and displaying the results received from accessor for said remote devices.
"""

import copy
import os
import subprocess
import sys
import tempfile
import threading

from absl import flags
from absl import logging
try:
  # For windows platform.
  from pyreadline3.rlmain import Readline                                       # type: ignore
  readline = Readline()
except(ImportError):
  import readline

from tcli import command_completer as completer
from tcli import command_parser
from tcli import command_register
from tcli import command_response
from tcli import display
# inventory import will be overridden in main.py
from tcli import accessor_base as accessor
from tcli import inventory_base as inventory
from tcli import text_buffer
from tcli.command_parser import ParseError, I
from tcli.tcli_textfsm import clitable
from tcli.tcli_textfsm.clitable import CliTableError
from textfsm import terminal
from textfsm import texttable
from textfsm.texttable import TableError

# Formats for displaying to the user.
DISPLAY_FORMATS = command_register.DISPLAY_FORMATS

# cli modes on the target device.
MODE_FORMATS = command_register.MODE_FORMATS

# TCLI (local) command prefix.
SLASH = command_parser.SLASH
# pylint: disable=redefined-builtin
if __doc__: __doc__ = __doc__.replace('%s', SLASH)

# Banner message to display at program start.
BANNER_WIDTH = 76
MOTD = f"""#!{'#'*BANNER_WIDTH}!#' 
#! TCLI - Tokenized Command Line Interface
#! Note: Beta code, use with caution.
#!
#! Type '{SLASH}help' to get started.
#! To disable color: '{SLASH}color off'.
#!
#! For more guidance see:
#! https://github.com/harro/tcli
#!
#! Note:
#! Interactive TCLI starts in safe mode (indicated by '*' in the prompt).
#! To disable safe mode: '{SLASH}safemode off'.
#!
#! Have a nice day!
#!{'#'*BANNER_WIDTH}!#"""

# Default path for config commands. Commands are run from this file at startup.
DEFAULT_CONFIGFILE = os.path.join(os.path.expanduser('~'), '.tclirc')

FLAGS = flags.FLAGS

flags.DEFINE_string(
  'config_file', DEFAULT_CONFIGFILE, """
    Configuration file to read. Lines in this file will be read into '
    buffer "startup" and played.'
    Skipped if file name is the string 'None|none'""", short_name='R')

flags.DEFINE_boolean(
  'dry_run', False,
  f'{I}Display commands and targets, without submitting commands.')

flags.DEFINE_boolean('sorted', False, f'{I}Sort device entries in output.')

flags.DEFINE_string(
  'template_dir', os.path.join(os.path.dirname(__file__), 'testdata'),
  f'{I}Path where command templates are located', short_name='t')


class Error(Exception):
  """Base class for errors."""


class TcliError(Error):
  """General TCLI error."""


class TcliCmdError(Error):
  """Error in command arguments or argument parsing."""


class TCLI(object):
  """TCLI - Tokenised Command-Line Interface.

  Parent object when file is invoked as an executable.

  Attributes:
    buffers: Object for storing and retrieving string buffer content.
    cli_parser: Object that handles CLI command attributes and handler.
    cmd_response: Object that handles collating device requests/responses.
    color: If output uses ANSI escape characters for color.
    display: String denoting how to format output data.
    filter: String denoting how to extract data from device command output.
    filter_engine: Object that parses device command data.
    interactive: Boolean, is the user running this in interactive mode.
    inventory: Object that implements inventory API.
    linewrap: Boolean, wrap displayed text strings.
    log: String buffer name for where to record data input and output.
    logall: Similar to log but records escape command input/output.
    mode: String denoting what device mode is the target of cli commands.
    pipe: String denoting shell commands to read/write output data.
    playback: A string, name of the active playback buffer.
    record: String buffer name for where to record command input.
    recordall: Similar to 'record' but stores escape commands too.
    safemode: Boolean, control if raw commands are forwarded to targets or not.
    targets: String of device names and regular expressions to match against.
    device_list: Sorted list of device names, the union of targets,
        excluding matches with xtargets. Read-only.
    timeout: Integer, Duration (in seconds) to wait for outstanding commands
        responses to complete.
    verbose: Boolean, if to display all columns or suppress Verbose ones.
    xtargets: String of device names and regular expressions to exclude.
  """

  def __init__(self, interactive=False, commands='', inventory=None) -> None:
    # Also see copy method when modifying/adding attributes.

    # Async callback.
    self._lock = threading.Lock()
    self.interactive = interactive
    self.inventory = inventory
    self.filter_engine = None
    self.playback = None
    self.safemode = False
    self.verbose = False
    # Attributes with defaults set by flags.
    self.color = True
    self.display = None
    self.filter = None
    self.linewrap = False
    self.mode = 'cli'
    self.timeout = 0
    # Buffers
    self.log = self.logall = ''
    self.record = self.recordall = ''

    self.buffers = text_buffer.TextBuffer()
    self.cmd_response = command_response.CmdResponse()
    self.cli_parser = command_parser.CommandParser()
    self.dsp = display.Display()
    if not self.inventory:
      self._InitInventory()
    command_register.RegisterCommands(self, self.cli_parser)
    command_register.SetFlagDefaults(self.cli_parser)
    # If interactive then the user will input furhter commands.
    # So we enable safe mode and apply the users .tclirc file.
    if self.interactive:
      # Set safe mode.
      self.cli_parser.ExecHandler('safemode', ['on'], False)
      # Apply user settings.
      self._ParseRCFile()
    if commands:
      self._ParseCommands(commands)

  def __copy__(self) -> "TCLI":
    """Copies attributes from self to new tcli object."""
    # Create new instance with existing inventory.
    tcli_obj = type(self)(inventory=self.inventory)
    #TODO(harro): Why does this break ParseCommands?
    # tcli_obj.__dict__.update(self.__dict__)
  
    tcli_obj.buffers = self.buffers
    tcli_obj.cmd_response = self.cmd_response
    tcli_obj.color = self.color
    tcli_obj.display = self.display
    tcli_obj.dsp = self.dsp
    tcli_obj.filter = self.filter
    tcli_obj.filter_engine = self.filter_engine
    tcli_obj.linewrap = self.linewrap
    tcli_obj.log = self.log
    tcli_obj.logall = self.logall
    tcli_obj.mode = self.mode
    tcli_obj.playback = self.playback
    tcli_obj.record = self.record
    tcli_obj.recordall = self.recordall
    tcli_obj.safemode = self.safemode
    tcli_obj.timeout = self.timeout
    tcli_obj.verbose = self.verbose
    return tcli_obj

  devices = property(lambda self: self.inventory.devices)
  device_list = property(lambda self: self.inventory.device_list)

  # pylint: disable=unused-argument
  def Completer(self, word: str, state: int) -> str|None:
    """Command line completion used by readline library."""

    # The readline completer is not stateful. So we read the full line and pass
    # that to the respective completer functions.

    # Silently discard leading whitespace on cli.
    full_line = readline.get_line_buffer().lstrip()                             # type: ignore

    if full_line and full_line.startswith(SLASH):
      if not self.cli_parser: return None
      # Return completions for matching TCLI commands.
      return completer.TCLICompleter(full_line, state, self.cli_parser)

    # If not a TCLI command, or an empty prompt, then return completions for 
    # known remote device commands that we support with TextFSM.
    if not self.filter_engine: return None
    return completer.CmdCompleter(full_line, state, self.filter_engine)

  def Motd(self) ->None:
    """Display message of the day."""
    self._Print(MOTD, msgtype='system')

  def Prompt(self) -> None:
    """Present prompt for further input."""

    # Clear response dictionary to ignore outstanding requests.
    self.cmd_response = command_response.CmdResponse()
    # Print the main prompt, so the ASCII escape sequences work.
    # Displays the target string, count of targets and if safe mode is on.
    print(self.dsp.getPrompt(self.inventory.targets,                            # type: ignore
                             self.device_list, self.safemode))                  
    # Stripped ASCII escape from here, as they are not interpreted in PY3.
    self._ParseCommands(input(display.PROMPT_STR))

  def _BufferInUse(self, buffername: str) -> bool:
    """Check if buffer is already being written to."""

    if buffername in (self.record, self.recordall, self.log, self.logall):
      self._Print(
        f"Buffer: '{buffername}', already open for writing.", msgtype='warning')
      return True

    if buffername == self.playback:
      self._Print(
        f"Buffer: '{self.playback}', already open by 'play' command.",
        msgtype='warning')
      return True

    return False

  def _Callback(self, response: inventory.Response) -> None:
    """Async callback called on each device response received."""

    with self._lock:
      logging.debug("Callback for '%s'.", response.uid)
      # Take a response from inventory and pass it to the command_response.
      self.cmd_response.AddResponse(response)

      # If we have all responses for current row/command then display.
      (row, pipe) = self.cmd_response.GetRow()
      while row:
        self._FormatRow(row, pipe)
        (row, pipe) = self.cmd_response.GetRow()

  def _CmdRequests(self, device_list:list[str], command_list:list[str],
                  explicit_cmd:bool=False) -> None:
    """Submits command list to devices and waits on responses.

    Args:
      device_list: List of strings, each string being a devicename
      command_list: List of strings, each string is a command to execute
      explicit_cmd: Bool, if commands submitted via '/command' or not
    """

    # Log commands, even if nothing to do, dry run, or we are in safe mode.
    for buf in (self.record, self.recordall, self.log, self.logall):
      self.buffers.Append(buf, '\n'.join(command_list))

    if not device_list or not command_list or not self.inventory:
      # Nothing to do.
      return

    if not explicit_cmd and self.safemode:
      self._Print('Safe mode on, command ignored.')
      return

    if FLAGS.dry_run:
      # With dry_run set, we show what devices are targets, and what commands
      # would have been sent to them and return.
      self._Print('Send Commands: ', msgtype='title')
      self._Print('  ' + '\r  '.join(command_list))
      self._Print('To Targets: ', msgtype='title')
      self._Print('  ' + ','.join(device_list))
      return

    # Response requests.
    requests = []
    self.cmd_response = command_response.CmdResponse()
    # The set of responses for a given command is known as a 'row'.
    for cmd_row_id, command in enumerate(command_list):
      # Split off client side pipe command.
      (command, pipe) = self.cli_parser.ExtractPipe(command)
      logging.debug("Extracted command and pipe: '%s' & '%s'.", command, pipe)
      self.cmd_response.InitCommandRow(cmd_row_id, pipe)

      # Create command requests.
      for device in device_list:
        req = inventory.CmdRequest(device, command, self.mode)
        # Track the order that commands are submitted.
        # Responses are received in any order and
        # we use the row ID to reassemble.
        logging.debug('UID: %s.', req.uid)
        self.cmd_response.SetRequest(cmd_row_id, req.uid)
        requests.append(req)

    # Submit command request to inventory manager for each device.
    requests_callbacks = [(req, self._Callback) for req in requests]
    # Setup progress indicator.
    self.cmd_response.StartIndicator()
    accessor.SendRequests(requests_callbacks, deadline=self.timeout)

    # Wait for all callbacks to complete.
    # We add a 5 seconds pad to allow requests to timeout and be included in the
    # results before cleanup and reporting results.
    if not self.cmd_response.done.wait(self.timeout +5):
      # If we had a timeout then clear pending responses.
      self.cmd_response = command_response.CmdResponse()
      self._Print('Timeout: timer exceeded while waiting for responses.',
                  msgtype='warning')
    logging.debug('CmdRequests: All callbacks completed.')

  def _DisplayFormatted(
      self, result: clitable.CliTable, pipe: str = '') -> None:
    """Displays output in tabular form."""

    if self.display == 'csv':
      self._Print(self._Pipe(str(result), pipe=pipe))

    elif self.display == 'nvp':
      # 'Host' is added to the LABEL prefix.
      result.AddKeys(['Host'])
      self._Print(self._Pipe(result.LabelValueTable(), pipe=pipe))

    elif self.display == 'tbl':
      (_, width) = terminal.TerminalSize()                                      # type: ignore
      try:
        self._Print(self._Pipe(result.FormattedTable(width), pipe=pipe))
      except TableError as error_message:
        width *= 2
        # Try again allowing text to wrap once.
        try:
          self._Print(self._Pipe(result.FormattedTable(width), pipe=pipe))
        except TableError as error_message:
          self._Print(str(error_message), msgtype='warning')
    else:
      # Problem with parsing of display command if we reach here.
      raise TcliCmdError('Unsupported display format: %s.' %
                         repr(self.display))

  def _DisplayRaw(self, response: inventory.Response, pipe: str = '') -> None:
    """Display response in raw format."""

    # Do nothing with raw output other than tagging
    # Which device/command generated it.
    self._Header(f'{response.device_name}:{response.command}')
    self._Print(self._Pipe(response.data, pipe=pipe))

  def _FormatErrorResponse(self, response: inventory.Response) -> None:
    """Formatted error derived from response."""

    self._Header(f'{response.device_name}:{response.command}', 'warning')
    self._Print(response.error, 'warning')

  def _FormatRow(self, response_uid_list: list[int], pipe: str = '') -> None:
    """Display the results from a list of responses (a row)."""

    # Filter required if display format is not 'raw'.
    if self.display != 'raw' and not self.filter:
      self._Print(f"No filter set, cannot display in '{self.display}' format",
                  'warning')
      return

    result = {}
    for response_uid in response_uid_list:
      response = self.cmd_response.GetResponse(response_uid)
      if not response:
        self._Print(
          'Invalid or missing response: Some output could not be displayed.',
          msgtype='warning')
        continue

      # If response includes an error then print that.
      if response.error:
        self._FormatErrorResponse(response)
        continue

      if self.display == 'raw':
        self._DisplayRaw(response, pipe=pipe)
        continue

      # Build a CliTable attribute filter from the response.
      filter_attr = {'Command': response.command,
                     'Hostname': response.device_name}

      device = self.devices[response.device_name]
      for attr in self.inventory.attributes:                                    # type: ignore
        # Some attributes are a list rather than a string, such as flags.
        # These are not supported by Clitable attribute matching
        # and we silently drop them here.
        if (not getattr(device, attr) or
            isinstance(getattr(device, attr), list)):
          continue

        # The filter index uses capitilised first letter for column names.
        # For some values we capitilise part of the value.
        if self.inventory.attributes[attr].display_case == 'title':             # type: ignore
          filter_attr[attr.title()] = getattr(device, attr).title()
        elif self.inventory.attributes[attr].display_case == 'upper':           # type: ignore
          filter_attr[attr.title()] = getattr(device, attr).upper()
        else:
          filter_attr[attr.title()] = getattr(device, attr)

      try:
        logging.debug('Parse response with attributes "%s".', filter_attr)
        if not self.filter_engine: raise(CliTableError)
        self.filter_engine.ParseCmd(
            response.data, attributes=filter_attr, verbose=self.verbose)
      except CliTableError as error_message:
        logging.debug('Parsing engine failed for device "%s".',
                      response.device_name)
        self._Print(error_message, msgtype='warning')
        # If unable to parse then output as raw.
        self._DisplayRaw(response, pipe=pipe)
        continue

      # Add host column to row, as single table may have
      # Multiple hosts with multiple rows each.
      self.filter_engine.AddColumn('Host', response.device_name, 0)

      # Is this the first line.
      if not result:
        # Print header line for this command response.
        self._Header(response.command)

      if str(self.filter_engine.header) not in result:
        # Copy initial command result, then append the rest as rows.
        # There will be a separate table for each unique set of table columns.
        result[str(self.filter_engine.header)] = copy.deepcopy(self.filter_engine)
      else:
        result[str(self.filter_engine.header)] += self.filter_engine

    for command_tbl in result:
      if FLAGS.sorted:
        result[command_tbl].sort()
      self._DisplayFormatted(result[command_tbl], pipe=pipe)

  def _Header(self, header: str = '', msgtype: str = 'title') -> None:
    """Formats header string."""
    self._Print(f'#!# {header} #!#', msgtype)

  def _InitInventory(self) -> None:
    """Inits inventory and triggers async load of device data."""

    try:
      self.inventory = inventory.Inventory()
      # Add additional command support for Inventory library.
      self.inventory.RegisterCommands(self.cli_parser)
      self.inventory.SetFiltersFromDefaults(self.cli_parser)
    except inventory.AuthError as error_message:
      self._Print(str(error_message), msgtype='warning')
      raise inventory.AuthError()

  def _ParseCommands(self, commands: str) -> None:
    """Parses commands and executes them.

    Splits commands on line boundary and forwards to either the:
      - TCLICmd the method for resolving TCLI commands.
      - CmdRequests the method for sending commands to the backend.

    Args:
      commands: String of newline separated commands.
    """

    def _Flush(devices, commands: list[str]) -> None:
      """Flush any pending device commands for the backend."""
      if not commands: return
      logging.debug('Flush commands: %s', commands)
      # Pass copy rather than reference to list.
      self._CmdRequests(devices, commands[:])
  
    # Split commands into list on newlines. Build new command_list.
    command_list = []
    for command in commands.split('\n'):
      command = command.strip()
      # Skip blank lines.
      if not command: continue

      # TCLI commands.
      if command.startswith(SLASH):
        _Flush(self.device_list, command_list)
        command_list = []
        # Remove command prefix and submit current command to TCLI interpreter.
        self._TCLICmd(command[1 :])
      else:
        # Backend commands for sending to devices.
        # Look for inline TCLI commands.
        (command_prefix, inline_commands
         ) = self.cli_parser.ExtractInlineCommands(command)
        if inline_commands:
          # Send any commands we have collecte so far.
          _Flush(self.device_list, command_list)
          command_list = []
          # Commands with inline display modifiers are submitted
          # to a copy of the  TCLI object with the inline modifiers applied.
          logging.debug('Inline Cmd: %s.', inline_commands)
          inline_tcli = copy.copy(self)
          inline_tcli.cli_parser.InlineOnly()
          # Apply the inline TCLI commands to this instance.
          for cmd in inline_commands:
            inline_tcli._TCLICmd(cmd)
          inline_tcli._CmdRequests(inline_tcli.device_list, [command_prefix])
        else:
          # Otherwise continue collecting multiple commands to send at once.
          command_list.append(command)

    _Flush(self.device_list, command_list)

  def _ParseRCFile(self) -> None:
    """Reads and execs the rc file.

      If present, it will be read into buffer 'startup', then
      'play'ed.

      A missing non-default file will raise an exception,
      but a missing default file will be silently ignored.

    Raises:
      EOFError: If unable to open the run command file.
    """

    if FLAGS.config_file.lower() != 'none':
      try:
        with open(FLAGS.config_file) as config_file:
          self.buffers.Append('startup', config_file.read())
        self._ParseCommands(self.buffers.GetBuffer('startup'))
      except IOError:
        # Silently fail if we don't find a file in the default location.
        # Warn the user if they supplied a file explicitly.
        if FLAGS.config_file != DEFAULT_CONFIGFILE:
          self._Print(
              'Error: Reading config file: %s' % sys.exc_info()[1],
              msgtype='warning')
          raise EOFError()

  def _Pipe(self, output: str, pipe: str = '') -> str|None:
    """Creates pipe for filtering command output."""

    if not pipe: return output
    pipe = pipe.lstrip('|')
    try:
      p = subprocess.Popen(
          [pipe], shell=True, close_fds=True,
          stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    except IOError as error_message:
      logging.error('IOerror opening pipe.')
      if str(error_message):
        self._Print(str(error_message), msgtype='warning')
      return

    try:
      result, _ = p.communicate(bytes(output, 'utf-8'))
      logging.debug('Output written to pipe:\n%s', output)
      logging.debug('Output read from pipe:\n%s', result)
      return result.decode('utf-8')
    except IOError:
      logging.error('IOerror writing/reading from pipe.')
      return

  def _Print(self, msg, msgtype='default') ->str|None:
    """Prints (and logs) outputs."""

    if not msg: return

    # Capture output in logs.
    for buf in (self.logall,):
      self.buffers.Append(buf, msg)
    
    self.dsp.printOut(msg, self.color, self.linewrap, msgtype)

  def _TCLICmd(self, line: str) -> None:
    f"""TCLI configuration command.

    Args:
      line: String command for TCLI parsing. Minus the {SLASH} escape prefix.

    Raises:
      EOFError: If exit is issued.
    """

    # Command parsing
    try:
      (command, args, append) = self.cli_parser.ParseCommandLine(line)
    except ParseError as error_message:
      self._Print(str(error_message), msgtype='warning')
      return

    # Command logging.
    # Don't log 'help' command and output.
    if command != 'help':
      # The command is valid so we can log it.
      for buf in (self.recordall, self.logall):
        # Don't log a logstop|recordstop' to a buffer as we stop logging.
        if command in ('recordstop', 'logstop') and args and args[0] == buf:
          continue
        # Add back the command prefix for the logs.
        self.buffers.Append(buf, SLASH + line)

    # Command execution.
    try:
      result = self.cli_parser.ExecHandler(command, args, append)
      if result: self._Print(result, msgtype='system')
    # pylint: disable=broad-except
    except ValueError as error_message:
      self._Print(str(error_message), msgtype='warning')

  ##############################################################################
  # Registered Commands.                                                       #
  ##############################################################################
  # All methods supplied to RegisterCommand have the identical parameters.
  # Args:
  #  command: str, name of command.
  #  args: list of commandline arguments, excluding any piping on rhs.
  #  append: bool, if command is to appeneded or replace current setting.
  #
  # pylint: disable=unused-argument

  def _CmdBuffer(
      self, command: str, args: list[str], append: bool=False) -> None:
    """"Displays buffer contents."""

    # Copy buffer to local var so we capture content before adding more here.
    try:
      buf = self.buffers.GetBuffer(args[0])
    except(AttributeError): 
      self._Print(f'Invalid buffer name "{args[0]}".', msgtype='warning')
      return

    # Because the output is bracketed by multiple _Print calls, we print here
    # rather than returning the output.
    self._Print(f'#! BUFFER {args[0]} !#', msgtype='warning')
    self._Print(buf, msgtype='system')
    self._Print('#! ENDBUFFER !#', msgtype='warning')

  def _CmdBufferList(
    self, command:str, args:list[str], append:bool=False) -> str:
    """List all buffers."""
    return self.buffers.ListBuffers()

  def _CmdClear(
      self, command: str, args: list[str], append: bool=False) -> None:
    """Clears content of the buffer."""
    self.buffers.Clear(args[0])

  def _CmdColorScheme(
    self, command:str, args:list[str], append:bool=False) -> str|None:
    """Sets ANSI color escape values."""

    if not args:
      return self.dsp.color_scheme
    
    scheme = args[0]
    self.dsp.setColorScheme(scheme)

  def _CmdCommand(self, command: str, args: list[str], append: bool) -> None:
    """Submit command to devices."""
    self._CmdRequests(self.device_list, [args[0]], True)

  def _CmdDefaults(
      self, command:str, args:list[str], append:bool=False) -> str|None:
    """Reset commands to the 'at start' value."""

    # Display rather than change.
    if not args: return self._CmdEnv(command, args, append)

    # Change everything
    default = args[0]
    if default == 'all':
      # Reapply explicit flags.
      command_register.SetFlagDefaults(self.cli_parser)
      if self.inventory:
        self.inventory.SetFiltersFromDefaults(self.cli_parser)
      return
  
    try:
      return self.cli_parser.ExecWithDefault(default)
    except Exception:
      raise ValueError("Cannot set '{default}' to defaults.")

  def _CmdDisplay(
    self, command:str, args:list[str], append:bool) -> str|None:
    """Set the layout format."""

    if not args:
      return f'Display: {self.display}'

    display_format = args[0]
    if display_format in DISPLAY_FORMATS:
      self.display = display_format
    else:
      raise ValueError(
          f"Unknown display '{repr(display_format)}'."
          f" Available displays are '{DISPLAY_FORMATS}'")

  def _CmdEnv(self, command: str, args: list[str], append: bool) -> str:
    """Display various environment variables."""

    inventory_str = ''
    if self.inventory:
      inventory_str = self.inventory.ShowEnv()

    return '\n'.join([
      f'Format: {self.display}, Filter: {self.filter}',
      f'Record: {self.record}, Recordall: {self.recordall}',
      f'Log: {self.log}, Logall: {self.logall}',
      f'Color: {self.color}, Scheme: {self.dsp.color_scheme}',
      f'Timeout: {self.timeout}, Verbose: {self.verbose}',
      f'CLI Mode: {self.mode}, Safemode: {self.safemode}',
      f'Line Wrap: {self.linewrap}\n{inventory_str}'
      ])

  def _CmdExecShell(
    self, command:str, args:list[str], append:bool) -> str:
    """Executes a shell command."""

    try:
      exec_out = os.popen(args[0])
      output = exec_out.read()
      exec_out.close()
    except IOError as error_message:
      raise ValueError(error_message)
    return output

  def _CmdEditor(self, command: str, args: list[str], append: bool) -> None:
    """Edits the named buffer content."""

    buf = args[0]
    buf_file: tempfile._TemporaryFileWrapper[bytes] = tempfile.NamedTemporaryFile()
    # Write out the buffer data to file.
    content: str = self.buffers.GetBuffer(buf)
    if content:
      buf_file.write(content.encode('ascii'))
      # Flush content so editor will see it.
      buf_file.flush()
    #TODO(#39): Support os.getenv('EDITOR', 'vi').
    #TODO(harro): Maybe catch exceptions here.
    # Open file with vi.
    os.system('vi -Z -n -u NONE -U NONE -- %s' % (buf_file.name))
    # Read back the data into the buffer.
    buf_file.seek(0)
    self.buffers.Clear(buf)
    self.buffers.Append(buf, buf_file.read().decode('ascii'))
    buf_file.close()

  def _CmdExit(
    self, command:str, args:list[str], append:bool=False) -> None:
    """Exit TCLI."""
    raise EOFError()

  def _CmdExpandTargets(
      self, command: str, args: list[str], append: bool) -> str:
    return ','.join(self.device_list)

  def _CmdFilter(
      self, command: str, args: list[str], append: bool) -> str|None:
    """Sets the clitable filter."""

    if not args: return 'Filter: %s' % self.filter

    filter_name = args[0]
    try:
      self.filter_engine = clitable.CliTable(filter_name, FLAGS.template_dir)
      self.filter = filter_name
    except (clitable.CliTableError, texttable.TableError, IOError):
      raise ValueError('Invalid filter %s.' % repr(filter_name))

  def _CmdHelp(self, command: str, args: list[str], append: bool) -> str:
    """Display help."""

    result: list[str] = []
    # Print the brief comment regarding escape commands.
    for cmd_name in sorted(self.cli_parser):
      cmd_obj = self.cli_parser[cmd_name]
      append_str = '[+]' if cmd_obj.append else ''
      arg = f' <{cmd_name}>' if cmd_obj.min_args else ''
      result.append(
        f'{cmd_name}{append_str}{arg} {cmd_obj.help_str}')
    return '\n\n'.join(result)

  def _CmdInventory(self, command: str, args: list[str], append: bool) -> str:
    """Displays devices in target list."""

    dlist = []
    for device_name in self.device_list:
      device = self.devices[device_name]
      attr_list = [device_name]
      for name in self.inventory.attributes:                                    # type: ignore
        if name == 'flags': continue
        if not getattr(device, name): continue
        attr_list.append(f'{name.title()}:{str(getattr(device, name)) or ""}')

      for fl in device.flags:
        attr_list.append(fl)

      dlist.append(', '.join(attr_list))
    return '\n'.join(dlist)

  def _CmdLogging(
      self, command: str, args: list[str], append: bool) -> str|None:
    """Activates one of the various logging functions."""

    # If no arg then display what buffer is currently active.
    if not args:
      buf_name = getattr(self, command)
      if not buf_name:
        buf_name = 'None'
      return f'{repr(command)} buffer is {repr(buf_name)}'

    buf = args[0]
    # In this we are appending but still need to check that we are not
    # already logging, or playing out from it.
    if self._BufferInUse(buf): return

    # Clear the buffer as we are not appending.
    if not append: self.buffers.Clear(buf)
    setattr(self, command, buf)

  def _CmdLogStop(
    self, command:str, args:list[str], append:bool=False) -> None:
    """Stop logging to a buffer."""

    for attr in ('record', 'recordall', 'log', 'logall'):
      if getattr(self, attr) == args[0]:
        setattr(self, attr, None)
        return

    raise ValueError('Buffer not in use for logging or recording.')

  def _CmdMode(
    self, command:str, args:list[str], append:bool) -> str|None:
    """Target CLI Mode to send to commands for."""

    if not args: return f'Mode: {self.mode}'

    mode = args[0]
    if mode not in MODE_FORMATS:
      raise ValueError(
        f"Unknown mode {repr(mode)}. Available modes are '{MODE_FORMATS}'")
    self.mode = mode

  def _CmdPlay(self, command: str, args: list[str], append: bool) -> None:
    """Plays out buffer contents to TCLI."""

    if self.playback is not None:
      raise ValueError('Recursive call of "play" rejected.')

    buf = args[0]
    # Do not allow playing out a buffer that is still being logged too.
    if not self._BufferInUse(buf):
      # Mark what buffer we are playing out from.
      self.playback = buf
      try:
        content = self.buffers.GetBuffer(buf)
        self._ParseCommands(content)
      except(AttributeError):
        self._Print(f"Nonexistent buffer: '{buf}'.", msgtype='warning')
      self.playback = None

  def _CmdRead(self, command: str, args: list[str], append: bool) -> str:
    """"Write buffer content to file."""

    buf = args[0]
    if len(args) > 1:
      filename = args[1]
    else:
      self._Print('Enter filename to read from: ', msgtype='system')
      filename = sys.stdin.readline().strip()
    filename = os.path.expanduser(os.path.expandvars(filename))

    try:
      buf_file = open(filename, 'r')
    except IOError as error_message:
      raise ValueError(str(error_message))

    if append:
      self.buffers.Clear(buf)

    self.buffers.Append(buf, buf_file.read())
    buf_file.close()
    return '%d lines read.' % self.buffers.GetBuffer(buf).count('\n')

  def _CmdTimeout(
      self, command: str, args: list[str], append: bool) -> str|None:
    """Sets or display the timeout setting."""

    if not args: return f'Timeout: {self.timeout}'

    try:
      timeout = int(args[0])
      if timeout > 0:
        self.timeout = int(args[0])
      else:
        raise ValueError
    except ValueError:
      raise ValueError('Invalid timeout value %s.' % repr(args[0]))

  def _CmdToggleValue(
      self, command: str, args: list[str], append: bool) -> None:
    """Commands that can 'toggle' their value."""

    if not args:
      # Toggle the current value if new value unspecified
      setattr(self, command, not getattr(self, command))
      return

    value = args[0].lower()
    if value not in ('on', 'true', 'off', 'false'):
      raise ValueError("Error: Argument must be 'on' or 'off'.")

    if value in ('on', 'true'): setattr(self, command, True)
    elif value in ('off', 'false'): setattr(self, command, False)

  #TODO(#40): Add flag to disable/block being able to write to file.
  def _CmdWrite(
      self, command: str, args: list[str], append: bool) -> str:
    """Writes out buffer content to file."""

    content = self.buffers.GetBuffer(args[0])
    if not content: raise ValueError('Buffer empty.')

    if len(args) > 1:
      filename = args[1]
    else:
      self._Print('Enter filename to write buffer to: ', msgtype='system')
      filename = sys.stdin.readline().strip()

    filename = os.path.expanduser(os.path.expandvars(filename))

    try:
      buf_file = open(filename, 'a') if append else open(filename, 'w')
      buf_file.writelines(content)
      buf_file.close()
    except IOError as error_message:
      raise ValueError(str(error_message))

    return '%d lines written.' % content.count('\n')
  
  # pylint: enable=unused-argument
  ##############################################################################
  # End of command handles.                                                    #
  ##############################################################################