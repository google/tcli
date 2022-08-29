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

"""TCLI - Accesses CLI of network devices.

TCLI is a frontend to TextFSM that supports batch or interactive execution of
commands on multiple target devices and returns the results in one of several
formats.

Type '%shelp' to get started. All TCLI commands are prefixed with a '%s'.
All other commands are forwarded to the target device/s for execution.

Pipes are supported locally in the client with '||' double piping.
  e.g. 'show inter terse | grep ge || wc -l'
Sends 'show inter terse | grep ge' to the targets and pipes the result
through 'wc -l' locally in the tcli client.

Inline commands are supported with '%s%s'.
  e.g 'show version %s%sdisplay csv %s%scolor on
Returns the output of the'show version' in csv format and with color
regardless of what the global setting are. Global settings are not changed
by inline commands.

Commands can be passed through to the shell with '%s!' or '%sexec'.

The file '~/.tclirc' is executed at startup by TCLI.

TCLI can be run interactively or in batch mode.

Starts in 'safe mode' when run interactively, toggle with '%sS' or '%ssafemode'.
"""


from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import copy
import os
import re
import readline
import subprocess
import sys
import tempfile
import threading

from absl import flags
from absl import logging
from tcli import command_parser
from tcli import command_response
from tcli import text_buffer
from tcli.command_parser import ParseError
from tcli.tcli_textfsm import clitable
from tcli.tcli_textfsm.clitable import CliTableError
from textfsm import terminal
from textfsm import texttable
from textfsm.texttable import TableError

# Substitute import with appropriate inventory/device accessor library.
# The example library provided uses static CSV file for inventory and canned
# output for device responses. It serves as an example only.
## CHANGEME
##
from tcli import inventory_csv as inventory  # pylint: disable=g-bad-import-order

DISPLAY_FORMATS = ['raw', 'csv', 'tbl', 'nvp']

MODE_FORMATS = ['cli', 'gated', 'http', 'shell']

# known as tilde for historic reasons.
TILDE = '/'
__doc__ = __doc__.replace('%s', TILDE)    # pylint: disable=redefined-builtin

# Banner message to display at program start.
MOTD = '#!' + '#' * 76 + '!#' + """
#! TCLI - Tokenized Command Line Interface
#! Note: Beta code, use with caution.
#!
#! Type '%shelp' to get started.
#! To disable color: '%scolor off'.
#!
#! For more guidance see:
#! https://github.com/google/tcli
#!
#! Note:
#! Interactive TCLI starts in safe mode (indicated by '*' in the prompt).
#! To disable safe mode: '%ssafemode off'.
#!
#! Have a nice day!
#!""".replace('%s', TILDE) + '#' * 76 + '!#'

# Text displayed by online help.
# The keys are the list of permissable escape commands.
TILDE_COMMAND_HELP = {
    'buffer': '\n    Show contents of buffer.',
    'bufferlist':
        '\n    Show buffers currently in use (written to and not cleared).',
    'clear': '\n    Deletes contents of named buffer.',
    'color': '\n    Toggle color support.',
    'color_scheme':
        "\n    Use 'light' scheme on dark background or 'dark' otherwise.",
    'command':
        "\n    Submit command to target device's. Safe mode enforces use of "
        "\n    'command' for sending input to targets."
        "\n    Shortname: 'C'.",
    'defaults':
        '\n    Returns environment to startup/factory defaults.'
        '\n    Supply argument to set a specific value back to default,'
        "\n    or 'all' to return everything to the defaults.",
    'display':
        '\n    Extensible set of routines used for formatting command output.'
        '\n    Available display formats are: %s'
        "\n    Shortname: 'D'." % DISPLAY_FORMATS,
    'env': '\n    Display current escape command settings.',
    'exec': '\n    Execute command in shell.'
            "\n    Shortname: '!'.",
    'exit': '\n    Exit tcli.',
    'expandtargets':
        "\n    Displays the expanded list of devices matched by 'targets' and"
        "\n    not matched by 'xtargets'.",
    'filter':
        '\n    File name that maps templates for extracting data from output.'
        "\n    Is disabled if display is in 'raw' mode."
        "\n    Shortname: 'F'.",
    'help': '\n    Display escape command online help.',
    'inventory':
        '\n    Displays attributes of matched targets.'
        "\n    Shortname: 'V'.",
    'linewrap': '\n    Set line wrap for displayed data.',
    'log':
        '\n    Record commands and device output to buffer.'
        '\n    Does not include escape commands or output from these commands.',
    'logall':
        '\n    Record both commands and escape commands and output to buffer.',
    'logstop':
        '\n    Stop recording or logging to named buffer (same as '
        "'recordstop').",
    'mode':
        '\n    CLI mode for command.'
        '\n    Available command modes are: %s.'
        "\n    Shortname: 'M'." % MODE_FORMATS,
    'quit': '\n    Exit by another name.',
    'read':
        '\n    Read contents of file and store in buffer.'
        '\n    File name is specified at a subsequent prompt.',
    'record':
        '\n    Record commands to named <buffer>.'
        '\n    If command is appended with {APPEND} then append to buffer.',
    'recordall':
        '\n    Record commands and escape commands to named <buffer>.'
        '\n    If command is appended with {APPEND} then append to buffer.',
    'recordstop':
        "\n    Stop recording or logging to named buffer (same as 'logstop').",
    'safemode':
        "\n    Do not forward input to 'targets' unless using 'command'."
        "\n    Shortname: 'S'.",
    'timeout':
        '\n    Period (in seconds) to wait for outstanding command responses.',
    'play':
        '\n    Play out recorded keystrokes from named buffer to target '
        "device/s.\n    Shortname: 'P'.",
    'write':
        '\n    Dumps contents of buffer to file.'
        '\n    File name is specified at a subsequent prompt.',
    'verbose': '\n    Display extra data columns in output (for csv mode).',
    'vi': '\n    Opens buffer in vi editor.',
}

