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

"""Stores response results and current state for device inventory Callback.

  Used to collate returned responses prior to outputing to the user.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import threading
from absl import logging
import tqdm

PROGRESS_MESSAGE = '#! Receiving:'


class CmdResponse(object):
  """Stores response results and current state for device inventory Callback.

  The command string itself is not handled here. Rather we have a unique ID(uid)
  that corresponds to a command sent. So here we track the number of commands
  sent (row numbers) and the number of hosts the command was issued to. When
  all responses are returned for the current row then a call to GetRow returns
  it.

  Each command sent to the targets ha a corresponding entry here setup by
  SetCommandRow. A command equates to a row, and each target is a column. We
  store any pipe value here as well, as it is not sent to the target and the
  inventory class doesn't handle it.

  Each request objects returned uid is tracked by SetRequest, mapping request
  uid to row ids.

  Responses are collected in 'results' by AddResponse, called asyncronously.

  GetRow is polled and returns the next row of results when it is ready for
  displaying. A row is ready when all responses have been received for that row.

  Attributes:
    done: (obj) Event object, true when GetRow reads beyond end of rows.
  """

  # Class will only few (one) instance, so class-wide locking is acceptable.
  _lock = threading.Lock()    # Lock access to data to support async calls.

  def Synchronized(func):  # pylint: disable=no-self-argument
    """Synchronization decorator."""

    def Wrapper(main_obj, *args, **kwargs):
      with main_obj._lock:          # pylint: disable=protected-access
        return func(main_obj, *args, **kwargs)  # pylint: disable=not-callable
    return Wrapper

  @Synchronized
  def __init__(self):
    """Init starting values."""

    self._pipe = {}             # Client side pipe function. Indexed on row id.
    self._results = {}          # All response objects indexed by uid.
    self._row_index = {}        # List of uid indexed by row.
    self._row_response = {}     # List of responses indexed by row.
    self._uid_index = {}        # Which row a uid response corresponds to.
    self._current_row = 0       # Current row index of requests being returned.
    self._response_count = 0    # Total count of received responses.
    self.done = threading.Event()
    # Graphic to indicate progress receiving responses.
    self._progressbar = None

  @Synchronized
  def SetCommandRow(self, command_row, pipe):
    """Initialise data for a new row, each row corresponds to a command.

    Args:
      command_row: int, the row number for the current command.
      pipe: str the rhs of the commandline that output is to be piped into.
            The pipe is not sent to the target so we track it here.
    """

    self._row_index[command_row] = []
    self._row_response[command_row] = []
    self._pipe[command_row] = pipe

  @Synchronized
  def SetRequest(self, command_row, request_uid):
    """Maps uid returned by inventory class to a row number and result.

    Args:
      command_row: int, the row number for the current command.
      request_uid: int, the corresponding UID provided by the inventory.
    """

    self._results[request_uid] = ''
    self._uid_index[request_uid] = command_row
    self._row_index[command_row].append(request_uid)

  @Synchronized
  def AddResponse(self, response):
    """Add response to results table.

    Args:
      response: obj, returned by inventory class, contains the targets response.
                we only care that it has a 'uid' attribute.

    Returns:
      True if we were expecting a response with this uid
      False if the uid is unknown, does not correspond to one of our requests.
    """

    if response.uid not in self._uid_index:
      # Response with an unexpected uid. This can be the case if outstanding
      # requests are interrupted - Silently discard.
      logging.warning("Discarded response: '%s', not expected (stale?)",
                      response.uid)
      return False

    # Add to the response object to results table.
    self._results[response.uid] = response
    # Find the row number from the uid in the response.
    command_row = self._uid_index[response.uid]
    # Add the uid to corresponding row.
    self._row_response[command_row].append(response.uid)
    # Track total number of responses received.
    self._response_count += 1
    # Visually indicate progress.
    if self._progressbar is not None:
      self._progressbar.update()
    return True

  @Synchronized
  def GetRow(self):
    """Return current row if fully populated with results.

    Returns:
      Tuple: List of responses of the row to display and a string of the
      commandline pipe to pass the responses through before displaying.
      None: if the current row is not ready.
    """

    if self._current_row not in self._row_response:
      # Reading off the end of the rows, either we've just started a new row
      # or we are off the bottom of the table and no more rows are needed.
      logging.debug('GetRow: Current row not in responses.')
      # Triggers the done flag if we already have all responses.
      if len(self._results) == self._response_count:
        logging.debug('GetRow: All results returned.')
        self.done.set()
      # Otherwise we are still waiting for our first responses for this row.
      return

    # Have we received all responses for the current row.
    if (len(self._row_response[self._current_row]) ==
        len(self._row_index[self._current_row])):
      logging.info('Row %s was complete (size %s) and returned.',
                   self._current_row,
                   len(self._row_response[self._current_row]))
      # Assemble the results for the row and any corresponding pipe content.
      result = (self._row_response[self._current_row],
                self._pipe[self._current_row])
      # Advance the current row.
      self._current_row += 1
      # Reset the progress indicator as there is results to display.
      if self._progressbar is not None:
        self._progressbar.close()
      return result
    logging.debug('Current row incomplete.')

  def GetResponse(self, uid):
    """Returns response object for a given uid."""

    try:
      return self._results[uid]
    except KeyError:
      logging.error('Invalid UID: %s, possible values: %s.',
                    uid, str(self._results))

  def StartIndicator(self, message=PROGRESS_MESSAGE):
    """Starts a progress indicator to indicate receiving of requests."""

    # TODO(harro): Display textmessage at outset, or remove.
    self._progressbar = tqdm.tqdm(list(range(len(self._results))), desc=message)
