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
from tcli.command_parser import APPEND

# Global vars so flags.FLAGS has inventroy intelligence in the main program.

TILDE_COMMAND_HELP = {
    'attributes': f"""
    Filter targets based on an attribute of the device. First argument is
    attribute name, the second is the value. If a attribute value is prefixed
    with a '^' then it is treated as a regexp and implicitly ends with '.*$'.
    If command is appended with {APPEND} then adds to current attribute value.
    A value of '^' resets the attribute filter to 'none'.
    Shortname: 'A'.""",

    'targets': f"""
    Set target devices to receive commands (hostnames or IP addresses,
    comma separated, no spaces). If a target is prefixed with a '^' then it is
    treated as a regexp and implicitly ends with '.*$'. Regexp target list is
    expanded against devices. If command is appended with {APPEND} then adds to
    current targets value."
    A target of '^' resets the list to 'none'.
    Shortname: 'T'.""",

    'maxtargets': f"""
    High water mark to prevent accidentally making changes to large numbers of
    targets. A value of 0, removes the restriction.""",

    'xattributes': f"""
    Omit targets that have the attribute of the same name as the first
    argument that matches a string or regexp from second argument.
    If command is appended with {APPEND} then adds to current xattributes value.
    Shortname: 'E'.""",

    'xtargets': f"""
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

# Data format of response.
CmdResponse = collections.namedtuple(
    'CmdResponse', ['uid', 'device_name', 'command', 'data', 'error'])

FLAGS = flags.FLAGS

flags.DEFINE_integer(
    'maxtargets', DEFAULT_MAXTARGETS,
    TILDE_COMMAND_HELP['maxtargets'])

flags.DEFINE_string(
    'targets', '',
    TILDE_COMMAND_HELP['targets'],
    short_name='T')

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


class Attribute(object):
  """Object for device attributes to be used as cli commands for filtering."""
  type Case = typing.Union[typing.Literal['lower'],
                           typing.Literal['upper'],
                           typing.Literal['title']]

  #TODO(harro): Use getters / setters here an hide internals.
  def __init__(
      self, name: str, default_value: str, valid_values: list[str] | None,
      help_str: str, display_case: Case='lower', command_flag: bool=False):
    self._default = default_value
    self.help_str = help_str
    self.name = name
    self.valid_values = valid_values
    self.display_case = display_case
    self.command_flag = command_flag
    if self.command_flag:
      flags.DEFINE_string(self.name, default_value, help_str)

  def _GetDefault(self):
    if self.command_flag and hasattr(flags, self.name):
      return getattr(flags, self.name)
    else:
      return self._default

  default_value = property(_GetDefault)


class Inventory(object):
  """Base class for device inventory retrieval and command submission.

  To be subclassed and customised for the users environment.
  Source specific instantiations of the class should replace private methods.

  Attributes:
    devices: A dict (keyed by string) of Device objects. Read-only.
    device_list: Array of device names satisfying the filters.
    source: String identifier of source of device inventory.
  """
  SOURCE = 'unknown'

  class CmdRequest(object):
    """Request object to be sent to the external device accessor service.

    The command request object created should satisfy the format required
    by the device manager that retrieves the command results.

    Each request object must be assigned a unique 'uid' attribute - unique
    within the context of all pending requests, and all requests that have not
    yet been rendered to the user. The device manager may generate this ID,
    otherwise we add it here. We have no way of determining if a result has
    been displayed (and the uid freed) so a monotomically increasing 32bit
    number would suffice.

    Some devices support multiple commandline modes or CLI interpretors
    e.g. router CLI and sub-system unix cli.

    Args:
      target: device to send command to.
      command: string single commandline to send to each device.
      mode: commandline mode on device to submit the command to.
    Returns:
      List of request objects.
    """

    UID = 0    # Each request has an identifier

    def __init__(self, target: str, command: str, mode: str='cli') -> None:
      Inventory.CmdRequest.UID += 1
      self.uid = Inventory.CmdRequest.UID
      self.target = target
      self.command = bytes(command, 'utf-8').decode('unicode_escape')
      self.mode = mode

  def __init__(self):
    """Initialise thread safe access to data to support async calls."""

    self._getter_lock = threading.Lock()
    self._load_lock = threading.Lock()
    self._loaded = threading.Event()
    self._loaded.set()
    # Devices keyed on device name.
    # If we have already loaded devices e.g. copy, don't do it again.
    if not hasattr(self, '_devices'):
      self._devices: dict = {}
      # Load device inventory from external source.
      self.Load()
    # List of device names.
    #TODO(harro): Lazy rebuild by assigning None - Maybe a setter is better?
    self._device_list: list[str] | None = None
    self._filters: dict[str, FilterMatch] = {}
    self._maxtargets: int = FLAGS.maxtargets

    # Filters and exclusions added by this library.
    # We always have "targets", which is matched against the device name.
    self._inclusions: dict[str, str] = {'targets': ''}
    self._exclusions: dict[str, str] = {'xtargets': ''}
    # Filters and exclusions added by this library.
    logging.debug(
      f'Device attributes statically defined: "{DEVICE_ATTRIBUTES}".')
    #TODO(harro): Compare against reserved words and raise exception if a dup.
    for attr in DEVICE_ATTRIBUTES:
      # TODO(harro): Add support for filtering on flag values.
      if attr == 'flags': continue
      self._inclusions[attr] = ''
      self._exclusions['x' + attr] = ''

  @property
  def devices(self) -> dict[str, typing.NamedTuple]:
    """Returns Devices from external store.

    Stores data in _devices in a dictionary of NamedTuples like:
    {'devicename1: Device(attribute1='value1',
                          attribute2='value2',
                          ... ),
     'devicename2: Device('attribute1='value3',
                          ... ),
     ...
    }
    """
    with self._getter_lock:
      # Wait for any pending device loading.
      self._loaded.wait()
      if not self._devices:
        raise InventoryError(
            'Device inventory data failed to load or no devices found.')
      return self._devices.copy()

  @property
  def device_list(self) -> list[str]:
    """Returns a filtered list of Devices."""
    with self._getter_lock:
      # 'None' means the list needs to be built first.
      if self._device_list is None: return self._BuildDeviceList()
      return self._device_list.copy()

  @property
  def inclusions(self) -> dict[str, str]:
    return self._inclusions.copy()

  @property
  def exclusions(self) -> dict[str, str]:
    return self._exclusions.copy()
  
  # pylint: disable=protected-access
  targets = property(lambda self: self._inclusions['targets'])

  def Load(self) -> None:
    """Loads Devices inventory from external store."""

    # Block additional requests until completed.
    self._load_lock.acquire()
    # Block reads of the devices until loaded.
    self._loaded.clear()
    # Collect result in a thread so it can complete in the background.
    # Threading here is helpful if device inventory is large.
    self._devices_thread = threading.Thread(name='Device loader',
                                            target=self._AsyncLoad,
                                            daemon=True)
    self._devices_thread.start()

  def RegisterCommands(self, cmd_register) -> None:
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
      if attribute.command_flag and attribute.name in FLAGS:
        default_value = getattr(FLAGS, attribute.name)
      else:
        default_value = attribute.default_value
      cmd_register.RegisterCommand(attribute.name,
                                   attribute.help_str,
                                   default_value=default_value,
                                   append=True, inline=True, regexp=True,
                                   handler=self._CmdFilter)

  def SendRequests(self, requests_callbacks, deadline:int|None=None):
    """Submits command requests to device manager.

    Submit the command requests to the device manager for resolution.
    Each tuple contains a request object created by CreateCmdRequest and a
    corresponding callback that expects a response object with a matching uid
    attribute.

    As command results from devices are collected then the callback function
    is to be executed by the device manager.

    Args:
      requests_callbacks: List of tuples.
        Each tuple pairs a request object with a callback function.
      deadline: An optional int, the deadline to set when sending the request.
    Returns:
      None
    """
    return self._SendRequests(requests_callbacks, deadline=deadline)

  def ShowEnv(self) -> str:
    """Show inventory attribute filter settings."""

    indent = ' '*2
    # Add headline to indicate this display section is from this module.
    display_string = ['Inventory:']
    display_string.append(f'{indent}Max Targets: {self._maxtargets}')
    # Sub section for Filters and Exclusions.
    display_string.append(f'{indent}Filters:')
    # Assumes that for every inclusion there is a corresponding exclusion.
    for incl, excl in zip(sorted(self._inclusions), sorted(self._exclusions)):
      # Create paired entries like 'Targets: ..., XTargets: ...'
      display_string.append(
        f'{indent*2}' +
        self._FormatLabelAndValue(incl, self._inclusions[incl]) +
        ', ' +
        self._FormatLabelAndValue(excl, self._exclusions[excl], caps=2)
        )

    return '\n'.join(display_string) + '\n'

  # Command handlers have identical arguments.
  def _CmdFilterCompleter(
    self, word_list:list[str], state:int) -> list[str]|None:
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

  def _AttributeFilter(
      self, command_name: str, args: list[str], append:bool=False) -> str:
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
      raise ValueError(f'Command "{command_name}" invalid.')
    
    # Display values of all device attribute filters.
    if not args:
      result = ''
      if command_name == 'attributes':
        attr_list = self._inclusions
      else: # xattributes
        attr_list = self._exclusions
      for attr in attr_list:
        result += self._CmdFilter(attr, [], append)
      return result

    # Update attribute filter/s.
    # TODO(harro): Can we set multiple attributes here by splitting the list?
    if command_name == 'attributes':
      self._CmdFilter(args[0], args[1 :], append)
    else:
      # 'xattributes' so add 'x' prefix to corresponding attribute.
      self._CmdFilter('x' + args[0], args[1 :], append)
    return ''
  
  def _CmdFilter(
      self, command_name: str, args: list[str], append:bool=False) -> str:
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

    if (command_name not in self._inclusions and
        command_name not in self._exclusions):
      raise ValueError(f'Command "{command_name}" invalid.')

    # Filter may be inclusive, or exclusive.
    if command_name in self._inclusions:
      filters = self._inclusions
      caps = 1    # Capitalise the first character.
    else:
      filters = self._exclusions
      caps = 2    # Capitalise the two characters.

    # No args, so display current value/s.
    if not args:
      return self._FormatLabelAndValue(
          command_name, filters[command_name], caps=caps)

    filter_string = args[0]   # TODO(harro): Raise exception is args >1 ?
    if filter_string in ('^', '^$'):
      del(self._filters[command_name])
      filters[command_name] = ''
      # Clear device list to trigger re-application of filter.
      self._device_list = None
      return ''

    # Appending a new filter string to an existing filter.
    if append and filter_string and filters[command_name]:
      filter_string = ','.join([filters[command_name], filter_string])
    #TODO(harro): Pass in ignorecase flag, add to class __ini__.
    _filter = FilterMatch(filter_string)
    if not self.ValidFilter(command_name, _filter.filters[0]):
      raise ValueError(
        f'Non-regexp filter entry "{_filter.filters[0]}" is not valid.')

    self._filters[command_name] = _filter
    filters[command_name] = filter_string
    # Clear device list to trigger re-application of filter.
    self._BuildDeviceList()
    return ''

  def _CmdMaxTargets(
    self, command_name: str, args: list[str], append=False) -> str:
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
      return self._FormatLabelAndValue(command_name, str(self._maxtargets))

    try:
      maxtargets = int(args[0])
      if maxtargets < 0:
        raise ValueError
    except ValueError:
      raise ValueError(f'Max Targets is a non-cardinal value: "{maxtargets}."')

    self._maxtargets = maxtargets
    return ''

  def _Flatten(self, container:list|tuple) -> typing.Iterator[str]:
    """Flattens arbitrarily deeply nested lists."""

    for i in container:
      if isinstance(i, list) or isinstance(i, tuple):
        for j in self._Flatten(i):
          yield j
      else:
        yield i

  def ValidFilter(self, filter_name:str, literals:list[str]) -> bool:
    """Update inventory filter.

    Sets the new value for the filter string. Only called against valid
    filter/exclusion names.

    Args:
      filter_name: str filter or exclusion name.
      literals: list of literals in the filter.
    Raises:
      ValueError: If literal device name specified and device is unknown.
    Returns:
      Bool The filter string 'arg'.
    """

    #TODO(harro): Add support for regexp validation.
    if not literals: return True

    attribute = filter_name
    # Trim off the 'x' prefix for matching exclusions against attributes.
    if filter_name.startswith('x'):
      attribute = filter_name[1 :]

    if attribute == 'targets':
      # Warn user if literal is unknown.
      validate_list = self.devices
    elif (attribute in DEVICE_ATTRIBUTES and
          DEVICE_ATTRIBUTES[attribute].valid_values):
      validate_list = DEVICE_ATTRIBUTES[attribute].valid_values
    else:
      # Without a specific list of valid values, check that at least one
      # device matches.
      # TODO(harro): For filter responsiveness reasons we may drop this.
      validate_list = [getattr(dev, attribute, None)
                        for dev in self.devices.values()]
      validate_list = set(self._Flatten(validate_list))

    validate_list = [value.lower() for value in validate_list]

    # Confirm that static content matches a valid entry.
    unmatched_literals = set(literals).difference(set(validate_list))
    return False if unmatched_literals else True

  def _FormatLabelAndValue(self, label:str, value:str, caps:int=1) -> str:
    """Returns string with titlecase label and corresponding value."""

    caps = min(caps, len(label))
    # Capitalise the prefix.
    label = label[:caps].upper() + label[caps :]
    return f'{label}: {value}'

  #TODO(harro): If we flip the exclude/include logic, is this cleaner?
  def _FilterMatch(self, devicename:str, device_attrs:typing.NamedTuple,
                   exclude:bool=False) -> bool:
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

      if attr not in self._filters:
        matched = False
      else:
        matched = self._filters[attr].Match(attr_value)
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

    # Special case, treatment of the null case for 'targets' is the inverse.
    # In other words, a null 'targets' expression doesn't match any devices.
    if not self._inclusions['targets']:
      self._device_list = []
      return self._device_list

    d_list = []
    for (devicename, d) in self.devices.items():
      # Skip devices that match any non-blank exclusions.
      if self._FilterMatch(devicename, d, exclude=True):
        continue

      # Include devices that match all filters (blank is a match).
      if self._FilterMatch(devicename, d):
        d_list.append(devicename)

    # Raise error if number of matches exceeds the maximum set by user.
    if self._maxtargets and len(d_list) > self._maxtargets:
      raise ValueError(
        f'Target list exceeded Maximum targets limit of: {self._maxtargets}.')

    # Cache the result.
    self._device_list = d_list
    logging.debug(f'Device List length: {len(self._device_list)}')
    return self._device_list

  def _AsyncLoad(self) -> None:
    """Wrapper for calling FetchDevices from withing a thread."""

    try:
      self._FetchDevices()
      logging.debug('Fetching of devices completed.')
    finally:
      self._load_lock.release()
      # Let pending getters know the data is ready.
      self._loaded.set()

  def _FetchDevices(self) -> None|NotImplementedError:
    """Fetches Devices from external store ."""
    raise NotImplementedError

  def _SendRequests(
      self, requests_callbacks:tuple, deadline:float|None=None
      ) -> None|NotImplementedError:
    """Submit command requests to device manager."""
    raise NotImplementedError

class FilterMatch(object):
  """Object for filter string decomposition and matching against values."""

  def __init__(self, filter_string: str, ignorecase: bool=True) -> None:
    # Literal strings and compiled regexps keyed on attribute name.
    self._Set(filter_string, ignorecase)

  @property
  def filters(self) -> tuple:
    return (self._literals, self._compiled)

  def _Set(self, filter_string: str, ignore_case: bool) -> None:
    """Assigns values to filters.

    Store the literal values and compiled regular expressions in their
    respective dictionaries.

    Args:
      filter_string: str to use as the basis of the filters.
    """

    # Split the string into literal and regexp elements.
    (self._literals, self._compiled) = self._DecomposeString(
      filter_string, ignore_case)

  def _DecomposeString(
      self, filter_string: str, ignore_case: bool) -> tuple:
    """Returns a tuple of lists of compiled and literal strings for matching.

    Args:
      filter_string: str comma separated substrings to use for filtering.
      ignore_case: bool to cononalise to lowercase or regexp ignores case.
    Raises:
      ValueError if a substring is indicated as a regexp but is not valid.
    Returns:
      Tuple of lists to use in filtering operations.
    """

    literal_substrs, re_substrs = [], []
    # Note we accept only a subset of RFC 4180 and do not support enclosing
    # in double double quotes
    # https://www.ietf.org/rfc/rfc4180.txt
    for substring in filter_string.split(','):
      # Trim excess space from around a substring..
      substring = substring.strip()
      if substring:
        # regexp style matches always start with '^'.
        if substring.startswith('^'):
          # Add implicit '$' to regexp.
          if not substring.endswith('$'):
            substring += '$'
          try:
            if ignore_case:
              re_substrs.append(re.compile(substring, re.IGNORECASE))
            else:
              re_substrs.append(re.compile(substring))
          except re.error:
            raise ValueError(f'The filter regexp "{substring}" is invalid.')
        else:
          if ignore_case:
            # Canonalise to all lowercase.
            literal_substrs.append(substring.lower())
          else:
            literal_substrs.append(substring)

    return (literal_substrs, re_substrs)

  def Match(self, value: str | list[str] | list[list[str]]) -> bool:
    """Returns if a value matches the filter."""

    # If we have a list of attributes, recurse down to find match.
    # This might be the case if matching the presence of a Flag.
    if isinstance(value, list):
      for list_elem in value:
        if self.Match(list_elem):
          return True
      return False

    # Is there a literal for this value?
    if (self._literals and value in self._literals):
      return True

    # Regular expressions are held separately as compiled expressions.
    if self._compiled:
      for regexp in self._compiled:
        if regexp.match(value):
          return True

    return False
