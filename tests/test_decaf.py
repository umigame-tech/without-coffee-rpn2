import io
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from decaf import VM, DecafError, DecafExit, DecafSyntaxError, IncompleteInput  # noqa: E402


def run(src, argv=None, stdin=""):
    out = io.StringIO()
    vm = VM(argv, out=out, inp=io.StringIO(stdin))
    vm.run(src, "<test>")
    return out.getvalue(), vm.stack


def output(src, **kw):
    return run(src, **kw)[0]


def stack(src, **kw):
    return run(src, **kw)[1]


class StackAndArithmetic(unittest.TestCase):
    def test_rpn(self):
        self.assertEqual(stack("1 2 + 3 *"), [9])
        self.assertEqual(stack("10 4 -"), [6])
        self.assertEqual(stack("7 2 /  8 2 /  7 2 div  7 2 mod"), [3.5, 4, 3, 1])
        self.assertEqual(stack("2 10 pow  -5 abs  3 neg"), [1024, 5, -3])
        self.assertEqual(stack("1.5 2 *  0x10  0b101  -2.5e1"), [3.0, 16, 5, -25.0])

    def test_stack_words(self):
        self.assertEqual(stack("1 2 swap"), [2, 1])
        self.assertEqual(stack("1 2 over"), [1, 2, 1])
        self.assertEqual(stack("1 2 3 rot"), [2, 3, 1])
        self.assertEqual(stack("1 2 3 -rot"), [3, 1, 2])
        self.assertEqual(stack("1 2 nip  3 4 tuck"), [2, 4, 3, 4])
        self.assertEqual(stack("1 2 2dup 2drop dup"), [1, 2, 2])
        self.assertEqual(stack("1 2 3 2 pick depth"), [1, 2, 3, 1, 4])

    def test_bigint(self):
        self.assertEqual(stack("2 100 pow"), [2 ** 100])

    def test_comparison_and_logic(self):
        self.assertEqual(stack("1 2 <  2 2 <=  3 2 >  1 1.0 =  1 true =  \"a\" \"b\" <"),
                         [True, True, True, True, False, True])
        self.assertEqual(stack("nil 0 or  5 0 or  false 1 and  true not"), [0, 5, False, False])
        self.assertEqual(stack("{ 1 { 2 } } { 1 { 2 } } ="), [True])

    def test_underflow(self):
        with self.assertRaises(DecafError) as cm:
            run("1 +")
        self.assertIn("stack underflow", str(cm.exception))

    def test_type_error(self):
        with self.assertRaises(DecafError):
            run('"a" 1 -')


class Strings(unittest.TestCase):
    def test_literals_and_escapes(self):
        self.assertEqual(stack(r'"a\tb\n\"q\"あ"'), ['a\tb\n"q"あ'])

    def test_concat_and_convert(self):
        self.assertEqual(stack('"n=" 42 +  3.5 str  "12" num  "x" num  "7" int'),
                         ["n=42", "3.5", 12, None, 7])

    def test_string_words(self):
        self.assertEqual(
            stack('"a,b,c" "," split  { 1 2 } "-" join  " hi " trim  "abc" upper  "hello" 1 3 slice'),
            [["a", "b", "c"], "1-2", "hi", "ABC", "el"])
        self.assertEqual(stack('"hello" "ll" contains?  "hello" "l" index-of  "abc" reverse  "abc" len'),
                         [True, 2, "cba", 3])
        self.assertEqual(stack('"a b  c" words  "x\\ny" lines  "A" ord  98 chr  "ab" 3 *'),
                         [["a", "b", "c"], ["x", "y"], 65, "b", "ababab"])
        self.assertEqual(stack('{ 1 "x" } "{} and {}" format'), ["1 and x"])

    def test_comments(self):
        self.assertEqual(stack("1 # comment\n( a b -- c ) 2 +"), [3])


class ListsAndDicts(unittest.TestCase):
    def test_list_literal(self):
        self.assertEqual(stack("{ 1 2 3 + }"), [[1, 5]])
        self.assertEqual(stack("{ }  { { 1 } { } }"), [[], [[1], []]])

    def test_list_words(self):
        self.assertEqual(stack("{ 1 2 } 3 push  dup len"), [[1, 2, 3], 3])
        self.assertEqual(stack("{ 1 2 3 } pop"), [[1, 2], 3])
        self.assertEqual(stack("{ 5 6 7 } 1 nth  { 5 6 7 } 0 9 set-nth  { 5 6 7 } -1 nth"),
                         [6, [9, 6, 7], 7])
        self.assertEqual(stack("{ 3 1 2 } sort  1 4 range  { 1 2 } { 3 } +  { 1 2 3 } sum"),
                         [[1, 2, 3], [1, 2, 3], [1, 2, 3], 6])
        self.assertEqual(stack("{ 1 2 } 5 get  { } empty?  { 1 2 } 2 contains?"), [None, True, True])

    def test_dict(self):
        out = output('dict "a" 1 put "b" 2 put dup "a" get . dup "z" get . dup "b" has? . '
                     '"a" del keys .')
        self.assertEqual(out, '1\nnil\ntrue\n{ "b" }\n')


