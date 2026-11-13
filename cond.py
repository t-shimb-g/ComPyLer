import itertools
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
                l = self.shrink_exp(left)
                r = self.shrink_exp(right)
                return BinOp(l, op, r)
            
            case UnaryOp(op, operand):
                o = self.shrink_exp(operand)
                return UnaryOp(op, o)
            
            case Call(func, args):
                fun = self.shrink_exp(func)
                new_args = [self.shrink_exp(arg) for arg in args]
                return Call(fun, new_args)

            case IfExp(test, body, orelse):
                t = self.shrink_exp(test)
                b = self.shrink_exp(body)
                oe = self.shrink_exp(orelse)
                return IfExp(t, b, oe)

            # Replace And with IfExp
            case BoolOp(And(), values):
                e1, e2 = self.shrink_exp(values[0]), self.shrink_exp(values[1])
                return IfExp(e1, e2, Constant(False)) # e2 if e1 else False

            # Replace Or with IfExp
            case BoolOp(Or(), values):
                e1, e2 = self.shrink_exp(values[0]), self.shrink_exp(values[1])
                return IfExp(e1, Constant(True), e2) # True if e1 else e2

            case Compare(left, [op], [right]):
                l = self.shrink_exp(left)
                r = self.shrink_exp(right)
                return Compare(l, [op], [r])
            
            case _:
                raise Exception('shrink_exp: ' + repr(e))

    
    def shrink_stmt(self, s: stmt) -> stmt:
        match s:
            case Assign(targets, value):
                new_targets = [self.shrink_exp(target) for target in targets]
                new_value = self.shrink_exp(value)
                return Assign(new_targets, new_value)

            case Expr(value):
                new_value = self.shrink_exp(value)
                return Expr(new_value)

            case If(test, body, orelse):
                new_test = self.shrink_exp(test)
                new_body = [self.shrink_stmt(stmt) for stmt in body]
                new_orelse = [self.shrink_stmt(stmt) for stmt in orelse]
                return If(new_test, new_body, new_orelse)

            case _:
                raise Exception('shrink_stmt: unexpected: ' + repr(s))

    
    def shrink(self, p: Module) -> Module:
        # type check = valid user program
        match p:
            case Module(body):
                new_body = [self.shrink_stmt(stmt) for stmt in body]
                # type check = pass isn't incorrect
                return Module(new_body)

    ############################################################################
    # Remove Complex Operands
    ############################################################################

    def rco_stmt(self, s: stmt) -> list[stmt]:
        match s:
            case If(test, body, orelse):
                # generate temporaries for test, body, orelse
                t, t_temps = self.rco_exp(test, False)
                t_vars = [ Assign([var], value) for var, value in t_temps ]
                new_body = [self.rco_stmt(stmt) for stmt in body]
                flattened_body = list(itertools.chain.from_iterable(new_body))
                new_orelse = [self.rco_stmt(stmt) for stmt in orelse]
                flattened_orelse = list(itertools.chain.from_iterable(new_orelse))
                # none need to be atomic
                return t_vars + [If(t, flattened_body, flattened_orelse)]

            case _:
                return super().rco_stmt(s)

    def rco_exp(self, e: expr, need_atomic: bool) -> tuple[expr, Temporaries]:
        match e:
            case IfExp(test, body, orelse):
                # rco for test, body, orelse
                atm_test, t_temps = self.rco_exp(test, True)
                atm_body, b_temps = self.rco_exp(body, True)
                atm_orelse, oe_temps = self.rco_exp(orelse, True)

                # make Begin blocks for body and orelse
                new_body = Begin( [Assign([tmp], value) for tmp, value in b_temps], atm_body )
                new_orelse = Begin( [Assign([tmp], value) for tmp, value in oe_temps], atm_orelse )
                if_exp = IfExp(atm_test, new_body, new_orelse)

                # if need_atomic == True: generate a temporary for the last expression assigned to
                if need_atomic:
                    tmp = Name(generate_name('tmp'))
                    return tmp, t_temps + [(tmp, if_exp)]
                else:
                    return if_exp, t_temps

            case Compare(left, [op], [right]):
                # rco for each part
                # if need_atomic, generate a temporary for last expression
                l, l_temps = self.rco_exp(left, True)
                r, r_temps = self.rco_exp(right, True)
                cmp = Compare(l, [op], [r])
                if need_atomic:
                    tmp = Name(generate_name('tmp'))
                    return tmp, l_temps + r_temps + [(tmp, cmp)]
                else:
                    return cmp, l_temps + r_temps

            case UnaryOp(op, exp):
                atm, temps = self.rco_exp(exp, True)
                uop = UnaryOp(op, atm)
                if need_atomic:
                    tmp = Name(generate_name('tmp'))
                    return tmp, temps + [(tmp, uop)]
                else:
                    return uop, temps
                
            case _:
                return super().rco_exp(e, need_atomic)


    ############################################################################
    # Explicate Control
    ############################################################################

    def create_block(self, stmts: list[stmt], basic_blocks: dict[str, list[stmt]]) -> list[stmt]:
        """ Insert labeled blocks into basic_blocks, returns a goto(label)"""
        match stmts:
            case [Goto(l)]:
                return stmts

            case _:
                label = generate_name('block')
                basic_blocks[label] = stmts
                return [Goto(label)]

    def explicate_effect(self, e: expr, cont: list[stmt],
                         basic_blocks: dict[str, list[stmt]]) -> list[stmt]:
        match e:
            case Begin(body, result):
                stmts = self.explicate_effect(result, cont, basic_blocks)
                for s in reversed(body):
                    stmts = self.explicate_stmt(s, stmts, basic_blocks)
                return stmts
            
            case IfExp(test, body, orelse):
                goto_cont = self.create_block(cont, basic_blocks)
                new_body = self.explicate_effect(body, goto_cont, basic_blocks)
                new_orelse = self.explicate_effect(orelse, goto_cont, basic_blocks)
                return self.explicate_pred(test, new_body, new_orelse, basic_blocks)
            
            case Call(func, args):
                return [Expr(e)] + cont
            
            case _:  # no effect, remove this expression
                return cont

    def explicate_assign(self, e: expr, x: Variable, cont: list[stmt],
                         basic_blocks: dict[str, list[stmt]]) -> list[stmt]:
        match e:
            case Begin(body, result):
                stmts = self.explicate_assign(result, x, cont, basic_blocks)
                for s in reversed(body):
                    stmts = self.explicate_stmt(s, stmts, basic_blocks)
                return stmts
          
            case IfExp(test, body, orelse):
                goto_cont = self.create_block(cont, basic_blocks)
                new_body = self.explicate_assign(body, x, goto_cont, basic_blocks)
                new_orelse = self.explicate_assign(orelse, x, goto_cont, basic_blocks)
                return self.explicate_pred(test, new_body, new_orelse, basic_blocks)
            
            case _:
                return [Assign([x], e)] + cont
            
    def generic_explicate_pred(self, cnd: expr, thn: list[stmt],
                               els: list[stmt],
                               basic_blocks: dict[str, list[stmt]]) -> list[stmt]:
        goto_thn = self.create_block(thn, basic_blocks)
        goto_els = self.create_block(els, basic_blocks)
        return [If(Compare(cnd, [Eq()], [Constant(True)]), goto_thn, goto_els)]

    def explicate_pred(self, cnd: expr, thn: list[stmt], els: list[stmt],
                       basic_blocks: dict[str, list[stmt]]) -> list[stmt]:
        match cnd:
            case Name(x):
                return self.generic_explicate_pred(cnd, thn, els, basic_blocks)

            case Compare(left, [op], [right]):
                goto_thn = self.create_block(thn, basic_blocks) # block.N : thn => goto block.N
                goto_els = self.create_block(els, basic_blocks)
                return [If(cnd, goto_thn, goto_els)]
            
            case Constant(True): # woo go fast!
                return thn
            
            case Constant(False):
                return els
            
            case UnaryOp(Not(), operand):
                # just swap thn and els
                new_operand = self.explicate_pred(operand, els, thn, basic_blocks)
                return new_operand
            
            case Begin(body, result):
                # body : list[stmts, assign(result, value)], result : expr
                stmts = self.explicate_pred(result, thn, els, basic_blocks)
                for s in reversed(body):
                    stmts = self.explicate_stmt(s, stmts, basic_blocks)
                return stmts
            
            case IfExp(test, body, orelse):
                goto_thn = self.create_block(thn, basic_blocks)
                goto_els = self.create_block(els, basic_blocks)
                body_stmts = self.explicate_pred(body, goto_thn, goto_els, basic_blocks)
                orelse_stmts = self.explicate_pred(orelse, goto_thn, goto_els, basic_blocks)
                test_stmts = self.explicate_pred(test, body_stmts, orelse_stmts, basic_blocks)
                return test_stmts
            
            case _:
                raise Exception('explicate_pred: unexpected ' + repr(cnd))

    def explicate_stmt(self, s: stmt, cont: list[stmt],
                       basic_blocks: dict[str, list[stmt]]) -> list[stmt]:
        match s:
            case Assign([lhs], rhs):
                return self.explicate_assign(rhs, lhs, cont, basic_blocks)
            
            case Expr(value):
                return self.explicate_effect(value, cont, basic_blocks)
            
            case If(test, body, orelse):
                # continuation after If
                goto = self.create_block(cont, basic_blocks) # jump to after If is done

                # true branch
                new_body = goto
                for s in reversed(body):
                    new_body = self.explicate_stmt(s, new_body, basic_blocks)

                # false branch
                new_orelse = goto
                for s in reversed(orelse):
                    new_orelse = self.explicate_stmt(s, new_orelse, basic_blocks)

                return self.explicate_pred(test, new_body, new_orelse, basic_blocks)

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
                return {Reg(byte_to_full_reg[id])}
            case _:
                return super().vars_arg(a)

    def read_vars(self, i: instr) -> set[location]:
        match i:
            case Jump(label):
                return set()
            case JumpIf(cc, label):
                return set()
            case _:
                return super().read_vars(i)

    def write_vars(self, i: instr) -> set[location]:
        match i:
            case Jump(label):
                return set()
            case JumpIf(cc, label):
                return set()
            case Instr('cmpq', args):
                return {Reg('__flag')}
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

    def collect_locals_instr(self, i: instr) -> set[location]:
        match i:
            case JumpIf(cc, label):
                return set()
            case Jump(label):
                return set()
            case _:
                return super().collect_locals_instr(i)

    def collect_locals_arg(self, a: arg) -> set[location]:
        match a:
            case ByteReg(id):
                return set()
            case _:
                return super().collect_locals_arg(a)

    def assign_homes_instr(self, i: instr, home: dict[location, arg]) -> instr:
        match i:
            case JumpIf(cc, label):
                return i
            case Jump(label):
                return i
            case _:
                return super().assign_homes_instr(i, home)

    def assign_homes_arg(self, a: arg, home: dict[location, arg]) -> arg:
        match a:
            case ByteReg(id):
                return a
            case _:
                return super().assign_homes_arg(a, home)

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
                return [Instr('movq', [Immediate(v), Reg('rax')]),
                        Instr('cmpq', [left, Reg('rax')])]

            case Instr('cmpq', [left, right]) if (self.in_memory(left) and self.in_memory(right)):
                return [Instr('movq', [right, Reg('rax')]),
                        Instr('cmpq', [left, Reg('rax')])]
            case Instr('movzbq', [s, t]) if self.in_memory(t):
                return [Instr('movzbq', [s, Reg('rax')]),
                        Instr('movq', [Reg('rax'), t])]
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
        # type check Lif here, in run_tests check before each interpreter BOTH pre and post condition
        for compiler in [self.shrink, self.remove_complex_operands, self.explicate_control,
                         self.select_instructions]:
                         # , self.assign_homes, self.patch_instructions,
                         # self.prelude_and_conclusion]:

            program = compiler(program)

        return program


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

    
    
