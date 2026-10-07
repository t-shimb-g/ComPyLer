from ast import *
import platform

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
        case _:
            raise NotImplementedError(f'{op}')


def str_ast(ast):
    """Returns str representation of an ast node"""
    match ast:
        case Module(body):
            stmts = map(str_ast, body)
            return f"Module([\n\t{''.join(stmts)}\n])"
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
        case _:
            raise NotImplementedError(f'{ast}')


def print_ast(ast):
    print(str_ast(ast))


# 64-bit integers
max_int = 2**63-1
min_int = -2**63
mask = 2**64-1
offset = 2**63

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

