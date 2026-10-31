"""Decaf の値の表現と、表示・比較などのヘルパー。

値と Python 型の対応:
    数値   int / float      文字列 str       真偽値 bool     nil  None
    リスト list             辞書   dict      クォーテーション Quot
    ワード参照 Word (ユーザー定義) / Prim (組み込み)
"""


class Quot:
    """クォーテーション `[ ... ]`。生成時の環境 (ローカル変数) を捕捉するクロージャ。"""

    __slots__ = ("code", "env")

    def __init__(self, code, env):
        self.code = code
        self.env = env


class Word:
    """`: name ... ;` で定義されたユーザー定義ワード。"""

    __slots__ = ("name", "code")

    def __init__(self, name, code):
        self.name = name
        self.code = code


class Prim:
    """Python で実装された組み込みワード。`gen` が真なら制御を VM に返すジェネレータ。"""

    __slots__ = ("name", "fn", "gen")

    def __init__(self, name, fn, gen):
        self.name = name
        self.fn = fn
        self.gen = gen


CALLABLE_TYPES = (Quot, Word, Prim)


def truthy(v):
    """false と nil だけが偽。0 や空文字列は真。"""
    return v is not None and v is not False


def is_num(v):
    t = type(v)
    return t is int or t is float


def type_name(v):
    if v is None:
        return "nil"
    t = type(v)
    if t is bool:
        return "bool"
    if t is int:
        return "int"
    if t is float:
        return "float"
    if t is str:
        return "string"
    if t is list:
        return "list"
    if t is dict:
        return "dict"
    if t is Quot:
        return "quotation"
    if t is Word or t is Prim:
        return "word"
    return t.__name__


def _quote_str(s):
    out = s.replace("\\", "\\\\").replace('"', '\\"')
    out = out.replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")
    return '"' + out + '"'


def fmt(v, quote=False, _seen=None):
    """値を文字列に変換する。quote が真なら文字列を引用符付きで表示する。"""
    if v is None:
        return "nil"
    t = type(v)
    if t is bool:
        return "true" if v else "false"
    if t is int:
        return str(v)
    if t is float:
        if v != v:
            return "nan"
        if v in (float("inf"), float("-inf")):
            return "inf" if v > 0 else "-inf"
        return repr(v)
    if t is str:
        return _quote_str(v) if quote else v
    if t is list or t is dict:
        if _seen is None:
            _seen = set()
        if id(v) in _seen:
            return "..."
        _seen.add(id(v))
        try:
            if t is list:
                if not v:
                    return "{ }"
                return "{ " + " ".join(fmt(x, True, _seen) for x in v) + " }"
            if not v:
                return "#{ }"
            items = ", ".join(
                f"{fmt(k, True, _seen)}: {fmt(x, True, _seen)}" for k, x in v.items()
            )
            return "#{ " + items + " }"
        finally:
            _seen.discard(id(v))
    if t is Quot:
        return "[quotation]"
    if t is Word or t is Prim:
        return "'" + v.name
    return repr(v)


def eq(a, b):
    """Decaf の等価性。true と 1 は等しくない。リストと辞書は中身で比較する。"""
    if is_num(a) and is_num(b):
        return a == b
    ta, tb = type(a), type(b)
    if ta is not tb:
        return False
    if ta is list:
        return len(a) == len(b) and all(eq(x, y) for x, y in zip(a, b))
    if ta is dict:
        return a.keys() == b.keys() and all(eq(a[k], b[k]) for k in a)
    if ta in CALLABLE_TYPES:
        return a is b
    return a == b
