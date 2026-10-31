# Decaf — 逆ポーランド記法の汎用プログラミング言語

**Decaf** は、逆ポーランド記法 (RPN) を採用したスタックベースの汎用プログラミング言語です。
値をスタックに積み、ワード (関数) がスタックから値を取り出して結果を積み直す、というモデルで
すべての計算を行います。

```
: fact ( n -- n! )
  dup 1 <= [ drop 1 ] [ dup 1 - fact * ] if ;

"10! = " 10 fact + .        # => 10! = 3628800
```

主な特徴は次のとおりです。

- スタックベースの実行モデル (Python の再帰を使わない仮想機械で実行)
- ユーザー定義ワード (関数)、再帰、相互再帰、**末尾呼び出し最適化**
- 条件分岐 (`if` / `when` / `unless`)、ループ (`while` / `times` / `for` / `each` / `loop`)
- 数値 (多倍長整数・浮動小数点数)、文字列、真偽値、nil、リスト、辞書
- クォーテーション (無名関数) とクロージャ、`map` / `filter` / `fold` などの高階ワード
- ローカル変数・グローバル変数、例外処理 (`try` / `throw`)
- ファイルの読み書き、標準入出力、コマンドライン引数、`include` によるファイル分割
- プログラムを実行する CLI と REPL (対話モード)

外部ライブラリには依存せず、Python 3.8 以降だけで動きます。

## インストールと実行

```sh
# インストールせずにそのまま使う
bin/decaf examples/hello.dcf

# pip でインストールすると decaf コマンドが使えるようになる
pip install .
decaf examples/hello.dcf
```

| コマンド | 説明 |
|---|---|
| `decaf FILE [ARGS...]` | プログラムを実行します。`ARGS` は `args` ワードで取得できます |
| `decaf -e 'CODE' [ARGS...]` | コード文字列を実行します |
| `decaf -` | 標準入力からプログラムを読んで実行します |
| `decaf` | REPL を起動します (各行の実行後にスタックの内容を表示します) |
| `decaf --dump FILE` | コンパイル結果の命令列を表示します |

エラーが起きると、ファイル名・行番号と呼び出し履歴を標準エラー出力に表示し、終了コード 1 で終了します。
`n exit` を使うと任意の終了コードで終了できます。ファイルの先頭に `#!/usr/bin/env decaf` と書けば
スクリプトとして直接実行することもできます。

```
$ bin/decaf
decaf> 1 2 +
<1> 3
decaf> : sq dup * ;
<1> 3
decaf> sq
<1> 9
```

## 言語ガイド

### 基本: スタックと逆ポーランド記法

トークンは空白で区切られ、左から順に実行されます。リテラルはスタックに積まれ、ワードはスタックを操作します。

```
1 2 + 3 *  .        # (1 + 2) * 3 を計算して表示 => 9
```

スタック効果は `( 入力 -- 出力 )` の形のコメントで書く慣習です。`(` の直後に空白があると `)` までが
コメントになり、`#` から行末までもコメントになります。

### 値の種類

| 型 | 例 | 備考 |
|---|---|---|
| int | `42` `-7` `0xFF` `0b1010` | 多倍長整数です |
| float | `3.14` `1e-3` | |
| string | `"こんにちは\n"` | エスケープ: `\n \t \r \" \\ \0 \e \uXXXX` |
| bool | `true` `false` | |
| nil | `nil` | 「値がない」ことを表します |
| list | `{ 1 2 "three" }` | `{ }` の中のコードを実行し、積まれた値を集めます (`{ 1 2 + }` は `{ 3 }`) |
| dict | `dict "key" 1 put` | 文字列・数値・真偽値・nil をキーにできます |
| quotation | `[ dup * ]` | 実行を遅延したコード片 (無名関数) です |

真偽の判定では `false` と `nil` だけが偽になり、`0` や `""` は真として扱われます。

### ワード (関数) の定義

