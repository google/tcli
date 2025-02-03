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

import asyncio
import os
import typing

from tcli import accessor_base as accessor
from tcli import inventory_base as inventory

DEADLINE = accessor.DEADLINE
## CHANGEME
## Where we store the canned responses.
DEFAULT_RESPONSE_DIRECTORY = os.path.join(
    os.path.dirname(__file__), 'testdata', 'device_output')


def SendRequests(
    requests_callbacks:list[tuple[accessor.CmdRequest, typing.Callable]],
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

  for (request, callback) in requests_callbacks:
    asyncio.run(_ReadCannedResult(request, callback))

async def _ReadCannedResult(
    request: inventory.CmdRequest, callback: typing.Callable) -> None:
  """Reads canned result from local file."""

  data, error = '', ''
  file_name = request.target + '_' + request.command.replace(' ', '_')
  file_path = os.path.join(DEFAULT_RESPONSE_DIRECTORY, file_name)
  try:
    with open(file_path) as fp:
      data = fp.read()
  except IOError:
    error = ('Failure to retrieve response from device "%s",'
              ' for command "%s".' % (request.target, request.command))
  callback(inventory.Response(uid=request.uid, device_name=request.target,
           command=request.command, data=data, error=error))