# Prompt displays the target string, count of targets and if safe mode is on.
PROMPT_HDR = '#! <%s[%s]%s> !#'
PROMPT_STR = '#! '

# Colour values.
COLOR_SCHEMES = ['light', 'dark', 'gross']

LIGHT_SYSTEM_COLOR = ['yellow']
LIGHT_WARNING_COLOR = ['red']
LIGHT_TITLE_COLOR = ['cyan']

DARK_SYSTEM_COLOR = ['bold', 'blue']
DARK_WARNING_COLOR = ['bold', 'red']
DARK_TITLE_COLOR = ['bold', 'magenta']

GROSS_SYSTEM_COLOR = ['bold', 'magenta', 'bg_cyan']
GROSS_WARNING_COLOR = ['bold', 'yellow', 'bg_magenta']
GROSS_TITLE_COLOR = ['bold', 'red', 'bg_green']

# Flag defaults.
DEFAULT_CMDS = {
    'color': True,
    'color_scheme': 'light',
    'display': 'raw',
    'filter': 'default_index',
    'linewrap': False,
    'mode': 'cli',
    'timeout': 45
}
# Run commands default location. Commands are run from this file at startup.
try:
  DEFAULT_CONFIGFILE = os.path.join(os.environ.get('HOME'), '.tclirc')
except (AttributeError, TypeError):
  DEFAULT_CONFIGFILE = 'none'

FLAGS = flags.FLAGS
flags.DEFINE_string('template_dir',
                    os.path.join(
                        os.path.dirname(__file__),
                        'testdata'),
                    '\n    Path where command templates are located',
                    short_name='t')

flags.DEFINE_boolean(
    'interactive', False,
    '\n    tcli runs in interactive mode. This is the default mode if no'
    ' cmds are supplied.\n',
    short_name='I')

flags.DEFINE_boolean(
    'color', DEFAULT_CMDS['color'],
    '\n    Use color when displaying results.')

flags.DEFINE_enum(
    'color_scheme', DEFAULT_CMDS['color_scheme'], COLOR_SCHEMES,
    TILDE_COMMAND_HELP['color_scheme'])

flags.DEFINE_boolean(
    'dry_run', False,
    '\n    Display commands and targets, without submitting commands.')

flags.DEFINE_boolean(
    'linewrap', DEFAULT_CMDS['linewrap'],
    '\n    Override default line wrap behavior.')

flags.DEFINE_string(
    'cmds', None,
    '\n    Commands (newline separated) to send to devices in the target list.'
    "'Prompting' commands, commands that request further input from the"
    ' user before completing are discouraged and will fail.\n'
    'Examples to avoid: telnet, ping, reload.',
    short_name='C')

flags.DEFINE_string(
    'config_file', DEFAULT_CONFIGFILE,
    '\n    Configuration file to read. Lines in this file will be read into '
    '\n    buffer "startup" and played.'
    "\n    Skipped if file name is the string 'None|none'",
    short_name='R')

flags.DEFINE_enum(
    'display', DEFAULT_CMDS['display'], DISPLAY_FORMATS,
    TILDE_COMMAND_HELP['display'],
    short_name='D')

flags.DEFINE_enum(
    'mode', DEFAULT_CMDS['mode'], MODE_FORMATS,
    TILDE_COMMAND_HELP['mode'],
    short_name='M')

flags.DEFINE_enum(
    'filter', DEFAULT_CMDS['filter'], ['default_index', ''],
    TILDE_COMMAND_HELP['filter'],
    short_name='F')

flags.DEFINE_integer(
    'timeout', DEFAULT_CMDS['timeout'],
    TILDE_COMMAND_HELP['timeout'],
    short_name='O')

flags.DEFINE_boolean('sorted', False, 'Sort device entries in output.')


class Error(Exception):
  """Base class for errors."""


# pylint: disable=g-bad-exception-name
class TcliError(Error):
  """General TCLI error."""
# pylint: enable=g-bad-exception-name


class TcliCmdError(Error):
  """Error in command arguments or argument parsing."""