```
: name  本体 ;
```

ワードは使う前でも後でも定義できます (ファイル単位で先に登録されるため、相互再帰も書けます)。
同じ名前で再定義すると上書きされます。定義はトップレベルにのみ書けます。

```
: square ( n -- n*n ) dup * ;
: cube   ( n -- n^3 ) dup square * ;
3 cube .     # => 27
```

### 変数

| 構文 | 意味 |
|---|---|
| `>name` | スタックから値を取り出し、ローカル変数 `name` に代入します (トップレベルではグローバル変数になります) |
| `>>name` | スタックから値を取り出し、グローバル変数 `name` に代入します |
| `\| a b c \|` | 3 つの値を取り出して `a b c` に代入します (`c` がスタックの一番上の値です) |
| `name` | 変数の値を積みます。変数がなければ同名のワードを実行します |

ローカル変数はワードの呼び出しごとに作られるので、再帰しても干渉しません。

```
: hypot | a b | a a * b b * + sqrt ;
3 4 hypot .    # => 5.0
```

### クォーテーションとクロージャ

`[ ... ]` はコードを値として積みます。`call` で実行できます。クォーテーションは作られた場所の
ローカル変数を捕捉するクロージャです。

```
: make-adder ( n -- [x -- x+n] ) >n [ n + ] ;
5 make-adder >add5
10 add5 call .        # => 15
```

`'name` と書くと、ワードを実行せずに値として積めます (`{ 1 2 3 } 0 '+ fold`)。

### 条件分岐

```
x 0 < [ "負" ] [ "0以上" ] if .     # ( 条件 then else -- )
x 0 = [ "ゼロです" . ] when          # ( 条件 then -- )
x 0 = [ "ゼロではありません" . ] unless
x 0 < "負" "0以上" if .             # 分岐が値ならそのまま積まれます
```

### ループ

```
0 >i [ i 5 < ] [ i . i 1 + >i ] while   # [条件] [本体] while
3 [ "hi" . ] times                      # n [本体] times
0 10 [ . ] for                          # from to [本体: i --] for  (to は含みません)
10 0 -2 [ . ] for-step                  # from to step [本体] for-step
{ 1 2 3 } [ . ] each                    # リスト・文字列・辞書 ([k v --]) を走査します
[ read-line dup nil? [ drop false ] [ . true ] if ] loop  # 本体が真を返す間くり返します
```

### 早期リターンと例外

`return` は現在のワードを途中で抜けます (ループの中からでも使えます)。

```
: sign ( n -- s )
  | n |
  n 0 < [ "負" return ] when
  n 0 = [ "ゼロ" return ] when
  "正" ;
```

`[ 本体 ] [ ハンドラ ] try` は、本体でエラーが起きるとスタックを本体開始時の深さに戻し、
エラー値を積んでハンドラを実行します。`throw` で任意の値を投げられます。
ゼロ除算・ファイルが見つからない・型の誤りなどの実行時エラーもメッセージ文字列として捕捉できます。

```
[ "data.txt" read-file ] [ "読めませんでした: " swap + . ] try
[ "独自のエラー" throw ] [ . ] try
```

### 再帰

非末尾の再帰は既定で約 20 万段まで可能です。末尾位置での呼び出し (ワード・`call`・`if` の分岐など)
はフレームを再利用するため、何段でもスタックを消費しません。

```
: countdown ( n -- ) dup 0 > [ 1 - countdown ] [ drop ] if ;
1000000 countdown     # 末尾再帰なので問題なく動きます
```

### ファイル分割

`"lib/util.dcf" include` で別ファイルを読み込みます。相対パスは読み込み元ファイルのディレクトリを
基準に解決され、同じファイルは一度しか読み込まれません。`"1 2 +" eval` で文字列をコードとして実行できます。

## 組み込みワード一覧

### スタック操作

