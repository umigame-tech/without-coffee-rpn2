"""組み込みワード。

通常の組み込みワードは `fn(vm)` としてその場で実行される。
ジェネレータとして書かれたもの (while, map など) は、呼び出したいクォーテーションを
yield すると VM がそれを実行し、終わると処理が再開される。こうすることで
Python の再帰なしに高階ワードを実装している。
"""

import inspect
import math
import os
import random
import sys
import time

from .errors import DecafError, DecafExit
from .values import CALLABLE_TYPES, eq, fmt, is_num, truthy, type_name

PRIMS = {}


def prim(*names):
    def deco(fn):
        from .values import Prim
        gen = inspect.isgeneratorfunction(fn)
        for n in names:
            PRIMS[n] = Prim(n, fn, gen)
        return fn
    return deco


# ---- 型チェックのヘルパー ---------------------------------------------

def need(v, types, what):
    if type(v) not in types:
        raise DecafError(f"{what}が必要ですが {type_name(v)} ({fmt(v, True)}) が渡されました")
    return v


def need_num(v):
    if type(v) is int or type(v) is float:
        return v
    return need(v, (int, float), "数値")


def need_int(v):
    if type(v) is int:
        return v
    if type(v) is float and v.is_integer():
        return int(v)
    return need(v, (int,), "整数")


def need_str(v):
    return need(v, (str,), "文字列")


def need_list(v):
    return need(v, (list,), "リスト")


def need_dict(v):
    return need(v, (dict,), "辞書")


def need_seq(v):
    return need(v, (list, str), "リストか文字列")


def need_callable(v):
    if not isinstance(v, CALLABLE_TYPES):
        raise DecafError(f"クォーテーションが必要ですが {type_name(v)} ({fmt(v, True)}) が渡されました")
    return v


def need_key(v):
    if type(v) in (list, dict) or isinstance(v, CALLABLE_TYPES):
        raise DecafError(f"{type_name(v)} は辞書のキーに使えません")
    return v


def iter_items(v):
    if type(v) is list:
        return list(v)
    if type(v) is str:
        return list(v)
    if type(v) is dict:
        return list(v.keys())
    raise DecafError(f"{type_name(v)} は繰り返しに使えません")


# ---- スタック操作 -----------------------------------------------------

@prim("dup")
def _dup(vm):
    s = vm.stack
    if not s:
        raise DecafError("スタックが空です (stack underflow)")
    s.append(s[-1])


@prim("drop")
def _drop(vm):
    vm.pop()


@prim("swap")
def _swap(vm):
    s = vm.stack
    if len(s) < 2:
        raise DecafError("スタックが空です (stack underflow)")
    s[-1], s[-2] = s[-2], s[-1]


@prim("over")
def _over(vm):
    s = vm.stack
    if len(s) < 2:
        raise DecafError("スタックが空です (stack underflow)")
    s.append(s[-2])


@prim("rot")
def _rot(vm):  # ( a b c -- b c a )
    c, b, a = vm.pop(), vm.pop(), vm.pop()
    vm.stack.extend((b, c, a))


@prim("-rot")
def _mrot(vm):  # ( a b c -- c a b )
    c, b, a = vm.pop(), vm.pop(), vm.pop()
    vm.stack.extend((c, a, b))


@prim("nip")
def _nip(vm):
    b = vm.pop()
    vm.pop()
    vm.push(b)


@prim("tuck")
def _tuck(vm):  # ( a b -- b a b )
    b, a = vm.pop(), vm.pop()
    vm.stack.extend((b, a, b))


@prim("2dup")
def _2dup(vm):
    s = vm.stack
    if len(s) < 2:
        raise DecafError("スタックが空です (stack underflow)")
    s.extend(s[-2:])


@prim("2drop")
def _2drop(vm):
    vm.pop()
    vm.pop()


@prim("pick")
def _pick(vm):  # ( ... n -- ... x )  0 pick = dup
    n = need_int(vm.pop())
    s = vm.stack
    if n < 0 or n >= len(s):
        raise DecafError("スタックが空です (stack underflow)")
    s.append(s[-1 - n])


@prim("depth")
def _depth(vm):
    vm.push(len(vm.stack))


@prim("clear")
def _clear(vm):
    vm.stack.clear()


# ---- 算術 -------------------------------------------------------------

