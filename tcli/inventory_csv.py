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

"""Loads device inventory for use by TCLI.

Implements API defined in inventory_base in order to pull devices from CSV file.

If devices are kept in a database or other, non CSV, inventory source then this
file can be replaced by a library that handles that source.
This can be achieved by copying the file and replacing the _FetchDevices
function.

Note: Uses canned responses.
The function _SendRequests should be edited to use the appropriate device
server, which may be one of:

          https://pypi.org/project/notch.agent/
          https://pypi.org/project/rancidcmd/
          https://github.com/saltstack/salt
          https://pypi.org/project/netmiko/

... or something else entirely.
"""

import collections
import os
import typing
from absl import flags
from absl import logging
from tcli import inventory_base
from tcli.inventory_base import CmdRequest
from tcli.inventory_base import AuthError       # pylint: disable=unused-import
from tcli.inventory_base import InventoryError  # pylint: disable=unused-import

## CHANGEME
## The fields in the CSV that we want content to be filtered on.
## they must match the column headers defined in the inventory file.
## Care should be taken when setting command_flag to true, first check that
## the flag does not clash with flags defined elsewhere in the TCLI modules.

## Note: Two values will be created for each attribute. The second will be
## prefixed with an 'x' to be used for inverse matching (exclusions).
DEVICE_ATTRIBUTES = inventory_base.DEVICE_ATTRIBUTES
#TODO(harro): Prevent this from being overridden by inventory_base.__init__
DEVICE_ATTRIBUTES['pop'] = inventory_base.Attribute(
    'pop', '', None,
    '\n    Limit device lists to specific pop/s')
DEVICE_ATTRIBUTES['realm'] = inventory_base.Attribute(
    'realm', 'lab', ['prod', 'lab'],
    '\n    Limit the device list to a specific realm/s.')
DEVICE_ATTRIBUTES['vendor'] = inventory_base.Attribute(
    'vendor', '', ['cisco', 'juniper'],
    '\n    Limit device lists to a specific vendor/s', display_case='title')

# Set here if known.
# In the case here this will be overwritten once the CSV content is known.
DEVICE = inventory_base.DEVICE

# TODO(harro): Handle the 'flags' attribute and filtering.

## CHANGEME
## To get up and running we use test data. Replace this path with the location
## of the device inventory CSV file that you wish to use.
DEFAULT_CSV_FILE = os.path.join(os.path.dirname(__file__),
                                'testdata', 'test_devices')
## CHANGEME
## Where we store the canned responses.
DEFAULT_RESPONSE_DIRECTORY = os.path.join(
    os.path.dirname(__file__), 'testdata', 'device_output')

## CHANGEME
## Any devices to exclude by default for all users, should be defined here.
## Add to the end of the list any additional expressions that should be
## implicitly filtered by default.
DEFAULT_XTARGETS = ','.join([inventory_base.DEFAULT_XTARGETS,])

FLAGS = flags.FLAGS

flags.DEFINE_string(
    'inventory', DEFAULT_CSV_FILE,
    'Location of file containing the CSV list of devices.')

# TODO(harro): Support using a different string for separating flags.
flags.DEFINE_string('separator', ', ',
                    'String sequence that separates entries in the CSV file.')

CmdResponse = inventory_base.CmdResponse

