from ast import *
from utils import *
from x86 import *
import var
from graph import UndirectedAdjList
from priority_queue import PriorityQueue

caller_save: set[str] = {'rax', 'rcx', 'rdx', 'rsi', 'rdi', 'r8', 'r9', 'r10', 'r11'}
callee_save: set[str] = {'rsp', 'rbp', 'rbx', 'r12', 'r13', 'r14', 'r15'}
reserved_registers: set[str] = {'rax', 'r11', 'r15', 'rsp', 'rbp', '__flag'}
general_registers: list[str] = ['rcx', 'rdx', 'rsi', 'rdi', 'r8', 'r9', 'r10',
                     'rbx', 'r12', 'r13', 'r14']
registers_for_alloc: list[str] = general_registers
arg_registers: list[str] = ['rdi', 'rsi', 'rdx', 'rcx', 'r8', 'r9']
registers = set(general_registers).union(reserved_registers)

caller_save_for_alloc = caller_save.difference(reserved_registers) \
                                   .intersection(set(registers_for_alloc))
callee_save_for_alloc = callee_save.difference(reserved_registers) \
                                   .intersection(set(registers_for_alloc))

byte_to_full_reg = \
    {'ah': 'rax', 'al': 'rax',
     'bh': 'rbx', 'bl': 'rbx',
     'ch': 'rcx', 'cl': 'rcx',
     'dh': 'rdx', 'dl': 'rdx'}

register_color = {'rax': -1, 'rsp': -2, 'rbp': -3, 'r11': -4, 'r15': -5, '__flag': -6}

for i, r in enumerate(registers_for_alloc):
    register_color[r] = i

extra_arg_registers = list(set(arg_registers) - set(registers_for_alloc))
for i, r in enumerate(extra_arg_registers):
    register_color[r] = -i - 6


