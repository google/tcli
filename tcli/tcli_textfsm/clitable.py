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

"""Clitable that supports additional TextFSM Value Attributes."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from absl import flags
from tcli.tcli_textfsm import textfsm
from textfsm import clitable
from textfsm import texttable
from textfsm.clitable import CliTableError
from textfsm.clitable import Error
from textfsm.clitable import IndexTableError  # pylint: disable=unused-import


FLAGS = flags.FLAGS


class DeviceError(Error):
  """Nest device query error."""


class QueryError(Error):
  """Gnetch device query error."""


class CliTable(clitable.CliTable):
  """Class that reads CLI output and parses into tabular format.

  Reads an index file and uses this to map command strings to templates and then
  uses the TextFSM to parse the command output (raw) into a tabular format.

  The superkey is the set of columns that contain data that uniquely defines the
  row, the key is the row number otherwise. This is typically gathered from the
  templates 'Key' value but is extensable.

  Attributes:
    raw: String, Unparsed command string from device/command.
    index_file: String, file where template/command mappings reside.
    template_dir: String, directory where index file and templates reside.
  """

  def ParseCmd(self, cmd_input, attributes=None, templates=None, verbose=True):
    """Creates a TextTable table of values from cmd_input string.

    Parses command output with template/s. If more than one template is found
    subsequent tables are merged if keys match (dropped otherwise).

    Args:
      cmd_input: String, Device/command response.
      attributes: Dict, attribute that further refine matching template.
      templates: String list of templates to parse with. If None, uses index
      verbose: Boolean, if to display all or only some columns.

    Raises:
      CliTableError: A template was not found for the given command.
    """
    # Store raw command data within the object.
    self.raw = cmd_input

    if not templates:
      # Find template in template index.
      row_idx = self.index.GetRowMatch(attributes)
      if row_idx:
        templates = self.index.index[row_idx]['Template']
      else:
        raise CliTableError('No template found for attributes: "%s"' %
                            attributes)

    template_files = self._TemplateNamesToFiles(templates)
    # Re-initialise the table.
    self.Reset()
    self._keys = set()
    self.table = self._ParseCmdItem(self.raw, verbose=verbose,
                                    template_file=template_files[0])

    # Add additional columns from any additional tables.
    for tmplt in template_files[1:]:
      self.extend(self._ParseCmdItem(self.raw, verbose=verbose,
                                     template_file=tmplt), set(self._keys))

  def _ParseCmdItem(self, cmd_input, template_file=None, verbose=True):
    """Creates Texttable with output of command.

    Args:
      cmd_input: String, Device response.
      template_file: File object, template to parse with.
      verbose: Boolean, if to display all or only some columns.

    Returns:
      TextTable containing command output.

    Raises:
      CliTableError: A template was not found for the given command.
    """
    # Build FSM machine from the template.
    fsm = textfsm.TextFSM(template_file, verbose=verbose)
    if not self._keys:
      self._keys = set(fsm.GetValuesByAttrib('Key'))

    # Pass raw data through FSM.
    table = texttable.TextTable()
    table.header = fsm.header

    # Fill TextTable from record entries.
    for record in fsm.ParseText(cmd_input):
      table.Append(record)
    return table