class TCLI(object):
  """TCLI - A Grouping Network Command-Line Interface.

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
    self.pipe = None
    self.playback = None
    self.prompt = None
    self.safemode = False
    self.verbose = False
    # Attributes with defaults set by flags.
    self.color = None
    self.color_scheme = None
    self.display = None
    self.filter = None
    self.linewrap = None
    self.mode = None
    self.timeout = None
    # Buffers
    self.log = None
    self.logall = None
    self.record = None
    self.recordall = None
    # Display values.
    self.system_color = ''
    self.title_color = ''
    self.warning_color = ''

    self.buffers = text_buffer.TextBuffer()
    self.cmd_response = command_response.CmdResponse()
    self.cli_parser = command_parser.CommandParser()
    if not hasattr(self, 'inventory'):
      self.inventory = None

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
    tcli_obj.pipe = self.pipe
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

  def Motd(self):
    """Display message of the day."""
    self._PrintSystem(MOTD)

  def _SetFiltersFromDefaults(self):
    """Trawls the filters and sets to the matching flags value."""

    # Commands that may be specified in flags.
    # pylint: disable=protected-access
    for filter_name in self.inventory._filters:
      try:
        self.cli_parser.ExecWithDefault(filter_name)
      except ValueError:
        pass
    for filter_name in self.inventory._exclusions:
      try:
        self.cli_parser.ExecWithDefault(filter_name)
      except ValueError:
        pass

  def _SetPrompt(self):
    """Sets the prompt string with current targets."""

    if self.safemode:
      safe = '*'
    else:
      safe = ''

    # Truncate prompt if too long to fit in terminal.
    (_, width) = terminal.TerminalSize()
    if (len(PROMPT_HDR % (
        self.inventory.targets,
        len(self.device_list), safe)) > width):
      target_str = '#####'
    else:
      target_str = self.inventory.targets

    self.prompt = PROMPT_HDR % (
        terminal.AnsiText(target_str, self.system_color),
        terminal.AnsiText(len(self.device_list), self.warning_color),
        terminal.AnsiText(safe, self.title_color))

  def _InitInventory(self):
    """Inits inventory and triggers async load of device data."""

    try:
      self.inventory = inventory.Inventory(batch=not self.interactive)
      # Add additional command support for Inventory library.
      self.inventory.RegisterCommands(self.cli_parser)
    except inventory.AuthError as error_message:
      self._PrintWarning(str(error_message))
      raise inventory.AuthError()

  def _ParseRCFile(self):
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
          self._PrintWarning(
              'Error: Reading config file: %s' % sys.exc_info()[1])
          raise EOFError()

  def RegisterCommands(self, cli_parser):
    """Register commands supported by TCLI core functions."""

    cli_parser.RegisterCommand(
        'buffer', TILDE_COMMAND_HELP['buffer'], min_args=1,
        handler=self._CmdBuffer)
    cli_parser.RegisterCommand(
        'bufferlist', TILDE_COMMAND_HELP['bufferlist'], max_args=0,
        handler=self._CmdBufferList)
    cli_parser.RegisterCommand(
        'clear', TILDE_COMMAND_HELP['clear'], min_args=1,
        handler=self._CmdClear)
    cli_parser.RegisterCommand(
        'color', TILDE_COMMAND_HELP['color'], inline=True, toggle=True,
        default_value=FLAGS.color, handler=self._CmdToggleValue,
        completer=lambda: ['on', 'off'])
    cli_parser.RegisterCommand(
        'color_scheme', TILDE_COMMAND_HELP['color_scheme'],
        inline=True, default_value=FLAGS.color_scheme,
        handler=self._CmdColorScheme, completer=lambda: COLOR_SCHEMES)
    cli_parser.RegisterCommand(
        'command', TILDE_COMMAND_HELP['command'], short_name='C', min_args=1,
        raw_arg=True, handler=self._CmdCommand)
    cli_parser.RegisterCommand(
        'defaults', TILDE_COMMAND_HELP['defaults'], handler=self._CmdDefaults)
    cli_parser.RegisterCommand(
        'display', TILDE_COMMAND_HELP['display'], short_name='D', inline=True,
        default_value=FLAGS.display, handler=self._CmdDisplay,
        completer=lambda: DISPLAY_FORMATS)
    cli_parser.RegisterCommand(
        'env', TILDE_COMMAND_HELP['env'], max_args=0, handler=self._CmdEnv)
    cli_parser.RegisterCommand(
        'exec', TILDE_COMMAND_HELP['exec'], short_name='!', min_args=1,
        raw_arg=True, handler=self._CmdExecShell)
    cli_parser.RegisterCommand(
        'exit', TILDE_COMMAND_HELP['exit'], inline=True, max_args=0,
        handler=self._CmdExit)
    cli_parser.RegisterCommand(
        'expandtargets', TILDE_COMMAND_HELP['expandtargets'], max_args=0,
        handler=self._CmdExpandTargets)
    cli_parser.RegisterCommand(
        'filter', TILDE_COMMAND_HELP['filter'], short_name='F',
        inline=True, default_value=FLAGS.filter, handler=self._CmdFilter)
    cli_parser.RegisterCommand(
        'help', TILDE_COMMAND_HELP['help'], max_args=0,
        inline=True, handler=self._CmdHelp)
    cli_parser.RegisterCommand(
        'inventory', TILDE_COMMAND_HELP['inventory'], short_name='V',
        max_args=0, handler=self._CmdInventory)
    cli_parser.RegisterCommand(
        'linewrap', TILDE_COMMAND_HELP['linewrap'],
        inline=True, toggle=True, default_value=FLAGS.linewrap,
        handler=self._CmdToggleValue, completer=lambda: ['on', 'off'])
    cli_parser.RegisterCommand(
        'log', TILDE_COMMAND_HELP['log'], append=True, inline=True,
        handler=self._CmdLogging)
    cli_parser.RegisterCommand(
        'logall', TILDE_COMMAND_HELP['logall'], append=True, inline=True,
        handler=self._CmdLogging)
    cli_parser.RegisterCommand(
        'logstop', TILDE_COMMAND_HELP['logstop'], inline=True, min_args=1,
        handler=self._CmdLogStop)
    cli_parser.RegisterCommand(
        'mode', TILDE_COMMAND_HELP['mode'], short_name='M', inline=True,
        default_value=FLAGS.mode, handler=self._CmdMode)
    cli_parser.RegisterCommand(
        'play', TILDE_COMMAND_HELP['play'], short_name='P', min_args=1,
        handler=self._CmdPlay)
    cli_parser.RegisterCommand(
        'quit', TILDE_COMMAND_HELP['quit'], inline=True, max_args=0,
        handler=self._CmdExit)
    cli_parser.RegisterCommand(
        'read', TILDE_COMMAND_HELP['read'], append=True, min_args=1, max_args=2,
        handler=self._CmdRead)
    cli_parser.RegisterCommand(
        'record', TILDE_COMMAND_HELP['record'], append=True, inline=True,
        handler=self._CmdLogging)
    cli_parser.RegisterCommand(
        'recordall', TILDE_COMMAND_HELP['recordall'], append=True, inline=True,
        handler=self._CmdLogging)
    cli_parser.RegisterCommand(
        'recordstop', TILDE_COMMAND_HELP['recordstop'], inline=True, min_args=1,
        handler=self._CmdLogStop)
    cli_parser.RegisterCommand(
        'safemode', TILDE_COMMAND_HELP['safemode'], short_name='S', inline=True,
        toggle=True, handler=self._CmdToggleValue,
        completer=lambda: ['on', 'off'])
    cli_parser.RegisterCommand(
        'timeout', TILDE_COMMAND_HELP['timeout'],
        default_value=FLAGS.timeout, handler=self._CmdTimeout)
    cli_parser.RegisterCommand(
        'write', TILDE_COMMAND_HELP['write'], append=True, min_args=1,
        max_args=2, handler=self._CmdWrite)
    cli_parser.RegisterCommand(
        'verbose', TILDE_COMMAND_HELP['verbose'], inline=True, toggle=True,
        handler=self._CmdToggleValue, completer=lambda: ['on', 'off'])
    cli_parser.RegisterCommand(
        'vi', TILDE_COMMAND_HELP['vi'], min_args=1, handler=self._CmdEditor)

  def StartUp(self, commands, interactive):
    """Runs rc file commands and initial startup tasks.

      The RC file may contain any valid TCLI commands including commands to send
      to devices. At the same time flags are a more specific priority than RC
      commands _IF_ set explicitly (non default).

      So we parse and set a bunch of flags early that a benigh (do not issue
      commands to devices or play out buffer content etc).
      Run the RC file, after which we re-appply explicitly set flags values.
    Args:
      commands: List of Strings, device commands to send at startup.
      interactive: Bool, are we running as an interactive CLI or batch.

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
    self._SetFiltersFromDefaults()
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

  def SetDefaults(self):
    """Parses command line flags ad sets default attributes.

      Commands here affect data representation/presentation but are otherwise
      harmless. Excuted both before and after any commands that may exist in a
      config file so that RC executed commands get the benefits without being
      able to override explicit flags.
    """

    # Calling the handlers directly will not be logged.
    for command_name in DEFAULT_CMDS:
      self.cli_parser.ExecWithDefault(command_name)

  # pylint: disable=unused-argument
  def Completer(self, word, state):
    """Command line completion used by readline library."""

    # Silently discard leading whitespace on cli.
    full_line = readline.get_line_buffer().lstrip()
    if full_line and full_line.startswith(TILDE):
      return self._TildeCompleter(full_line, state)
    return self._CmdCompleter(full_line, state)

  def _TildeCompleter(self, full_line, state):
    """Command line completion for escape commands."""

    # Pass subsequent arguments of a command to its completer.
    if ' ' in full_line:
      cmd = full_line[1:full_line.index(' ')]
      arg_string = full_line[full_line.index(' ') +1:]
      completer_list = []
      if self.cli_parser.GetCommand(cmd):
        for arg_options in self.cli_parser.GetCommand(cmd).completer():
          if arg_options.startswith(arg_string):
            completer_list.append(arg_options)

      if state < len(completer_list):
        return completer_list[state]
      return None

    # First word, a TCLI command word.
    completer_list = []
    for cmd in self.cli_parser:
      # Strip TILDE and compare.
      if cmd.startswith(full_line[1:]):
        completer_list.append(cmd)
        if self.cli_parser.GetCommand(cmd).append:
          completer_list.append(cmd + command_parser.APPEND)
    completer_list.sort()

    if state < len(completer_list):
      # Re-apply TILDE to completion.
      return TILDE + completer_list[state]
    return None

  def _CmdCompleter(self, full_line, state):
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

  def ParseCommands(self, commands):
    """Parses commands and executes them.

    Splits commands on line boundary and forwards to either the:
      - TildeCmd the method for resolving TCLI commands.
      - CmdRequests the method for sending commands to the backend.

    Args:
      commands: String of newline separated commands.
    """

    def _FlushCommands(command_list):
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
      if command.startswith(TILDE):
        _FlushCommands(command_list)
        # Remove tilde command prefix and submit to TCLI command interpreter.
        self.TildeCmd(command[1:])
      else:
        # Backend commands.
        # Look for inline tilde commands.
        (inline_command, inline_tcli) = self._ExtractInlineCommands(command)
        if inline_command != command:
          _FlushCommands(command_list)
          # Commands with inline display modifiers are submitted
          # to a child TCLI object that only supports inline commands.
          logging.debug('Inline Cmd: %s.', inline_command)
          inline_tcli.ParseCommands(inline_command)
        else:
          # Otherwise collect multiple commands to send at once.
          command_list.append(command)

    _FlushCommands(command_list)

  def Callback(self, response):
    """Async callback for device command."""

    with self._lock:
      logging.debug("Callback for '%s'.", response.uid)
      # Convert from inventory specific format to a more generic dictionary.
      self.cmd_response.AddResponse(
          self.inventory.ReformatCmdResponse(response))

      # If we have all responses for current row/command then display.
      row = self.cmd_response.GetRow()
      while row:
        self._FormatResponse(row[0], row[1])
        row = self.cmd_response.GetRow()

  def CmdRequests(self, device_list, command_list, explicit_cmd=False):
    """Submits command list to devices and receives responses.

    Args:
      device_list: List of strings, each string being a devicename
      command_list: List of strings, each string is a command to execute
      explicit_cmd: Bool, if commands submitted via '/command' or not
    """

    for buf in (self.record, self.recordall, self.log, self.logall):
      self.buffers.Append(buf, '\n'.join(command_list))

    if not device_list or not command_list:
      # Nothing to do.
      return

    if not explicit_cmd and self.safemode:
      self._PrintWarning('Safe mode on, command ignored.')
      return

    if FLAGS.dry_run:
      # Batch mode with dry_run set, then show what commands and devices would
      # have been sent and return.
      self._PrintOutput('Send Commands: ', title=True)
      self._PrintOutput('  ' + '\r  '.join(command_list))
      self._PrintOutput('To Targets: ', title=True)
      self._PrintOutput('  ' + ','.join(device_list))
      return

    # Response requests.
    requests = []
    self.cmd_response = command_response.CmdResponse()
    # Responses from hosts for a single command are known as a 'row'.
    for cmd_row, command in enumerate(command_list):
      # Split off client side pipe command.
      (command, pipe) = self._ExtractPipe(command)
      logging.debug("Extracted command and pipe: '%s' & '%s'.", command, pipe)
      self.cmd_response.SetCommandRow(cmd_row, pipe)

      # Create command requests.
      for host in device_list:
        req = self.inventory.CreateCmdRequest(host, command, self.mode)
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
      self._PrintWarning('Timeout: timer exceeded while waiting for responses.')
    logging.debug('CmdRequests: All callbacks completed.')

  def TildeCmd(self, line):
    """Tilde escape tcli configuration command.

    Args:
      line: String command for TCLI parsing.

    Raises:
      EOFError: If exit is issued.
    """

    # Command parsing
    try:
      (command, args, append) = self.cli_parser.ParseCommandLine(line)
    except ParseError as error_message:
      self._PrintWarning(str(error_message))
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
        self.buffers.Append(buf, TILDE + line)

    # Command execution.
    try:
      self._PrintSystem(
          self.cli_parser.ExecHandler(command, args, append))
    # pylint: disable=broad-except
    except ValueError as error_message:
      self._PrintWarning(str(error_message))

  def _ExtractInlineCommands(self, command):
    # pylint: disable=missing-docstring
    """Separate out linewise commmand overrides from command input.

    Converts something like:
      'cat alpha | grep abc || grep xyz %sdisplay csv %slog buffername'
    Into:
      command = ['cat alpha | grep ablc || grep xyz']
      display = 'csv'
      log = 'buffername'

    Double tilde '%s' that are not preceded by a space and are
    part of a valid command are ignored and treated as part of the command body.

      'show flash:%sfile_name %sbogus %slog filelist'
    Converts into:
      ('show flash:%sfile_name %sbogus', ((%slog filelist),))

    Creates child TCLI object with runtime environment modified by the values
    pulled from the inline arguments.

    Args:
      command: str, command issued to target devices.

    Returns:
      Tuple, the command line with inline TCLI commands removed and TCLI
      instance with the tilde commands applied (None if no tilde commands).
    """.replace('%s', (TILDE * 2))

    if '%s' % (TILDE * 2) not in command:
      return (command, None)

    # Create new child with inline escape command changes.
    inline_tcli = copy.copy(self)

    token_list = command.split(' %s' % (TILDE * 2))
    # If all tokens parse then the first token is the commandline.
    command_left = token_list[0]
    command_right = token_list[1:]
    # Reverse the order of the tokens so that we work right to left.
    command_right.reverse()
    index = len(command_right)
    for token in command_right:
      # Confirm that is parses and executes cleanly.
      try:
        (new_cmd, args, append) = inline_tcli.cli_parser.ParseCommandLine(token)
        inline_tcli.cli_parser.ExecHandler(new_cmd, args, append)
      except (ValueError, ParseError):
        # If a token doesn't parse then it and all tokens to the left are
        # returned to the commandline.
        command_left = (' %s' % (TILDE * 2)).join(token_list[:index + 1])
        break
      except EOFError:
        # Exit in this context stop further inline command parsing.
        # Inline commands to the left of the exit are treated as regular input.
        command_left = (' %s' % (TILDE * 2)).join(token_list[:index])
        break
      index -= 1

    return (command_left, inline_tcli)

  def _ExtractPipe(self, command):
    """Separate out local pipe suffix from command input.

    Converts something like:
      'cat alpha | grep abc || grep xyz || grep -v "||"'
    Into:
      ('cat alpha | grep abc', 'grep xyz | grep -v "||"')

    Args:
      command: str, command issued to target devices.

    Returns:
      Tuple with the first argument being the text to pass on to the device
      and the second value is the local pipe with the '||' replaced with '|'.
    """

    if '||' not in command:
      return (command, '')

    found_single_pipe = False
    dbl_pipe_str = ''
    cmd_str = ''
    # Split out quoted and non-quoted text and work through from the right.
    for cmd_elem in reversed(
        re.findall("""([^"']+)|("[^"]*")|('[^']*')""", command)):
      (nonquoted, _, _) = cmd_elem
      if nonquoted and not found_single_pipe:
        # At this point we have non-quoted text that may have '|' or '||' in it.
        # Convert something like:
        #   '0 || 1 | 2 || 3 |||'
        # Into:
        #   ('0 || 1 | 2', '| 3 |||')

        tmp_str = ''
        # Split out pipe commands and work through from right.
        for pipe_elem in reversed(re.findall(r'([^|]+)|(\|+)', nonquoted)):
          (pipe_text, pipe_cmd) = pipe_elem
          if not pipe_cmd:
            tmp_str = pipe_text + tmp_str
            continue

          if pipe_cmd == '||' and not found_single_pipe:
            dbl_pipe_str = '|' + tmp_str + cmd_str + dbl_pipe_str
            cmd_str = ''
            tmp_str = ''
          else:
            if pipe_cmd == '|':
              # No more double pipe elements.
              found_single_pipe = True
            tmp_str = pipe_cmd + tmp_str

        cmd_str = tmp_str + cmd_str
      else:
        cmd_str = ''.join(cmd_elem) + cmd_str

    return (cmd_str.rstrip(), dbl_pipe_str.strip())

  def _FormatRaw(self, response, pipe=''):
    """Display response in raw format."""

    # Do nothing with raw output other than tagging
    # Which device/command generated it.

    self._PrintOutput('#!# %s:%s #!#' %
                      (response.device_name, response.command),
                      title=True)
    self._PrintOutput(self._Pipe(response.data, pipe=pipe))

  def _FormatErrorResponse(self, response):
    """Formatted error derived from response."""

    self._PrintWarning('#!# %s:%s #!#\n%s' %
                       (response.device_name, response.command, response.error))

  def _FormatResponse(self, response_uid_list, pipe=''):
    """Display the results from a list of responses."""

    # Filter required if display format is not 'raw'.
    if self.display != 'raw' and not self.filter:
      self._PrintWarning(
          'No filter set, cannot display in %s format' % repr(self.display))
      return

    result = None
    for response_uid in response_uid_list:
      response = self.cmd_response.GetResponse(response_uid)
      if not response:
        self._PrintWarning(
            'Invalid or missing response: Some output could not be displayed.')
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
        self.filter_engine.ParseCmd(
            response.data, attributes=filter_attr, verbose=self.verbose)
      except CliTableError as error_message:
        logging.debug('Parsing engine failed for device "%s".',
                      response.device_name)
        self._PrintWarning(error_message)
        # If unable to parse then output as raw.
        self._FormatRaw(response, pipe=pipe)
        continue

      # Add host column to row, as single table may have
      # Multiple hosts with multiple rows each.
      self.filter_engine.AddColumn('Host', response.device_name, 0)

      # Is this the first line.
      if not result:
        # Print header line for new table and initialise record.
        self._PrintOutput('#!# %s #!#' % response.command, title=True)
        result = copy.deepcopy(self.filter_engine)
      # Next line has incompatible row header.
      # Display previous table and start new table.
      elif str(self.filter_engine.header) != str(result.header):
        self._DisplayTable(result, pipe=pipe)
        result = copy.deepcopy(self.filter_engine)
      else:
        # Add record to existing table.
        result += self.filter_engine

    if result:
      if FLAGS.sorted:
        result.sort()
      self._DisplayTable(result, pipe=pipe)

  def _DisplayTable(self, result, pipe=''):
    """Displays output in tabular form."""

    if self.display == 'csv':
      self._PrintOutput(self._Pipe(str(result), pipe=pipe))

    elif self.display == 'nvp':
      # 'Host' is added to the LABEL prefix.
      result.AddKeys(['Host'])
      self._PrintOutput(self._Pipe(result.LabelValueTable(), pipe=pipe))

    elif self.display == 'tbl':
      (_, width) = terminal.TerminalSize()
      try:
        self._PrintOutput(self._Pipe(result.FormattedTable(width), pipe=pipe))
      except TableError as error_message:
        width *= 2
        # Try again allowing text to wrap once.
        try:
          self._PrintOutput(self._Pipe(result.FormattedTable(width), pipe=pipe))
        except TableError as error_message:
          self._PrintWarning(str(error_message))
    else:
      # Problem with parsing of display command if we reach here.
      raise TcliCmdError('Unsupported display format: %s.' %
                         repr(self.display))

  def _Pipe(self, output, pipe=''):
    """Creates pipe for filtering command output."""

    if not pipe:
      pipe = self.pipe

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
        self._PrintWarning(str(error_message))
      return

    try:
      result, _ = p.communicate(bytes(output, 'utf-8'))
      logging.debug('Output written to pipe:\n%s', output)
      logging.debug('Output read from pipe:\n%s', result)
      return result.decode('utf-8')

    except IOError:
      logging.error('IOerror writing/reading from pipe.')
      return

  def Prompt(self):
    """Present prompt for further input."""

    # Clear response dictionary to ignore outstanding requests.
    self.cmd_response = command_response.CmdResponse()
    try:
      self._SetPrompt()
    except ValueError as error_message:
      self._PrintWarning(str(error_message))
    # Print the main prompt, so the ASCII escape sequences work.
    print(self.prompt)
    # Stripped ASCII escape from here, as they are not interpreted in PY3.
    self.ParseCommands(input(PROMPT_STR))

  def _BufferInUse(self, buffername):
    """Check if buffer is already being written to."""

    if buffername in (self.record, self.recordall, self.log, self.logall):
      self._PrintWarning('Buffer: %s, already open for writing.' %
                         repr(buffername))
      return True

    if buffername == self.playback:
      self._PrintWarning("Buffer: %s, already open by 'play' command." %
                         self.playback)
      return True

    return False

  ##############################################################################
  # Registered Commands.                                                       #
  ##############################################################################
  # All methods supplied to RegisterCommand have the same parameters.
  # Args:
  #  command: str, name of command.
  #  args: list of commandline arguments, excluding any piping on rhs.
  #  append: bool, if command is to appeneded or replace current setting.
  #
  # pylint: disable=unused-argument

  def _CmdBuffer(self, command, args, append=False):
    """"Displays buffer contents."""

    buffer_name = args[0]
    # Assign buffer to local var so we no longer log to it in this command.
    buf = self.buffers.GetBuffer(buffer_name)
    if buf is None:
      raise ValueError('Invalid buffer name "%s".' % buffer_name)

    # Because the output is bracketed by PrintWarning calls, we print here
    # rather than returning the output.
    self._PrintWarning('#! BUFFER %s !#' % args[0])
    self._PrintSystem(buf)
    self._PrintWarning('#! ENDBUFFER !#')

  def _CmdBufferList(self, command, args=None, append=False):
    """List all buffers."""
    return self.buffers.ListBuffers()

  def _CmdClear(self, command, args, append=False):
    """Clears contrent of the buffer."""
    self.buffers.Clear(args[0])

  def _CmdColorScheme(self, command, args=None, append=False):
    """Sets ANSI color escape values."""

    if not args:
      return self.color_scheme

    scheme = args[0]
    if not self.color:
      self.system_color = ''
      self.warning_color = ''
      self.title_color = ''
    else:
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
      else:
        raise ValueError('Error: Unknown color scheme: %s' % scheme)
      self.color_scheme = scheme

  def _CmdCommand(self, command, args, append):
    """Submit command to devices."""
    self.CmdRequests(self.device_list, [args[0]], True)

  def _CmdDefaults(self, command, args=None, append=False):
    """Reset commands to the 'at start' value."""

    if not args:
      return self._CmdEnv(command, args, append)

    default = args[0]
    if default == 'all':
      # Re apply explicit flags.
      # TODO(harro): Only sets some core values (with flags), could reset more?
      self.SetDefaults()
      self._SetFiltersFromDefaults()
    else:
      try:
        return self.cli_parser.ExecWithDefault(default)
      except Exception:
        raise ValueError("Cannot set '%s' to defaults." % default)

  def _CmdDisplay(self, command, args, append):
    """Set the layout format."""

    if not args:
      return 'Display: %s' % self.display

    display_format = args[0]
    if display_format in DISPLAY_FORMATS:
      self.display = display_format
    else:
      raise ValueError(
          "Unknown display %s. Available displays are '%s'" % (
              repr(display_format), DISPLAY_FORMATS))

  def _CmdEnv(self, command, args, append):
    """Display various environment variables."""

    return ('Display: %s, Filter: %s\n'
            'Record: %s, Recordall: %s\n'
            'Log: %s, Logall: %s\n'
            'Color: %s, Scheme: %s\n'
            'Timeout: %d, Verbose: %s\n'
            'CLI Mode: %s, Safemode: %s\n'
            'Line Wrap: %s\n%s'
            % (self.display, self.filter,
               self.record, self.recordall,
               self.log, self.logall,
               self.color, self.color_scheme,
               self.timeout, self.verbose,
               self.mode, self.safemode,
               self.linewrap,
               self.inventory.ShowEnv()))

  def _CmdExecShell(self, command, args, append):
    """Executes a shell command."""

    try:
      exec_out = os.popen(args[0])
      output = exec_out.read()
      exec_out.close()
    except IOError as error_message:
      raise ValueError(error_message)

    return output

  def _CmdEditor(self, command, args, append):
    """Edits the named buffer content."""

    buf = args[0]
    buf_file = tempfile.NamedTemporaryFile()
    # Write out the buffer data to file.
    if self.buffers.GetBuffer(buf):
      buf_file.writelines(self.buffers.GetBuffer(buf))
      # Flush content so editor will see it.
      buf_file.flush()
    # TODO(harro): Support os.getenv('EDITOR', 'vi').
    # Open file with vi.
    os.system('vi -Z -n -u NONE -U NONE -- %s' % (buf_file.name))
    # Read back the data into the buffer.
    buf_file.seek(0)
    self.buffers.Clear(buf)
    self.buffers.Append(buf, buf_file.read())
    buf_file.close()

  def _CmdExit(self, command, args=None, append=False):
    """Exit TCLI."""
    raise EOFError()

  def _CmdExpandTargets(self, command, args, append):
    return ','.join(self.device_list)

  def _CmdFilter(self, command, args, append):
    """Sets the clitable filter."""

    if not args:
      return 'Filter: %s' % self.filter

    filter_name = args[0]
    try:
      self.filter_engine = clitable.CliTable(filter_name, FLAGS.template_dir)
      self.filter = filter_name
    except (clitable.CliTableError, texttable.TableError, IOError):
      raise ValueError('Invalid filter %s.' % repr(filter_name))

  def _CmdHelp(self, command, args, append):
    """Display help."""

    result = []
    # Print the brief comment regarding escape commands.
    for cmd in sorted(self.cli_parser):
      append = ''
      if self.cli_parser.GetCommand(cmd).append:
        append = '[+]'
      arg = ''
      if self.cli_parser.GetCommand(cmd).min_args:
        arg = ' <%s>' % cmd
      result.append('%s%s%s%s\n\n' %
                    (cmd, append, arg,
                     self.cli_parser.GetCommand(cmd).help_str))
    return ''.join(result)

  def _CmdInventory(self, command, args, append):
    """Displays devices in target list."""

    device_list = []
    for device_name in self.device_list:
      device = self.devices[device_name]
      attr_list = [device_name]
      # TODO(harro): Shouldn't need to call DEVICE_ATTRIBUTES directly.
      for name in inventory.DEVICE_ATTRIBUTES:
        if name == 'flags':
          continue

        if not getattr(device, name):
          continue

        attr_list.append('%s:%s' % (name.title(), getattr(device, name) or ''))

      for fl in device.flags:
        attr_list.append(fl)

      device_list.append(', '.join(attr_list))
    return '\n'.join(device_list)

  def _CmdLogging(self, command, args, append):
    """Activates one of the various logging functions."""

    # If no arg then display what buffer is currently active.
    if not args:
      buf_name = getattr(self, command)
      if not buf_name:
        buf_name = 'None'
      return '%s buffer is %s' % (repr(command), repr(buf_name))

    buf = args[0]
    # In this we are appending but still need to check that we are not
    # already logging, or playing out from it.
    if self._BufferInUse(buf):
      return

    if not append:
      # Clear the buffer as we are not appending.
      self.buffers.Clear(buf)
    setattr(self, command, buf)

  def _CmdLogStop(self, command, args, append=False):
    """Stop logging to a buffer."""

    buf = args[0]
    for attr in ('record', 'recordall', 'log', 'logall'):
      if getattr(self, attr) == buf:
        setattr(self, attr, None)
        return

    raise ValueError('Buffer not in use for logging or recording.')

  def _CmdMode(self, command, args, append):
    """Target CLI Mode to send to commands for."""

    if not args:
      return 'Mode: %s' % self.mode

    mode = args[0]
    if mode in MODE_FORMATS:
      self.mode = mode
    else:
      raise ValueError("Unknown mode %s. Available modes are '%s'" % (
          repr(mode), MODE_FORMATS))

  def _CmdPlay(self, command, args, append):
    """Plays out buffer contents to TCLI."""

    if self.playback is not None:
      raise ValueError('Recursive call of "play" rejected.')

    buf = args[0]
    # Do not allow playing out a buffer that is still being logged too.
    if not self._BufferInUse(buf):
      # Mark what buffer we are playing out from.
      self.playback = buf
      self.ParseCommands(self.buffers.GetBuffer(buf))
      self.playback = None

  def _CmdRead(self, command, args, append):
    """"Write buffer content to file."""

    buf = args[0]
    if len(args) > 1:
      filename = args[1]
    else:
      self._PrintSystem('Enter filename to read from: ',)
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

  def _CmdTimeout(self, command, args, append):
    """Sets or display the timeout setting."""

    if not args:
      return 'Timeout: %s' % self.timeout
    try:
      timeout = int(args[0])
      if timeout > 0:
        self.timeout = int(args[0])
      else:
        raise ValueError
    except ValueError:
      raise ValueError('Invalid timeout value %s.' % repr(args[0]))

  def _CmdWrite(self, command, args, append):
    """Writes out buffer content to file."""

    buf = args[0]
    if not self.buffers.GetBuffer(buf):
      raise ValueError('Buffer empty.')

    if len(args) > 1:
      filename = args[1]
    else:
      self._PrintSystem('Enter filename to write buffer to: ',)
      filename = sys.stdin.readline().strip()
    filename = os.path.expanduser(os.path.expandvars(filename))

    try:
      if append:
        buf_file = open(filename, 'a')
      else:
        buf_file = open(filename, 'w')
      buf_file.writelines(self.buffers.GetBuffer(buf))
      buf_file.close()
    except IOError as error_message:
      raise ValueError(str(error_message))

    return '%d lines written.' % self.buffers.GetBuffer(buf).count('\n')

  def _CmdToggleValue(self, command, args, append):
    """Commands that can 'toggle' their value."""

    if args:
      value = args[0]
      value = value.lower()
      if value in ('on', 'true'):
        bool_result = True
      elif value in ('off', 'false'):
        bool_result = False
      else:
        raise ValueError("Error: Argument must be 'on' or 'off'.")
      setattr(self, command, bool_result)
    else:
      # toggle the bool value.
      setattr(self, command, not getattr(self, command))

  # pylint: enable=unused-argument
  ##############################################################################
  # End of command handles.                                                    #
  ##############################################################################

  def _PrintWarning(self, msg):
    """Prints warnings to stderr."""

    if not msg:
      return

    for buf in (self.logall,):
      self.buffers.Append(buf, msg)

    if self.linewrap:
      msg = terminal.LineWrap(msg)

    if self.color:
      print(terminal.AnsiText(msg, self.warning_color), file=sys.stderr)
    else:
      print(msg, file=sys.stderr)

  def _PrintOutput(self, msg, title=False):
    """Prints output to stdout."""

    if not msg:
      return

    for buf in (self.log, self.logall):
      self.buffers.Append(buf, msg)

    if self.linewrap:
      msg = terminal.LineWrap(msg)

    if title and self.color:
      print(terminal.AnsiText(msg, self.title_color))
    else:
      print(msg)

  def _PrintSystem(self, msg):
    """Prints system messages to stdout."""

    if not msg:
      return

    for buf in (self.logall,):
      self.buffers.Append(buf, msg)

    if self.linewrap:
      msg = terminal.LineWrap(msg)

    if self.color:
      print(terminal.AnsiText(msg, self.system_color))
    else:
      print(msg)

  devices = property(lambda self: self.inventory.devices)
  device_list = property(lambda self: self.inventory.device_list)