class RegisterAllocator(var.Var):
    ######################################################################
    # Uncover live
    ######################################################################
    def vars_arg(self, a: arg) -> set[location]:
        match a:
            case Variable(id):
                return set([a])
            case Reg(id):
                return set([a])
            case Deref(reg, offset):
                return set([Reg(reg)])
            case Immediate(value):
                return set()
            case _:
                raise ValueError(f'vars_arg unexpected: {a}')

    def read_vars(self, i: instr) -> set[location]:
        match i:
            case Instr('movq', [src, _]):
                return self.vars_arg(src)
            case Instr(_, args):
                args_set = set()
                for arg in args:
                    args_set.update(self.vars_arg(arg))  
                return args_set
            case Callq(_, num_args):
                # Take into account that caller could have passed arguments to callee's procedure
                args_set = set()
                for i in range(num_args):
                    args_set.update(self.vars_arg(Reg(arg_registers[i])))
                return args_set
            case _:
                raise ValueError(f'read_vars unexpected: {i}')

    def write_vars(self, i: instr) -> set[location]:
        match i:
            case Instr(instr, [dest]):
                return self.vars_arg(dest)
            case Instr(instr, [_, dest]):
                return self.vars_arg(dest)
            case Callq(_, _):
                # Take into account that caller cannot expect procedure arguments to not be overwritten
                args_set = set()
                for arg in caller_save:
                    args_set.update(self.vars_arg(Reg(arg)))
                return args_set
            case _:
                raise ValueError(f'write_vars unexpected: {i}')

    def uncover_live_instr(self, i: instr, live_before_succ: set[location],
                           live_before: dict[instr, set[location]], live_after: dict[instr, set[location]]):
        # Live after k = live before k+1
        live_after[i] = live_before_succ
        live_before[i] = (live_after[i] - self.write_vars(i)).union(self.read_vars(i))
        

    def uncover_live(self, p: X86Program) -> dict[instr, set[location]]:
        match p:
            case X86Program(body):
                live_before = {}
                live_after = {}
                # live_before from next line down (k+1)
                live_before_succ = set() # succ = successor

                for i in reversed(body):
                    self.uncover_live_instr(i, live_before_succ, live_before, live_after)
                    live_before_succ = live_before[i] # live_before k+1

                self.trace_live(p, live_before, live_after) # pretty print live_after with instructions
                return live_after

    def trace_live(self, p: X86Program, live_before: dict[instr, set[location]],
                   live_after: dict[instr, set[location]]) -> None:
        match p:
            case X86Program(body):
                print(f'\t\t\t{live_before[body[0]]}')
                for inst in body:
                    print(inst)
                    print(f'\t\t\t{live_after[inst]}')


    ######################################################################
    # Build interference
    ######################################################################
    def build_interference(self, p: X86Program, live_after: dict[instr, set[location]]) -> UndirectedAdjList:
        match p:
            case X86Program(body):
                graph = UndirectedAdjList()
                for instr in body:
                    self.interfere_instr(instr, graph, live_after)
                return graph

    def interfere_instr(self, i: instr, graph: UndirectedAdjList,
                        live_after: dict[instr, set[location]]) -> None:
        """Add an edge to the graph for each interfering location"""
        match i:
            case Instr('movq', [src, dest]):
                # Take into account src=dest contain same value, but do not interfere
                for v in live_after[i]:
                    if v != dest and v != src:
                        graph.add_edge(v.id, dest.id)
            case _:
                for d in self.write_vars(i):
                    for v in live_after[i]:
                        if d != v:
                             graph.add_edge(d.id, v.id)
                             
                    


    ###########################################################################
    # Allocate Registers
    ###########################################################################

    def choose_color(self, v, unavailable_colors: dict[Variable, set[int]]) -> int:
        """Choose the lowest color for Vertex v that is not in unavailable_colors"""
        i = 0
        while True:
            if i not in unavailable_colors[v]:
                return i
            i = i + 1

    def color_graph(self, graph: UndirectedAdjList, variables: set[location]) -> tuple[dict[location, int], set[location]]:
        # the saturation of each variable (colors which it cannot be due to adjacent colors)
        unavailable_colors : dict[Variable, set[int]] = {}

        # sort the vertices such that the most saturated one will appear at the front of the priority queue
        def compare(u, v):
            return len(unavailable_colors[u.key]) < len(unavailable_colors[v.key])

        pq = PriorityQueue(compare)

        # dictionary of Register|Variable to color (int)
        colors = {}

        # add each color for each register
        for r in registers_for_alloc:
            colors[Reg(r)] = register_color[r]

        # initialize unavailable_colors by first handling any variable
        # that cannot conflict with a register (this could happen
        # during a function call with arguments and return registers)
        for x in variables:
            adjacent_registers = [y for y in graph.adjacent(x) if y.id in registers]
            unavailable_colors[x] = set().union([register_color[r.id] for r in adjacent_registers])

            # put each variable into the priority queue
            pq.push(x)
            

        # during register allocation we might need extra space for
        # variables that cannot fit into registers, spills will
        # contain these variables which will later be put on the stack
        spills = set()
            
        # DSATUR
        while not pq.empty():
            # pick a random vertex with the highest saturation (least amount of color options left)
            v = pq.pop()

            # find lowest color
            color = self.choose_color(v, unavailable_colors)
            colors[v] = color

            # if color is larger than available registers (register_for_alloc), then update spill variables
            if color >= len(registers_for_alloc):
                spills.add(v)

            # for every Variable adjacent to v (ignore registers), update unavailable_colors for each
            # when a node's saturation has changed, use pq.increase_key(node) to update the priority queue
            for u in graph.out[v]:
                if isinstance(u, Variable):
                    unavailable_colors[u].add(color)
                    pq.increase_key(u)

        return colors, spills



    def identify_home(self, c: int, first_location: int) -> arg:
        """If color is within register colors values, then return the register. Otherwise, return a stack location"""
        if c < len(registers_for_alloc):
            return Reg(registers_for_alloc[c])
        else:
            offset = first_location + 8 * (c - len(registers_for_alloc))
            return Deref('rbp', - offset)
        

    def is_callee_color(self, c: int) -> bool:
        return c < len(registers_for_alloc) and registers_for_alloc[c] in callee_save

    def used_callee_reg(self, variables: set[location], color: dict[location, int]) -> set[str]:
        """Calculate which callee saved registers have been allocated to"""
        result = set()
        for x in variables:
            if self.is_callee_color(color[x]):
                result.add(registers_for_alloc[color[x]])
        return list(result)

    def allocate_registers(self, p: X86Program,
                           graph: UndirectedAdjList) -> X86Program:
        match p:
            case X86Program(body):
                variables = self.collect_locals_instrs(body)
                color, spills = self.color_graph(graph, variables)

                used_callee = self.used_callee_reg(variables, color)
                num_callee = len(used_callee)
                
                home = {}
                for x in variables:
                    home[x] = self.identify_home(color[x], 8 + 8 * num_callee)

                new_body = [self.assign_homes_instr(s, home) for s in body]
                new_p = X86Program(new_body)
                new_p.stack_space = align(8 * (num_callee + len(spills)), 16) \
                    - 8 * num_callee
                new_p.used_callee = used_callee
                return new_p

    def assign_homes(self, pseudo_x86: X86Program) -> X86Program:
        """Override assign_homes from Var to build an interference graph and use it to assign registers"""
        live_after = self.uncover_live(pseudo_x86)
        graph = self.build_interference(pseudo_x86, live_after)
        return self.allocate_registers(pseudo_x86, graph)
            
    ###########################################################################
    # Patch Instructions
    ###########################################################################

    def patch_instr(self, i: instr) -> list[instr]:
        """Remove trivial moves: s -> d if s == d. Pass everything else onto Var's patch_instr"""
        match i:
            case Instr('movq', [src, dest]) if src == dest:
                return []
            case _:
                return super().patch_instr(i)

    def patch_instructions(self, p: X86Program) -> X86Program:
        match p:
            case X86Program(body):
                new_p = X86Program(self.patch_instrs(body))
                new_p.stack_space = p.stack_space
                new_p.used_callee = p.used_callee
                return new_p
            
    ###########################################################################
    # Prelude & Conclusion
    ###########################################################################

    def prelude_and_conclusion(self, p: X86Program) -> X86Program:
        match p:
            case X86Program(body):
                save_callee_reg = []
                for r in p.used_callee:
                    save_callee_reg.append(Instr('pushq', [Reg(r)]))
                restore_callee_reg = []
                for r in reversed(p.used_callee):
                    restore_callee_reg.append(Instr('popq', [Reg(r)]))
                prelude = [Instr('pushq', [Reg('rbp')]), \
                        Instr('movq', [Reg('rsp'), Reg('rbp')])] \
                       + save_callee_reg \
                       + [Instr('subq', [Immediate(p.stack_space),Reg('rsp')])]
                concl = [Instr('addq', [Immediate(p.stack_space),Reg('rsp')])] \
                        + restore_callee_reg \
                        + [Instr('popq', [Reg('rbp')]),
                           Instr('retq', [])]
                return X86Program(prelude + body + concl)



    def compile(self, program: Module) -> X86Program:
        for compiler in [self.remove_complex_operands, self.select_instructions,
                         self.assign_homes, self.patch_instructions,
                         self.prelude_and_conclusion]:
            program = compiler(program)

        return program
            
