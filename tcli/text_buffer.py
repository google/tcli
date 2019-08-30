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

"""Routines for storing and accessing named text buffers.

Dictionary of string buffers with methods for managing content.
"""


import collections


class TextBuffer(object):
  """Routines for storing and accessing named text buffers.

  Attributes:
    buffers: Dictionary for storing/retrieving named text buffers.
  """

  def __init__(self):
    self._buffers = collections.defaultdict(str)

  def Append(self, text_buffer, line):
    """Append row of text to buffer."""
    # Accept and silently discard empty buffer name or data.
    if not text_buffer or not line:
      return

    if self._buffers[text_buffer]:
      self._buffers[text_buffer] += '\n' + line
    else:
      self._buffers[text_buffer] = line

  def Clear(self, text_buffer):
    """Clears content of named buffer."""
    if text_buffer in self._buffers:
      del self._buffers[text_buffer]
      return True
    return False

  def GetBuffer(self, text_buffer):
    """Returns named buffer if it exists, returns 'None' otherwise."""
    return self._buffers.get(text_buffer)

  def ListBuffers(self):
    """Returns list of buffers that exist (created and not cleared)."""
    return ' '.join(sorted(self._buffers.keys()))
