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

Device inventory is potentially sourced from repositories such as:
  Flat files, databases or scraped from network configs.

This abstract data type defines the generic API for loading and querying devices
regardless of origin.

All calls to this library use the public methods here. Individual
implememtations override the corresponding private methods to provide
source specific support.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import collections
import re
import sre_constants
import threading
from absl import flags
from absl import logging

TILDE_COMMAND_HELP = {
    'attributes': """
    Filter targets based on an attribute of the device.
    First argument is attribute name, the second is the value.
    If a attribute value is prefixed with a '^' then it is
    treated as a regexp and implicitly ends with '.*$'.
    If command is appended with {APPEND} then adds to current attribute value.
    A value of '^' resets the attribute filter to 'none'.
    Shortname: 'A'.""",

    'targets': """
    Set target devices to receive commands
    (hostnames or IP addresses, comma separated, no spaces).
    If a target is prefixed with a '^' then it is
    treated as a regexp and implicitly ends with '.*$'.
    Regexp target list is expanded against devices.
    If command is appended with {APPEND} then adds to current targets value."
    A target of '^' resets the list to 'none'.
    Shortname: 'T'.""",

    'maxtargets': """
    High water mark to prevent accidentally making changes to large numbers of
    targets. A value of 0, removes the restriction.""",

    'xattributes': """
    Omit targets that have the attribute of the same name as the first
    argument that matches a string or regexp from second argument.
    If command is appended with {APPEND} then adds to current xattributes value.
    Shortname: 'E'.""",

    'xtargets': """
    Omit targets that match a string or regexp from this list.
    If command is appended with {APPEND} then adds to current xtargets value.
    Shortname: 'X'.""",
}

DEFAULT_MAXTARGETS = 50
DEFAULT_XTARGETS = ''
DEVICE_ATTRIBUTES = {}

FLAGS = flags.FLAGS

flags.DEFINE_string(
    'targets', '',
    TILDE_COMMAND_HELP['targets'],
    short_name='T')

flags.DEFINE_integer(
    'maxtargets', DEFAULT_MAXTARGETS,
    TILDE_COMMAND_HELP['maxtargets'])

flags.DEFINE_string(
    'xtargets', DEFAULT_XTARGETS,
    TILDE_COMMAND_HELP['xtargets'],
    short_name='X')


# Data format of response.
CmdResponse = collections.namedtuple(
    'CmdResponse', ['uid', 'device_name', 'command', 'data', 'error'])


class Error(Exception):
  """Base class for errors."""


class AuthError(Error):
  """Inventory Authentication error."""


class InventoryError(Error):
  """General Inventory error."""


class DeviceAttribute(object):
  """Container for holding attribute of device and its associated values."""

  def __init__(self, attrib_name, default_value, valid_values, help_str,
               display_case='lower', command_flag=False):
    self._default_value = default_value
    self.help_str = help_str
    self.attrib_name = attrib_name
    self.valid_values = valid_values
    self.display_case = display_case
    self.command_flag = command_flag
    if self.command_flag:
      flags.DEFINE_string(self.attrib_name, default_value, help_str)

  def _GetDefault(self):
    if self.command_flag and hasattr(flags, self.attrib_name):
      return getattr(flags, self.attrib_name)
    else:
      return self._default_value

  default_value = property(_GetDefault)


