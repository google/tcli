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

"""Sends commands to devices via callbacks."""
import typing

from tcli.inventory_base import CmdRequest

DEADLINE = None


def SendRequests(
    requests_callbacks: list[tuple[CmdRequest, typing.Callable]],
    deadline: float | None=DEADLINE) -> None:
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
  raise NotImplementedError