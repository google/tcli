"""Commandline completion functions for interactive TCLI."""

import re

from tcli import command_parser

_COMPLETER_LIST = []


def CmdCompleter(full_line: str, state: int, filter_engine) -> str|None:
  """Commandline completion used by readline library."""

  global _COMPLETER_LIST

  def _ScrubToken(token: str) -> str:
    """Remove nested (...)? from command completion string."""
    # This could break legitimate regexps but since these are completion
    # candidates, That breakage is cosmetic.
    _reg_exp_str = r'\((?P<value>.*)\)\?'
    clean_token = re.sub(_reg_exp_str, '\g<value>', token)                      # type: ignore
    # Repeat until all nested (...)? are removed.
    while token != clean_token:
      token = clean_token
      clean_token = re.sub(_reg_exp_str, '\g<value>', clean_token)              # type: ignore
    return token

  # First invocation, so build candidate list and cache for re-use.
  if state == 0:
    _completer_set = set()
    current_word = ''
    line_tokens = []
    word_boundary = False
    # What has been typed so far.

    # Collapse quotes to remove any whitespace within.
    cleaned_line = re.sub(r'\".+\"', '""', full_line)
    cleaned_line = re.sub(r'\'.+\'', '""', cleaned_line)
    # Remove double spaces etc
    cleaned_line = re.sub(r'\s+', ' ', cleaned_line)

    # Are we part way through typing a word, or a word boundary.
    if cleaned_line and cleaned_line.endswith(' '):
      word_boundary = True

    cleaned_line = cleaned_line.rstrip()
    # If a blank line then this is also a word boundary.
    if not cleaned_line:
      word_boundary = True
    else:
      # Split into word tokens.
      line_tokens = cleaned_line.split(' ')
      # If partially through typing a word then don't include it as a token.
      if not word_boundary and line_tokens:
        current_word = line_tokens.pop()

    # Compare with table of possible command matches in filter_engine.
    for row in filter_engine.index.index:                                       # type: ignore
      # Split the command match into tokens.
      cmd_tokens = row['Command'].split(' ')
      # Does the line match the partial list of tokens.
      if not line_tokens and cmd_tokens:
        # Currently a blank line so the first token is what we want.
        token = cmd_tokens[0]
      # Does our line match this command completion candidate.
      elif (
        len(cmd_tokens) > len(line_tokens) and
        re.match(' '.join(cmd_tokens[:len(line_tokens)]), cleaned_line)):
        # Take the token from off the end of the Completer command.
        token = cmd_tokens[len(line_tokens)]
      else:
        continue

      # We have found a match. Remove completer syntax.
      token = _ScrubToken(token)
      # If on word boundary or our current word is a partial match.
      if word_boundary or token.startswith(current_word):
        _completer_set.add(token)
    _COMPLETER_LIST = list(_completer_set)
    _COMPLETER_LIST.sort()
        

  if state < len(_COMPLETER_LIST):
    return _COMPLETER_LIST[state]
  return None


def TCLICompleter(full_line: str, state: int, cli_parser) -> str|None:
  """Command line completion for escape commands."""

  # Remove the leading slash.
  full_line = full_line[1:]
  completer_list = []
  # We have a complete TCLI command.
  # Ignore get_completer_delims, we only use spaces as separators.
  if ' ' in full_line:
    word_sep = full_line.index(' ')         # Word boundary.
    (cmd_name, arg_string) = (full_line[:word_sep], full_line[word_sep +1:])

    # If we have a shortname, expand it before continuing.
    if len(cmd_name) == 1:
      for cname in cli_parser:
        if cli_parser[cname].short_name is cmd_name:
          cmd_name = cname

    # Compare the subsequent arguments with the specific command completer.
    if cmd_name in cli_parser:
      for arg_option in cli_parser[cmd_name].completer():
        if arg_option.startswith(arg_string):
          completer_list.append(arg_option)

    if state < len(completer_list):
      return completer_list[state]
    return None

  # Partial, or whole command word with no arguments.
  for cmd_name in cli_parser:
    if cmd_name.startswith(full_line):
      completer_list.append(cmd_name)
      if (cmd_name in cli_parser and cli_parser[cmd_name].append):
        # Add the apend option of the command to the list
        completer_list.append(cmd_name + command_parser.APPEND)
  completer_list.sort()

  if state < len(completer_list):
    # Re-apply slash to completion.
    return command_parser.SLASH + completer_list[state]
  return None