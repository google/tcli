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

"""Executable for TCLI. Sets up command completion and then prompts the user."""

import importlib
import sys

from absl import app
from absl import flags

import tcli.tcli_lib as tcli


flags.DEFINE_string(
  'cmds', None, """
    Commands (newline separated) to send to devices in the target list.
    'Prompting' commands, commands that request further input from the
    user before completing are discouraged and will fail.
    Examples to avoid: telnet, ping, reload.
    Shortname: 'C'.""", short_name='C')
flags.DEFINE_boolean(
  'interactive', False, """
    TCLI runs in interactive mode. This is the default if no cmds are supplied.'
    Shortname: 'I'.""", short_name='I')
# Defaults to inventory_csv.py which contains canned data for testing.
flags.DEFINE_string('inventory_file', 'inventory_csv',
                    'Name of the  module that implements the Inventory class.')
FLAGS = flags.FLAGS


def main(_):
  # Replace the generic Inventory class with the site specific one.
  tcli.inventory = importlib.import_module(f'tcli.{FLAGS.inventory_file}')
  try:
    # If no commands supplied via flags then assume interactive mode.
    interactive =  FLAGS.interactive or not FLAGS.cmds
    tcli_singleton = tcli.TCLI(interactive, FLAGS.cmds)
  except (EOFError, tcli.TcliCmdError,
          tcli.inventory.AuthError, tcli.inventory.InventoryError,
          ValueError) as error_message:
    print('%s' % error_message, file=sys.stderr)
    sys.exit(1)

  if not tcli_singleton.interactive:
    del tcli_singleton
    sys.exit(0)

  # Interactive prompt, setup Tab completion
  tcli.readline.set_completer(tcli_singleton.Completer)
  tcli.readline.parse_and_bind('tab: complete')
  tcli.readline.parse_and_bind('?: complete')
  tcli.readline.set_completer_delims(' ')
  tcli_singleton.Motd()

  while True:
    try:
      tcli_singleton.Prompt()
    except KeyboardInterrupt:
      continue
    except EOFError:
      del tcli_singleton
      sys.exit(0)


if __name__ == '__main__':
  app.run(main)
