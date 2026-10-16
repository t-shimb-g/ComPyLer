from ast import *
from sys import platform
from dataclasses import dataclass


# pretty printing ast nodes
def str_op(op):
    """Returns str representation of an operator"""
    match op:
        case USub():
            return 'USub()'
        case Add():
            return 'Add()'
        case Sub():
            return 'Sub()'
        case And():
            return 'And()'
        case Or():
            return 'Or()'
        case Not():
            return 'Not()'
        case Eq():
            return 'Eq()'
        case NotEq():
            return 'NotEq()'
        case Lt():
            return 'Lt()'
        case LtE():
            return 'LtE()'
        case Gt():
            return 'Gt()'
        case GtE():
            return 'GtE()'
        case _:
            return str(op)


def str_ast(ast):
    """Returns str representation of an ast node"""
    match ast:
        case Module(body):
            stmts = map(str_ast, body)
            return f"Module([\n  {'\n  '.join(stmts)}\n])"
        case Expr(value):
            return f'Expr({str_ast(value)})'
        case Constant(value):
            return f'Constant({value})'
        case UnaryOp(op, operand):
            return f'UnaryOp({str_op(op)}, {str_ast(operand)})'
        case BinOp(left, op, right):
            return f'BinaryOp({str_ast(left)}, {str_op(op)}, {str_ast(right)})'
        case Call(func, args):
            args = list(map(str_ast, args))
            return f'Call({str_ast(func)}, [{", ".join(args)}])'
        case Assign(targets, value):
            return f'Assign({str_ast(targets[0])}, {str_ast(value)})'
        case Name(id):
            return f"Name('{id}')"
        case IfExp(test, body, orelse):
            return f"IfExp({str_ast(test)}, {str_ast(body)}, {str_ast(orelse)})"
        case If(test, body, orelse):
            body = list(map(str_ast, body))
            orelse = list(map(str_ast, orelse))
            return f"If({str_ast(test)}, [{', '.join(body)}], [{', '.join(orelse)}])"
        case BoolOp(op, exprs):
            exprs = list(map(str_ast, exprs))
            return f"BoolOp({str_op(op)}, [{', '.join(exprs)}])"
        case Compare(left, ops, comparators):
            ops = list(map(str_op, ops))
            comparators = list(map(str_ast, comparators))
            return f"Compare({str_ast(left)}, [{', '.join(ops)}], [{', '.join(comparators)}])"
        case Return(value):
            return f"Return({str_ast(value)})"
        case _:
            return str(ast)


def print_ast(ast):
    print(str_ast(ast))


# 64-bit integers
max_int = 2 ** 63 - 1
min_int = -2 ** 63
mask = 2 ** 64 - 1
offset = 2 ** 63


def to_unsigned(x):
    return x & mask


def to_signed(x):
    return ((x + offset) & mask) - offset


def add64(x, y):
    return to_signed(x + y)


def sub64(x, y):
    return to_signed(x - y)


def neg64(x):
    return to_signed(-x)


def xor64(x, y):
    return to_signed(x ^ y)


def input_int():
    x = int(input())
    # clamp to 64-bit signed int
    x = min(max_int, max(min_int, x))
    return x

# Generate unique names
name_id = 0

def generate_name(name):
    """Generate a unique name by appending a number, e.g. 'main' -> 'main.3'."""
    global name_id
    base, *rest = name.split('.')
    new_id = name_id
    name_id += 1
    return f'{base}.{new_id}'

def label_name(name):
    """Generate a valid x86 label ensuring that labels start with an underscore on Mac."""
    if platform == "darwin":
        return f'_{name}'
    else:
        return name


def align(n: int, alignment: int) -> int:
    """Round up n to next highest multiple of alignment"""
    if 0 == n % alignment:
        return n
    else:
        return n + (alignment - n % alignment)


def unzip(ls):
    xs, ys = [], []
    for x, y in ls:
        xs += [x]
        ys += [y]
    return xs, ys


################################################################################
# AST types
################################################################################
class Type:
    pass


@dataclass(eq=True)
class IntType(Type):
    def __str__(self):
        return 'int'


@dataclass(eq=True)
class BoolType(Type):
    def __str__(self):
        return 'bool'


@dataclass
class CProgram:
    body: dict[str, list[stmt]]

    def __str__(self):
        result = ''
        for label, stmts in self.body.items():
            result += f'{label}:\n'
            for s in stmts:
                result += f'\t{str_ast(s)}\n'

        return result


@dataclass
class Goto(stmt):
    label: str

    def __str__(self):
        return f'goto {self.label}'


def make_assigns(bs):
    return [Assign([x], rhs) for (x, rhs) in bs]


def make_begin(bs, e):
    if len(bs) > 0:
        return Begin([Assign([x], rhs) for (x, rhs) in bs], e)
    else:
        return e


@dataclass
class Begin(expr):
    body: list[stmt]
    result: expr

    def __str__(self):
        stmts = ''.join([str(s) for s in self.body])
        end = 'produce ' + str(self.result)
        return '{\n' + stmts + end + '}'