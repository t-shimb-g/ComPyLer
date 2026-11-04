from ast import *
from x86 import *
from utils import *
from var import Temporaries # used in remove_complex_operands
import register_allocation
from graph import DirectedAdjList, UndirectedAdjList, transpose, topological_sort


class Conditionals(register_allocation.RegisterAllocator):

    ############################################################################
    # Shrink
    ############################################################################

    def shrink_exp(self, e: expr) -> expr:
        match e:
            case Name(id):
                return e
            
            case Constant(value):
                return e
            
            case BinOp(left, op, right):
                l = self.shrink_exp(left);
                r = self.shrink_exp(right)
                return BinOp(l, op, r)
            
            case UnaryOp(op, operand):
                pass
            
            case Call(func, args):
                pass

            case IfExp(test, body, orelse):
                pass

            # Replace And with IfExp
            case BoolOp(And(), values):
                pass

            # Replace Or with IfExp
            case BoolOp(Or(), values):
                pass

            case Compare(left, [op], [right]):
                pass
            
            case _:
                raise Exception('shrink_exp: ' + repr(e))

    
    def shrink_stmt(self, s: stmt) -> stmt:
        match s:
            case Assign(targets, value):
                pass
            case Expr(value):
                pass
            case If(test, body, orelse):
                pass
            case _:
                raise Exception('shrink_stmt: unexpected: ' + repr(s))

    
    def shrink(self, p: Module) -> Module:
        match p:
            case Module(body):
                pass

    ############################################################################
    # Remove Complex Operands
    ############################################################################

    def rco_stmt(self, s: stmt) -> list[stmt]:
        match s:
            case If(test, body, orelse):
                # generate temporaries for test, body, orelse
                # none need to be atomic
                pass
            
            case _:
                return super().rco_stmt(s)

    def rco_exp(self, e: expr, need_atomic: bool) -> tuple[expr, Temporaries]:
        match e:
            case IfExp(test, body, orelse):
                # rco for test, body, orelse
                # make Begin blocks for body and orelse
                # if need_atomic == True: generate a temporary for the last expression assigned to
                pass
            case Compare(left, [op], [right]):
                # rco for each part
                # if need_atomic, generate a temporary for last expression
                pass
                
            case _:
                return super().rco_exp(e, need_atomic)


    ############################################################################
    # Explicate Control
    ############################################################################

    def create_block(self, stmts: list[stmt], basic_blocks: dict[str, list[stmt]]) -> list[stmt]:
        match stmts:
            case [Goto(l)]:
                pass

            case _:
                pass

    def explicate_effect(self, e: expr, cont: list[stmt],
                         basic_blocks: dict[str, list[stmt]]) -> list[stmt]:
        match e:
            case Begin(body, result):
                pass
            
            case IfExp(test, body, orelse):
                pass
            
            case Call(func, args):
                pass
            
            case _:  # no effect, remove this expression
                return cont

    def explicate_assign(self, e: expr, x: Variable, cont: list[stmt],
                         basic_blocks: dict[str, list[stmt]]) -> list[stmt]:
        match e:
            case Begin(body, result):
              pass
          
            case IfExp(test, body, orelse):
                pass
            
            case _:
                return [Assign([x], e)] + cont
            
    def generic_explicate_pred(self, cnd: expr, thn: list[stmt],
                               els: list[stmt],
                               basic_blocks: dict[str, list[stmt]]) -> list[stmt]:
        pass

    def explicate_pred(self, cnd: expr, thn: list[stmt], els: list[stmt],
                       basic_blocks: dict[str, list[stmt]]) -> list[stmt]:
        match cnd:
            case Name(x):
                pass
            
            case Compare(left, [op], [right]):
                pass
            
            case Constant(True):
                pass
            
            case Constant(False):
                pass
            
            case UnaryOp(Not(), operand):
                pass
            
            case Begin(body, result):
                pass
            
            case IfExp(test, body, orelse):
                pass
            
            case _:
                raise Exception('explicate_pred: unexpected ' + repr(cnd))

    def explicate_stmt(self, s: stmt, cont: list[stmt],
                       basic_blocks: dict[str, list[stmt]]) -> list[stmt]:
        match s:
            case Assign([lhs], rhs):
                pass
            
            case Expr(value):
                pass
            
            case If(test, body, orelse):
                pass

            case _:
                raise Exception('explicate_stmt: unexpected ' + repr(s))

    def explicate_control(self, p: Module) -> CProgram:
        match p:
            case Module(body):
                new_body = [Return(Constant(0))]
                basic_blocks = {}
                for s in reversed(body):
                    new_body = self.explicate_stmt(s, new_body, basic_blocks)
                basic_blocks['start'] = new_body
                return CProgram(basic_blocks)
            
            case _:
                raise Exception('explicate_control: unexpected ' + repr(p))

    ############################################################################
    # Select Instructions
    ############################################################################

    def select_arg(self, a: expr) -> arg:
        match a:
            case Constant(True):
                pass
            
            case Constant(False):
                pass
            
            case Reg(id):  # cause how we handle Return
                pass
            
            case _:
                return super().select_arg(a)

    def select_op(self, op: operator) -> str:
        match op:
            case Sub():
                pass
            case And():
                pass
            case Eq():
                pass
            case NotEq():
                pass
            case Lt():
                pass
            case LtE():
                pass
            case Gt():
                pass
            case GtE():
                pass
            case _:
                return super().select_op(op)
            

    def select_stmt(self, s: stmt) -> list[instr]:
        match s:
            case If(Compare(left, [op], [right]), [Goto(thn)], [Goto(els)]):
                pass
            case Goto(label):
                pass
            case Assign([lhs], UnaryOp(Not(), operand)): # lhs = ! operand = xorq operand, movq operand, lhs
                pass
            
            case Assign([lhs], BinOp(left, Sub(), right)) if left == lhs: # sub right, lhs # lhs -= right
                pass
            case Assign([lhs], Compare(left, [op], [right])): # lhs = x == y, cmp x, y, movzbq al, rax
                pass
            
            case Return(value):
                pass
            
            case _:
                return super().select_stmt(s)




    def select_instructions(self, p: CProgram) -> X86Program:
        match p:
            case CProgram(body):
                blocks = {}
                for (l, ss) in body.items():
                    blocks[l] = sum([self.select_stmt(s) for s in ss], [])
                return X86Program(blocks)

    ############################################################################
    # Uncover Live
    ############################################################################

    def vars_arg(self, a: arg) -> set[location]:
        match a:
            case ByteReg(id):
                pass
            case _:
                return super().vars_arg(a)

    def read_vars(self, i: instr) -> set[location]:
        match i:
            case Jump(label):
                pass
            case JumpIf(cc, label):
                pass
            case _:
                return super().read_vars(i)

    def write_vars(self, i: instr) -> set[location]:
        match i:
            case Jump(label):
                pass
            case JumpIf(cc, label):
                pass
            case Instr('cmpq', args):
                pass
            case _:
                return super().write_vars(i)

    @staticmethod
    def adjacent_instr(s: instr) -> list[str]:
        if isinstance(s, Jump) or isinstance(s, JumpIf):
            return [s.label]
        else:
            return []

    def blocks_to_graph(self, blocks: dict[str, list[instr]]) -> DirectedAdjList:
        graph = DirectedAdjList()
        for u in blocks.keys():
            graph.add_vertex(u)
        for (u, ss) in blocks.items():
            for s in ss:
                for v in self.adjacent_instr(s):
                    graph.add_edge(u, v)
        return graph

    def trace_live_blocks(self, blocks, live_before: dict[instr, set[location]],
                   live_after: dict[instr, set[location]]):
        for (l, ss) in blocks.items():
            print(l + ':\n')
            i = 0 
            for s in ss:
                if i == 0:
                    print('\t\t{' + ', '.join([str(l) for l in live_before[s]]) + '}')
                print(str(s))
                print('\t\t{' + ', '.join([str(l) for l in live_after[s]]) + '}')
                i = i + 1
                
    def trace_live(self, p: X86Program, live_before: dict[instr, set[location]],
                   live_after: dict[instr, set[location]]):
        match p:
            case X86Program(body):
                self.trace_live_blocks(body, live_before, live_after)
                
    def uncover_live(self, p: X86Program) -> dict[instr, set[location]]:
        match p:
            case X86Program(body):
                live_before = {}
                live_after = {}
                cfg = self.blocks_to_graph(body)
                cfg_trans = transpose(cfg)
                live_before_block = \
                    {'conclusion': {Reg('rax'), Reg('rsp')}}
                for l in topological_sort(cfg_trans):
                    if l != 'conclusion':
                        adj_live = [live_before_block[v] \
                                    for v in cfg.adjacent(l)]
                        live_before_succ = set().union(*adj_live)
                        for i in reversed(body[l]):
                            self.uncover_live_instr(i, live_before_succ,
                                                    live_before, live_after)
                            live_before_succ = live_before[i]
                        live_before_block[l] = live_before_succ
                #print("uncover live:")
                #self.trace_live(p, live_before, live_after)
                return live_after


    ############################################################################
    # Build Interference
    ############################################################################

    
    def interfere_instr(self, i: instr, graph,
                        live_after: dict[instr, set[location]]):
        match i:
            case Instr('movzbq', [s, t]):
                for v in live_after[i]:
                    for d in self.write_vars(i):
                        if v != d and s != v:
                            graph.add_edge(d, v)
            case _:
                return super().interfere_instr(i, graph, live_after)

    def build_interference_blocks(self, blocks,
                           live_after: dict[instr, set[location]]) -> UndirectedAdjList:
        graph = UndirectedAdjList()
        for (l, ss) in blocks.items():
            for i in ss:
                self.interfere_instr(i, graph, live_after)
        return graph
            
    def build_interference(self, p: X86Program,
                           live_after: dict[instr, set[location]]) -> UndirectedAdjList:
        match p:
            case X86Program(blocks):
                return self.build_interference_blocks(blocks, live_after)



    ############################################################################
    # Allocate Registers
    ############################################################################

    def alloc_reg_blocks(self, blocks,
                         graph: UndirectedAdjList) -> X86Program:
        variables = set().union(*[self.collect_locals_instrs(ss) \
                                  for (l, ss) in blocks.items()])
        (color, spills) = self.color_graph(graph, variables)
        used_callee = self.used_callee_reg(variables, color)
        num_callee = len(used_callee)
        home = {x: self.identify_home(color[x], 8 + 8 * num_callee) \
                for x in variables}
        new_blocks = {l: self.assign_homes_instrs(ss, home) \
               for (l, ss) in blocks.items()}
        return (new_blocks, used_callee, num_callee, spills)
    
    def allocate_registers(self, p: X86Program,
                           graph: UndirectedAdjList) -> X86Program:
        match p:
            case X86Program(blocks):
                (new_blocks, used_callee, num_callee, spills) = \
                    self.alloc_reg_blocks(blocks, graph)
                new_p = X86Program(new_blocks)
                new_p.stack_space = align(8 * (num_callee + len(spills)), 16) \
                                    - 8 * num_callee
                new_p.used_callee = used_callee
                return new_p

    ############################################################################
    # Assign Homes
    ############################################################################

    def collect_locals_arg(self, a: arg) -> set[location]:
        match a:
            case ByteReg(id):
                return set()
            case _:
                return super().collect_locals_arg(a)
    
    def collect_locals_instr(self, i: instr) -> set[location]:
        match i:
            case JumpIf(cc, label):
                return set()
            case Jump(label):
                return set()
            case _:
                return super().collect_locals_instr(i)

    def assign_homes_arg(self, a: arg, home: dict[location, arg]) -> arg:
        match a:
            case ByteReg(id):
                return a
            case _:
                return super().assign_homes_arg(a, home)

    def assign_homes_instr(self, i: instr, home: dict[location, arg]) -> instr:
        match i:
            case JumpIf(cc, label):
                return i
            case Jump(label):
                return i
            case _:
                return super().assign_homes_instr(i, home)



    ############################################################################
    # Patch Instructions
    ############################################################################

    def patch_instructions(self, p: X86Program) -> X86Program:
        match p:
            case X86Program(body):
                blocks = {l: self.patch_instrs(ss) for (l, ss) in body.items()}
                new_p = X86Program(blocks)
                new_p.stack_space = p.stack_space
                new_p.used_callee = p.used_callee
                return new_p

    def patch_instr(self, i: instr) -> list[instr]:
        match i:
            case JumpIf(cc, label):
                return [i]
            case Jump(label):
                return [i]
            case Instr('cmpq', [left, Immediate(v)]):
                pass
            
            case Instr('cmpq', [left, right]) if (self.in_memory(left) and self.in_memory(right)):
                pass
            
            case Instr('movzbq', [s, t]) if self.in_memory(t):
                pass
            
            case _:
                return super().patch_instr(i)

    ############################################################################
    # Prelude & Conclusion
    ############################################################################

    def prelude_and_conclusion(self, p: X86Program) -> X86Program:
        match p:
            case X86Program(body):
                save_callee_reg = []
                for r in p.used_callee:
                    save_callee_reg.append(Instr('pushq', [Reg(r)]))
                restore_callee_reg = []
                for r in reversed(p.used_callee):
                    restore_callee_reg.append(Instr('popq', [Reg(r)]))
                main = [Instr('pushq', [Reg('rbp')]), \
                        Instr('movq', [Reg('rsp'), Reg('rbp')])] \
                       + save_callee_reg \
                       + [Instr('subq', [Immediate(p.stack_space),Reg('rsp')]),\
                          Jump('start')]
                concl = [Instr('addq', [Immediate(p.stack_space),Reg('rsp')])] \
                        + restore_callee_reg \
                        + [Instr('popq', [Reg('rbp')]),
                           Instr('retq', [])]
                body['main'] = main
                body['conclusion'] = concl
                return X86Program(body)

    def compile(self, program: Module) -> X86Program:
        pass


if __name__ == '__main__':
    ast = parse('42 if input_int() == 1 else 0')
    print_ast(ast)
    c = Conditionals()
    print('shrink')
    ast = c.shrink(ast)
    print_ast(ast)
    print('rco')
    ast = c.remove_complex_operands(ast)
    print_ast(ast)

    
    
