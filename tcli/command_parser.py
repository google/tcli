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

"""Parses TCLI command string and calls handler methods."""


import re
import shlex

# Command suffix for denoting appending values.
APPEND = '+'


class Error(Exception):
  """Base class for errors."""


class ParseError(Error):
  """General command parse error."""


class CommandParser(dict):
  """Class handles the setup of commandline functions and runtime parsing."""

  class _Command(object):
    """Holds attributes of a command."""

    def __init__(self, command_attr):
      self.attr = command_attr

    # Expose the dictionary as read-only attributes of the object.

    # Command can set a value by either apend or replace.
    append = property(lambda self: self.attr['append'])
    # Interactive command completion.
    completer = property(lambda self: self.attr['completer'])
    # At start value, typically derived form flags.
    default_value = property(lambda self: self.attr['default_value'])
    # Method to call when command executed.
    handler = property(lambda self: self.attr['handler'])
    # Text explaining how to use the command.
    help_str = property(lambda self: self.attr['help_str'])
    # Can be supplied on the rhs as a inline command modifier.
    inline = property(lambda self: self.attr['inline'])
    # Maximum and minimum number of args permitted.
    max_args = property(lambda self: self.attr['max_args'])
    min_args = property(lambda self: self.attr['min_args'])
    # Only one unparsed arg i.e. may contain unquoted white space etc.
    raw_arg = property(lambda self: self.attr['raw_arg'])
    # Command args may have non-alphanums.
    regexp = property(lambda self: self.attr['regexp'])
    # Single letter short name for command.
    short_name = property(lambda self: self.attr['short_name'])
    # The command expects a bool and flips the value if unspecified.
    toggle = property(lambda self: self.attr['toggle'])

  def _ShortCommand(self, short_name):
    """Find full command name for a short command letter."""

    for command_name in self:
      if self[command_name].short_name == short_name:
        return command_name

  def _CommandExpand(self, line):
    """Strips off command name and append indicator.

    e.g. S -> ('safemode', '', False),
         C show vers -> ('command', 'show vers', False)

    Args:
      line: (str) escape command (minus the escape prefix).

    Returns:
      Tuple, Command name shortname replaced by long one, remainder of the line
          and a bool for if the command had an append suffix or not.
    """

    # Short commands are non-alphabetic or capitalised,
    # long names are always lowercase.
    append = False
    command_name = None
    if line:
      command_name = self._ShortCommand(line[0])
      if command_name:
        line = line[1:]
        # Short commands optionally have the APPEND suffix.
        if line and line[0] == APPEND:
          append = True
          line = line[1:]
        line = line.lstrip(' ')
    return (command_name, line, append)

  def ExecHandler(self, command_name, args, append):
    """Execute the handler associated with this command."""

    if not self[command_name].handler:
      raise ParseError('Unable to exec handler, "%s" has no handler.' %
                       command_name)

    return self[command_name].handler.__call__(command_name, args, append)

  def ExecWithDefault(self, command_name):
    """Executes command handler with the default provided as the argument.

    Args:
      command_name: str, command.

    Returns:
      None is there is no default value or the resultant execution if there is.

    Raises:
      ValueError: if command_name is not a registered command.
      ParseError: if command doesn't accept an argument, default or otherwise.
    """

    if command_name not in self:
      raise ValueError

    if not hasattr(self[command_name], 'default_value'):
      return

    value = self[command_name].default_value
    if self[command_name].toggle:
      if value:
        value = 'on'
      else:
        value = 'off'
    # Confirm that command expects an argument.
    if not self[command_name].max_args:
      raise ParseError('Unable to set default, "%s" expects no arguments.' %
                       command_name)

    return self.ExecHandler(command_name, [value], False)

  def GetCommand(self, command_name):
    """Returns object for a command, None otherwise."""
    return self.get(command_name)

  def GetDefault(self, command_name):
    """Returns default value for a command.

    Precondition, command is valid and exists.

    Args:
      command_name: str, command.

    Returns:
      Default value for the command.
    """
    return self[command_name].default_value

  def InlineOnly(self):
    """Unregister all non-inline commands from parser."""

    for command_name in [c for c in self.keys()]:
      if not self[command_name].inline:
        self.UnRegisterCommand(command_name)

  def ParseCommandLine(self, line):
    """Parse string into command and arguments.

    Split line into command, list of arguments and bool indicating append
    status. Validating arguments against attributes of the command i.e. number
    of arguments etc.

    Args:
      line: Str, command line in entirety.

    Returns:
      Tuple, command name, list of arguments, and bool indicating append or not.

    Raises:
      ParseError: If command not registered, or arguments are invalid.
    """

    # Expand short form of commands.
    (command_name, line, append) = self._CommandExpand(line)

    # Not short name, so extract long one.
    if not command_name:
      # Separate command from subsequent arguments.
      if ' ' in line:
        command_end = line.index(' ')
        command_name = line[:command_end]
        line = line[command_end:]
      else:
        command_name = line
        line = ''
      # Remove trailing whitespace.
      line = line.strip()
      if command_name.endswith(APPEND):
        command_name = command_name[:-1]
        append = True

    if command_name not in self:
      raise ParseError('Invalid escape command %s.' % repr(command_name))

    # Raw args receive no further parsing.
    if self[command_name].raw_arg:
      return (command_name, [line], append)

    if append and not self[command_name].append:
      raise ParseError(
          'Command "%s" does not support append mode.' % command_name)

    # Split remaining line into arguments.
    # Silently discard additional arguments.
    try:
      arguments = shlex.split(line)
    except ValueError as error_message:
      raise ParseError('Invalid string could not be parsed into arguments: %s' %
                       error_message)

    if (len(arguments) < self[command_name].min_args or
        len(arguments) > self[command_name].max_args):
      raise ParseError('Invalid number of arguments, found "%s".' %
                       len(arguments))

    # Check if a command only expects (Alpha numeric) arguments.
    if (not self[command_name].regexp and
        not self[command_name].raw_arg):
      for arg in arguments:
        if re.search(r'\W', arg):
          raise ParseError('Arguments with alphanumeric characters only.')

    return (command_name, arguments, append)

  def RegisterCommand(self, command_name, help_str, short_name='', min_args=0,
                      max_args=1, default_value=None, append=False,
                      inline=False, raw_arg=False, regexp=False, toggle=False,
                      handler=lambda: None, completer=lambda: None):
    """Adds command to parser so parser can determine if well-formed or not.

    Args:
      command_name: String name of command.
      help_str: String describing command functionality.
      short_name: Optional alias for command, a single capitilised character.
      min_args: Int, minimum number of additional arguments the command expects.
      max_args: Int, maximum number of additional arguments the command expects.
      default_value: Value to assign to command in absece of flag overrides.
      append: Bool, does the command support appending additional values.
      inline: Bool, can the command be supplied on the rhs of a pipe.
      raw_arg: Bool, do not parse args, treat as raw string.
      regexp: Bool, can the argument be a regular expression.
      toggle: Bool, does running the command without arguments toggle its value.
      handler: method, execute method for this command.
      completer: method, returns list of valid completions for commandline.
    """

    self[command_name] = self._Command({
        'help_str': help_str.format(APPEND=APPEND),
        'short_name': short_name,
        'min_args': min_args,
        'max_args': max_args,
        'default_value': default_value,
        'append': append,
        'inline': inline,
        'raw_arg': raw_arg,
        'regexp': regexp,
        'toggle': toggle,
        'handler': handler,
        'completer': completer
    })

  def UnRegisterCommand(self, command_name):
    """Remove support from command.

    Precondition, command is valid and exists.

    Args:
      command_name: str, command.
    """
    if command_name in self:
      del self[command_name]