if __name__ == '__main__':
    text = """
x = input_int()
y = input_int()
print((x + y) + 42)
    """

    from run_tests import TestCase
    from pathlib import Path
    t = TestCase(Path('tests/var/eg19'))
    ast = t.ast

    ast = parse(text)

    r = RegisterAllocator()
    ast = r.remove_complex_operands(ast)
    x86 = r.select_instructions(ast)
    live_after = r.uncover_live(x86)
    g = r.build_interference(x86, live_after)
    print("=== interference ===")
    for e in g.edges():
        print(f"  {e.source} -- {e.target}")

    g.show().render()

    # from run_tests import TestCase
    # from pathlib import Path
    #
    # print(Callq('read_int', 0) == Callq('read_int', 0),
    #   hash(Callq('read_int', 0)) == hash(Callq('read_int', 0)))
    #
    # t = TestCase(Path('tests/var/add-sub'))
    # r = RegisterAllocator()
    #
    # ast = r.remove_complex_operands(t.ast)
    # x86 = r.select_instructions(ast)
    # print("=== pseudo-x86 ===");  print(x86)
    #
    # live_after = r.uncover_live(x86)          # already prints the trace
    # g = r.build_interference(x86, live_after)
    # print("=== interference ===")
    # for e in g.edges():
    #     print(f"  {e.source} -- {e.target}")
    #
    # homes = r.allocate_registers(x86, g)
    # print("=== after allocation ===");  print(homes)