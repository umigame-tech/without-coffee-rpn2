"""スタックベースの仮想機械。

Python の再帰を使わず、明示的なフレームスタックで実行する。そのため
深い再帰が可能で、末尾位置の呼び出しはフレームを置き換える (末尾呼び出し最適化)。

フレームの種類:
    CODE  命令列を実行するフレーム (ワード本体・クォーテーション・トップレベル)
    GEN   ジェネレータで書かれた組み込みワード (while, map など)。
          クォーテーションを yield すると VM がそれを実行し、終わると再開する。
    TRY   `try` の例外ハンドラを保持するマーカー。
"""

import os
import sys

from .compiler import GSTORE, LBEGIN, LEND, LOCALS, PUSH, QUOT, STORE, WORD, WREF, compile_source
from .errors import DecafError, DecafExit
from .values import Prim, Quot, Word, type_name

CODE, GEN, TRY = 0, 1, 2
MAX_FRAMES = 200_000


class Frame:
    __slots__ = ("kind", "code", "ops", "pc", "env", "boundary", "gen", "handler", "depth", "nmarks")

    def __init__(self, kind, code=None, env=None, boundary=False, gen=None):
        self.kind = kind
        self.code = code
        self.ops = code.ops if code is not None else None
        self.pc = 0
        self.env = env
        # boundary: `return` で抜ける単位 (ワード呼び出し・トップレベル・eval) か
        self.boundary = boundary
        self.gen = gen
        self.handler = None
        self.depth = 0
        self.nmarks = 0


def translate_exception(e):
    """Python の例外を Decaf のエラーメッセージに変換する。"""
    if isinstance(e, ZeroDivisionError):
        return "ゼロで割ることはできません"
    if isinstance(e, IndexError):
        if "pop from empty list" in str(e):
            return "スタックが空です (stack underflow)"
        return "インデックスが範囲外です"
    if isinstance(e, KeyError):
        return f"キーが見つかりません: {e}"
    if isinstance(e, UnicodeError):
        return f"文字コードのエラー: {e}"
    if isinstance(e, OSError):
        if e.filename is not None:
            return f"ファイルエラー: {e.strerror}: {e.filename}"
        return f"ファイルエラー: {e.strerror or e}"
    if isinstance(e, TypeError):
        return f"型エラー: {e}"
    if isinstance(e, ValueError):
        return f"値エラー: {e}"
    if isinstance(e, OverflowError):
        return f"数値が大きすぎます: {e}"
    if isinstance(e, RecursionError):
        return "データ構造の入れ子が深すぎます"
    return f"{type(e).__name__}: {e}"


CONVERTED = (ZeroDivisionError, IndexError, KeyError, TypeError, ValueError,
             OSError, OverflowError, RecursionError)


