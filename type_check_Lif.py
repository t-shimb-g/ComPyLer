from ast import *
from type_check_Lvar import TypeCheckLvar
from utils import *

class TypeCheckLif(TypeCheckLvar):
    def type_check_exp(self, e, env):
        match e:
            case Constant(value) if isinstance(value, bool):
                return BoolType()
            case UnaryOp(Not(), v):
                t = self.type_check_exp(v, env)
                self.check_type_equal(t, BoolType(), v)
                return BoolType() 
            case BoolOp(op, values):
                left, right = values[0], values[1]
                l = self.type_check_exp(left, env)
                self.check_type_equal(l, BoolType(), left)
                r = self.type_check_exp(right, env)
                self.check_type_equal(r, BoolType(), right)
                return BoolType()
            case Compare(left, [cmp], [right]) if isinstance(cmp, Eq) or isinstance(cmp, NotEq):
                l = self.type_check_exp(left, env)
                r = self.type_check_exp(right, env)
                self.check_type_equal(l, r, e)
                return BoolType()
            case Compare(left, [cmp], [right]):
                l = self.type_check_exp(left, env)
                self.check_type_equal(l, IntType(), left)
                r = self.type_check_exp(right, env)
                self.check_type_equal(r, IntType(), right)
                return BoolType()
            case IfExp(test, body, orelse):
                t = self.type_check_exp(test, env)
                self.check_type_equal(BoolType(), t, test)
                b = self.type_check_exp(body, env)
                o = self.type_check_exp(orelse, env)
                self.check_type_equal(b, o, e)
                return b
            case _:
                return super().type_check_exp(e, env)

    def type_check_stmts(self, ss, env):
        if len(ss) == 0:
            return
        match ss[0]:
            case If(test, body, orelse):
                t = self.type_check_exp(test, env)
                self.check_type_equal(BoolType(), t, test)
                b = self.type_check_stmts(body, env)
                o = self.type_check_stmts(orelse, env)
                self.check_type_equal(b, o, ss[0])

            case _:
                return super().type_check_stmts(ss, env)
