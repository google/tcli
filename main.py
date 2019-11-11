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

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import logging
import readline
import sys
from absl import app
from absl import flags
import tcli.tcli_lib as tcli

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
  readline.set_completer(tcli_singleton.Completer)
  readline.parse_and_bind('tab: complete')
  readline.parse_and_bind('?: complete')
  readline.set_completer_delims(' ')
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
