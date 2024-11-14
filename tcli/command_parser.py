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
import typing

# Command start with a slash, inline commands a double slash
SLASH = '/'
INLINE = SLASH*2
# Command suffix for denoting appending values.
APPEND = '+'
# Indent for help strings.
I = '\n' + ' '*4


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

  def _ShortCommand(self, short_name: str) -> str|None:
    """Find full command name for a short command letter."""

    for command_name in self:
      if self[command_name].short_name == short_name:
        return command_name

  def _CommandExpand(self, line:str) -> tuple[str|None, str, bool]:
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
        line = line[1 :]
        # Short commands optionally have the APPEND suffix.
        if line and line[0] == APPEND:
          append = True
          line = line[1 :]
        line = line.lstrip(' ')
    return (command_name, line, append)

  def ExecHandler(self, command_name:str, args:list[str], append:bool):
    """Execute the handler associated with this command."""

    if not self[command_name].handler:
      raise ParseError('Unable to exec handler, "%s" has no handler.' %
                       command_name)

    return self[command_name].handler.__call__(command_name, args, append)

  def ExecWithDefault(self, command_name:str):
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
      raise ValueError(f"Called unknown command: '{command_name}'.")

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

  def GetCommand(self, command_name:str) -> _Command|None:
    """Returns object for a command, None otherwise."""
    return self.get(command_name)

  def GetDefault(self, command_name:str) -> typing.Any:
    """Returns default value for a command.

    Precondition, command is valid and exists.

    Args:
      command_name: str, command.

    Returns:
      Default value for the command.
    """
    return self[command_name].default_value

  def InlineOnly(self) -> None:
    """Unregister all non-inline commands from parser."""

    for command_name in [c for c in self]:
      if not self[command_name].inline:
        self.UnRegisterCommand(command_name)

  def ParseCommandLine(self, line:str) -> tuple[str, list[str], bool]:
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
        line = line[command_end :]
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

  def RegisterCommand(self, command_name:str, help_str:str, short_name:str='', 
                      min_args:int=0, max_args:int=1, default_value=None, 
                      append:bool=False, inline:bool=False, raw_arg:bool=False,
                      regexp:bool=False, toggle:bool=False,
                      handler:typing.Callable=lambda: None,
                      completer:typing.Callable=lambda: None) -> None:
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
        'help_str': help_str,
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

  def UnRegisterCommand(self, command_name:str) -> None:
    """Remove support from command.

    Precondition, command is valid and exists.

    Args:
      command_name: str, command.
    """
    if command_name in self:
      del self[command_name]

  # Create new child with inline escape command changes.
  def ExtractInlineCommands(self, command:str) -> tuple[str,list[str]]:
    # pylint: disable=missing-docstring
    f"""Separate out inline commmand overrides from command input.

    Converts something like:
      'cat alpha | grep abc || grep xyz {INLINE}display csv {INLINE}log bufname'
    Into:
      command = ['cat alpha | grep ablc || grep xyz']
      display = 'csv'
      log = 'buffername'

    A sequence with '{INLINE}' that is not preceded by a space and part of a
    valid command is treated as part of the command body and no further matches
    are made. This determination is done from right to left.

    e.g.
      'show flash:{INLINE}file_name {INLINE}bogus {INLINE}log filelist'
    Converts into:
      ('show flash:{INLINE}file_name {INLINE}bogus', ('log filelist',))

    Args:
      command: str, command issued to target devices.

    Returns:
      List, the command line (minus inline commands) and a tupe of inline the
      TCLI commands extracted.
    """

    token_list = command.split(f' {INLINE}')
    # Do we need to extract inline commands at all?
    if len(token_list) == 1: return (command, [])

    (command_str, token_list) = (token_list[0], token_list[1:])
    inline_commands = []
    command_suffix = ''
    index = 0
    # Work from right to left.
    for i in range(len(token_list), 0, -1):
      index = i
      token = token_list[i -1]
      try:
        # 'exit' in this context stops any further inline command parsing.
        if token == 'exit':
          # Any inline commands to the left are treated as regular input.
          # Drop 'exit' from the inline commands, it has no other purpose here.
          token_list.pop(index -1)
          break
        # Confirm that token parses cleanly.
        self.ParseCommandLine(token)
        inline_commands.insert(0, token)
      except (ValueError, ParseError):
        # If a token doesn't parse then it and all tokens to the left are
        # returned back to the commandline.
        index += 1    # Including the current one.
        break

    if index > 1:     # True if we broke early from the above for loop.
      # Add back any remaining unparsed tokens to the command string.
      command_suffix = f' {INLINE}' + f' {INLINE}'.join(token_list[:index-1])

    return (command_str + command_suffix, inline_commands)

  def ExtractPipe(self, command:str) -> tuple[str,str]:
    """Separate out local pipe suffix from command input.

    Converts something like:
      'cat alpha | grep abc || grep xyz || grep -v "||"'
    Into:
      ('cat alpha | grep abc', 'grep xyz | grep -v "||"')

    Args:
      command: str, command string to split.

    Returns:
      Tuple with the first argument being the text to pass on to the device
      and the second value is the local pipe with '||' replaced with '|'.
    """

    # Trivial case, there is no pipes.
    if '||' not in command:
      return (command, '')

    found_single_pipe = False
    dbl_pipe_str = ''
    cmd_str = ''
    # Split out quoted and non-quoted text and work through from the right.
    #TODO(harro): Could be more legible. And does this handle nested quotes?
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