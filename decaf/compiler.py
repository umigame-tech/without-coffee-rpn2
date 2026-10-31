"""トークン列を VM 用の命令列 (Code) にコンパイルする。

命令は (opcode, 引数, 行番号) のタプル。
"""

import re

from .errors import DecafSyntaxError, IncompleteInput
from .lexer import tokenize
from .values import Word

PUSH, WORD, QUOT, STORE, GSTORE, LOCALS, LBEGIN, LEND, WREF = range(9)

OP_NAMES = ["PUSH", "WORD", "QUOT", "STORE", "GSTORE", "LOCALS", "LBEGIN", "LEND", "WREF"]

IDENT_RE = re.compile(r"[^\W\d][\w\-?!]*\Z")
CONSTANTS = {"true": True, "false": False, "nil": None}
CLOSERS = {"]": "[", "}": "{", ";": ":"}


class Code:
    __slots__ = ("ops", "name", "file")

    def __init__(self, ops, name, file):
        self.ops = ops
        self.name = name
        self.file = file

    def dump(self, indent=0):
        """デバッグ用の逆アセンブル表示。"""
        pad = "  " * indent
        lines = []
        for op, arg, line in self.ops:
            if op == QUOT:
                lines.append(f"{pad}{line:4d} QUOT")
                lines.append(arg.dump(indent + 1))
            else:
                lines.append(f"{pad}{line:4d} {OP_NAMES[op]} {'' if arg is None else repr(arg)}")
        return "\n".join(lines)


def is_ident(s):
    return bool(IDENT_RE.match(s))


class Parser:
    def __init__(self, toks, file):
        self.toks = toks
        self.pos = 0
        self.file = file
        self.defs = {}

    def error(self, line, msg, incomplete=False):
        cls = IncompleteInput if incomplete else DecafSyntaxError
        return cls(f"{self.file}:{line}: {msg}")

    def block(self, end, start_line=0):
        """`end` が現れるまでの命令列を返す。end が None ならトップレベル。"""
        ops = []
        toks = self.toks
        while True:
            if self.pos >= len(toks):
                if end is None:
                    return ops
                raise self.error(start_line, f"'{CLOSERS[end]}' に対応する '{end}' がありません", True)
            t = toks[self.pos]
            self.pos += 1
            line = t.line
            if t.kind != "sym":
                ops.append((PUSH, t.value, line))
                continue
            v = t.value
            if v == end:
                return ops
            if v in CLOSERS:
                raise self.error(line, f"予期しない '{v}' です")
            if v == "[":
                body = self.block("]", line)
                ops.append((QUOT, Code(body, "[quotation]", self.file), line))
            elif v == "{":
                ops.append((LBEGIN, None, line))
                ops.extend(self.block("}", line))
                ops.append((LEND, None, line))
            elif v == ":":
                if end is not None:
                    raise self.error(line, "ワード定義 ':' はトップレベルでのみ使えます")
                if self.pos >= len(toks):
                    raise self.error(line, "':' の後にワード名が必要です", True)
                nt = toks[self.pos]
                self.pos += 1
                if nt.kind != "sym" or nt.value in "[]{};:|" or nt.value in CONSTANTS:
                    raise self.error(nt.line, f"ワード名として使えません: {nt.value!r}")
                name = nt.value
                body = self.block(";", line)
                self.defs[name] = Word(name, Code(body, name, self.file))
            elif v == "|":
                names = []
                while True:
                    if self.pos >= len(toks):
                        raise self.error(line, "'|' が閉じられていません", True)
                    nt = toks[self.pos]
                    self.pos += 1
                    if nt.kind == "sym" and nt.value == "|":
                        break
                    if nt.kind != "sym" or not is_ident(nt.value):
                        raise self.error(nt.line, f"変数名として使えません: {nt.value!r}")
                    names.append(nt.value)
                ops.append((LOCALS, tuple(names), line))
            elif v in CONSTANTS:
                ops.append((PUSH, CONSTANTS[v], line))
            elif v.startswith(">>") and is_ident(v[2:]):
                ops.append((GSTORE, v[2:], line))
            elif v.startswith(">") and is_ident(v[1:]):
                ops.append((STORE, v[1:], line))
            elif v.startswith("'") and len(v) > 1:
                ops.append((WREF, v[1:], line))
            else:
                ops.append((WORD, v, line))


def compile_source(src, file="<input>"):
    """ソースをコンパイルし (トップレベルの Code, 定義された Word の dict) を返す。"""
    parser = Parser(tokenize(src, file), file)
    ops = parser.block(None)
    return Code(ops, "<toplevel>", file), parser.defs
