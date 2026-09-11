from ast import *
from utils import *

class InterpLint:
    def interp_exp(self, e, env):
        match e:
            case BinOp(left, Add(), right):
                l = self.interp_exp(left, env)
                r = self.interp_exp(right, env)
                return add64(l, r)
            case BinOp(left, Sub(), right):
                l = self.interp_exp(left, env)
                r = self.interp_exp(right, env)
                return sub64(l, r)
            case UnaryOp(USub(), v):
                return neg64(self.interp_exp(v, env))
            case Constant(value):
                return value
            case Call(Name('input_int'), []):
                return input_int()
            case _:
                raise NotImplementedError(f'{e}')

    def interp_stmt(self, s, env, cont):
        match s:
            case Expr(Call(Name('print'), [arg])):
                val = self.interp_exp(arg, env)
                print(val, end='')
                return self.interp_stmts(cont, env) # evaluate next statements inside cont (cont = ss here)
            case Expr(value):
                self.interp_exp(value, env)
                return self.interp_stmts(cont, env)
            case _:
                raise NotImplementedError(f'{s}')

    def interp_stmts(self, ss, env):
        match ss:
            case[]:
                return 0
            case[s, *ss]: # recursive for-loop (unpack first statement, keep rest, interp_stmt)
                return self.interp_stmt(s, env, ss)

    def interp(self, p):
        match p:
            case Module(body):
                self.interp_stmts(body, {})

def interp_Lint(p):
    return InterpLint().interp(p
