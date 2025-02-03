# Colour mapping depending on colour scheme.
import sys

from textfsm import terminal
from tcli import command_register

PROMPT_HDR = '#! <%s[%s]%s> !#'
PROMPT_STR = '#! '

LIGHT_SYSTEM_COLOR = ['yellow']
LIGHT_WARNING_COLOR = ['red']
LIGHT_TITLE_COLOR = ['cyan']

DARK_SYSTEM_COLOR = ['bold', 'blue']
DARK_WARNING_COLOR = ['bold', 'red']
DARK_TITLE_COLOR = ['bold', 'magenta']

GROSS_SYSTEM_COLOR = ['bold', 'magenta', 'bg_cyan']
GROSS_WARNING_COLOR = ['bold', 'yellow', 'bg_magenta']
GROSS_TITLE_COLOR = ['bold', 'red', 'bg_green']
# Display color combinations.
COLOR_SCHEMES = command_register.COLOR_SCHEMES

class Display(object):
  """
  Attributes:
    color_scheme: Whether to use 'dark' on light background or vice versa.
    system_color: Color for system strings.
    title_color: Color for titles in standard strings.
    warning_color: Color for warning strings.
  """


  def __init__(self) -> None:
    self.color_scheme: str | None = None
    self.system_color = self.title_color = self.warning_color = ''

  def setColorScheme(self, scheme) -> None:
    if scheme not in COLOR_SCHEMES:
      raise ValueError(f"Error: Unknown color scheme: '{scheme}'")

    self.color_scheme = scheme
    if scheme == 'light':
      self.system_color = LIGHT_SYSTEM_COLOR
      self.warning_color = LIGHT_WARNING_COLOR
      self.title_color = LIGHT_TITLE_COLOR
    elif scheme == 'dark':
      self.system_color = DARK_SYSTEM_COLOR
      self.warning_color = DARK_WARNING_COLOR
      self.title_color = DARK_TITLE_COLOR
    elif scheme == 'gross':
      self.system_color = GROSS_SYSTEM_COLOR
      self.warning_color = GROSS_WARNING_COLOR
      self.title_color = GROSS_TITLE_COLOR

  def getPrompt(self, targets: str, devices: list[str], safemode: bool) -> str:
    """Sets the prompt string with current targets."""

    safe = '*' if safemode else ''

    (_, width) = terminal.TerminalSize()
    # Expand the targets displayed in prompt, if it fits in the terminal.
    if (width > len(PROMPT_HDR % (targets, len(devices), safe))):
      target_str = targets
    else:
      # Truncate prompt if too long to fit in terminal.
      target_str = '#####'

    return PROMPT_HDR % (
      terminal.AnsiText(target_str, self.system_color),
      terminal.AnsiText(len(devices), self.warning_color),
      terminal.AnsiText(safe, self.title_color))

  def printOut(self, msg, color, linewrap, msgtype='default') -> None:
    """Prints (and logs) outputs."""

    # Format for width of display.
    if linewrap: msg = terminal.LineWrap(msg)
    # Colourise depending on nature of message.
    if color:
      msg_color = f'{msgtype}_color'
      if hasattr(self, msg_color) and type(getattr(self, msg_color) is str):
        msg = terminal.AnsiText(msg, getattr(self, msg_color))
    # Warnings go to stderr.
    if msgtype == 'warning':
      print(msg, file=sys.stderr)
    else:
      print(msg)