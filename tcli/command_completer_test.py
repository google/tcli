"""tests command completer functions."""


import unittest
from unittest import mock

from absl import flags

from tcli import tcli_lib as tcli
from tcli.tcli_textfsm import clitable

from tcli import command_completer as completer

APPEND = tcli.command_parser.APPEND
FLAGS = flags.FLAGS


class UnitTestCompleter(unittest.TestCase):
  """Tests the TCLI class."""

  def setUp(self):
      # Instantiate FLAGS global var.
      tcli.FLAGS([__file__,])
      return super().setUp()

  def testTCLICompleter(self):
    """Tests completing TCLI native commands."""

    with mock.patch.object(tcli.inventory, 'Inventory'):
      self.tcli_obj = tcli.TCLI()
    _cp = self.tcli_obj.cli_parser

    self.assertEqual(completer.TCLICompleter('/reco', 0, _cp), '/record')
    self.assertEqual(
      completer.TCLICompleter('/reco', 1, _cp), f'/record{APPEND}')
    self.assertEqual(completer.TCLICompleter('/reco', 2, _cp), '/recordall')
    self.assertEqual(
      completer.TCLICompleter('/reco', 3, _cp), f'/recordall{APPEND}')
    self.assertEqual(completer.TCLICompleter('/reco', 4, _cp), '/recordstop')
    self.assertIsNone(completer.TCLICompleter('/reco', 5, _cp))
    # Complete on command arguments.
    self.assertEqual(completer.TCLICompleter('/safemode ', 0, _cp), 'on')
    # Complete on command arguments for short names.
    self.assertEqual(completer.TCLICompleter('/S ', 0, _cp), 'on')

  def testCmdCompleter(self):
    with mock.patch.object(tcli.inventory, 'Inventory'):
      self.tcli_obj = tcli.TCLI()
    self.tcli_obj.filter = 'default'
    clitable.CliTable.INDEX = {}
    self.tcli_obj.filter_engine = clitable.CliTable(
        'default_index', template_dir=tcli.FLAGS.template_dir)
    _fe = self.tcli_obj.filter_engine

    # Completions are alphabetical.
    self.assertEqual('cat', completer.CmdCompleter('', 0, _fe))
    self.assertEqual('show', completer.CmdCompleter('', 1, _fe))
    self.assertIsNone(completer.CmdCompleter('', 2, _fe))

    self.assertEqual('cat', completer.CmdCompleter('c', 0, _fe))
    self.assertIsNone(completer.CmdCompleter('c', 1, _fe))

    self.assertEqual('alpha', completer.CmdCompleter('c ', 0, _fe))
    self.assertEqual('beta', completer.CmdCompleter('c ', 1, _fe))
    self.assertEqual('epsilon', completer.CmdCompleter('c ', 2, _fe))
    self.assertIsNone(completer.CmdCompleter('c ', 3, _fe))

    self.assertEqual('alpha', completer.CmdCompleter('c al', 0, _fe))
    self.assertIsNone(completer.CmdCompleter('c al', 1, _fe))

    # Regular expressions appear as valid completions.
    self.assertEqual('int.+', completer.CmdCompleter('show ', 0, _fe))
    self.assertEqual('brief', completer.CmdCompleter('show int.+ ', 0, _fe))
    # If an argument satisfies a regexp then completions work past that point.
    self.assertEqual('brief', completer.CmdCompleter('show int01 ', 0, _fe))
    self.assertIsNone(completer.CmdCompleter('show int00 ', 1, _fe))
    self.assertEqual('.+', completer.CmdCompleter('show int01 brief ', 0, _fe))
    self.assertIsNone(completer.CmdCompleter('show int00 brief yes', 1, _fe))