| ワード | スタック効果 |
|---|---|
| `dup` | `( a -- a a )` |
| `drop` | `( a -- )` |
| `swap` | `( a b -- b a )` |
| `over` | `( a b -- a b a )` |
| `rot` | `( a b c -- b c a )` |
| `-rot` | `( a b c -- c a b )` |
| `nip` | `( a b -- b )` |
| `tuck` | `( a b -- b a b )` |
| `2dup` / `2drop` | `( a b -- a b a b )` / `( a b -- )` |
| `pick` | `( ... n -- ... x )` n 番目の要素を複製します (`0 pick` は `dup`) |
| `depth` / `clear` | スタックの深さを積みます / スタックを空にします |

### 算術・数値

| ワード | 説明 |
|---|---|
| `+` | 数値の加算です。文字列が含まれていれば文字列として連結し、リスト同士なら連結します |
| `-` `*` | 減算・乗算です (`"ab" 3 *` や `{ 0 } 5 *` で繰り返しもできます) |
| `/` | 除算です。整数同士で割り切れれば整数、そうでなければ浮動小数点数になります |
| `div` `mod` (`%`) | 切り捨て除算・剰余です |
| `pow` (`**`) `sqrt` `abs` `neg` `inc` `dec` | |
| `min` `max` `floor` `ceil` `round` | |
| `even?` `odd?` | |
| `random` / `random-int` | `( -- 0〜1 の小数 )` / `( lo hi -- n )` (両端を含みます) |

### 比較・論理

| ワード | 説明 |
|---|---|
| `=` `!=` | 等価比較です (リストや辞書は中身で比較し、`1` と `1.0` は等しく、`1` と `true` は等しくありません) |
| `<` `>` `<=` `>=` | 数値同士・文字列同士・リスト同士を比較します |
| `and` `or` `not` | `a b and` は a が偽なら a、そうでなければ b を返します。`a b or` は a が真なら a、そうでなければ b を返します (`x 0 or` で既定値を与えられます) |
| `nil?` | `( x -- flag )` |

### 制御

| ワード | スタック効果 |
|---|---|
| `call` | `( quot -- ... )` |
| `if` | `( flag then else -- ... )` |
| `when` / `unless` | `( flag quot -- ... )` |
| `while` | `( [-- flag] [--] -- )` |
| `loop` | `( [-- flag] -- )` |
| `times` | `( n quot -- )` |
| `for` / `for-step` | `( from to [i --] -- )` / `( from to step [i --] -- )` |
| `each` | `( seq [x --] -- )` 辞書の場合は `[k v --]` |
| `map` / `filter` | `( seq [x -- y] -- list )` / `( seq [x -- flag] -- list )` |
| `fold` | `( seq init [acc x -- acc] -- acc )` |
| `sort-by` | `( seq [x -- key] -- list )` |
| `dip` | `( x quot -- x )` x を一時的に退避して quot を実行します |
| `try` / `throw` | `( [body] [err --] -- )` / `( value -- )` |
| `return` | 現在のワードから抜けます |
| `exit` | `( code -- )` プログラムを終了します |
| `assert` | `( flag message -- )` |
| `eval` / `include` | `( source -- )` / `( path -- )` |

### 文字列

| ワード | スタック効果 |
|---|---|
| `len` | `( seq -- n )` 文字列・リスト・辞書の長さを返します |
| `str` / `repr` | 値を文字列にします (`repr` は文字列を引用符付きにします) |
| `num` / `int` / `float` | 数値に変換します (`num` は変換できなければ nil を返します) |
| `split` / `join` | `( s sep -- list )` / `( list sep -- s )` |
| `words` / `lines` / `chars` | 空白・改行・1 文字ごとに分割します |
| `upper` `lower` `trim` `reverse` | |
| `replace` | `( s old new -- s )` |
| `contains?` / `index-of` | `( seq x -- flag )` / `( seq x -- i )` 見つからなければ -1 を返します |
| `starts-with?` `ends-with?` | `( s prefix -- flag )` |
| `ord` / `chr` | 文字とコードポイントを相互に変換します |
| `format` | `( list template -- s )` `{ 1 2 } "{} + {}" format` |
| `slice` | `( seq start end -- seq )` end に nil を渡すと末尾までになります |