class Inventory(object):
  """ADT Class for device inventory retrieval and command submission.

  Public classes should not require modification and should not be referenced
  directly here. They are simply thread safe wrappers for the private methods
  of the same name.

  Source specific instantiations of the class should replace private methods.

  Attributes:
    batch: Bool indicating that the inventory is being used non interactively.
    devices: A dict (keyed by string) of Device objects. Read-only.
    device_list: Array of device names satisfying the filters.
    source: String identifier of source of device inventory.
  """
  SOURCE = 'unknown'

  class Request(object):
    """Holds a request named dictionary and wrapped with a uid."""
    UID = 0    # Each request has an identifier

    def __init__(self):
      Inventory.Request.UID += 1
      self.uid = Inventory.Request.UID
      self.target = None
      self.command = None
      self.mode = None

  def __init__(self, batch=False):
    """Initialise thread safe access to data to support async calls."""

    self.batch = batch
    # Devices keyed on device name.
    # Each value is a dictionary of attribute/value pairs.
    # If we have already loaded the devices, don't do it again.
    if not hasattr(self, '_devices'):
      self._devices = None
    # List of device names.
    self._device_list = None
    # Filters and exclusions added by this library.
    self._filters = {'targets': ''}
    self._exclusions = {'xtargets': ''}
    # Store literal strings and compiled regexps in dedicated dictionary
    # Use to accelerate matching against devices when buidling device_list
    self._literals_filter = {}
    self._compiled_filter = {}
    self._lock = threading.Lock()
    self._devices_loaded = threading.Event()
    self._devices_loaded.set()
    self._maxtargets = FLAGS.maxtargets

    # Filters and exclusions added by this library.
    logging.debug('Device attributes statically defined: "%s".',
                  DEVICE_ATTRIBUTES.keys())
    for attr in DEVICE_ATTRIBUTES:
      if attr == 'flags':
        # TODO(harro): Add support for filtering on flag values.
        continue
      self._filters[attr] = ''
      self._exclusions['x' + attr] = ''

    if not batch:
      # Load full device inventory (once) if we are interactive.
      self.LoadDevices()
      logging.debug('Device inventory load triggered for interactive mode.')

  ############################################################################
  # Thread safe public methods and properties.                               #
  ############################################################################

  def CreateCmdRequest(self, target, command, mode):
    """Creates command request for sending to device manager.

    The command request object created should satisfy the format required
    by the device manager in order to retrieve the command result from a device.

    Each request object must be assigned a unique 'uid' attribute - unique
    within the context of all pending requests and all requests that have not
    yet been rendered to the user. The device manager may generate this ID,
    otherwise CreateCmdRequest may add it. We have no way of determining
    if a result has been displayed (and the uid freed) however something like
    a monotomically increasing 32bit number would suffice.

    Some devices support multiple commandline modes or CLI interpretors
    e.g. router CLI and sub-system unix cli.
    The mode can be used by the device manager to execute the command on the
    appropriate CLI.

    Args:
      target: device to send command to.
      command: string single commandline to send to each device.
      mode: commandline mode to submit the command to.
    Returns:
      List of request objects.
    """
    with self._lock:
      return self._CreateCmdRequest(target, command, mode)

  def GetDevices(self):
    """Returns a dict of Device objects. Blocks until devices have loaded."""
    with self._lock:
      return self._GetDevices()

  def GetDeviceList(self):
    """Returns a list of Device names."""
    with self._lock:
      return self._GetDeviceList()

  def LoadDevices(self):
    """Loads Devices from external store.

    Stores data in _devices in a format like:
    {'devicename1: Device(attribute1='value1',
                          attribute2='value2',
                          ... ),
     'devicename2: Device('attribute1='value3',
                          ... ),
     ...
    }
    """

    with self._lock:
      self._LoadDevices()

  def ReformatCmdResponse(self, response):
    """Formats command response into name value pairs in a dictionary.

    The device manager specific format of the response is transformed into a
    more generic dictionary format:

      {
        'device_name': Device name string
        'device': Corresponding entry for the device in the device inventory.
        'command': Command string issued to device
        'error': Optional error message string
        'data': Command response string, null if error string populated.
      }

    Args:
      response: device manager response object for a single device with a
                uid that corresponds to uid of original request.
    Returns:
      Dictionary representation of command response.
    """
    return self._ReformatCmdResponse(response)

  def RegisterCommands(self, cmd_register):
    """Add module specific command support to TCLI."""

    # Register common to any inventory source.
    cmd_register.RegisterCommand('attributes', TILDE_COMMAND_HELP['attributes'],
                                 max_args=2, append=True, regexp=True,
                                 inline=True, short_name='A',
                                 handler=self._CmdFilter,
                                 completer=self._CmdFilterCompleter)
    cmd_register.RegisterCommand('targets', TILDE_COMMAND_HELP['targets'],
                                 append=True, regexp=True, inline=True,
                                 short_name='T', default_value=FLAGS.targets,
                                 handler=self._CmdFilter)
    cmd_register.RegisterCommand('maxtargets', TILDE_COMMAND_HELP['maxtargets'],
                                 default_value=FLAGS.maxtargets,
                                 handler=self._CmdMaxTargets)
    cmd_register.RegisterCommand('xattributes',
                                 TILDE_COMMAND_HELP['xattributes'],
                                 max_args=2, append=True, regexp=True,
                                 inline=True, short_name='E',
                                 handler=self._CmdFilter,
                                 completer=self._CmdFilterCompleter)
    cmd_register.RegisterCommand('xtargets', TILDE_COMMAND_HELP['xtargets'],
                                 append=True, regexp=True, inline=True,
                                 short_name='X', default_value=FLAGS.xtargets,
                                 handler=self._CmdFilter)

    # Register commands specific to a source.
    for attribute in DEVICE_ATTRIBUTES.values():
      if attribute.command_flag and attribute.attrib_name in FLAGS:
        default_value = getattr(FLAGS, attribute.attrib_name)
      else:
        default_value = attribute.default_value
      cmd_register.RegisterCommand(attribute.attrib_name,
                                   attribute.help_str,
                                   default_value=default_value,
                                   append=True, inline=True, regexp=True,
                                   handler=self._CmdFilter)

  def SendRequests(self, requests_callbacks, deadline=None):
    """Submits command requests to device manager.

    Submit the command requests to the device manager for resolution.
    Each tuple contains a request object created by CreateCmdRequest and a
    corresponding callback that expects a response object with a matching uid
    attribute.

    As command results from devices are collected then the callback function
    is to be executed by the device manager.

    The response object structure is unspecified but corresponds to a response
    from a single device and must be parsable by ReformatCmdResponse.

    Args:
      requests_callbacks: List of tuples.
        Each tuple pairs a request object with a callback function.
      deadline: An optional int, the deadline to set when sending the request.
    Returns:
      None
    """
    return self._SendRequests(requests_callbacks, deadline=deadline)

  def ShowEnv(self):
    """Show command settings."""
    with self._lock:
      return self._ShowEnv()

  # Obtains devices when they have been loaded.
  devices = property(GetDevices)
  # Returns a sorted list targets.
  device_list = property(GetDeviceList)
  # pylint: disable=protected-access
  targets = property(lambda self: self._filters['targets'])

  ############################################################################
  # Methods related to registering/executing TCLI CLI command extensions.    #
  ############################################################################

  # Command handlers have identical arguments.
  # pylint: disable=unused-argument
  def _CmdFilterCompleter(self, word_list, state):
    """Returns a command completion list for valid attribute completions."""

    # Only complete on the first word, the attribute name.
    if not word_list or len(word_list) > 1:
      return None

    # We are only interested in the first word.
    word = word_list[0]
    # Inter word gap, so show full list.
    if word == ' ':
      word = ''
    completer_list = []
    for attrib in self.ATTRIBUTES:
      if attrib.startswith(word):
        completer_list.append(attrib)
    completer_list.sort()

    if state < len(completer_list):
      return completer_list[state]
    else:
      return None

  def _CmdFilter(self, command_name, args, append=False):
    """Updates or displays inventory filter.

    Args:
      command_name: str command name entered by user (minus tilde prefix).
      args: list of positional args.
      append: bool indicating that command had a suffix to append data.
    Returns:
      None or String to display.
    Raises:
      ValueError: If called on unknown attribute.
    """

    if command_name in ('attributes', 'xattributes'):
      if not args:
        # Display value of all filters.
        if command_name == 'attributes':
          for attr in self._filters:
            self._CmdFilter(attr, [], append)
        else:
          for attr in self._exclusions:
            self._CmdFilter(attr, [], append)
      else:
        if command_name == 'attributes':
          self._CmdFilter(args[0], args[1:], append)
        else:
          # 'xattributes' so add 'x' prefix to attribute.
          self._CmdFilter('x' + args[0], args[1:], append)
      return

    # Filter may be inclusive, or exclusive.
    if command_name in self._filters:
      filter_value = self._filters
      caps = 1
    elif command_name in self._exclusions:
      filter_value = self._exclusions
      caps = 2
    else:
      raise ValueError('Device attribute "%s" invalid.' % command_name)

    if not args:
      return self._FormatLabelAndValue(
          command_name, filter_value[command_name], caps=caps)
    filter_string = args[0]
    if append and filter_string and filter_value[command_name]:
      filter_string = ','.join([filter_value[command_name], filter_string])
    filter_value[command_name] = self._ChangeFilter(command_name, filter_string)

  def _CmdMaxTargets(self, command_name, args, append=False):
    """Updates or displays maxtargets filter.

    Args:
      command_name: str command name entered by user (minus tilde prefix).
      args: list of positional args.
      append: bool indicating that command had a suffix to append data.
    Returns:
       String to display
    Raises:
      ValueError: If argument cannot be interpreted as a cardinal. Or is less
        than the current device list.
    """
    if not args:
      return self._FormatLabelAndValue(command_name, self._maxtargets)

    try:
      maxtargets = int(args[0])
      if maxtargets < 0:
        raise ValueError
    except ValueError:
      raise ValueError('Max Targets is a non-cardinal value: "%s"' % maxtargets)

    self._maxtargets = maxtargets
  # pylint: enable=unused-argument

  def _Flatten(self, container):
    """Flattens arbitrarily deeply nested lists."""

    for i in container:
      if isinstance(i, list) or isinstance(i, tuple):
        for j in self._Flatten(i):
          yield j
      else:
        yield i

  def _ChangeFilter(self, filter_name, arg):
    """Update inventory filter.

    Sets the new value for the filter string. Only called against valid
    filter/exclusion names.

    Args:
      filter_name: str filter or exclusion name.
      arg: str new value for filter.
    Raises:
      ValueError: If literal device name specified and device is unknown.
    Returns:
      The filter string 'arg'.
    """

    # Clearing a filter requires no content validation.
    if not arg or arg == '^':
      arg = ''
      (literals, compiled) = (None, None)
    else:
      # Split the string into literal and regexp elements.
      # Filter matching is case insensitive.
      (literals, compiled) = self._DecomposeFilter(arg, ignore_case=True)

      if not self.batch and literals:
        attribute = filter_name
        # Trim off the 'x' prefix for matching exclusions against attributes.
        if filter_name.startswith('x'):
          attribute = attribute[1:]

        if attribute == 'targets':
          # Warn user if literal is unknown, skip warning in batch mode
          # as it is less valuable in this context and would trigger a
          # re-retrieval of the inventory.
          validate_list = self._GetDevices().keys()

        elif (attribute in DEVICE_ATTRIBUTES and
              DEVICE_ATTRIBUTES[attribute].valid_values):
          validate_list = DEVICE_ATTRIBUTES[attribute].valid_values
        else:
          # Without a specific list of valid values, check that at least one
          # device matches.
          # TODO(harro): For filter responsiveness reasons we may drop this.
          validate_list = [getattr(dev, attribute, None)
                           for dev in self._GetDevices().values()]
          validate_list = set(self._Flatten(validate_list))

        validate_list = [value.lower() for value in validate_list]

        # Confirm that static content matches a valid entry.
        unmatched_literals = set(literals).difference(set(validate_list))
        if unmatched_literals:
          raise ValueError('Non-regexp filter entry "%s" is not valid.' %
                           unmatched_literals)

    self._ChangeDeviceListFilters(filter_name, literals, compiled)
    return arg

  def _ChangeDeviceListFilters(self, filter_name, literals, compiled):
    """Assigns values to filters used to derive the device_list.

    Store the literal device names and compiled regular expressions
    in respective dictionary.

    Clear the device_list so the next time it is queried it will be built
    from these newly updated filter content.

    Args:
      filter_name: str filter or exclusion name.
      literals: list of strings that represent individual devices.
      compiled: List of compiled regular expressions.
    """

    # Shared dictionaries for filters and exclusions.
    self._literals_filter[filter_name] = literals
    self._compiled_filter[filter_name] = compiled
    # Clear device list to trigger re-application of filter.
    self._device_list = None

  def _DecomposeFilter(self, filter_string, ignore_case=False):
    """Returns a tuple of compiled and literal lists.

    For device names, they are case insensitive so the compiled
    regular expressions ignores case.

    Args:
      filter_string: str filter supplied by the user
      ignore_case: bool for if the newly compiled regexps should ignore case.
    Raises:
      ValueError if a regexp is not valid.
    Returns:
      Tuple of lists to use in matching operations.
    """

    literal_match = []
    re_match = []
    for filter_item in filter_string.split(','):
      # Spaces have no meaning, as filters never have spaces in them.
      filter_item = filter_item.strip()
      if filter_item:
        if filter_item.startswith('^'):
          # Add implicit '$' to regexp.
          if not filter_item.endswith('$'):
            filter_item += '$'
          try:
            # Filter expressions are case insensitive.
            if ignore_case:
              re_match.append(re.compile(filter_item, re.IGNORECASE))
            else:
              re_match.append(re.compile(filter_item))
          except sre_constants.error:
            raise ValueError('Argument regexp %r is invalid' % filter_item)
        else:
          if ignore_case:
            literal_match.append(filter_item.lower())
          else:
            literal_match.append(filter_item)

    return (literal_match, re_match)

  def _FormatLabelAndValue(self, label, value, caps=1):
    """Returns string with capitilized label and corresponding value."""

    if caps > len(label):
      caps = len(label)
    label = label[0:caps].upper() + label[caps:]
    return '%s: %s' % (label, value)

  def _ShowEnv(self):
    """Extends show environment to display filters and exclusions."""

    indent = '  '
    # Add headline to indicate this display section is from this module.
    display_string = ['Inventory:']
    display_string.append(indent + 'Max Targets: %d' % self._maxtargets)
    # Sub section for Filters and Exclusions.
    display_string.append(indent + 'Filters:')
    # Increase indent.
    indent += '  '
    # TODO(harro): Will break a filter doesn't have corresponding exclusion.
    for f, x in zip(sorted(self._filters), sorted(self._exclusions)):
      # Create paired entries like 'Targets: ..., XTargets: ...'
      display_string.append('%s%s, %s' % (
          indent,
          self._FormatLabelAndValue(f, self._filters[f]),
          self._FormatLabelAndValue(x, self._exclusions[x], caps=2)))

    return '\n'.join(display_string)

  ############################################################################
  # Methods related to managing and serving the device inventory.            #
  ############################################################################

  def _GetDevices(self):
    """Returns a dict of Device objects. Blocks until devices have loaded."""

    if self.batch and not self._devices:
      # In batch mode we retrieve the devices from backend each time.
      self._LoadDevices()
      logging.debug('GetDevices: triggered load of devices.')

    # Wait for any pending device load.
    self._devices_loaded.wait()
    if not self._devices:
      raise InventoryError(
          'Device inventory data failed to load or no devices found.')
    return self._devices

  def _GetDeviceList(self):
    """Returns a list of Device name."""

    # A value of 'None' means the list needs to be built first.
    if self._device_list is not None:
      return self._device_list
    return self._BuildDeviceList()

  def _Excluded(self, devicename, device_attrs):
    """Returns true if device matches an exclusions filter."""

    for attr in self._exclusions:
      # Blank filters are ignored.
      if not self._exclusions[attr]:
        continue
      # For xtargets we match on device name.
      if attr == 'xtargets':
        attr_value = devicename
      else:
        # Strip 'x' prefix.
        stripped_attr = attr[1:]
        attr_value = getattr(device_attrs, stripped_attr, None)
        # Devices without this attribute are ignored.
        if attr_value is None:
          continue

      # If the attribute matches then this is a device to exclude.
      if self._Match(attr, attr_value):
        return True

    return False

  def _Included(self, devicename, device_attrs):
    """Returns true if device matches all filters for inclusion."""

    for attr in self._filters:
      # Blank filters are ignored.
      if not self._filters[attr]:
        continue
      # For targets we match on device name.
      if attr == 'targets':
        attr_value = devicename
      else:
        attr_value = getattr(device_attrs, attr, None)
        # Devices without this attribute are not a match.
        if attr_value is None:
          return False

      # If the attribute does not match then this device is not included.
      if not self._Match(attr, attr_value):
        return False

    return True

  def _BuildDeviceList(self):
    """Parses devices against filters and builds a device list.

    Builds the device_list by matching each device against the filters and
    exclusions.

    Returns:
      Array of device names that passed the filters.
    Raises:
      ValueError: if size of device list exceeds max targets limit.
    """

    self._device_list = []
    # Special case, null targets doesn't match any devices.
    if not self._filters['targets']:
      return self._device_list

    device_list = []
    for (devicename, d) in self._GetDevices().items():
      # Skip devices that match any non-blank exclusions.
      if self._Excluded(devicename, d):
        continue

      # Include devices that match all filters (blank is a match).
      if self._Included(devicename, d):
        device_list.append(devicename)

    if self._maxtargets and len(device_list) > self._maxtargets:
      raise ValueError('Target list exceeded Maximum targets limit of: %s.' %
                       self._maxtargets)
    self._device_list = device_list
    logging.debug('Device List length: %d', len(self._device_list))
    return self._device_list

  def _AsyncLoadDevices(self):
    try:
      self._FetchDevices()
    finally:
      self._devices_loaded.set()

  def _FetchDevices(self):
    """Fetches Devices from external store ."""

    raise NotImplementedError

  def _LoadDevices(self):
    """Loads Devices from external store."""

    # Wait for any pending load to complete.
    self._devices_loaded.wait()
    # Block reads of the devices until loaded.
    self._devices_loaded.clear()
    self._devices_thread = threading.Thread(name='Device loader',
                                            target=self._AsyncLoadDevices)
    self._devices_thread.setDaemon(True)
    self._devices_thread.start()

  def _Match(self, attr, attr_value):
    """Returns if a attribute value matches the corresponding filter."""

    # If we have list of attributes, recurse down to find match.
    if isinstance(attr_value, list):
      for attr_elem in attr_value:
        if self._Match(attr, attr_elem):
          return True
      return False

    if (attr in self._literals_filter and self._literals_filter[attr] and
        attr_value in self._literals_filter[attr]):
      return True
    if attr in self._compiled_filter:
      for regexp in self._compiled_filter[attr]:
        if regexp.match(attr_value):
          return True
    return False

  #############################################################################
  # Methods related to sending commands and receiving responses from devices. #
  #############################################################################

  def _CreateCmdRequest(self, target, command, mode):
    """Creates command request for Device Accessor."""

    request = self.Request()
    request.target = target
    request.command = bytes(command, 'utf-8').decode('unicode_escape')
    request.mode = mode
    logging.debug("Built Cmd Request: '%s' for host: '%s'.", command, target)
    return request

  def _ReformatCmdResponse(self, response):
    """Formats command response into name value pairs in a dictionary."""
    raise NotImplementedError

  def _SendRequests(self, requests_callbacks, deadline=None):
    """Submit command requests to device manager."""
    raise NotImplementedError
