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

"""Tests for tcli.command_parser."""

from absl.testing import absltest as unittest
from tcli import command_parser


class CommandParserTest(unittest.TestCase):

  def setUp(self):
    super(CommandParserTest, self).setUp()
    self.cmd_parser = command_parser.CommandParser()

  def testCommandExpand(self):
    """Test short cmd expansion."""

    self.cmd_parser.RegisterCommand(
        'command', 'A help string.', short_name='C')

    self.assertEqual(('command', 'acommand', False),
                     self.cmd_parser._CommandExpand('Cacommand'))
    self.assertEqual(('command', 'acommand', False),
                     self.cmd_parser._CommandExpand('C acommand'))
    self.assertEqual((None, 'ganoncommand', False),
                     self.cmd_parser._CommandExpand('ganoncommand'))
    self.assertEqual(('command', '', False),
                     self.cmd_parser._CommandExpand('C'))
    self.assertEqual((None, '', False),
                     self.cmd_parser._CommandExpand(''))

  def testGetDefault(self):
    """Tests retrieving default values."""

    self.cmd_parser.RegisterCommand('a', '', default_value=None)
    self.cmd_parser.RegisterCommand('b', '', default_value='abc')
    self.cmd_parser.RegisterCommand('c', '', default_value=10)
    self.assertEqual(None, self.cmd_parser.GetDefault('a'))
    self.assertEqual('abc', self.cmd_parser.GetDefault('b'))
    self.assertEqual(10, self.cmd_parser.GetDefault('c'))

  def testHandler(self):
    """Tests handler execution."""

    def _Handler(command, args, append):
      return (command, args, append)

    self.cmd_parser.RegisterCommand('a', '', handler=_Handler)
    self.assertEqual(('a', ['b'], False),
                     self.cmd_parser.ExecHandler('a', ['b'], False))

  def testExecWithDefault(self):
    """Tests handler execution."""

    def _Handler(command, args, append):
      return (command, args, append)

    self.cmd_parser.RegisterCommand('a', '', toggle=True,
                                    default_value=True, handler=_Handler)
    self.assertEqual(('a', ['on'], False), self.cmd_parser.ExecWithDefault('a'))

  def testInlineOnly(self):
    """Tests trimming down to only inline commands."""
    self.cmd_parser.RegisterCommand('a', '', inline=True)
    self.cmd_parser.RegisterCommand('b', '')
    self.cmd_parser.RegisterCommand('c', '', inline=True)
    self.cmd_parser.InlineOnly()
    self.assertTrue(self.cmd_parser.GetCommand('a'))
    self.assertFalse(self.cmd_parser.GetCommand('b'))
    self.assertTrue(self.cmd_parser.GetCommand('c'))

  def testParseCommandLine1(self):
    """Tests parsing a command with default arguments."""

    self.cmd_parser.RegisterCommand(
        'boo', 'A help string.', short_name='B', min_args=0,
        max_args=2, default_value=None, append=False,
        inline=False, raw_arg=False, regexp=False, toggle=False)

    self.assertEqual(
        ('boo', [], False),
        self.cmd_parser.ParseCommandLine('boo'))
    self.assertEqual(
        ('boo', ['hoo'], False),
        self.cmd_parser.ParseCommandLine('boo hoo'))
    self.assertEqual(
        ('boo', ['hello', 'world'], False),
        self.cmd_parser.ParseCommandLine('boo hello world'))
    self.assertEqual(
        ('boo', ['hello', 'world'], False),
        self.cmd_parser.ParseCommandLine('Bhello world'))

    # Append disallowed.
    self.assertRaises(command_parser.ParseError,
                      self.cmd_parser.ParseCommandLine, 'boo+ hoo')
    # Regexp disallowed.
    self.assertRaises(command_parser.ParseError,
                      self.cmd_parser.ParseCommandLine, 'boo ^.*')
    # b/3173498 invalid \ escape terminated string.
    self.assertRaises(command_parser.ParseError,
                      self.cmd_parser.ParseCommandLine, 'boo slash ending\\')

  def testParseCommandLine2(self):
    """Tests parsing a with non default arguments."""

    self.cmd_parser.RegisterCommand(
        'boo', 'A help string.', short_name='B', min_args=1,
        max_args=2, default_value='on', append=True,
        inline=False, raw_arg=False, regexp=True, toggle=False)

    # Quoted text is OK.
    self.assertEqual(
        ('boo', ['A quoted long line'], False),
        self.cmd_parser.ParseCommandLine('boo "A quoted long line"'))
    # Regexps are marked OK as is append.
    self.assertEqual(
        ('boo', ['^.* ?'], True),
        self.cmd_parser.ParseCommandLine('boo+ "^.* ?"'))
    # Append still works when things are short and cramped.
    self.assertEqual(
        ('boo', ['hello', 'world'], True),
        self.cmd_parser.ParseCommandLine('B+hello world'))

    # Minimum arguments triggers exception.
    self.assertRaises(command_parser.ParseError,
                      self.cmd_parser.ParseCommandLine, 'boo')
    # As does the maximum.
    self.assertRaises(command_parser.ParseError,
                      self.cmd_parser.ParseCommandLine,
                      'boo hoo the line is too long')

  def testParseCommandLine3(self):
    """Test parsing a commnad with raw argument."""

    self.cmd_parser.RegisterCommand(
        'boo', 'A help string.', short_name='B', raw_arg=True)

    # Single argument, the remainder of the line.
    self.assertEqual(
        ('boo', ['hello world...'], False),
        self.cmd_parser.ParseCommandLine('boo hello world...'))

    self.assertEqual(
        ('boo', ['^.*$ .?'], False),
        self.cmd_parser.ParseCommandLine('B^.*$ .?'))

  def testRegisterCommand(self):

    # Lots of defaults.
    self.cmd_parser.RegisterCommand('boo', 'A help string.', short_name='B')
    boo = self.cmd_parser.GetCommand('boo')
    boo_dict = {
        'min_args': 0, 'max_args': 1, 'default_value': None, 'append': False,
        'inline': False, 'raw_arg': False, 'regexp': False, 'toggle': False,
        'handler': None}

    # Lots on non-default
    self.cmd_parser.RegisterCommand(
        'hoo', 'A help string.', short_name='H', min_args=1,
        max_args=2, default_value=10, append=True,
        inline=True, raw_arg=True, regexp=True, toggle=True)
    hoo = self.cmd_parser.GetCommand('hoo')
    hoo_dict = {
        'min_args': 1, 'max_args': 2, 'default_value': 10, 'append': True,
        'inline': True, 'raw_arg': True, 'regexp': True, 'toggle': True,
        'handler': None}

    for attr in ('min_args', 'max_args', 'default_value', 'append',
                 'inline', 'raw_arg', 'regexp', 'toggle'):
      self.assertEqual(boo_dict[attr], getattr(boo, attr))
      self.assertEqual(hoo_dict[attr], getattr(hoo, attr))


if __name__ == '__main__':
  unittest.main()
