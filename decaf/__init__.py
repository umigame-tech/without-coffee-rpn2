"""Decaf: 逆ポーランド記法 (RPN) を採用したスタックベースの汎用プログラミング言語。"""

__version__ = "0.1.0"

from .errors import DecafError, DecafExit, DecafSyntaxError, IncompleteInput  # noqa: F401
from .vm import VM  # noqa: F401
