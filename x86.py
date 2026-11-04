from dataclasses import dataclass
from collections import defaultdict
from typing import Iterable
from utils import label_name, input_int, add64, sub64, neg64, xor64

class arg: ...
class location(arg): ...


@dataclass(frozen=True)
class Immediate(arg):
    value: int

    def __str__(self):
        return f'${self.value}'


@dataclass(frozen=True)
class Reg(location):
    id: str

    def __str__(self):
        return f'%{self.id}'

@dataclass(frozen=True)
class ByteReg(Reg):
    pass

@dataclass(frozen=True)
class Variable(location):
    id: str

    def __str__(self):
        return self.id

    
@dataclass(frozen=True)
class Deref(arg):
    reg: str
    offset: int

    def __str__(self):
        return f'{self.offset}(%{self.reg})'

class instr: ...


@dataclass(frozen=True, eq=False)
class Callq(instr):
    func: str
    num_args: int

    def __str__(self):
        return f'callq {label_name(self.func)}'


@dataclass(frozen=True, eq=False)
class Instr(instr):
    instr: str
    args: tuple[arg, ...]

    def __init__(self, name: str, args: Iterable[arg]):
        # https://docs.python.org/3/library/dataclasses.html#frozen-instances
        object.__setattr__(self, 'instr', name)
        object.__setattr__(self, 'args', tuple(args))

    def __str__(self):
        return f"{self.instr} {', '.join(str(arg) for arg in self.args)}"


@dataclass(frozen=True, eq=False)
class JumpIf(instr):
    cc: str
    label: str

    def __str__(self):
        return f'j{self.cc} {label_name(self.label)}'


@dataclass(frozen=True, eq=False)
class Jump(instr):
    label: str

    def __str__(self):
        return f'jmp {label_name(self.label)}'

@dataclass
class X86Program:
    body: list[instr] | dict[str, list[instr]]

    def __str__(self):
        if isinstance(self.body, dict):
            result = ''
            for label, stmts in self.body.items():
                if label == 'main':
                    result += f"\t.globl {label_name(label)}\n"

                # result += f".align 16\n" # ensure labels are aligned to 16 bit addrs (faster jumps)
                result += f"{label_name(label)}:\n"
                result += '\n'.join(f"\t{s}" for s in stmts)
                result += '\n'
            return result
                
        else: # list of instructions
            main = label_name('main')
            result = f"\t.globl {main}\n"
            result += f"{main}:\n"
            result += '\n'.join(f"\t{s}" for s in self.body)
            result += '\n'
            return result
        

