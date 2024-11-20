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

"""Executable for TCLI."""

import logging
import sys
from absl import app
from absl import flags
import tcli.tcli_lib as tcli

flags.DEFINE_boolean(
  'interactive', False,
  'TCLI runs in interactive mode. This is the default mode if no'
  ' cmds are supplied.\n', short_name='I')
flags.DEFINE_string(
  'cmds', None, """
    Commands (newline separated) to send to devices in the target list.
    'Prompting' commands, commands that request further input from the
    user before completing are discouraged and will fail.

    Examples to avoid: telnet, ping, reload.""", short_name='C')
FLAGS = flags.FLAGS


def main(_):
  tcli_singleton = tcli.TCLI()
  try:
    logging.debug('Executing StartUp.')
    tcli_singleton.StartUp(FLAGS.cmds, FLAGS.interactive)
  except (EOFError, tcli.TcliCmdError,
          tcli.inventory.AuthError, tcli.inventory.InventoryError,
          ValueError) as error_message:
    print('%s' % error_message, file=sys.stderr)
    del tcli_singleton
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