class VM:
    def __init__(self, argv=None, out=None, inp=None):
        from .builtins import PRIMS
        self.stack = []
        self.frames = []
        self.marks = []
        self.globals = {}
        self.words = dict(PRIMS)
        self.argv = list(argv or [])
        self.out = out if out is not None else sys.stdout
        self.inp = inp if inp is not None else sys.stdin
        self.included = set()

    # ---- スタック操作 -------------------------------------------------
    def push(self, v):
        self.stack.append(v)

    def pop(self):
        try:
            return self.stack.pop()
        except IndexError:
            raise DecafError("スタックが空です (stack underflow)") from None

    # ---- コンパイル ---------------------------------------------------
    def compile(self, src, file="<input>"):
        code, defs = compile_source(src, file)
        self.words.update(defs)
        return code

    def current_file(self):
        for f in reversed(self.frames):
            if f.kind == CODE and f.code.file and not f.code.file.startswith("<"):
                return f.code.file
        return None

    # ---- 実行 ---------------------------------------------------------
    def run(self, src, file="<input>"):
        """ソース文字列をコンパイルして実行する。"""
        self.execute(self.compile(src, file))

    def run_file(self, path):
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        self.included.add(os.path.abspath(path))
        self.run(src, path)

    def execute(self, code):
        self.frames.append(Frame(CODE, code, self.globals, True))
        self._loop()

    def push_frame(self, fr):
        frames = self.frames
        if frames:
            top = frames[-1]
            # 末尾呼び出し最適化: 実行し終えたコードフレームは置き換える
            if top.kind == CODE and top.pc >= len(top.ops):
                frames.pop()
                if top.boundary:
                    fr.boundary = True
        if len(frames) >= MAX_FRAMES:
            raise DecafError("コールスタックがあふれました (再帰が深すぎます)")
        frames.append(fr)

    def invoke(self, w):
        """呼び出し可能な値を実行する。"""
        t = type(w)
        if t is Prim:
            if w.gen:
                self.push_frame(Frame(GEN, gen=w.fn(self)))
            else:
                w.fn(self)
        elif t is Quot:
            self.push_frame(Frame(CODE, w.code, w.env))
        elif t is Word:
            self.push_frame(Frame(CODE, w.code, {}, True))
        else:
            raise DecafError(f"{type_name(w)} は呼び出せません")

    def invoke_or_push(self, v):
        """呼び出し可能なら実行し、そうでなければ値をそのまま積む (if などで使う)。"""
        if isinstance(v, (Quot, Word, Prim)):
            self.invoke(v)
        else:
            self.stack.append(v)

    def do_return(self):
        frames = self.frames
        while frames:
            fr = frames.pop()
            if fr.kind == GEN:
                fr.gen.close()
            if fr.boundary:
                break

    def _loop(self):
        while self.frames:
            try:
                self._run()
            except DecafExit:
                self._unwind_all()
                raise
            except DecafError as e:
                self._handle_error(e)
            except CONVERTED as e:
                self._handle_error(DecafError(translate_exception(e)))

    def _unwind_all(self):
        for fr in self.frames:
            if fr.kind == GEN:
                fr.gen.close()
        self.frames.clear()
        self.marks.clear()

    def _location(self):
        for f in reversed(self.frames):
            if f.kind == CODE and f.pc > 0:
                return f"{f.code.file}:{f.ops[f.pc - 1][2]}"
        return None

    def _traceback(self):
        trace = []
        for f in reversed(self.frames):
            if f.kind == CODE and f.boundary and f.pc > 0:
                trace.append(f"{f.code.name} ({f.code.file}:{f.ops[f.pc - 1][2]})")
        if len(trace) > 12:
            trace = trace[:6] + [f"... ({len(trace) - 12} フレーム省略)"] + trace[-6:]
        return trace

    def _handle_error(self, e):
        frames = self.frames
        for i in range(len(frames) - 1, -1, -1):
            if frames[i].kind == TRY:
                break
        else:
            if e.location is None:
                e.location = self._location()
            e.trace = self._traceback()
            self._unwind_all()
            raise e
        tf = frames[i]
        for fr in frames[i + 1:]:
            if fr.kind == GEN:
                fr.gen.close()
        del frames[i:]
        del self.stack[tf.depth:]
        del self.marks[tf.nmarks:]
        self.stack.append(e.value)
        self.invoke(tf.handler)

    def _run(self):
        frames = self.frames
        stack = self.stack
        g = self.globals
        words = self.words
        while frames:
            f = frames[-1]
            kind = f.kind
            if kind == CODE:
                ops = f.ops
                pc = f.pc
                if pc >= len(ops):
                    frames.pop()
                    continue
                op, arg, _ = ops[pc]
                f.pc = pc + 1
                if op == WORD:
                    env = f.env
                    if arg in env:
                        stack.append(env[arg])
                    elif arg in g:
                        stack.append(g[arg])
                    else:
                        w = words.get(arg)
                        if w is None:
                            raise DecafError(f"未定義のワードです: {arg}")
                        if type(w) is Prim and not w.gen:
                            w.fn(self)
                        else:
                            self.invoke(w)
                elif op == PUSH:
                    stack.append(arg)
                elif op == QUOT:
                    stack.append(Quot(arg, f.env))
                elif op == STORE:
                    f.env[arg] = self.pop()
                elif op == GSTORE:
                    g[arg] = self.pop()
                elif op == LOCALS:
                    n = len(arg)
                    if len(stack) < n:
                        raise DecafError("スタックが空です (stack underflow)")
                    env = f.env
                    vals = stack[len(stack) - n:]
                    del stack[len(stack) - n:]
                    for k, v in zip(arg, vals):
                        env[k] = v
                elif op == LBEGIN:
                    self.marks.append(len(stack))
                elif op == LEND:
                    d = self.marks.pop()
                    items = stack[d:]
                    del stack[d:]
                    stack.append(items)
                elif op == WREF:
                    w = words.get(arg)
                    if w is None:
                        raise DecafError(f"未定義のワードです: {arg}")
                    stack.append(w)
            elif kind == GEN:
                try:
                    q = f.gen.send(None)
                except StopIteration:
                    frames.pop()
                    continue
                self.invoke(q)
            else:  # TRY: 本体が正常終了した
                frames.pop()
