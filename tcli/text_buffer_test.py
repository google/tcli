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

"""Tests for tcli.text_buffer."""

from absl.testing import absltest as unittest
from tcli import text_buffer


class TextBufferTest(unittest.TestCase):
  """Tests the TextBuffer class."""

  def setUp(self):
    super(TextBufferTest, self).setUp()
    self.buf = text_buffer.TextBuffer()

  def testInit(self):
    self.assertEqual({}, self.buf._buffers)
    self.buf.Append('', 'hello')
    self.assertEqual({}, self.buf._buffers)
    self.buf.Append('boo', '')
    self.assertEqual({}, self.buf._buffers)

  def testAppend(self):
    self.buf.Append('boo', 'hi')
    self.buf.Append('boo', 'there')
    self.assertEqual('hi\nthere', self.buf._buffers['boo'])
    self.buf.Append('boo', 'hello\nworld')
    self.assertEqual('hi\nthere\nhello\nworld', self.buf._buffers['boo'])
    self.assertEqual({'boo': 'hi\nthere\nhello\nworld'}, self.buf._buffers)

  def testClear(self):
    self.buf._buffers['boo'] = 'hello\nworld'
    self.buf.Clear('boo')
    self.assertEqual({}, self.buf._buffers)
    self.buf._buffers['boo'] = 'hello\nworld'
    self.buf._buffers['hoo'] = 'hi\nthere'
    self.buf.Clear('boo')
    self.assertEqual({'hoo': 'hi\nthere'}, self.buf._buffers)
    self.assertTrue(self.buf.Clear('hoo'))
    self.assertFalse(self.buf.Clear('non_exist'))

  def testGetBuffer(self):
    self.buf._buffers['boo'] = 'hello\nworld'
    self.assertEqual('hello\nworld', self.buf.GetBuffer('boo'))
    self.assertEqual(None, self.buf.GetBuffer('non_exist'))

  def testListBuffer(self):
    self.buf._buffers['boo'] = 'hello\nworld'
    self.buf._buffers['hoo'] = 'hello\nworld'
    self.assertEqual('boo hoo', self.buf.ListBuffers())
    self.buf.Clear('boo')
    self.assertEqual('hoo', self.buf.ListBuffers())


if __name__ == '__main__':
  unittest.main()
