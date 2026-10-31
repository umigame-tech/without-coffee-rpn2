"""Decaf の例外クラス。"""


class DecafError(Exception):
    """実行時エラー。`value` は `throw` された値 (内部エラーではメッセージ文字列)。"""

    def __init__(self, value, location=None):
        self.value = value
        self.location = location
        self.trace = []
        super().__init__(value)

    @property
    def message(self):
        from .values import fmt
        return fmt(self.value)

    def __str__(self):
        if self.location:
            return f"{self.location}: {self.message}"
        return self.message


class DecafSyntaxError(DecafError):
    """構文エラー。"""


class IncompleteInput(DecafSyntaxError):
    """入力が途中で終わっている (REPL で継続行を読むために使う)。"""


class DecafExit(Exception):
    """`exit` によるプログラム終了。"""

    def __init__(self, code=0):
        self.code = code
        super().__init__(code)
