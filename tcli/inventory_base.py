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

import collections
import re
import threading
import typing
from absl import flags
from absl import logging

# Global vars so flags.FLAGS has inventroy intelligence in the main program.

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

# Maximum number of devices that can be the recipient of a command.
# Can (and should) be overriden in the child module or the command line.
DEFAULT_MAXTARGETS = 50
# System default for what device targets to exclude form matching.
# Set this to avoid overly matching on devices that may rarely be an
# intentional target of commands (but you still want to be able to send
# commands to them as the exception rather than the rule).
DEFAULT_XTARGETS = ''
# System wide set of device attributes that a device may have.
# Populated by the child module that actually populates the inventory.
DEVICE_ATTRIBUTES = {}
# The single device entry in the inventory. Set in child module.
DEVICE = None

# TODO(harro): Define CmdRequest here too?
# Data format of response.
CmdResponse = collections.namedtuple(
    'CmdResponse', ['uid', 'device_name', 'command', 'data', 'error'])

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
  """Class for device inventory retrieval and command submission.

  Public classes should not require modification and should not be referenced
  directly here. They are simply thread safe wrappers for the private methods
  of the same name.

  Source specific instantiations of the class should replace private methods.

  Attributes:
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
      self.target = ''
      self.command = ''
      self.mode = ''

  def __init__(self):
    """Initialise thread safe access to data to support async calls."""

    # Devices keyed on device name.
    # Each value is a dictionary of attribute/value pairs.
    # If we have already loaded the devices, don't do it again.
    if not hasattr(self, '_devices'):
      self._devices = {}
    # List of device names.
    self._device_list = None
    # Filters and exclusions added by this library.
    self._inclusions = {'targets': ''}
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
                  DEVICE_ATTRIBUTES)
    for attr in DEVICE_ATTRIBUTES:
      # TODO(harro): Add support for filtering on flag values.
      if attr == 'flags': continue
      self._inclusions[attr] = ''
      self._exclusions['x' + attr] = ''


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
      return self._GetDevices()

  def GetDeviceList(self):
    """Returns a filtered list of Devices."""
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

    # Register commands common to any inventory source.
    cmd_register.RegisterCommand('attributes', TILDE_COMMAND_HELP['attributes'],
                                 max_args=2, append=True, regexp=True,
                                 inline=True, short_name='A',
                                 handler=self._AttributeFilter,
                                 # TODO(harro): Change completer.
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
                                 handler=self._AttributeFilter,
                                 # TODO(harro): Change completer.
                                 completer=self._CmdFilterCompleter)
    cmd_register.RegisterCommand('xtargets', TILDE_COMMAND_HELP['xtargets'],
                                 append=True, regexp=True, inline=True,
                                 short_name='X', default_value=FLAGS.xtargets,
                                 handler=self._CmdFilter)

    # Register commands specific to this inventory source.
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
  targets = property(lambda self: self._inclusions['targets'])

  ############################################################################
  # Methods related to registering/executing TCLI CLI command extensions.    #
  ############################################################################

  # Command handlers have identical arguments.
  # pylint: disable=unused-argument
  def _CmdFilterCompleter(self, word_list, state):
    """Returns a command completion list for valid attribute completions."""

    # Only complete on a single word, the attribute name.
    #TODO(harro): Why accept a list if we only support matching the first word?
    if not word_list or len(word_list) > 1:
      return None

    # We are only interested in the first word.
    word = word_list[0]
    # Inter word gap, so show full list.
    if word == ' ':
      word = ''
    completer_list = []
    for attrib in DEVICE_ATTRIBUTES:
      if attrib.startswith(word):
        completer_list.append(attrib)
    completer_list.sort()

    if state < len(completer_list):
      return completer_list[state]
    else:
      return None

  def _CmdFilter(self, command_name: str, args: list[str], append=False) -> str:
    """Updates or displays target device inventory filter.

    Args:
      command_name: Command entered by the user (minus tilde prefix).
      args: list of positional args after the command.
      append: bool indicating that filters args are to be appended.
    Returns:
      String to display.
    Raises:
      ValueError: If called on unknown attribute.
    """

    if not (command_name in self._inclusions or 
            command_name in self._exclusions):
      raise ValueError('Command "%s" invalid.' % command_name)

    # Filter may be inclusive, or exclusive.
    if command_name in self._inclusions:
      filters = self._inclusions
      # Do we want to captialise the first one or two characters.
      caps = 1
    else:
      filters = self._exclusions
      caps = 2

    if not args:
      return self._FormatLabelAndValue(
          command_name, filters[command_name], caps=caps)

    filter_string = args[0]   # TDOD(harro): Raise exception is args >1 ?
    # Appending a new filter string to an existing filter.
    if append and filter_string and filters[command_name]:
      filter_string = ','.join([filters[command_name], filter_string])
    #TDOD(harro): Replace _ChangeFilter with _AttributeFilter.
    filters[command_name] = self._ChangeFilter(command_name, filter_string)
    return ''

  def _AttributeFilter(self, command_name: str, args: list[str], append=False) -> str:
    """Updates or displays the inventory inclusions or exclusions (filters).

    Args:
      command_name: 'attributes' or 'xattributes'.
      args: list of positional args.
    Returns:
      String to display.
    Raises:
      ValueError: If called on unknown attribute.
    """

    if command_name not in ('attributes', 'xattributes'):
      raise ValueError('Command "%s" invalid.' % command_name)

    if args:
      # Update attribute filter/s.
      # TODO(harro): Can we set multiple attributes here by splitting the list?
      if command_name == 'attributes':
        self._CmdFilter(args[0], args[1 :], append)
      else:
        # 'xattributes' so add 'x' prefix to corresponding attribute.
        self._CmdFilter('x' + args[0], args[1 :], append)
      return ''

    # Display values of all device attribute filters.
    result = ''
    if command_name == 'attributes':
      attr_list = self._inclusions
    else: # xattributes
      attr_list = self._exclusions
    for attr in attr_list:
      result += self._CmdFilter(attr, [], append)
    return result

  def _CmdMaxTargets(self, command_name: str, args: list[str], append=False) -> str:
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
    return ''
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
    if not arg or arg in ('^', '^$'):
      arg = ''
      (literals, compiled) = (None, None)
    else:
      # Split the string into literal and regexp elements.
      # Filter matching is case insensitive.
      (literals, compiled) = self._DecomposeFilter(arg, ignore_case=True)

      if literals:
        attribute = filter_name
        # Trim off the 'x' prefix for matching exclusions against attributes.
        if filter_name.startswith('x'):
          attribute = attribute[1 :]

        if attribute == 'targets':
          # Warn user if literal is unknown.
          validate_list = self._GetDevices()

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

    Clear the device_list so the next time it is queried it will be rebuilt
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
          except re.error:
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
    label = label[0:caps].upper() + label[caps :]
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
    for f, x in zip(sorted(self._inclusions), sorted(self._exclusions)):
      # Create paired entries like 'Targets: ..., XTargets: ...'
      display_string.append('%s%s, %s' % (
          indent,
          self._FormatLabelAndValue(f, self._inclusions[f]),
          self._FormatLabelAndValue(x, self._exclusions[x], caps=2)))

    return '\n'.join(display_string) + '\n'

  ############################################################################
  # Methods related to building, managing and serving the device inventory.  #
  ############################################################################

  def _GetDevices(self) -> dict[str, typing.NamedTuple]:
    """Returns a dict of Device objects. Blocks until devices have loaded."""

    # Wait for any pending device loading.
    self._devices_loaded.wait()
    if not self._devices:
      raise InventoryError(
          'Device inventory data failed to load or no devices found.')
    return self._devices

  def _GetDeviceList(self) -> list[str]:
    """Returns a list of Device names."""

    # 'None' means the list needs to be built first.
    if self._device_list is None: return self._BuildDeviceList()
    return self._device_list
     

  def _FilterMatch(self, devicename: str, device_attrs: typing.NamedTuple,
                   exclude=False) -> bool:
    """Returns true if device matches the inclusion/exclusion filter."""

    filter = self._exclusions if exclude else self._inclusions
    prefix = 'x' if exclude else ''
    for attr in filter:
      # Blank filters are ignored.
      if not filter[attr]:
        continue
      
      # For xtargets we match on device name as the attributes value.
      if attr == prefix + 'targets':
        attr_value = devicename
      else:
        # Strip 'x' attribute prefix if an exclusion.
        stripped_attr = attr[1 :] if exclude else attr
        attr_value = getattr(device_attrs, stripped_attr, None)
        # Devices without this attribute are ignored.
        if not attr_value:
          continue

      matched = self._Match(attr, attr_value)
      # For exclusion, exclude as soon as one matches.
      if exclude:
        if matched:
          return True
      # For inclusion, don't include as soon as one doesn't match.
      else:
        if not matched:
          return False

    # If we get to here then match if an inclusion, or not if an exclusion.
    return not exclude

  def _BuildDeviceList(self) -> list[str]:
    """Parses device inventory against filters and builds a device list.

    Builds the device_list by matching each device against the filters and
    exclusions.

    Returns:
      Array of device names that passed the filters.
    Raises:
      ValueError: if size of device list exceeds max targets limit.
    """

    self._device_list = []
    # Special case, a null targets expression doesn't match any devices.
    if not self._inclusions['targets']:
      return self._device_list

    device_list = []
    for (devicename, d) in self._GetDevices().items():
      # Skip devices that match any non-blank exclusions.
      if self._FilterMatch(devicename, d, exclude=True):
        continue

      # Include devices that match all filters (blank is a match).
      if self._FilterMatch(devicename, d):
        device_list.append(devicename)

    if self._maxtargets and len(device_list) > self._maxtargets:
      raise ValueError('Target list exceeded Maximum targets limit of: %s.' %
                       self._maxtargets)

    # Cache the result.
    self._device_list = device_list
    logging.debug('Device List length: %d', len(self._device_list))
    return self._device_list

  def _AsyncBuildDeviceData(self) -> None:
    try:
      self._FetchDevices()
    finally:
      self._devices_loaded.set()

  def _FetchDevices(self) -> None|NotImplementedError:
    """Fetches Devices from external store ."""

    raise NotImplementedError

  def _LoadDevices(self) -> None:
    """Loads Devices from external store."""

    # Wait for any pending load to complete.
    self._devices_loaded.wait()
    # Block reads of the devices until loaded.
    self._devices_loaded.clear()
    # Collect result in a thread so it can complete in the background.
    self._devices_thread = threading.Thread(name='Device loader',
                                            target=self._AsyncBuildDeviceData,
                                            daemon=True)
    self._devices_thread.start()

  def _Match(self, attr: str, attr_value: str | list[str] | list[list[str]]) -> bool:
    """Returns if a attribute value matches the corresponding filter."""

    # If we have a list of attributes, recurse down to find match.
    # This might be the case if matching the presence of a Flag.
    if isinstance(attr_value, list):
      for attr_elem in attr_value:
        if self._Match(attr, attr_elem):
          return True
      return False

    # Is there this attribute, is it set and does it match?
    if (attr in self._literals_filter and self._literals_filter[attr] and
        attr_value in self._literals_filter[attr]):
      return True
    
    # Regular expressions are held separately as compiled expressions.
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

class AttributeFilter(object):
  """Commands and data for matching attribute filters against devices."""
