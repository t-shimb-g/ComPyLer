from dataclasses import dataclass
from utils import label_name, input_int, add64, sub64, neg64

class arg: ...
class location(arg): ...


@dataclass
class Immediate(arg):
    value: int

    def __str__(self):
        return f'${self.value}'

@dataclass
class Reg(location):
    reg: str

    def __str__(self):
        return f'%{self.reg}'

@dataclass(frozen=True)
class Variable(location):
    id: str

    def __str__(self):
        return self.id

    
@dataclass
class Deref(arg):
    reg: str
    offset: int

    def __str__(self):
        return f'{self.offset}(%{self.reg})'

class instr: ...


@dataclass
class Callq(instr):
    func: str
    num_args: int

    def __str__(self):
        return f'callq {self.func}'


@dataclass
class Instr(instr):
    instr: str
    args: tuple[arg, ...]

    def __str__(self):
        return f"{self.instr} {', '.join(str(arg) for arg in self.args)}"

@dataclass
class X86Program:
    body: list[instr]

    def __str__(self):
        main = label_name('main')
        result = f"\t.globl {main}\n"
        result += f"{main}:\n"
        result += '\n'.join(f"\t{s}" for s in self.body)
        result += '\n'
        return result
        

class X86Emulator:
    def __init__(self, debug=False):
        self.debug = debug
        self.registers = {}
        self.memory = {}
        self.variables = {}

        self.store(Reg('rsp'), 1024)
        self.store(Reg('rbp'), 1024)

    
    def __str__(self):
        s = f"X86Emulator(\n  registers = {self.registers}"
        s += f"\n  memory    = {self.memory}"
        s += f"\n  variables = {self.variables}\n)\n"
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
                    
                for s in body:
                    if self.debug:
                        print(s, end='\n\n')
                    
                    self.interp_instr(s)

                    if self.debug:
                        print(self)


    def interp_instr(self, s: instr):
        match s:
            case Instr('movq', [src, dest]):
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

            case Callq('print_int', num_args):
                print(self.load(Reg('rdi')))

            case Callq('read_int', 0):
                value = input_int()
                self.store(Reg('rax'), value)
                
                
            case _:
                raise ValueError(f"unhandled instr: {s}")


def interp_x86(p: X86Program):
    X86Emulator().interp(p)
    
            
if __name__ == '__main__':
    x = X86Emulator(debug=True)
    
    p = X86Program([
        Instr('movq', [Immediate(1), Reg('rdi')]),
        Callq('print_int', 1)
    ])

    x.interp(p)