@prim("+")
def _add(vm):
    s = vm.stack
    b = s.pop()
    a = s.pop()
    ta, tb = type(a), type(b)
    if (ta is int or ta is float) and (tb is int or tb is float):
        s.append(a + b)
    elif ta is str or tb is str:
        s.append(fmt(a) + fmt(b))
    elif ta is list and tb is list:
        s.append(a + b)
    else:
        raise DecafError(f"{type_name(a)} と {type_name(b)} は足せません")


@prim("-")
def _sub(vm):
    s = vm.stack
    b = s.pop()
    a = s.pop()
    s.append(need_num(a) - need_num(b))


@prim("*")
def _mul(vm):
    s = vm.stack
    b = s.pop()
    a = s.pop()
    if type(a) in (str, list) and type(b) is int:
        s.append(a * b)
    else:
        s.append(need_num(a) * need_num(b))


@prim("/")
def _div(vm):
    """整数同士で割り切れるなら整数、そうでなければ浮動小数点数を返す。"""
    b = need_num(vm.pop())
    a = need_num(vm.pop())
    if type(a) is int and type(b) is int:
        if b == 0:
            raise ZeroDivisionError
        q, r = divmod(a, b)
        vm.push(q if r == 0 else a / b)
    else:
        vm.push(a / b)


