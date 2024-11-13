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

TCLI is a frontend to TextFSM that adds interactive execution of commands on
multiple target devices and returns the results in one of several formats.

Type '%shelp' to get started. All TCLI commands are prefixed with a '%s'.
All other commands are forwarded to the target device/s for execution.

Pipes are supported locally in the client with '||' double piping.
  e.g. 'show inter terse | grep ge || wc -l'
Sends 'show inter terse | grep ge' to the targets and pipes the result
through 'wc -l' locally in the tcli client.

Inline commands are supported with '%s%s'.
  e.g 'show version %s%sdisplay csv %s%scolor on
Returns the output of the'show version' in csv format, with color still on,
regardless of what the global setting are. Global settings are not changed
by inline commands.

Commands can be passed to the client shell with '%s!' or '%sexec'.

The file '~/.tclirc' is executed at startup.

Exercise caution against 'overmatching' with your target and attribute filters.

Interactive TCLI starts in 'safe mode' - toggle off with '%sS' or '%ssafemode'.
"""

import copy
import os
import re
import subprocess
import sys
import tempfile
import threading
import typing

from absl import flags
from absl import logging
try:
  # For windows platform.
  from pyreadline3.rlmain import Readline
  readline = Readline()
except(ImportError):
  import readline
from tcli import command_parser
from tcli import command_register
from tcli import command_response
from tcli import text_buffer
from tcli.command_parser import ParseError
from tcli.tcli_textfsm import clitable
from tcli.tcli_textfsm.clitable import CliTableError
from textfsm import terminal
from textfsm import texttable
from textfsm.texttable import TableError

# Substitute import with appropriate inventory/device accessor library.
# The example library provided uses static CSV file for inventory and some
# canned output as example device responses. It serves as an example only.
## CHANGEME
##
from tcli import inventory_csv as inventory  #pylint: disable=g-bad-import-order

# Formats for displaying to the user.
DISPLAY_FORMATS = command_register.DISPLAY_FORMATS

# cli modes on the target device.
MODE_FORMATS = command_register.MODE_FORMATS

# Display color combinations.
COLOR_SCHEMES = command_register.COLOR_SCHEMES

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

# Prompt displays the target string, count of targets and if safe mode is on.
PROMPT_HDR = '#! <%s[%s]%s> !#'
PROMPT_STR = '#! '

# Colour mapping depending on colour scheme.
LIGHT_SYSTEM_COLOR = ['yellow']
LIGHT_WARNING_COLOR = ['red']
LIGHT_TITLE_COLOR = ['cyan']

DARK_SYSTEM_COLOR = ['bold', 'blue']
DARK_WARNING_COLOR = ['bold', 'red']
DARK_TITLE_COLOR = ['bold', 'magenta']

GROSS_SYSTEM_COLOR = ['bold', 'magenta', 'bg_cyan']
GROSS_WARNING_COLOR = ['bold', 'yellow', 'bg_magenta']
GROSS_TITLE_COLOR = ['bold', 'red', 'bg_green']

# Default path for config commands. Commands are run from this file at startup.
DEFAULT_CONFIGFILE = os.path.join(os.path.expanduser('~'), '.tclirc')

FLAGS = flags.FLAGS
I = command_parser.I

flags.DEFINE_string(
  'cmds', None,
  f'{I}Commands (newline separated) to send to devices in the target list.'
  f"{I}'Prompting' commands, commands that request further input from the"
  f'{I}user before completing are discouraged and will fail.\n'
  f'{I}Examples to avoid: telnet, ping, reload.', short_name='C')

flags.DEFINE_string(
  'config_file', DEFAULT_CONFIGFILE,
  f'{I}Configuration file to read. Lines in this file will be read into '
  f'{I}buffer "startup" and played.'
  f"{I}Skipped if file name is the string 'None|none'", short_name='R')

flags.DEFINE_boolean(
  'dry_run', False,
  f'{I}Display commands and targets, without submitting commands.')

flags.DEFINE_boolean(
  'interactive', False,
  f'{I}tcli runs in interactive mode. This is the default mode if no'
  ' cmds are supplied.\n', short_name='I')

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
    color_scheme: Whether to use 'dark' on light background or vice versa.
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
    prompt: String to display back to the user in interactive mode.
    record: String buffer name for where to record command input.
    recordall: Similar to 'record' but stores escape commands too.
    safemode: Boolean, control if raw commands are forwarded to targets or not.
    system_color: Color for system strings.
    targets: String of device names and regular expressions to match against.
    device_list: Sorted list of device names, the union of targets,
        excluding matches with xtargets. Read-only.
    title_color: Color for titles in standard strings.
    timeout: Integer, Duration (in seconds) to wait for outstanding commands
        responses to complete.
    verbose: Boolean, if to display all columns or suppress Verbose ones.
    warning_color: Color for warning strings.
    xtargets: String of device names and regular expressions to exclude.
  """

  def __init__(self):
    # Also see copy method when modifying/adding attributes.

    # Async callback.
    self._lock = threading.Lock()
    self._completer_list = []
    self.interactive = False
    self.filter_engine = None
    self.playback = None
    self.prompt: str|None = None
    self.safemode = False
    self.verbose = False
    # Attributes with defaults set by flags.
    self.color = True
    self.color_scheme: str|None = None
    self.display = None
    self.filter = None
    self.linewrap = False
    self.mode = 'cli'
    self.timeout = 0
    # Buffers
    self.log = self.logall = ''
    self.record = self.recordall = ''
    # Display values.
    self.system_color = self.title_color = self.warning_color = ''

    self.buffers = text_buffer.TextBuffer()
    self.cmd_response = command_response.CmdResponse()
    self.cli_parser = command_parser.CommandParser()
    if not hasattr(self, 'inventory'):
      self.inventory: inventory.Inventory|None = None

  def __copy__(self):
    """Copies attributes from self to new tcli child object."""

    # Inline escape commands are processed in a child object.
    tcli_obj = TCLI()

    # Copy by reference.
    # log and record to the same buffers.
    tcli_obj.buffers = self.buffers
    tcli_obj.filter_engine = self.filter_engine
    tcli_obj.cmd_response = self.cmd_response
    # Use the same client and device access for fetching results.
    tcli_obj.inventory = self.inventory

    tcli_obj.cli_parser = command_parser.CommandParser()
    # Only register base class commands, not the inventory.
    tcli_obj.RegisterCommands(tcli_obj.cli_parser)
    # Only support commands that are valid when called inline.
    tcli_obj.cli_parser.InlineOnly()

    # String values can also be copied by reference.
    # Assigning new value will not impact original in parent.
    tcli_obj.color = self.color
    tcli_obj.color_scheme = self.color_scheme
    tcli_obj.display = self.display
    tcli_obj.filter = self.filter
    tcli_obj.linewrap = self.linewrap
    tcli_obj.log = self.log
    tcli_obj.logall = self.logall
    tcli_obj.mode = self.mode
    tcli_obj.playback = self.playback
    tcli_obj.record = self.record
    tcli_obj.recordall = self.recordall
    tcli_obj.safemode = self.safemode
    tcli_obj.system_color = self.system_color
    tcli_obj.timeout = self.timeout
    tcli_obj.title_color = self.title_color
    tcli_obj.verbose = self.verbose
    tcli_obj.warning_color = self.warning_color

    return tcli_obj

  def Motd(self) ->None:
    """Display message of the day."""
    self._Print(MOTD, msgtype='system')

  def _SetFiltersFromDefaults(
      self, inv:inventory.Inventory) -> None:
    """Trawls filters and sets the matching commands via the cli_parser."""

    # Commands that may be specified in flags.
    for filter_name in inv.inclusions:
      try:
        self.cli_parser.ExecWithDefault(filter_name)
      except ValueError:
        pass
  
    for filter_name in inv.exclusions:
      try:
        self.cli_parser.ExecWithDefault(filter_name)
      except ValueError:
        pass

  def _SetPrompt(self, inv: inventory.Inventory) -> None:
    """Sets the prompt string with current targets."""

    safe = '*' if self.safemode else ''

    # Truncate prompt if too long to fit in terminal.
    (_, width) = terminal.TerminalSize()
    # Render, without replacing, the prompt to see if it will fit on a row.
    # Drop the target_str if that is not the case.
    if (len(PROMPT_HDR % (inv.targets, len(self.device_list), safe)) > width):
      target_str = '#####'
    else:
      target_str = inv.targets

    self.prompt = PROMPT_HDR % (
      terminal.AnsiText(target_str, self.system_color),
      terminal.AnsiText(len(self.device_list), self.warning_color),
      terminal.AnsiText(safe, self.title_color))

  def _InitInventory(self) -> None:
    """Inits inventory and triggers async load of device data."""

    try:
      self.inventory = inventory.Inventory()
      # Add additional command support for Inventory library.
      self.inventory.RegisterCommands(self.cli_parser)
    except inventory.AuthError as error_message:
      self._Print(str(error_message), msgtype='warning')
      raise inventory.AuthError()

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
        config_file = open(FLAGS.config_file)
        self.buffers.Append('startup', config_file.read())
        self.ParseCommands(self.buffers.GetBuffer('startup'))
      except IOError:
        # Silently fail if we don't find a file in the default location.
        # Warn the user if they supplied a file explicitly.
        if FLAGS.config_file != DEFAULT_CONFIGFILE:
          self._Print(
              'Error: Reading config file: %s' % sys.exc_info()[1],
              msgtype='warning')
          raise EOFError()

  def RegisterCommands(self, cli_parser:command_parser.CommandParser) ->None:
    """Register commands supported by TCLI core functions."""
    command_register.RegisterCommands(self, cli_parser, I)

  def StartUp(self, commands, interactive) ->None:
    """Runs rc file commands and initial startup tasks.

      The RC file may contain any valid TCLI commands including commands to send
      to devices. At the same time flags are a more specific priority than RC
      commands _IF_ set explicitly (non default).

      So we parse and set a bunch of flags early that a benigh (do not issue
      commands to devices or play out buffer content etc).
      Run the RC file, after which we re-appply explicitly set flags values.
    Args:
      commands: List of Strings, device commands to send at startup.
      interactive: Bool, are we running as an interactive CLI.

    Raises:
      EOFError: A non-default config_file could not be opened.
      inventory.AuthError: Inventory could not be retrieved due to permissions.
      TcliCmdError: Same buffer is target of several record/log commands.
    """

    # Determine if we are interactive or not.
    self.interactive = interactive
    if not commands:
      self.interactive = True
    if not self.inventory:
      self._InitInventory()
    self.RegisterCommands(self.cli_parser)
    if self.inventory:
      self._SetFiltersFromDefaults(self.inventory)
    # Set some markup flags early.
    self.SetDefaults()
    if self.interactive:
      # Set safe mode.
      self.cli_parser.ExecHandler('safemode', ['on'], False)
      # Apply user settings.
      self._ParseRCFile()
      # Reapply flag values that may have changed by RC commands.
      self.SetDefaults()
    if commands:
      self.ParseCommands(commands)

  def SetDefaults(self) ->None:
    """Parses command line flags ad sets default attributes.

      Commands here affect data representation/presentation but are otherwise
      harmless. Excuted both before and after any commands that may exist in a
      config file so that RC executed commands get the benefits without being
      able to override explicit flags.
    """

    # Calling the handlers directly will not be logged.
    for command_name in ('color', 'color_scheme', 'display', 'filter',
                         'linewrap', 'mode', 'timeout'):
      self.cli_parser.ExecWithDefault(command_name)

  # pylint: disable=unused-argument
  def Completer(self, word:str, state:int) -> str|None:
    """Command line completion used by readline library."""

    # Silently discard leading whitespace on cli.
    full_line = readline.get_line_buffer().lstrip() # type: ignore
    if full_line and full_line.startswith(SLASH):
      return self._TildeCompleter(full_line, state)
    return self._CmdCompleter(full_line, state)

  def _TildeCompleter(self, full_line:str, state:int) -> str|None:
    """Command line completion for escape commands."""

    # Pass subsequent arguments of a command to its completer.
    if ' ' in full_line:
      cmd = full_line[1:full_line.index(' ')]
      arg_string = full_line[full_line.index(' ') + 1 :]
      completer_list = []
      cmd_obj = self.cli_parser.GetCommand(cmd)
      if cmd_obj:
        for arg_options in cmd_obj.completer():
          if arg_options.startswith(arg_string):
            completer_list.append(arg_options)

      if state < len(completer_list):
        return completer_list[state]
      return None

    # First word, a TCLI command word.
    completer_list = []
    for cmd in self.cli_parser:
      # Strip TILDE and compare.
      if cmd.startswith(full_line[1 :]):
        completer_list.append(cmd)
        cmd_obj = self.cli_parser.GetCommand(cmd)
        if cmd_obj and cmd_obj.append:
          completer_list.append(cmd + command_parser.APPEND)
    completer_list.sort()

    if state < len(completer_list):
      # Re-apply TILDE to completion.
      return SLASH + completer_list[state]
    return None

  def _CmdCompleter(self, full_line:str, state:int) -> str|None:
    """Commandline completion used by readline library."""

    # First invocation, so build candidate list and cache for re-use.
    if state == 0:
      self._completer_list = []
      current_word = ''
      line_tokens = []
      word_boundary = False
      self._completer_list = []
      # What has been typed so far.

      # Collapse quotes to remove any whitespace within.
      cleaned_line = re.sub(r'\".+\"', '""', full_line)
      cleaned_line = re.sub(r'\'.+\'', '""', cleaned_line)
      # Remove double spaces etc
      cleaned_line = re.sub(r'\s+', ' ', cleaned_line)

      # Are we part way through typing a word or not.
      if cleaned_line and cleaned_line.endswith(' '):
        word_boundary = True

      cleaned_line = cleaned_line.rstrip()
      # If blank line then this is also a word boundary.
      if not cleaned_line:
        word_boundary = True
      else:
        # Split into word tokens.
        line_tokens = cleaned_line.split(' ')
        # If partially through typing a word then don't include it as a token.
        if not word_boundary and line_tokens:
          current_word = line_tokens.pop()

      # Compare with table of possible commands
      if self.filter_engine:
        for row in self.filter_engine.index.index:
          # Split the regexp into tokens, re combine only as many as there are
          # in the line entered so far.
          cmd_tokens = row['Command'].split(' ')
          # Does the line match the partial list of tokens.
          if (line_tokens and
              re.match(' '.join(cmd_tokens[:len(line_tokens)]), cleaned_line)):
            # Take token not from end of regexp, but from the Completer command.
            token = cmd_tokens[len(line_tokens)]
          elif not line_tokens:
            # Currently a blank line so the first token is what we want.
            token = cmd_tokens[0]
          else:
            continue
          # We have found a match.
          # Remove completer syntax.
          token = re.sub(r'\(|\)\?', '', token)
          # If on word boundary or our current word is a partial match.
          if word_boundary or token.startswith(current_word):
            if token not in self._completer_list:
              self._completer_list.append(token)

    try:
      return self._completer_list[state]
    except IndexError:
      return None

  def ParseCommands(self, commands:str) -> None:
    """Parses commands and executes them.

    Splits commands on line boundary and forwards to either the:
      - TildeCmd the method for resolving TCLI commands.
      - CmdRequests the method for sending commands to the backend.

    Args:
      commands: String of newline separated commands.
    """

    def _FlushCommands(command_list:list[str]) -> None:
      """Submit commands and clear list."""

      if command_list:
        # Flush all accumulated commands beforehand.
        # This is necessary so that recording and logging are correct.
        logging.debug('Flush commands: %s', command_list)
        # Pass copy rather than reference to list.
        self.CmdRequests(self.device_list, command_list[:])
        # Ensure list is deleted.
        command_list[:] = []

    # Split commands into list on newlines. Build new command_list.
    command_list = []
    for command in commands.split('\n'):
      command = command.strip()
      # Skip blank lines.
      if not command:
        continue

      # TCLI commands.
      if command.startswith(SLASH):
        _FlushCommands(command_list)
        # Remove command prefix and submit to TCLI command interpreter.
        self.TildeCmd(command[1 :])
      else:
        # Backend commands.
        # Look for inline commands.
        (command_prefix, inline_commands
         ) = self.cli_parser.ExtractInlineCommands(command)
        if inline_commands:
          # Send any commands we have collecte so far.
          _FlushCommands(command_list)
          # Commands with inline display modifiers are submitted
          # to a copy of the  TCLI object with the inline modifiers applied.
          logging.debug('Inline Cmd: %s.', inline_commands)
          inline_tcli = copy.copy(self)
          for cmd in inline_commands:
            inline_tcli.TildeCmd(cmd)
          inline_tcli.ParseCommands(command_prefix)
        else:
          # Otherwise continue collecting multiple commands to send at once.
          command_list.append(command)

    _FlushCommands(command_list)

  def Callback(self, response:inventory.CmdResponse) -> None:
    """Async callback for device command."""

    with self._lock:
      logging.debug("Callback for '%s'.", response.uid)
      # Convert from inventory specific format to a more generic dictionary.
      self.cmd_response.AddResponse(response)

      # If we have all responses for current row/command then display.
      row = self.cmd_response.GetRow()
      while row:
        self._FormatResponse(row[0], row[1])
        row = self.cmd_response.GetRow()

  def CmdRequests(
    self, device_list:list[str], command_list:list[str], explicit_cmd:bool=False
    ) -> None:
    """Submits command list to devices and receives responses.

    Args:
      device_list: List of strings, each string being a devicename
      command_list: List of strings, each string is a command to execute
      explicit_cmd: Bool, if commands submitted via '/command' or not
    """

    for buf in (self.record, self.recordall, self.log, self.logall):
      self.buffers.Append(buf, '\n'.join(command_list))

    if not device_list or not command_list or not self.inventory:
      # Nothing to do.
      return

    if not explicit_cmd and self.safemode:
      self._Print('Safe mode on, command ignored.')
      return

    if FLAGS.dry_run:
      # Batch mode with dry_run set, then show what commands and devices would
      # have been sent and return.
      self._Print('Send Commands: ', msgtype='title')
      self._Print('  ' + '\r  '.join(command_list))
      self._Print('To Targets: ', msgtype='title')
      self._Print('  ' + ','.join(device_list))
      return

    # Response requests.
    requests = []
    self.cmd_response = command_response.CmdResponse()
    # Responses from hosts for a single command are known as a 'row'.
    for cmd_row, command in enumerate(command_list):
      # Split off client side pipe command.
      (command, pipe) = self.cli_parser.ExtractPipe(command)
      logging.debug("Extracted command and pipe: '%s' & '%s'.", command, pipe)
      self.cmd_response.SetCommandRow(cmd_row, pipe)

      # Create command requests.
      for host in device_list:
        req = self.inventory.CmdRequest(host, command, self.mode)
        # Track the order that commands are submitted.
        # Responses are received in any order and
        # we use the row ID to reassemble.
        logging.debug('UID: %s.', req.uid)
        self.cmd_response.SetRequest(cmd_row, req.uid)
        requests.append(req)

    # Submit command request to inventory manager for each host.
    try:
      requests_callbacks = [(req, self.Callback) for req in requests]
    except AttributeError as error_message:
      logging.error('Submitting the requests caused an AttributeError: %s.',
                    error_message)
    # Setup progress indicator.
    self.cmd_response.StartIndicator()
    self.inventory.SendRequests(requests_callbacks, deadline=self.timeout)

    # Wait for all callbacks to complete.
    # We add a 5 seconds pad to allow requests to timeout and be added to the
    # results before cleaning up any outstanding entries and reporting results
    if not self.cmd_response.done.wait(self.timeout +5):
      # If we timeout then clear pending responses.
      self.cmd_response = command_response.CmdResponse()
      self._Print('Timeout: timer exceeded while waiting for responses.',
                  msgtype='warning')
    logging.debug('CmdRequests: All callbacks completed.')

  def TildeCmd(self, line:str) -> None:
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
        # Prefix tilde back onto logs.
        self.buffers.Append(buf, SLASH + line)

    # Command execution.
    try:
      result = self.cli_parser.ExecHandler(command, args, append)
      if result: self._Print(result, msgtype='system')
    # pylint: disable=broad-except
    except ValueError as error_message:
      self._Print(str(error_message), msgtype='warning')

  def _FormatRaw(self, response:inventory.CmdResponse, pipe:str='') -> None:
    """Display response in raw format."""

    # Do nothing with raw output other than tagging
    # Which device/command generated it.
    self._Print(
      '#!# %s:%s #!#' % (response.device_name, response.command),
      msgtype='title')
    self._Print(self._Pipe(response.data, pipe=pipe))

  def _FormatErrorResponse(self, response:inventory.CmdResponse) -> None:
    """Formatted error derived from response."""

    self._Print('#!# %s:%s #!#\n%s' %
      (response.device_name, response.command, response.error),
      msgtype='warning')

  def _FormatResponse(self, response_uid_list:list[int], pipe:str='') -> None:
    """Display the results from a list of responses."""

    # Filter required if display format is not 'raw'.
    if self.display != 'raw' and not self.filter:
      self._Print(
        'No filter set, cannot display in %s format' % repr(self.display),
        msgtype='warning')
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
        self._FormatRaw(response, pipe=pipe)
        continue

      # Build a CliTable attribute filter from the response.
      filter_attr = {'Command': response.command,
                     'Hostname': response.device_name}

      device = self.devices[response.device_name]
      # TODO(harro): Referencing DEVICE_ATTRIBUTES directly should be avoided.
      for attr in inventory.DEVICE_ATTRIBUTES:

        # Some attributes are a list rather than a string, such as flags.
        # These are not supported by Clitable attribute matching
        # and we silently drop them here.
        if (not getattr(device, attr) or
            isinstance(getattr(device, attr), list)):
          continue

        # The filter index uses capitilised first letter for column names.
        # For some values we capitilise part of the value.
        if inventory.DEVICE_ATTRIBUTES[attr].display_case == 'title':
          filter_attr[attr.title()] = getattr(device, attr).title()
        elif inventory.DEVICE_ATTRIBUTES[attr].display_case == 'upper':
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
        self._FormatRaw(response, pipe=pipe)
        continue

      # Add host column to row, as single table may have
      # Multiple hosts with multiple rows each.
      self.filter_engine.AddColumn('Host', response.device_name, 0)

      # Is this the first line.
      if not result:
        # Print header line for this command response.
        self._Print('#!# %s #!#' % response.command, msgtype='title')

      if str(self.filter_engine.header) not in result:
        # Copy initial command result, then append the rest as rows.
        # There will be a separate table for each unique set of table columns.
        result[str(self.filter_engine.header)] = copy.deepcopy(self.filter_engine)
      else:
        result[str(self.filter_engine.header)] += self.filter_engine

    for command_tbl in result:
      if FLAGS.sorted:
        result[command_tbl].sort()
      self._DisplayTable(result[command_tbl], pipe=pipe)

  def _DisplayTable(self, result:clitable.CliTable, pipe:str='') -> None:
    """Displays output in tabular form."""

    if self.display == 'csv':
      self._Print(self._Pipe(str(result), pipe=pipe))

    elif self.display == 'nvp':
      # 'Host' is added to the LABEL prefix.
      result.AddKeys(['Host'])
      self._Print(self._Pipe(result.LabelValueTable(), pipe=pipe))

    elif self.display == 'tbl':
      (_, width) = terminal.TerminalSize()
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

  def _Pipe(self, output:str, pipe:str='') -> str|None:
    """Creates pipe for filtering command output."""

    if not pipe:
      return output

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

  def Prompt(self) -> None:
    """Present prompt for further input."""

    # Clear response dictionary to ignore outstanding requests.
    self.cmd_response = command_response.CmdResponse()
    if self.inventory:
      self._SetPrompt(self.inventory)
    # Print the main prompt, so the ASCII escape sequences work.
    print(self.prompt)
    # Stripped ASCII escape from here, as they are not interpreted in PY3.
    self.ParseCommands(input(PROMPT_STR))

  def _BufferInUse(self, buffername:str) -> bool:
    """Check if buffer is already being written to."""

    if buffername in (self.record, self.recordall, self.log, self.logall):
      self._Print('Buffer: %s, already open for writing.' %
                  repr(buffername), msgtype='warning')
      return True

    if buffername == self.playback:
      self._Print("Buffer: %s, already open by 'play' command." %
                  self.playback, msgtype='warning')
      return True

    return False

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

  def _CmdBuffer(self, command:str, args:list[str], append:bool=False) -> None:
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

  def _CmdClear(self, command:str, args:list[str], append:bool=False) -> None:
    """Clears content of the buffer."""
    self.buffers.Clear(args[0])

  def _CmdColorScheme(
    self, command:str, args:list[str], append:bool=False) -> str|None:
    """Sets ANSI color escape values."""

    if not args:
      return self.color_scheme
    
    scheme = args[0]
    if scheme not in COLOR_SCHEMES:
      raise ValueError(f"Error: Unknown color scheme: '{scheme}'")

    self.color_scheme = scheme
    if not self.color:
      # If we're not displaying colour, then clear the values.
      self.system_color = self.warning_color = self.title_color = ''
      return

    if scheme == 'light':
      self.system_color = LIGHT_SYSTEM_COLOR
      self.warning_color = LIGHT_WARNING_COLOR
      self.title_color = LIGHT_TITLE_COLOR
    elif scheme == 'dark':
      self.system_color = DARK_SYSTEM_COLOR
      self.warning_color = DARK_WARNING_COLOR
      self.title_color = DARK_TITLE_COLOR
    elif scheme == 'gross':
      self.system_color = GROSS_SYSTEM_COLOR
      self.warning_color = GROSS_WARNING_COLOR
      self.title_color = GROSS_TITLE_COLOR

  def _CmdCommand(self, command:str, args:list[str], append:bool) -> None:
    """Submit command to devices."""
    self.CmdRequests(self.device_list, [args[0]], True)

  def _CmdDefaults(
      self, command:str, args:list[str], append:bool=False) -> str|None:
    """Reset commands to the 'at start' value."""

    # Display rather than change.
    if not args: return self._CmdEnv(command, args, append)

    # Change everything
    default = args[0]
    if default == 'all':
      # Reapply explicit flags.
      # TODO(harro): Only sets some core values (with flags), could reset more?
      self.SetDefaults()
      if self.inventory:
        self._SetFiltersFromDefaults(self.inventory)
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

  def _CmdEnv(self, command:str, args:list[str], append:bool) -> str:
    """Display various environment variables."""

    if self.inventory:
      inventory_str = self.inventory.ShowEnv()

    return '\n'.join([
      f'Display: {self.display}, Filter: {self.filter}',
      f'Record: {self.record}, Recordall: {self.recordall}',
      f'Log: {self.log}, Logall: {self.logall}',
      f'Color: {self.color}, Scheme: {self.color_scheme}',
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

  def _CmdEditor(self, command:str, args:list[str], append:bool) -> None:
    """Edits the named buffer content."""

    buf = args[0]
    buf_file: tempfile._TemporaryFileWrapper[bytes] = tempfile.NamedTemporaryFile()
    # Write out the buffer data to file.
    content: str = self.buffers.GetBuffer(buf)
    if content:
      buf_file.write(content.encode('ascii'))
      # Flush content so editor will see it.
      buf_file.flush()
    #TODO(harro): Support os.getenv('EDITOR', 'vi').
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

  def _CmdExpandTargets(self, command:str, args:list[str], append:bool) -> str:
    return ','.join(self.device_list)

  def _CmdFilter(
    self, command:str, args:list[str], append:bool) -> str|None:
    """Sets the clitable filter."""

    if not args: return 'Filter: %s' % self.filter

    filter_name = args[0]
    try:
      self.filter_engine = clitable.CliTable(filter_name, FLAGS.template_dir)
      self.filter = filter_name
    except (clitable.CliTableError, texttable.TableError, IOError):
      raise ValueError('Invalid filter %s.' % repr(filter_name))

  def _CmdHelp(self, command:str, args:list[str], append:bool):
    """Display help."""

    result: list[str] = []
    # Print the brief comment regarding escape commands.
    for cmd in sorted(self.cli_parser):
      cmd_obj: typing.Any|None = self.cli_parser.GetCommand(cmd)
      if not cmd_obj: continue
      append_str = '[+]' if cmd_obj.append else ''
      arg = ''
      if cmd_obj.min_args:
        arg = f' <{cmd}>'
      result.append(
        f'{cmd}{append_str}{arg}{cmd_obj.help_str}\n\n')
    return ''.join(result)

  def _CmdInventory(self, command:str, args:list[str], append:bool) -> str:
    """Displays devices in target list."""

    dlist = []
    for device_name in self.device_list:
      device = self.devices[device_name]
      attr_list = [device_name]
      # TODO(harro): Shouldn't need to call DEVICE_ATTRIBUTES directly.
      for name in inventory.DEVICE_ATTRIBUTES:
        if name == 'flags': continue
        if not getattr(device, name): continue
        attr_list.append(f'{name.title()}:{str(getattr(device, name)) or ''}')

      for fl in device.flags:
        attr_list.append(fl)

      dlist.append(', '.join(attr_list))
    return '\n'.join(dlist)

  def _CmdLogging(self, command:str, args:list[str], append:bool) -> str|None:
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

  def _CmdPlay(self, command:str, args:list[str], append:bool) -> None:
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
        self.ParseCommands(content)
      except(AttributeError):
        self._Print(f"Nonexistent buffer: '{buf}'.", msgtype='warning')
      self.playback = None

  def _CmdRead(self, command:str, args:list[str], append:bool) -> str:
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
    return f"{self.buffers.GetBuffer(buf).count('\n')} lines read."

  def _CmdTimeout(self, command:str, args:list[str], append:bool) -> str|None:
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

  #TODO(harro): Add flag to disable being able to write to file.
  def _CmdWrite(
    self, command:str, args:list[str], append:bool) -> str:
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

    return f"{content.count('\n')} lines written."

  def _CmdToggleValue(self, command:str, args:list[str], append:bool) -> None:
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

  # pylint: enable=unused-argument
  ##############################################################################
  # End of command handles.                                                    #
  ##############################################################################

  def _Print(self, msg, msgtype='default') ->str|None:
    """Prints (and logs) outputs."""

    if not msg: return

    # Capture output in logs.
    for buf in (self.logall,):
      self.buffers.Append(buf, msg)

    # Format for width of display.
    if self.linewrap: msg = terminal.LineWrap(msg)
    # Colourise depending on nature of message.
    if self.color:
      msg_color = f'{msgtype}_color'
      if hasattr(self, msg_color) and type(getattr(self, msg_color) is str):
        msg = terminal.AnsiText(msg, getattr(self, msg_color))
    # Warnings go to stderr.
    if msgtype == 'warning':
      print(msg, file=sys.stderr)
    else:
      print(msg)

  devices = property(lambda self: self.inventory.devices)
  device_list = property(lambda self: self.inventory.device_list)
