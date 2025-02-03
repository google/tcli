import unittest

from tcli import display

class UnitTestDisplay(unittest.TestCase):
  """Tests the TCLI Display class."""

  def setUp(self):
    self.d = display.Display()

  def tearDown(self):
    pass

  def testColorScheme(self):
    self.assertIsNone(self.d.color_scheme)
    # Valid color_scheme accepted
    self.d.setColorScheme('light')
    self.assertEqual('light', self.d.color_scheme)
    self.d.setColorScheme('dark')
    self.assertEqual('dark', self.d.color_scheme)
    self.assertRaises(ValueError, self.d.setColorScheme, 'bogus')