"""字句解析器。ソースをトークン列に変換する。

- 空白で区切られた語がトークンになる。`[ ] { } ;` は空白なしでも単独のトークン。
- `#` から行末まではコメント。`( ... )` (開き括弧の直後が空白) はスタック効果コメント。
- `"..."` は文字列リテラル。エスケープ \\n \\t \\r \\" \\\\ \\0 \\e \\uXXXX に対応。
"""

import re

from .errors import DecafSyntaxError, IncompleteInput

NUM_RE = re.compile(r"[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?\Z")
HEX_RE = re.compile(r"[+-]?0[xX][0-9a-fA-F]+\Z")
BIN_RE = re.compile(r"[+-]?0[bB][01]+\Z")
DELIMS = frozenset("[]{};")
ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "0": "\0", "e": "\x1b"}


class Token:
    __slots__ = ("kind", "value", "line")

    def __init__(self, kind, value, line):
        self.kind = kind  # 'num' | 'str' | 'sym'
        self.value = value
        self.line = line

    def __repr__(self):
        return f"Token({self.kind}, {self.value!r}, {self.line})"


def parse_number(word):
    if NUM_RE.match(word):
        if any(c in word for c in ".eE"):
            return float(word)
        return int(word)
    if HEX_RE.match(word) or BIN_RE.match(word):
        return int(word, 0)
    return None


def tokenize(src, file="<input>"):
    toks = []
    i, n, line = 0, len(src), 1
    while i < n:
        c = src[i]
        if c == "\n":
            line += 1
            i += 1
            continue
        if c.isspace():
            i += 1
            continue
        if c == "#":
            while i < n and src[i] != "\n":
                i += 1
            continue
        if c == "(" and (i + 1 >= n or src[i + 1].isspace() or src[i + 1] == ")"):
            start = line
            i += 1
            while i < n and src[i] != ")":
                if src[i] == "\n":
                    line += 1
                i += 1
            if i >= n:
                raise IncompleteInput(f"{file}:{start}: コメント '(' が閉じられていません")
            i += 1
            continue
        if c == '"':
            start = line
            i += 1
            buf = []
            while True:
                if i >= n:
                    raise IncompleteInput(f"{file}:{start}: 文字列が閉じられていません")
                ch = src[i]
                if ch == '"':
                    i += 1
                    break
                if ch == "\\":
                    if i + 1 >= n:
                        raise IncompleteInput(f"{file}:{start}: 文字列が閉じられていません")
                    esc = src[i + 1]
                    if esc in ESCAPES:
                        buf.append(ESCAPES[esc])
                        i += 2
                    elif esc == "u":
                        hexdigits = src[i + 2:i + 6]
                        if len(hexdigits) != 4 or not all(h in "0123456789abcdefABCDEF" for h in hexdigits):
                            raise DecafSyntaxError(f"{file}:{line}: 不正な \\u エスケープです")
                        buf.append(chr(int(hexdigits, 16)))
                        i += 6
                    else:
                        raise DecafSyntaxError(f"{file}:{line}: 不明なエスケープ '\\{esc}' です")
                    continue
                if ch == "\n":
                    line += 1
                buf.append(ch)
                i += 1
            toks.append(Token("str", "".join(buf), start))
            continue
        if c in DELIMS:
            toks.append(Token("sym", c, line))
            i += 1
            continue
        j = i
        while j < n and not src[j].isspace() and src[j] not in DELIMS and src[j] != '"':
            j += 1
        word = src[i:j]
        i = j
        num = parse_number(word)
        if num is not None:
            toks.append(Token("num", num, line))
        else:
            toks.append(Token("sym", word, line))
    return toks