@prim("div")
def _idiv(vm):
    b = need_num(vm.pop())
    a = need_num(vm.pop())
    vm.push(a // b)


@prim("mod", "%")
def _mod(vm):
    b = need_num(vm.pop())
    a = need_num(vm.pop())
    vm.push(a % b)


@prim("neg")
def _neg(vm):
    vm.push(-need_num(vm.pop()))


@prim("abs")
def _abs(vm):
    vm.push(abs(need_num(vm.pop())))


@prim("inc")
def _inc(vm):
    vm.push(need_num(vm.pop()) + 1)


@prim("dec")
def _dec(vm):
    vm.push(need_num(vm.pop()) - 1)


@prim("min")
def _min(vm):
    b, a = vm.pop(), vm.pop()
    vm.push(b if _lt(b, a) else a)


@prim("max")
def _max(vm):
    b, a = vm.pop(), vm.pop()
    vm.push(b if _lt(a, b) else a)


@prim("pow", "**")
def _pow(vm):
    b = need_num(vm.pop())
    a = need_num(vm.pop())
    vm.push(a ** b)


@prim("sqrt")
def _sqrt(vm):
    vm.push(math.sqrt(need_num(vm.pop())))


@prim("floor")
def _floor(vm):
    vm.push(math.floor(need_num(vm.pop())))


@prim("ceil")
def _ceil(vm):
    vm.push(math.ceil(need_num(vm.pop())))


@prim("round")
def _round(vm):
    vm.push(round(need_num(vm.pop())))


@prim("even?")
def _even(vm):
    vm.push(need_int(vm.pop()) % 2 == 0)


@prim("odd?")
def _odd(vm):
    vm.push(need_int(vm.pop()) % 2 == 1)


@prim("random")
def _random(vm):
    vm.push(random.random())


@prim("random-int")
def _random_int(vm):  # ( lo hi -- n ) lo <= n <= hi
    hi = need_int(vm.pop())
    lo = need_int(vm.pop())
    vm.push(random.randint(lo, hi))


# ---- 比較・論理 -------------------------------------------------------

def _lt(a, b):
    if is_num(a) and is_num(b):
        return a < b
    if type(a) is str and type(b) is str:
        return a < b
    if type(a) is list and type(b) is list:
        for x, y in zip(a, b):
            if _lt(x, y):
                return True
            if _lt(y, x):
                return False
        return len(a) < len(b)
    raise DecafError(f"{type_name(a)} と {type_name(b)} は比較できません")


@prim("=")
def _eq(vm):
    b, a = vm.pop(), vm.pop()
    vm.push(eq(a, b))


@prim("!=")
def _ne(vm):
    b, a = vm.pop(), vm.pop()
    vm.push(not eq(a, b))


@prim("<")
def _lt_w(vm):
    b, a = vm.pop(), vm.pop()
    vm.push(_lt(a, b))


@prim(">")
def _gt(vm):
    b, a = vm.pop(), vm.pop()
    vm.push(_lt(b, a))


@prim("<=")
def _le(vm):
    b, a = vm.pop(), vm.pop()
    vm.push(not _lt(b, a))


@prim(">=")
def _ge(vm):
    b, a = vm.pop(), vm.pop()
    vm.push(not _lt(a, b))


@prim("and")
def _and(vm):  # a が偽なら a、そうでなければ b
    b, a = vm.pop(), vm.pop()
    vm.push(b if truthy(a) else a)


@prim("or")
def _or(vm):  # a が真なら a、そうでなければ b  (例: x 0 or で既定値)
    b, a = vm.pop(), vm.pop()
    vm.push(a if truthy(a) else b)


@prim("not")
def _not(vm):
    vm.push(not truthy(vm.pop()))


@prim("nil?")
def _is_nil(vm):
    vm.push(vm.pop() is None)


# ---- 制御構造 ---------------------------------------------------------

@prim("call")
def _call(vm):
    vm.invoke(vm.pop())


@prim("if")
def _if(vm):  # ( cond then else -- ... )
    e, t, c = vm.pop(), vm.pop(), vm.pop()
    vm.invoke_or_push(t if truthy(c) else e)


@prim("when")
def _when(vm):  # ( cond quot -- ... )
    q, c = vm.pop(), vm.pop()
    if truthy(c):
        vm.invoke_or_push(q)


@prim("unless")
def _unless(vm):
    q, c = vm.pop(), vm.pop()
    if not truthy(c):
        vm.invoke_or_push(q)


@prim("while")
def _while(vm):  # ( [cond] [body] -- )
    body = need_callable(vm.pop())
    cond = need_callable(vm.pop())
    while True:
        yield cond
        if not truthy(vm.pop()):
            return
        yield body


@prim("loop")
def _loop(vm):  # ( [body -- flag] -- ) flag が真の間くり返す
    body = need_callable(vm.pop())
    while True:
        yield body
        if not truthy(vm.pop()):
            return


@prim("times")
def _times(vm):  # ( n [body] -- )
    body = need_callable(vm.pop())
    n = need_int(vm.pop())
    for _ in range(n):
        yield body


@prim("for")
def _for(vm):  # ( from to [body: i --] -- )  to は含まない
    body = need_callable(vm.pop())
    to = need_num(vm.pop())
    i = need_num(vm.pop())
    while i < to:
        vm.stack.append(i)
        yield body
        i += 1


@prim("for-step")
def _for_step(vm):  # ( from to step [body: i --] -- )
    body = need_callable(vm.pop())
    step = need_num(vm.pop())
    to = need_num(vm.pop())
    i = need_num(vm.pop())
    if step == 0:
        raise DecafError("for-step のステップに 0 は使えません")
    while (i < to) if step > 0 else (i > to):
        vm.stack.append(i)
        yield body
        i += step


@prim("each")
def _each(vm):  # ( seq [body: x --] -- )  辞書なら [body: k v --]
    body = need_callable(vm.pop())
    seq = vm.pop()
    if type(seq) is dict:
        for k, v in list(seq.items()):
            vm.stack.append(k)
            vm.stack.append(v)
            yield body
    else:
        for x in iter_items(seq):
            vm.stack.append(x)
            yield body


@prim("map")
def _map(vm):  # ( seq [x -- y] -- list )
    body = need_callable(vm.pop())
    seq = vm.pop()
    out = []
    for x in iter_items(seq):
        vm.stack.append(x)
        yield body
        out.append(vm.pop())
    vm.stack.append(out)


@prim("filter")
def _filter(vm):  # ( seq [x -- flag] -- list )
    body = need_callable(vm.pop())
    seq = vm.pop()
    out = []
    for x in iter_items(seq):
        vm.stack.append(x)
        yield body
        if truthy(vm.pop()):
            out.append(x)
    vm.stack.append(out)


@prim("fold")
def _fold(vm):  # ( seq init [acc x -- acc] -- acc )
    body = need_callable(vm.pop())
    acc = vm.pop()
    seq = vm.pop()
    vm.stack.append(acc)
    for x in iter_items(seq):
        vm.stack.append(x)
        yield body


@prim("sort-by")
def _sort_by(vm):  # ( list [x -- key] -- list )
    body = need_callable(vm.pop())
    seq = iter_items(vm.pop())
    keys = []
    for x in seq:
        vm.stack.append(x)
        yield body
        keys.append(vm.pop())
    order = _sorted_indices(keys)
    vm.stack.append([seq[i] for i in order])


@prim("dip")
def _dip(vm):  # ( x [q] -- x ) x を退避して q を実行し、戻す
    body = vm.pop()
    x = vm.pop()
    yield body
    vm.stack.append(x)


@prim("try")
def _try(vm):  # ( [body] [handler: err --] -- )
    from .vm import TRY, Frame
    handler = need_callable(vm.pop())
    body = vm.pop()
    fr = Frame(TRY)
    fr.handler = handler
    fr.depth = len(vm.stack)
    fr.nmarks = len(vm.marks)
    vm.push_frame(fr)
    vm.invoke(body)


@prim("throw")
def _throw(vm):
    raise DecafError(vm.pop())


@prim("return")
def _return(vm):
    vm.do_return()


@prim("exit")
def _exit(vm):  # ( code -- )
    raise DecafExit(need_int(vm.pop()))


@prim("assert")
def _assert(vm):  # ( flag message -- )
    msg, flag = vm.pop(), vm.pop()
    if not truthy(flag):
        raise DecafError("assert 失敗: " + fmt(msg))


@prim("eval")
def _eval(vm):  # ( source -- ... )
    from .vm import CODE, Frame
    code = vm.compile(need_str(vm.pop()), "<eval>")
    vm.push_frame(Frame(CODE, code, vm.globals, True))


@prim("include")
def _include(vm):  # ( path -- )  同じファイルは一度だけ読み込む
    from .vm import CODE, Frame
    path = need_str(vm.pop())
    cur = vm.current_file()
    if not os.path.isabs(path) and cur:
        path = os.path.join(os.path.dirname(cur), path)
    key = os.path.abspath(path)
    if key in vm.included:
        return
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    vm.included.add(key)
    code = vm.compile(src, path)
    vm.push_frame(Frame(CODE, code, vm.globals, True))


# ---- 型・変換 ---------------------------------------------------------

@prim("type")
def _type(vm):
    vm.push(type_name(vm.pop()))


@prim("str")
def _str(vm):
    vm.push(fmt(vm.pop()))


@prim("repr")
def _repr(vm):
    vm.push(fmt(vm.pop(), True))


def _parse_num(s):
    from .lexer import parse_number
    return parse_number(s.strip())


@prim("num")
def _num(vm):  # ( string -- number|nil )
    v = vm.pop()
    if is_num(v):
        vm.push(v)
    else:
        vm.push(_parse_num(need_str(v)))


@prim("int")
def _int(vm):
    v = vm.pop()
    if type(v) is str:
        n = _parse_num(v)
        if n is None:
            raise DecafError(f"整数に変換できません: {fmt(v, True)}")
        v = n
    vm.push(int(need_num(v)))


@prim("float")
def _float(vm):
    v = vm.pop()
    if type(v) is str:
        n = _parse_num(v)
        if n is None:
            raise DecafError(f"数値に変換できません: {fmt(v, True)}")
        v = n
    vm.push(float(need_num(v)))


# ---- 文字列 -----------------------------------------------------------

@prim("len")
def _len(vm):
    v = vm.pop()
    vm.push(len(need(v, (str, list, dict), "文字列・リスト・辞書")))


@prim("chars")
def _chars(vm):
    vm.push(list(need_str(vm.pop())))


@prim("split")
def _split(vm):  # ( s sep -- list )
    sep = need_str(vm.pop())
    s = need_str(vm.pop())
    vm.push(list(s) if sep == "" else s.split(sep))


@prim("words")
def _words(vm):  # ( s -- list ) 空白で分割
    vm.push(need_str(vm.pop()).split())


@prim("lines")
def _lines(vm):
    vm.push(need_str(vm.pop()).splitlines())


@prim("join")
def _join(vm):  # ( list sep -- s )
    sep = need_str(vm.pop())
    vm.push(sep.join(fmt(x) for x in need_list(vm.pop())))


@prim("upper")
def _upper(vm):
    vm.push(need_str(vm.pop()).upper())


@prim("lower")
def _lower(vm):
    vm.push(need_str(vm.pop()).lower())


@prim("trim")
def _trim(vm):
    vm.push(need_str(vm.pop()).strip())


@prim("replace")
def _replace(vm):  # ( s old new -- s )
    new = need_str(vm.pop())
    old = need_str(vm.pop())
    vm.push(need_str(vm.pop()).replace(old, new))


@prim("starts-with?")
def _starts(vm):
    p = need_str(vm.pop())
    vm.push(need_str(vm.pop()).startswith(p))


@prim("ends-with?")
def _ends(vm):
    p = need_str(vm.pop())
    vm.push(need_str(vm.pop()).endswith(p))


@prim("ord")
def _ord(vm):
    s = need_str(vm.pop())
    if len(s) != 1:
        raise DecafError("ord には 1 文字の文字列が必要です")
    vm.push(ord(s))


@prim("chr")
def _chr(vm):
    vm.push(chr(need_int(vm.pop())))


@prim("format")
def _format(vm):  # ( list template -- s )  "{}" を順に置き換える
    tpl = need_str(vm.pop())
    args = need_list(vm.pop())
    parts = tpl.split("{}")
    if len(parts) - 1 != len(args):
        raise DecafError(f"format: プレースホルダは {len(parts) - 1} 個ですが値は {len(args)} 個です")
    out = [parts[0]]
    for a, p in zip(args, parts[1:]):
        out.append(fmt(a))
        out.append(p)
    vm.push("".join(out))


# ---- リスト・シーケンス -----------------------------------------------

@prim("nth")
def _nth(vm):  # ( seq i -- x )
    i = need_int(vm.pop())
    vm.push(need_seq(vm.pop())[i])


@prim("set-nth")
def _set_nth(vm):  # ( list i x -- list )
    x = vm.pop()
    i = need_int(vm.pop())
    lst = need_list(vm.pop())
    lst[i] = x
    vm.push(lst)


@prim("push")
def _push(vm):  # ( list x -- list )  末尾に追加 (破壊的)
    x = vm.pop()
    lst = need_list(vm.pop())
    lst.append(x)
    vm.push(lst)


@prim("pop")
def _pop(vm):  # ( list -- list x )  末尾を取り出す (破壊的)
    lst = need_list(vm.pop())
    if not lst:
        raise DecafError("空のリストからは取り出せません")
    x = lst.pop()
    vm.push(lst)
    vm.push(x)


@prim("insert")
def _insert(vm):  # ( list i x -- list )
    x = vm.pop()
    i = need_int(vm.pop())
    lst = need_list(vm.pop())
    lst.insert(i, x)
    vm.push(lst)


@prim("first")
def _first(vm):
    vm.push(need_seq(vm.pop())[0])


@prim("last")
def _last(vm):
    vm.push(need_seq(vm.pop())[-1])


@prim("rest")
def _rest(vm):
    vm.push(need_seq(vm.pop())[1:])


@prim("slice")
def _slice(vm):  # ( seq start end -- seq )  end が nil なら末尾まで
    end = vm.pop()
    start = vm.pop()
    seq = need_seq(vm.pop())
    start = None if start is None else need_int(start)
    end = None if end is None else need_int(end)
    vm.push(seq[start:end])


@prim("reverse")
def _reverse(vm):
    vm.push(need_seq(vm.pop())[::-1])


def _sorted_indices(keys):
    import functools

    def cmp(i, j):
        if _lt(keys[i], keys[j]):
            return -1
        if _lt(keys[j], keys[i]):
            return 1
        return 0
    return sorted(range(len(keys)), key=functools.cmp_to_key(cmp))


@prim("sort")
def _sort(vm):
    seq = iter_items(vm.pop())
    vm.push([seq[i] for i in _sorted_indices(seq)])


@prim("range")
def _range(vm):  # ( from to -- list )  to は含まない
    to = need_int(vm.pop())
    vm.push(list(range(need_int(vm.pop()), to)))


@prim("empty?")
def _empty(vm):
    vm.push(len(need(vm.pop(), (str, list, dict), "文字列・リスト・辞書")) == 0)


@prim("contains?")
def _contains(vm):  # ( seq x -- flag )
    x = vm.pop()
    seq = vm.pop()
    if type(seq) is str:
        vm.push(need_str(x) in seq)
    elif type(seq) is list:
        vm.push(any(eq(y, x) for y in seq))
    elif type(seq) is dict:
        vm.push(need_key(x) in seq)
    else:
        raise DecafError(f"{type_name(seq)} に contains? は使えません")


@prim("index-of")
def _index_of(vm):  # ( seq x -- i )  見つからなければ -1
    x = vm.pop()
    seq = need_seq(vm.pop())
    if type(seq) is str:
        vm.push(seq.find(need_str(x)))
        return
    for i, y in enumerate(seq):
        if eq(y, x):
            vm.push(i)
            return
    vm.push(-1)


@prim("copy")
def _copy(vm):
    v = vm.pop()
    vm.push(v.copy() if type(v) in (list, dict) else v)


@prim("sum")
def _sum(vm):
    total = 0
    for x in need_list(vm.pop()):
        total += need_num(x)
    vm.push(total)


# ---- 辞書 -------------------------------------------------------------

@prim("dict")
def _dict(vm):
    vm.push({})


@prim("get")
def _get(vm):  # ( dict key -- value|nil ) リスト・文字列なら範囲外で nil
    k = vm.pop()
    c = vm.pop()
    if type(c) is dict:
        vm.push(c.get(need_key(k)))
    else:
        seq = need_seq(c)
        i = need_int(k)
        vm.push(seq[i] if -len(seq) <= i < len(seq) else None)


@prim("put")
def _put(vm):  # ( dict key value -- dict )
    v = vm.pop()
    k = need_key(vm.pop())
    d = need_dict(vm.pop())
    d[k] = v
    vm.push(d)


@prim("has?")
def _has(vm):  # ( dict key -- flag )
    k = need_key(vm.pop())
    vm.push(k in need_dict(vm.pop()))


@prim("del")
def _del(vm):  # ( dict key -- dict )
    k = need_key(vm.pop())
    d = need_dict(vm.pop())
    d.pop(k, None)
    vm.push(d)


@prim("keys")
def _keys(vm):
    vm.push(list(need_dict(vm.pop()).keys()))


@prim("values")
def _values(vm):
    vm.push(list(need_dict(vm.pop()).values()))


# ---- 入出力 -----------------------------------------------------------

@prim(".", "println")
def _println(vm):
    vm.out.write(fmt(vm.pop()) + "\n")


@prim("print")
def _print(vm):
    vm.out.write(fmt(vm.pop()))


@prim("cr")
def _cr(vm):
    vm.out.write("\n")


@prim(".s")
def _dot_s(vm):
    vm.out.write(stack_repr(vm.stack) + "\n")


def stack_repr(stack):
    return f"<{len(stack)}> " + " ".join(fmt(x, True) for x in stack)


@prim("eprint")
def _eprint(vm):
    sys.stderr.write(fmt(vm.pop()) + "\n")


@prim("read-line")
def _read_line(vm):  # ( -- s|nil )  EOF なら nil
    vm.out.flush()
    line = vm.inp.readline()
    vm.push(None if line == "" else line.rstrip("\n").rstrip("\r"))


@prim("input")
def _input(vm):  # ( prompt -- s|nil )
    vm.out.write(fmt(vm.pop()))
    _read_line(vm)


@prim("read-all")
def _read_all(vm):
    vm.push(vm.inp.read())


@prim("read-file")
def _read_file(vm):  # ( path -- s )
    with open(need_str(vm.pop()), encoding="utf-8") as fh:
        vm.push(fh.read())


@prim("read-lines")
def _read_lines(vm):  # ( path -- list )
    with open(need_str(vm.pop()), encoding="utf-8") as fh:
        vm.push(fh.read().splitlines())


@prim("write-file")
def _write_file(vm):  # ( s path -- )
    path = need_str(vm.pop())
    data = fmt(vm.pop())
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(data)


@prim("append-file")
def _append_file(vm):  # ( s path -- )
    path = need_str(vm.pop())
    data = fmt(vm.pop())
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(data)


@prim("file-exists?")
def _file_exists(vm):
    vm.push(os.path.exists(need_str(vm.pop())))


@prim("delete-file")
def _delete_file(vm):
    os.remove(need_str(vm.pop()))


@prim("list-dir")
def _list_dir(vm):
    vm.push(sorted(os.listdir(need_str(vm.pop()))))


# ---- その他 -----------------------------------------------------------

@prim("args")
def _args(vm):
    vm.push(list(vm.argv))


@prim("now")
def _now(vm):
    vm.push(time.time())


@prim("getenv")
def _getenv(vm):  # ( name -- s|nil )
    vm.push(os.environ.get(need_str(vm.pop())))