class X86Emulator:
    def __init__(self, debug=False):
        self.debug = debug
        self.registers = defaultdict(lambda: None)
        self.memory = defaultdict(lambda: None)
        self.variables = defaultdict(lambda: None)

        self.store(Reg('rsp'), 1024)
        self.store(Reg('rbp'), 1024)

    
    def __str__(self):
        s = f"X86Emulator(\n  registers = {dict(self.registers)}"
        s += f"\n  memory    = {dict(self.memory)}"
        s += f"\n  variables = {dict(self.variables)}\n)\n"
        return s

        
    def store(self, a: location, value: int) -> None:
        match a:
            case Reg(reg):
                self.registers[reg] = value
            case Deref(reg, offset):
                addr = self.registers[reg] + offset
                self.memory[addr] = value
            case Variable(id):
                self.variables[id] = value
            case _:
                raise ValueError(f"Cannot store {value} -> {a}")


    def load(self, a: arg) -> int:
        match a:
            case Immediate(value):
                return value
            case Reg(reg):
                return self.registers[reg]
            case Deref(reg, offset):
                addr = self.registers[reg] + offset
                return self.memory[addr]
            case Variable(id):
                return self.variables[id]
            case _:
                raise ValueError(f"Cannot load arg: {a}")


    def interp(self, p: X86Program) -> None:
        match p:
            case X86Program(body):
                if self.debug:
                    print(self)

                if isinstance(body, list):
                    # turn list of statments into a single 'main' block
                    body = {'main': body}

                    
                self.blocks = body

                entry_point = 'start' if 'start' in self.blocks else 'main'
                self.interp_instrs(self.blocks[entry_point])


    def interp_instrs(self, instrs: list[instr]):
        for i in instrs:
            if self.debug:
                print('Evaluating:', i)

            # interpret a single instruction
            match i:
                case Instr('movq', [src, dest]):
                    value = self.load(src)
                    self.store(dest, value)

                case Instr('movzbq', [src, dest]):
                    value = self.load(src)
                    self.store(dest, value)

                case Instr('addq', [src, dest]):
                    value = add64(self.load(dest), self.load(src))
                    self.store(dest, value)

                case Instr('subq', [src, dest]):
                    value = sub64(self.load(dest), self.load(src))
                    self.store(dest, value)

                case Instr('negq', [dest]):
                    value = self.load(dest)
                    self.store(dest, neg64(value))

                case Instr('xorq', [src, dest]):
                    value = xor64(self.load(dest), self.load(src))
                    self.store(dest, value)

                case Instr('pushq', [arg]):
                    # decrement rsp
                    self.store(Reg('rsp'), self.load(Reg('rsp')) - 8) 
                    # save value to top of stack
                    value = self.load(arg)
                    self.store(Deref('rsp', 0), value)

                case Instr('popq', [arg]):
                    # increment rsp
                    value = self.load(Deref('rsp', 0))
                    self.store(Reg('rsp'), self.load(Reg('rsp')) + 8)
                    self.store(arg, value)

                case Callq('print_int', num_args):
                    print(self.load(Reg('rdi')), end='')

                case Callq('read_int', 0):
                    value = input_int()
                    self.store(Reg('rax'), value)

                case Instr('cmpq', [left, right]):
                    l = self.load(left)
                    r = self.load(right)
                    # remember, cmpq args are swapped compared to Python

                    if r == l:
                        self.registers['EFLAGS'] = 'e'
                    elif r < l:
                        self.registers['EFLAGS'] = 'l'
                    elif r > l:
                        self.registers['EFLAGS'] = 'g'
                    else:
                        raise ValueError(f'Invalid comparison {i}')

                case Instr('retq', []):
                    return # stop running

                case Jump(label):
                    if label in self.blocks.keys():
                        self.interp_instrs(self.blocks[label])
                        return # throw away continuations
                    else:
                        print(self.blocks)
                        raise RuntimeError(f'Jump to invalid label: {i}')

                case JumpIf(cc, label):
                    jump = False
                    flag = self.registers['EFLAGS']
                    if cc == 'e' and flag == 'e':
                        jump = True
                    elif cc == 'ne' and flag != 'e':
                        jump = True
                    elif cc == 'l' and flag == 'l':
                        jump = True
                    elif cc == 'le' and flag in ['l', 'e']:
                        jump = True
                    elif cc == 'g' and flag == 'g':
                        jump = True
                    elif cc == 'ge' and flag in ['g', 'e']:
                        jump = True
                        
                    if jump:
                        if label in self.blocks.keys():
                            self.interp_instrs(self.blocks[label])
                            return
                        else:
                            print(self.blocks)
                            raise RuntimeError(f'Jump to invalid label: {i}')

                case Instr('sete', [al]):
                    self.store(al, int(self.registers['EFLAGS'] == 'e'))

                case Instr('setne', [al]):
                    self.store(al, int(self.registers['EFLAGS'] != 'e'))

                case Instr('setl', [al]):
                    self.store(al, int(self.registers['EFLAGS'] == 'l'))

                case Instr('setle', [al]):
                    self.store(al, int(self.registers['EFLAGS'] in ['l', 'e']))

                case Instr('setg', [al]):
                    self.store(al, int(self.registers['EFLAGS'] == 'g'))

                case Instr('setge', [al]):
                    self.store(al, int(self.registers['EFLAGS'] in ['g', 'e']))

                case _:
                    raise ValueError(f"unhandled instr: {i}")

            
            if self.debug:
                print(self)


def interp_x86(p: X86Program):
    X86Emulator().interp(p)

            
if __name__ == '__main__':
    x = X86Emulator(debug=True)
    
    p = X86Program([
        Instr('movq', [Immediate(1), Reg('rdi')]),
        Callq('print_int', 1)
    ])

    p = X86Program({
        'main': [Jump('start')],
        'conclusion': [Callq('print_int', 1),
                       Instr('retq', [])],

        'start': [Instr('movq', [Immediate(1), Variable('x')]),
                  Instr('cmpq', [Immediate(1), Variable('x')]),
                  JumpIf('l', 'true'),
                  Jump('false')],

        'true': [Instr('movq', [Immediate(1), Reg('rdi')]),
                 Jump('conclusion')],

        'false': [Instr('movq', [Immediate(0), Reg('rdi')]),
                 Jump('conclusion')],
        })

    # p = X86Program({
    #     'main': [Instr('pushq', [Reg('rdi')]),
    #              Instr('retq', [])]
    #     })
                       

    x.interp(p)

    print(x)
