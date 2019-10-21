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

"""Template based text parser.

This module implements a parser, intended to be used for converting
human readable text, such as command output from a router CLI, into
a list of records, containing values extracted from the input text.

A simple template language is used to describe a state machine to
parse a specific type of text input, returning a record of values
for each input entity.

https://github.com/google/textfsm
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import json
from absl import flags
import textfsm
from textfsm import TextFSMError          # pylint: disable=unused-import
from textfsm import TextFSMTemplateError  # pylint: disable=unused-import
from textfsm import Usage                 # pylint: disable=unused-import

FLAGS = flags.FLAGS


class TextFSMOptions(textfsm.TextFSMOptions):
  """Additional options to TextFSMOptionsBase."""

  class Blank(textfsm.TextFSMOptions.OptionBase):
    """Value is always blank."""

    def OnCreateOptions(self):
      if len(self.value.options) != 1:
        raise textfsm.TextFSMTemplateError(
            'Blank is a mutually exclusive option.')

    def OnSaveRecord(self):
      self.value.value = ''

  class Verbose(textfsm.TextFSMOptions.OptionBase):
    """Value only shown in 'verbose' mode."""

    def OnCreateOptions(self):
      if 'Key' in self.value.OptionNames():
        raise textfsm.TextFSMTemplateError(
            'Options "Key" and "Verbose" are mutually exclusive')

    def OnGetValue(self):
      # pylint: disable=protected-access
      if not self.value.fsm._verbose:
        raise textfsm.SkipValue

    def OnSaveRecord(self):
      # pylint: disable=protected-access
      if not self.value.fsm._verbose:
        raise textfsm.SkipValue

  class Key(textfsm.TextFSMOptions.OptionBase):
    """Value is a key in the row."""

    def OnCreateOptions(self):
      if 'Verbose' in self.value.OptionNames():
        raise textfsm.TextFSMTemplateError(
            'Options "Key" and "Verbose" are mutually exclusive')


class TextFSM(textfsm.TextFSM):
  """Adds support for additional options to TextFSM.

  Options useful for formatting and displaying of the data.
  """

  def __init__(self, template, verbose=True,
               options_class=TextFSMOptions):
    """Initialises and also parses the template file."""

    # Display 'all' or 'only some' of the columns.
    # For real estate challenged displays.
    self._verbose = verbose
    super(TextFSM, self).__init__(template, options_class=options_class)

  def Dump(self):
    """Dump the table in a pseudo-JSON format.

    ParseText() must have previously been called in order to populate the
    internal result.

    Returns:
      A str. The first line is a JSON representation of the header. The
        following lines are JSON representations of each row.
    """
    output = [json.dumps(self.header, separators=(',', ':'))]
    for row in self._result:
      output.append(json.dumps(row, separators=(',', ':')))
    return  '\n'.join(output)