class Inventory(inventory_base.Inventory):
  """CSV Inventory Class.

    Attributes:
      source: String identifier of source of device inventory.
  """

  SOURCE = 'csv'

  def _ParseDevicesFromCsv(
      self, buf:typing.TextIO,
      separator:str=',') -> dict[str, typing.NamedTuple]:
    """Parses buffer into tabular format.

    Strips off comments (preceded by '#').
    Parses and indexes by first line (header).

    Args:
      buf: String file buffer containing CSV data.
      separator: String that CSV is separated by.

    Returns:
      Returns a dictionary of device attributes, keyed on device name.

    Raises:
      ValueError: A parsing error occurred.
    """

    # If then the following routine could _almost_ be replaced with
    # the following lines:
    #   import csv
    #   self._devices = csv.DictReader(filter(lambda row: row[0]!='#', buf),
    #                                  delimiter=separator, restkey='flags')
    #
    # But we need the data to be in the following format:
    # {'devicename1: Device(attribute1='value1',
    #                       attribute2='value2',
    #                       ... ),
    #  'devicename2: Device('attribute1='value3',
    #                       ... ),
    # ...
    # }
    #
    # So we built an ordered dict of NamedTuples (python 3.6)
    # We enforce 'device' as the header of the first column and 'flags' as
    # the header of an optional list as the last column.

    # Read in the header line which we will use to name the fields.
    row = buf.readline()
    header_str = ''
    while row and not header_str:
      # Remove comments.
      header_str = row.split('#')[0].strip()
      if not header_str:
        row = buf.readline()

    # Header line found, split into fields.
    header_list = header_str.split(separator)
    # Strip excess whitespace.
    header_list = [l.strip() for l in header_list]
    if header_list[0] != 'device':
      raise ValueError(
          'Column named "device" must be first column of header.\n'
          'Found: "%s".' % header_str)
    # Strip device, it will be used for the index.
    header_list = header_list[1 :]
    row_length = len(header_list)
    # Data format for a single device entry.
    DEVICE = collections.namedtuple('Device', header_list)

    # pylint: enable=invalid-name
    devices = {}
    # xreadlines would be better but not supported by StringIO for testing.
    for row in buf:
      # Support commented lines, provide '#' is first character of line.
      row = row.strip()
      if not row or row.startswith('#'):
        continue
      row = row.split(separator)
      # Strip excess whitespace.
      row = [l.strip() for l in row]
      (device_name, row) = (row[0], row[1 :])
      if header_list[-1] == 'flags':
        # Provided the last header is 'flags' then accept extra columns.
        # Entries that trail on the rhs are gathered into a list under flags.
        (device_flags, row) = (row[row_length -1:], row[:row_length -1])
        row.append(device_flags) # type: ignore
      try:
        devices[device_name] = DEVICE(*row)
      except TypeError:
        raise ValueError('Final column header must be "flags" if'
                         ' rows are to be variable length.\n'
                         'Found: %s' % header_str)
    logging.debug('Parsed "%s" devices from CSV file.', len(devices))
    return devices

  def _FetchDevices(self):
    """Fetches Devices from a file."""

    with open(FLAGS.inventory) as csv_file:
      logging.debug('Reading device inventory for file "%s".', FLAGS.inventory)
      self._devices = self._ParseDevicesFromCsv(csv_file)

  def SendRequests(
      self, requests_callbacks:list[tuple[CmdRequest, typing.Callable]],
      deadline: float|None=None) -> None:
    """Submit command requests to device connection service."""

    for (request, callback) in requests_callbacks:
      # Routine supports sending commands as non blocking async calls.
      # Effective in cases where device access is controlled by a service.
      # Here we simply open a file with canned responses and return them
      # iteratively.

      # Rather than canned responses, users should make use of a device accessor
      # library such as:

      data, error = '', ''
      file_name = request.target + '_' + request.command.replace(' ', '_')
      file_path = os.path.join(DEFAULT_RESPONSE_DIRECTORY, file_name)
      try:
        with open(file_path) as fp:
          data = fp.read()
      except IOError:
        error = ('Failure to retrieve response from device "%s",'
                 ' for command "%s".' % (request.target, request.command))
      response = inventory_base.CmdResponse(uid=request.uid,
                                            device_name=request.target,
                                            command=request.command,
                                            data=data,
                                            error=error)
      # Normally the commands would be submitted to a device server and the
      # responses returned in callbacks. For canned responses we built the
      # response and call the callback straight away.
      callback(response)