class ControlFlow(unittest.TestCase):
    def test_if(self):
        self.assertEqual(stack("1 2 < [ \"yes\" ] [ \"no\" ] if"), ["yes"])
        self.assertEqual(stack("false \"yes\" \"no\" if"), ["no"])
        self.assertEqual(stack("0 [ 1 ] when  nil [ 2 ] when  nil [ 3 ] unless"), [1, 3])

    def test_loops(self):
        self.assertEqual(output("0 >i [ i 3 < ] [ i . i 1 + >i ] while"), "0\n1\n2\n")
        self.assertEqual(output("3 [ \"x\" print ] times"), "xxx")
        self.assertEqual(stack("{ } 0 5 [ push ] for"), [[0, 1, 2, 3, 4]])
        self.assertEqual(stack("{ } 10 0 -3 [ push ] for-step"), [[10, 7, 4, 1]])
        self.assertEqual(stack("0 { 1 2 3 } [ + ] each"), [6])
        self.assertEqual(stack("0 [ 1 + dup 5 < ] loop"), [5])

    def test_higher_order(self):
        self.assertEqual(stack("{ 1 2 3 } [ dup * ] map"), [[1, 4, 9]])
        self.assertEqual(stack("{ 1 2 3 4 } [ even? ] filter"), [[2, 4]])
        self.assertEqual(stack("{ 1 2 3 4 } 0 [ + ] fold"), [10])
        self.assertEqual(stack("{ 1 2 3 } 1 '* fold"), [6])
        self.assertEqual(stack('{ "ccc" "a" "bb" } [ len ] sort-by'), [["a", "bb", "ccc"]])
        self.assertEqual(stack("1 2 [ 10 * ] dip"), [10, 2])

    def test_return(self):
        src = ": f ( n -- s ) | n | n 0 < [ \"neg\" return ] when \"pos\" ; -1 f 1 f"
        self.assertEqual(stack(src), ["neg", "pos"])
        src = ": find | xs x | 0 xs len [ | i | xs i nth x = [ i return ] when ] for -1 ; "
        self.assertEqual(stack(src + "{ 5 6 7 } 6 find { 5 6 7 } 9 find"), [1, -1])


