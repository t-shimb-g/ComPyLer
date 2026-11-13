import unittest
import sys
import pathlib
import subprocess
import ast
from io import StringIO
import Lint
import Lvar
import Lif
import Cif
import x86
import var
import register_allocation
import cond
import utils

compiler = var.Var
compiler = register_allocation.RegisterAllocator
compiler = cond.Conditionals


def gather_test_names(path):
    """Create a set of filenames without extensions that represent the
    tests cases found in the given folder path.

    """
    return {filename.with_suffix('') for filename in pathlib.Path(path).iterdir()}


class TestCase:
    def __init__(self, name):
        if not isinstance(name, pathlib.Path):
            name = pathlib.Path(name)

        self.name = name

        filenames = [name.with_suffix(extension) for extension in ('.py', '.in', '.golden')]

        # check for existence
        for filename in filenames:
            if not filename.exists():
                raise IOError(f'Missing test file {filename}')

        # read text, remove leading/trailing whitespace
        self.source = filenames[0].read_text().strip()
        self.input = filenames[1].read_text().strip()
        self.golden = filenames[2].read_text().strip()

        self.ast = ast.parse(self.source)

    def __str__(self):
        msg = f"TestCase({self.name})\n"
        sep = '\n' + '-' * 70 + '\n'
        msg += f"{self.name.with_suffix('.py')}{sep}{self.source}{sep}\n"
        msg += f"{self.name.with_suffix('.in')}{sep}{self.input}{sep}\n"
        msg += f"{self.name.with_suffix('.golden')}{sep}{self.golden}{sep}\n"

        msg += f"ast = {utils.str_ast(self.ast)}\n"

        return msg


def load_test_cases(path):
    return [TestCase(name) for name in gather_test_names(path)]


def run_interpreter(test_case, interpreter):
    # redirect stdin/out for builtin input() and print()
    import sys
    sys.stdin = StringIO(test_case.input)
    sys.stdout = StringIO()

    # run interpreter and get output as string
    interpreter(test_case.ast)
    output = sys.stdout.getvalue().strip()

    # undo redirects
    sys.stdin = sys.__stdin__
    sys.stdout = sys.__stdout__

    return output


class TestCompiler(unittest.TestCase):
    """Series of tests for each compiler pass"""

    def test_interp_Lint(self):
        for test_case in load_test_cases('tests/int'):
            output = run_interpreter(test_case, Lint.interp_Lint)
            self.assertEqual(output, test_case.golden, msg=test_case)

    def test_partial_evalution(self):
        for test_case in load_test_cases('tests/int'):
            test_case.ast = Lint.pe_P_int(test_case.ast)
            output = run_interpreter(test_case, Lint.interp_Lint)
            self.assertEqual(output, test_case.golden, msg=test_case)

    def test_64bit_operations(self):
        for test_case in load_test_cases('tests/int64'):
            output = run_interpreter(test_case, Lvar.interp_Lvar)
            self.assertEqual(output, test_case.golden, msg=test_case)

    def test_shrink(self):
        c = compiler()
        for test_case in load_test_cases('tests/var') + load_test_cases('tests/if'):
            for transform in [c.shrink]:
                test_case.ast = transform(test_case.ast)

            output = run_interpreter(test_case, Lif.interp_Lif)
            self.assertEqual(output, test_case.golden, msg=test_case)

    def test_remove_complex_operands(self):
        c = compiler()
        for test_case in load_test_cases('tests/var') + load_test_cases('tests/if'):
            for transform in [c.shrink, c.remove_complex_operands]:
                test_case.ast = transform(test_case.ast)

            output = run_interpreter(test_case, Lif.interp_Lif)
            self.assertEqual(output, test_case.golden, msg=test_case)

    def test_explicate_control(self):
        c = compiler()
        for test_case in load_test_cases('tests/var') + load_test_cases('tests/if'):
            for transform in [c.shrink, c.remove_complex_operands, c.explicate_control]:
                test_case.ast = transform(test_case.ast)

            output = run_interpreter(test_case, Cif.interp_Cif)
            self.assertEqual(output, test_case.golden, msg=test_case)
    #
    # def test_select_instructions(self):
    #     c = compiler()
    #     for test_case in load_test_cases('tests/var') + load_test_cases('tests/if'):
    #         print(test_case)
    #         for transform in [c.shrink, c.remove_complex_operands, c.explicate_control, c.select_instructions,
    #                           c.assign_homes, c.patch_instructions, c.prelude_and_conclusion]:
    #             test_case.ast = transform(test_case.ast)
    #
    #         output = run_interpreter(test_case, x86.interp_x86)
    #         self.assertEqual(output, test_case.golden, msg=test_case)

if __name__ == '__main__':
    unittest.main(verbosity=2)
