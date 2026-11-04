import itertools
from ast import *
from typing import List, Tuple, Set, Dict
import subprocess

import utils
from utils import str_ast, generate_name, label_name, neg64, align
from x86 import *

Binding = Tuple[Name, expr]
Temporaries = List[Binding]

class Var:
    ######################################################################
    # Remove complex operands
    ######################################################################
    def rco_exp(self, e: expr, need_atomic: bool) -> Tuple[expr, Temporaries]:
        """For each expression return a pair: new expression and list
        of temporaries. Boolean parameter 'need_atomic' determines
        whether an expression should be flattened into a list of
        statements."""
        match e:
            case Constant(n):
                return e, []

            case Name(id):
                return e, []
            
            case Call(Name('input_int'), []):
                if need_atomic:
                    tmp = Name(generate_name('tmp'))
                    return tmp, [(tmp, e)]
                return e, []
            
            case UnaryOp(USub(), exp):
                atm, temps = self.rco_exp(exp, True)
                usub = UnaryOp(USub(), atm)
                if need_atomic:
                    tmp = Name(generate_name('tmp'))
                    return tmp, temps + [(tmp, usub)]
                else:
                    return usub, temps

            # TODO: add generic UnaryOp here
                
            case BinOp(exp1, op, exp2):
                atm1, temps1 = self.rco_exp(exp1, True)
                atm2, temps2 = self.rco_exp(exp2, True)
                sum = BinOp(atm1, op, atm2)
                if need_atomic:
                    tmp = Name(generate_name('tmp'))
                    # order of temps1 and temps2 does not matter because unique temporary names (except for exponentiation)
                    return tmp, temps1 + temps2 + [(tmp, sum)]
                else:
                    return sum, temps1 + temps2
            case _:
                raise ValueError(f'rco_exp unexpected: {str_ast(e)}')


    def rco_stmt(self, s: stmt) -> List[stmt]:
        """For each statement, collect new atomic expressions and concatenate temporaries"""
        match s:
            case Expr(Call(Name('print'), [exp])):
                atm, temps = self.rco_exp(exp, True)
                vars = [ Assign([var], value) for var, value in temps ] # vars is creating all the temps we need to finally print (p)
                p = Expr(Call(Name('print'), [atm]))
                return vars + [p]
            case Expr(exp):
                expr, temps = self.rco_exp(exp, False)
                vars = [ Assign([var], value) for var, value in temps ]
                return vars + [Expr(expr)]
            case Assign([Name(var)], exp):
                expr, temps = self.rco_exp(exp, False)
                vars = [ Assign([var], value) for var, value in temps ]
                return vars + [Assign([Name(var)], expr)]
            case _:
                raise ValueError(f'rco_stmt not implemented: {str_ast(s)}')


    def remove_complex_operands(self, p: Module) -> Module:
        """Transform each statement and expression into atomic expressions"""
        match p:
            case Module(body):
                # flatten list of lists (because rco_stmt returns a list)
                new_body = list(itertools.chain.from_iterable([self.rco_stmt(stmt) for stmt in body]))
                return Module(new_body)

    
    ######################################################################
    # Select instructions
    ######################################################################
    def select_arg(self, e: expr) -> arg:
        """Translate terminals in Lvar to x86 ast types"""
        match e:
            # Name -> Variable
            case Name(id):
                return Variable(id)

            # Constant -> Immediate
            case Constant(value):
                return Immediate(value)

            # Throw error for _
            case _:
                raise ValueError('select_arg unhandled: ' + str_ast(e))

            
    def select_op(self, op: operator) -> str:
        """Translate operators in Lvar to x86 instructions"""
        # Add() -> 'addq', also handle Sub and USub
        match op:
            # add code here
            case Add():
                return 'addq'
            case Sub():
                return 'subq'
            case USub():
                return 'negq'
            case _:
                raise ValueError('select_op unhanded: ' + str_ast(op))

            
    def select_stmt(self, s: stmt) -> List[instr]:
        match s:
            # print(op) -> [move to rdi, callq print_int]
            case Expr(Call(Name('print'), [operand])):
                src = self.select_arg(operand)
                return [Instr('movq', [src, Reg('rdi')]), Callq('print_int', 1)]

            # input_int() -> callq read_int
            case Expr(Call(Name('input_int'), [])):
                return [Callq('read_int', 0)]

            case Expr(_): 
                return [] # Don't generate asm for unused expressions


            # lhs = number
            case Assign([lhs], Constant(value)):
                src = self.select_arg(Constant(value))
                dest = self.select_arg(lhs)
                return [Instr('movq', [src, dest])]
                
            # lhs = identifier
            case Assign([Name(left)], Name(right)):
                if left == right:
                    return []
                else:
                    src = self.select_arg(Name(right))
                    dest = self.select_arg(Name(left))
                    return [Instr('movq', [src, dest])]

            # unary
            case Assign([lhs], UnaryOp(USub(), Constant(i))):
                dest = self.select_arg(lhs)
                src = Immediate(neg64(i)) # make sure i -> -i is still within [-2^63, 2^63-1]
                return [Instr('movq', [src, dest])]

            case Assign([lhs], UnaryOp(op, operand)):
                dest = self.select_arg(lhs)
                operator = self.select_op(op)
                src = self.select_arg(operand)
                return [Instr('movq', [src, dest]), Instr(operator, [dest])]

            # binary
            # x = x + y
            case Assign([Name(lhs)], BinOp(Name(left), Add(), right)) if left == lhs:
                # Name('x') == Name('x') = False, so unpack id's and compare those instead
                dest = self.select_arg(Name(lhs))
                src = self.select_arg(right)
                return [Instr('addq', [src, dest])]

            # x = y + x
            case Assign([Name(lhs)], BinOp(left, Add(), Name(right))) if right == lhs:
                dest = self.select_arg(Name(lhs))
                src = self.select_arg(left)
                return [Instr('addq', [src, dest])]
            
            # transform x = y - x to x = -x + y
            case Assign([Name(lhs)], BinOp(left, Sub(), Name(right))) if right == lhs:
                dest = self.select_arg(Name(lhs))
                src = self.select_arg(left)
                return [Instr('negq', [dest]), Instr('addq', [src, dest])]

            # general x = y op z
            case Assign([lhs], BinOp(left, op, right)):
                dest = self.select_arg(lhs)
                l_arg = self.select_arg(left)
                r_arg = self.select_arg(right)
                operator = self.select_op(op)
                return [Instr('movq', [l_arg, dest]), Instr(operator, [r_arg, dest])]

            # transform x = input_int() to (callq read_int; rax -> x)
            case Assign([lhs], Call(Name('input_int'), [])):
                dest = self.select_arg(lhs)
                return [Callq('read_int', 0), Instr('movq', [Reg('rax'), dest])]
                        
            case _:
                raise ValueError('select_stmt unhandled: ' + str(s))
            

    def select_instructions(self, p: Module) -> X86Program:
        match p:
            case Module(body):
                new_stmts = [self.select_stmt(s) for s in body]
                # flatten the list of lists of statements
                flattened = list(itertools.chain.from_iterable(new_stmts))
                return X86Program(flattened)

    ######################################################################
    # Assign homes
    ######################################################################
    def collect_locals_arg(self, a: arg) -> Set[location]:
        """Return set( variable names ), otherwise empty set()"""
        match a:
            case Reg():
                return set([])
            case Variable():
                return set([a])
            case Immediate():
                return set([])
            case _:
                raise TypeError(f'unknown arg: {a}')
                

    def collect_locals_instr(self, i: instr) -> Set[location]:
        """For a given instruction i, collect_local_args on it's arguments"""
        match i:
            case Instr(inst, args):
                sets = [self.collect_locals_arg(arg) for arg in args]
                return set().union(*sets)
            case Callq(func, num_args):
                return set([])
            case _:
                raise TypeError(f'unknown instr: {i}')

    def collect_locals_instrs(self, ss: List[stmt]) -> Set[location]:
        """Collect local variables from a list of statements"""
        tmps = [self.collect_locals_instr(s) for s in ss]
        return set().union(*tmps)

    def gen_stack_access(self, i: int) -> arg:
        """Return an address on the stack for local variable i"""
        return Deref('rbp', -(8 + 8*i))

    def assign_homes_arg(self, a: arg, homes: Dict[Variable, arg]) -> arg:
        """If a given arg is a Variable, return it's new home address
        on the stack. For all other args, simply return them."""
        match a:
            case Variable():
                if a in homes.keys():
                    return homes[a]
                else:
                    return a
            case Reg() | Immediate():
                return a
            case _:
                raise TypeError(f'unknown arg: {a}')

    def assign_homes_instr(self, i: instr, homes: Dict[Variable, arg]) -> instr:
        """Assign homes for each argument in an instruction"""
        match i:
            case Instr(instr, args):
                new_args = [self.assign_homes_arg(arg, homes) for arg in args]
                return Instr(instr, new_args)
            case Callq(func, num_args):
                return i
            case _:
                raise TypeError(f'unknown instr: {i}')

    def assign_homes_instrs(self, ss: List[instr], homes: Dict[Variable, arg]) -> List[instr]:
        """Assign homes on the stack for each local variable within the given statements"""
        return [self.assign_homes_instr(s, homes) for s in ss]

    def assign_homes(self, p: X86Program) -> X86Program:
        """Replace local variables in program with stack locations"""
        match p:
            case X86Program(body):
                tmps = self.collect_locals_instrs(body)
                homes = {x: self.gen_stack_access(i) for i, x in enumerate(tmps)}
                body = self.assign_homes_instrs(body, homes)
                p = X86Program(body)
                p.stack_space = align(8 * len(tmps), 16)
                return p
            case _:
                raise TypeError(f'Expected X86Program, not {p}')
        
    
    ######################################################################
    # Patch instructions
    ######################################################################

    def big_constant(self, c: arg) -> bool:
        """Test if |c| > 2**16"""
        return isinstance(c, Immediate) and (c.value > 2**16 or c.value < -2**16)
    
    def in_memory(self, a: arg) -> bool:
        """Test if given arg is a memory reference"""
        return isinstance(a, Deref)
    
    def patch_instr(self, i: instr) -> List[instr]:
        """Break up instructions containing two memory addresses into
        separate statements using rax as a temporary location. Also
        moves large constants into a register first, before including
        them directly in instructions."""
        match i:
            case Instr('movq', [src, dest]):
                if (self.in_memory(src) or self.big_constant(src)) and self.in_memory(dest):
                    return [Instr('movq', [src, Reg('rax')]), Instr('movq', [Reg('rax'), dest])]
                else:
                    return [i]

            case Instr(inst, [src, dest]):
                if (self.in_memory(src) and self.in_memory(dest)) or self.big_constant(src):
                    return [Instr('movq', [src, Reg('rax')]), Instr(inst, [Reg('rax'), dest])]
                else:
                    return [i]

            case _:
                return [i]
    
    def patch_instrs(self, ss: List[instr]) -> List[instr]:
        """Patch up all instructions in list of statements"""
        patched = [self.patch_instr(i) for i in ss]
        flattened = list(itertools.chain.from_iterable(patched))
        return flattened
    
    def patch_instructions(self, p: X86Program) -> X86Program:
        """Fix any instructions that do not conform to x86's idiosyncrasies."""
        match p:
            case X86Program(body):
                new_p = X86Program(self.patch_instrs(body))
                new_p.stack_space = p.stack_space
                return new_p

    ######################################################################
    # Prelude and conclusion
    ######################################################################

    def prelude_and_conclusion(self, p: X86Program) -> X86Program:
        """Add prelude and conclusion around p's code. The prelude
        should create a new stack frame and make stack space for local
        variables. The conclusion should undo these operations and
        return to the caller."""
        match p:
            case X86Program(body):
                prelude = [Instr('pushq', [Reg('rbp')]),
                           Instr('movq', [Reg('rsp'), Reg('rbp')]),
                           Instr('subq', [Immediate(p.stack_space), Reg('rsp')])
                           ]
                conclusion = [Instr('addq', [Immediate(p.stack_space), Reg('rsp')]),
                              Instr('popq', [Reg('rbp')]),
                              Instr('retq', [])
                              ]
                return X86Program(prelude + body + conclusion)



    def compile(self, program: Module) -> X86Program:
        compiler_passes = [self.remove_complex_operands,
                           self.select_instructions,
                           self.assign_homes,
                           self.patch_instructions,
                           self.prelude_and_conclusion]


        print(str_ast(program))
        for compiler in compiler_passes:
            print('-'*30 + '\n', compiler.__name__, '\n' + '-'*30)
            program = compiler(program)
            if isinstance(program, Module):
                print(str_ast(program))
            else:
                print(program)

        return program
            
    
if __name__ == '__main__':
    text = "x = 5; y = 10; x = y + x; print(x)"
    # text = "x = 5; y = 10; x = x + y"
    #text = "x = 5; x = x;"
    #text = "print(5)"
    ast = parse(text)

    c = Compiler()
    x86 = c.compile(ast)

    with open('test.s', 'w') as f:
        f.write(str(x86))

    result = subprocess.run(['gcc', 'runtime.o', 'test.s'], capture_output=True)
    if result.returncode == 0:
        print('Compilation succeeded!')
    else:
        print('Compilation failed!')
        print(result.stderr.decode())


        