class Functions(unittest.TestCase):
    def test_definition_and_recursion(self):
        src = ": fact dup 1 <= [ drop 1 ] [ dup 1 - fact * ] if ; 10 fact"
        self.assertEqual(stack(src), [3628800])

    def test_forward_reference_and_mutual_recursion(self):
        src = (": even2? dup 0 = [ drop true ] [ 1 - odd2? ] if ; "
               ": odd2? dup 0 = [ drop false ] [ 1 - even2? ] if ; 10001 even2?")
        self.assertEqual(stack(src), [False])

    def test_tail_call_is_constant_space(self):
        src = ": down dup 0 > [ 1 - down ] when ; 500000 down"
        self.assertEqual(stack(src), [0])

    def test_deep_non_tail_recursion(self):
        src = ": sum-to dup 0 = [ ] [ dup 1 - sum-to + ] if ; 50000 sum-to"
        self.assertEqual(stack(src), [50000 * 50001 // 2])

    def test_stack_overflow_is_reported(self):
        with self.assertRaises(DecafError) as cm:
            run(": f f 1 + ; f")
        self.assertIn("再帰が深すぎます", str(cm.exception))

    def test_locals_are_per_call(self):
        src = ": f | n | n 0 = [ 0 ] [ n 1 - f n + ] if ; 4 f"
        self.assertEqual(stack(src), [10])

    def test_globals(self):
        self.assertEqual(stack("0 >>count : bump count 1 + >>count ; bump bump count"), [2])
        self.assertEqual(stack("5 >x : f 10 >x x ; f x"), [10, 5])

    def test_closures(self):
        src = (": make-counter 0 >c [ c 1 + >c c ] ; "
               "make-counter >a make-counter >b a call a call b call")
        self.assertEqual(stack(src), [1, 2, 1])

    def test_word_reference(self):
        self.assertEqual(stack(": sq dup * ; 4 'sq call"), [16])

    def test_redefinition(self):
        self.assertEqual(stack(": f 1 ; : f 2 ; f"), [2])

    def test_definition_only_at_toplevel(self):
        with self.assertRaises(DecafSyntaxError):
            run("[ : f 1 ; ]")


class Errors(unittest.TestCase):
    def test_try_catches_runtime_error(self):
        self.assertEqual(stack("[ 1 0 / ] [ \"err\" swap drop ] try"), ["err"])

    def test_try_restores_stack(self):
        self.assertEqual(stack("1 2 [ 3 4 \"x\" throw ] [ ] try"), [1, 2, "x"])

    def test_throw_any_value(self):
        self.assertEqual(stack("[ { 1 2 } throw ] [ len ] try"), [2])

    def test_nested_try_and_rethrow(self):
        src = '[ [ "inner" throw ] [ "re:" swap + throw ] try ] [ ] try'
        self.assertEqual(stack(src), ["re:inner"])

    def test_error_in_word_unwinds(self):
        src = ": bad 1 { 2 3 } \"boom\" throw ; [ bad ] [ ] try depth"
        self.assertEqual(stack(src), ["boom", 1])

    def test_uncaught_error_location(self):
        with self.assertRaises(DecafError) as cm:
            run("1\n2\nundefined-word")
        self.assertIn("<test>:3", str(cm.exception))

    def test_incomplete_input(self):
        for src in ("[ 1", "{ 1", ": f 1", '"abc', "( comment"):
            with self.assertRaises(IncompleteInput):
                run(src)

    def test_exit(self):
        with self.assertRaises(DecafExit) as cm:
            run("7 exit")
        self.assertEqual(cm.exception.code, 7)

    def test_assert(self):
        with self.assertRaises(DecafError):
            run('1 2 = "must be equal" assert')


class IO(unittest.TestCase):
    def test_print(self):
        self.assertEqual(output('1 . "a" print "b" print cr { 1 "s" } . 1 2 .s'),
                         '1\nab\n{ 1 "s" }\n<2> 1 2\n')

    def test_stdin(self):
        self.assertEqual(stack("read-line read-line read-line", stdin="a\nb\n"), ["a", "b", None])

    def test_files(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "f.txt").replace("\\", "/")
            src = (f'"one\\n" "{p}" write-file "two\\n" "{p}" append-file '
                   f'"{p}" read-file "{p}" read-lines "{p}" file-exists? '
                   f'"{p}" delete-file "{p}" file-exists?')
            self.assertEqual(stack(src), ["one\ntwo\n", ["one", "two"], True, False])

    def test_file_error_is_catchable(self):
        out = stack('[ "/no/such/dir/x" read-file ] [ "ファイルエラー" starts-with? ] try')
        self.assertEqual(out, [True])

    def test_include_and_eval(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "lib.dcf"), "w", encoding="utf-8") as fh:
                fh.write(": triple 3 * ;\n")
            with open(os.path.join(d, "main.dcf"), "w", encoding="utf-8") as fh:
                fh.write('"lib.dcf" include "lib.dcf" include 5 triple\n')
            vm = VM(out=io.StringIO())
            vm.run_file(os.path.join(d, "main.dcf"))
            self.assertEqual(vm.stack, [15])
        self.assertEqual(stack('"2 3 +" eval'), [5])

    def test_args(self):
        self.assertEqual(stack("args", argv=["x", "y"]), [["x", "y"]])


class CLI(unittest.TestCase):
    def cli(self, *args, stdin=""):
        return subprocess.run([sys.executable, "-m", "decaf", *args], cwd=ROOT,
                              input=stdin, capture_output=True, text=True, encoding="utf-8")

    def test_run_file(self):
        r = self.cli("examples/hello.dcf")
        self.assertEqual(r.returncode, 0)
        self.assertIn("Hello, World!", r.stdout)

    def test_eval_option_and_args(self):
        r = self.cli("-e", "args len .", "a", "b")
        self.assertEqual(r.stdout, "2\n")

    def test_stdin_program(self):
        r = self.cli("-", stdin="6 7 * .")
        self.assertEqual(r.stdout, "42\n")

    def test_error_exit_code(self):
        r = self.cli("-e", "1 0 /")
        self.assertEqual(r.returncode, 1)
        self.assertIn("ゼロ", r.stderr)

    def test_exit_code(self):
        self.assertEqual(self.cli("-e", "3 exit").returncode, 3)

    def test_examples(self):
        expected = {
            "fizzbuzz.dcf": "FizzBuzz",
            "factorial.dcf": "30! = 265252859812191058636308480000000",
            "quicksort.dcf": "{ 3 3 9 10 27 38 43 82 }",
            "closures.dcf": "{ 3 5 7 }",
            "files.dcf": "削除しました",
            "primes.dcf": "97",
            "brainfuck.dcf": "Hello World!",
        }
        for name, needle in expected.items():
            r = self.cli(os.path.join("examples", name))
            self.assertEqual(r.returncode, 0, name + r.stderr)
            self.assertIn(needle, r.stdout, name)
        r = self.cli("examples/calc.dcf", stdin="3 4 + 2 *\n1 +\n")
        self.assertIn("= 14", r.stdout)
        self.assertIn("オペランドが足りません", r.stdout)
        r = self.cli("examples/wordcount.dcf", "README.md")
        self.assertIn("総単語数", r.stdout)


if __name__ == "__main__":
    unittest.main()
