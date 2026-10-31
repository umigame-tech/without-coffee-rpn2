"""コマンドラインインターフェース。

    decaf FILE [ARGS...]    Decaf プログラムを実行する
    decaf -e CODE [ARGS...] コード文字列を実行する
    decaf -                 標準入力からプログラムを読んで実行する
    decaf                   REPL (対話モード) を起動する
"""

import os
import sys

from . import __version__
from .builtins import stack_repr
from .errors import DecafError, DecafExit, IncompleteInput
from .vm import VM

USAGE = """\
使い方:
  decaf FILE [ARGS...]      Decaf プログラム (.dcf) を実行する
  decaf -e CODE [ARGS...]   コード文字列を実行する
  decaf -                   標準入力からプログラムを読んで実行する
  decaf                     REPL (対話モード) を起動する
  decaf --dump FILE         コンパイル結果の命令列を表示する

オプション:
  -h, --help                このヘルプを表示する
  -v, --version             バージョンを表示する
"""


def report(e):
    sys.stdout.flush()
    sys.stderr.write(f"エラー: {e}\n")
    for t in e.trace:
        sys.stderr.write(f"  呼び出し元: {t}\n")


def run_source(vm, src, file):
    try:
        vm.run(src, file)
    except DecafExit as e:
        return e.code
    except DecafError as e:
        report(e)
        return 1
    finally:
        sys.stdout.flush()
    return 0


def repl(vm):
    try:
        import readline  # noqa: F401  行編集と履歴を有効にする
    except ImportError:
        pass
    print(f"Decaf {__version__} — 逆ポーランド記法の言語です。Ctrl-D で終了します。")
    buf = ""
    while True:
        try:
            line = input("...... " if buf else "decaf> ")
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print()
            buf = ""
            continue
        buf += line + "\n"
        try:
            vm.run(buf, "<repl>")
        except IncompleteInput:
            continue
        except DecafExit as e:
            return e.code
        except DecafError as e:
            report(e)
        except KeyboardInterrupt:
            vm._unwind_all()
            print("\n中断しました")
        buf = ""
        sys.stdout.flush()
        if vm.stack:
            print(stack_repr(vm.stack))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("-h", "--help"):
        print(USAGE, end="")
        return 0
    if argv and argv[0] in ("-v", "--version"):
        print(f"Decaf {__version__}")
        return 0
    try:
        if not argv:
            if sys.stdin.isatty():
                return repl(VM())
            return run_source(VM(), sys.stdin.read(), "<stdin>")
        if argv[0] == "--dump":
            if len(argv) < 2:
                sys.stderr.write("エラー: --dump にはファイル名が必要です\n")
                return 2
            from .compiler import compile_source
            with open(argv[1], encoding="utf-8") as fh:
                code, defs = compile_source(fh.read(), argv[1])
            for name, w in defs.items():
                print(f": {name}")
                print(w.code.dump(1))
            print("<toplevel>")
            print(code.dump(1))
            return 0
        if argv[0] == "-e":
            if len(argv) < 2:
                sys.stderr.write("エラー: -e にはコードが必要です\n")
                return 2
            return run_source(VM(argv[2:]), argv[1], "<-e>")
        if argv[0] == "-":
            return run_source(VM(argv[1:]), sys.stdin.read(), "<stdin>")
        path = argv[0]
        try:
            with open(path, encoding="utf-8") as fh:
                src = fh.read()
        except OSError as e:
            sys.stderr.write(f"エラー: ファイルを開けません: {path}: {e.strerror}\n")
            return 2
        vm = VM(argv[1:])
        vm.included.add(os.path.abspath(path))
        return run_source(vm, src, path)
    except DecafError as e:
        report(e)
        return 1
    except KeyboardInterrupt:
        sys.stderr.write("\n中断しました\n")
        return 130


if __name__ == "__main__":
    sys.exit(main())
