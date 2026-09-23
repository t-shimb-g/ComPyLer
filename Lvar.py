from Lint import InterpLint
from ast import *

class InterpLvar(InterpLint):
    def interp_exp(self, e, env):
        match e:
            case Name(id):
                return env[id]
            case _:
                return super().interp_exp(e, env)

    def interp_stmt(self, s, env, cont):
        match s:
            case Assign([Name(id)], value):
                env[id] = self.interp_exp(value, env)
                return self.interp_stmts(cont, env)
            case _:
                return super().interp_stmt(s, env, cont)

    def interp(self, p):
        match p:
            case Module(body):
                self.interp_stmts(body, {})
            case _:
                raise ValueError(f'unexpected: {print_ast(p)}')

def interp_Lvar(p):
    InterpLvar().interp(p)