### リスト・辞書

| ワード | スタック効果 |
|---|---|
| `nth` / `get` | `( seq i -- x )` / `( coll key -- x\|nil )` (`get` は範囲外やキーがないときに nil を返します) |
| `set-nth` | `( list i x -- list )` |
| `push` / `pop` / `insert` | `( list x -- list )` / `( list -- list x )` / `( list i x -- list )` |
| `first` `last` `rest` | |
| `sort` `reverse` `copy` `sum` `empty?` | |
| `range` | `( from to -- list )` |
| `dict` | `( -- dict )` 空の辞書を作ります |
| `put` / `del` | `( dict key value -- dict )` / `( dict key -- dict )` |
| `has?` `keys` `values` | |

`push` `pop` `set-nth` `insert` `put` `del` は渡されたリストや辞書を直接書き換え、同じものを積み直します。
複製したい場合は `copy` を使ってください。

### 入出力・ファイル

| ワード | スタック効果 |
|---|---|
| `.` (`println`) / `print` / `cr` | 改行付きで表示します / 改行なしで表示します / 改行を出力します |
| `.s` | スタック全体を表示します (デバッグ用) |
| `eprint` | 標準エラー出力に表示します |
| `read-line` / `input` / `read-all` | `( -- s\|nil )` / `( prompt -- s\|nil )` / `( -- s )` 標準入力から読みます |
| `read-file` / `read-lines` | `( path -- s )` / `( path -- list )` |
| `write-file` / `append-file` | `( s path -- )` 上書き / 追記します (UTF-8) |
| `file-exists?` `delete-file` `list-dir` | `( path -- ... )` |
| `args` | `( -- list )` コマンドライン引数を返します |
| `getenv` / `now` / `type` | 環境変数 / 現在時刻 (秒) / 型名を返します |

## サンプルプログラム

`examples/` に次のプログラムがあります。

| ファイル | 内容 |
|---|---|
| `hello.dcf` | Hello, World |
| `fizzbuzz.dcf` | ループ・条件分岐・早期リターン |
| `factorial.dcf` | 再帰・末尾再帰・多倍長整数・フィボナッチ |
| `quicksort.dcf` | リストと再帰によるクイックソート |
| `closures.dcf` | クロージャ・高階ワード・ワード参照 |
| `files.dcf` | ファイルの書き込み・追記・読み込み・削除と例外処理 |
| `wordcount.dcf` | 引数で受け取ったファイルの単語頻度を集計します (`decaf examples/wordcount.dcf README.md`) |
| `calc.dcf` | Decaf で書いた対話型の RPN 電卓です |
| `primes.dcf` + `lib/mathlib.dcf` | `include` によるライブラリ分割 (gcd・lcm・素数判定) |
| `brainfuck.dcf` | Decaf で書いた Brainfuck インタプリタです |

## 実装の構成

```
decaf/
  lexer.py     字句解析 (ソース → トークン)
  compiler.py  構文解析とコンパイル (トークン → 命令列)
  vm.py        仮想機械 (明示的なフレームスタックで実行し、末尾呼び出しを最適化します)
  builtins.py  組み込みワード
  values.py    値の表現・表示・比較
  cli.py       コマンドラインと REPL
tests/         ユニットテスト (python3 -m unittest discover -s tests)
examples/      サンプルプログラム
```

VM は Python の再帰を使わず、フレームのリストを自前で管理します。`while` や `map` のような高階ワードは
Python のジェネレータとして実装されており、クォーテーションを `yield` すると VM がそれを実行して
戻ってくる仕組みです。このため深い再帰でも Python のスタックがあふれることはありません。
