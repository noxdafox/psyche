import os
import sys
import random
import string
import textwrap
import importlib
import itertools

from types import ModuleType
from typing import NamedTuple
from tempfile import NamedTemporaryFile

from lark import lark
from lark import visitors

from psyche import reconstructor


def import_source_code(source: str, module_name: str) -> ModuleType:
    with NamedTemporaryFile(buffering=0, suffix='.py') as module_file:
        module_file.write(source.encode())

        spec = importlib.util.spec_from_file_location(
            module_name, module_file.name)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules[module_name] = module

        return module


def compile_rule(environment: 'Environment',
                 module_name: str,
                 name, lhs: lark.Tree,
                 rhs: lark.Tree) -> str:
    lhs_compiler = LHSCompiler(module_name, name, lhs)
    lhs_string, variables = lhs_compiler.compile()
    rhs_compiler = RHSCompiler(environment, module_name, name, rhs, variables)
    rhs_string = rhs_compiler.compile()

    return os.linesep.join((f'(defrule {name}', lhs_string, '  =>', rhs_string, ')'))


class LHSCompiler(visitors.Transformer):
    def __init__(self, module_name: str, name: str, tree: lark.Tree):
        super().__init__()

        self._module_name = module_name
        self._name = name
        self._tree = tree
        self._variables = []

    def __default__(self, *args):
        raise SyntaxError(f"Rule: {self._name} - Invalid Syntax: {args}")

    def compile(self):
        lhs = self.transform(self._tree)

        return lhs, self._variables

    def lhs_stmt(self, node):
        return os.linesep.join(node)

    def condition(self, node):
        return '  ' + ' '.join(node)

    def fact_match(self, node):
        return Fact(f'({node[0]} ' + ' '.join(node[1:]) + ')')

    def bind(self, node):
        var, operator, value = node
        if var in self._variables:
            raise SyntaxError(f"Rule: {self._name} - Variable <{var}> already defined")

        self._variables.append(var)

        variable = Variable(f'?{var}')

        if isinstance(value, Fact):
            return Bind(f'{variable} {operator} {value}')
        if isinstance(value, Variable):
            return Bind(f'({value} {variable})')

        raise SyntaxError(f"Rule: {self._name} - Invalid Syntax: {node}")

    def bind_op(self, node):
        return Binder('<-')

    def constraint_list(self, node):
        return Constraints(' '.join([n.clips_string()
                                     if isinstance(n, Function)
                                     else n
                                     for n in node]))

    def python__funccall(self, node):
        if len(node) > 1:
            funcname, arguments = node
        else:
            funcname = node[0]
            arguments = []

        data = RuleData(self._module_name, self._variables)
        args = ', '.join(arguments).replace('"', '\'')

        return Function(f'{funcname}({args})',
                        self._module_name,
                        *find_slot(funcname, arguments, data),
                        find_variables(arguments, data))

    def python__arith_expr(self, node):
        left, operator, right = node
        data = RuleData(self._module_name, self._variables)

        return Operation(f' {operator} '.join((left, right)),
                         self._module_name,
                         *find_slot(operator, (left, right), data),
                         find_variables((left, right), data))

    def python__getattr(self, node):
        root, stem = node
        code = f'{root}.{stem}'

        if isinstance(root, Function):
            return Function(code,
                            root.module,
                            slot=root.slot,
                            varname=root.varname,
                            variables=root.variables)

        return GetAttr(code)

    def python__arguments(self, node):
        return node

    def python__argvalue(self, node):
        return '='.join(node)

    def python__comparison(self, node):
        left, cmp, right = node
        variables = left, right
        data = RuleData(self._module_name, self._variables)

        if is_constant_constraint(cmp, variables, data):
            left, right = (f'?{v}' if v in self._variables else v for v in variables)
            return CLIPSComparison(f'({left} {right})')

        slot, variable = find_slot(cmp, variables, data)

        if is_clips_constraint(*variables):
            left, right = (e.clips_string(slot=False)
                           if isinstance(e, Function) else e
                           for e in (left, right))

            return CLIPSComparison(f'({slot} {variable}&:({cmp} {left} {right}))')

        return PythonComparison(f'{left} {cmp} {right}',
                                self._module_name,
                                slot=slot,
                                varname=variable,
                                variables=find_variables((left, right), data))

    def python__comp_op(self, node):
        return Comparator(COMPARATOR_MAP[str(node[0])])

    def python__var(self, node):
        return Variable(str(node[0]))

    def python__string(self, node):
        code = str(node[0]).strip('"').strip("'")

        return String(f'"{code}"')

    def python__number(self, node):
        return Number(str(node[0]))

    def python__const_true(self, _):
        return Boolean('TRUE')

    def python__const_false(self, _):
        return Boolean('FALSE')


class RHSCompiler(visitors.Transformer):
    def __init__(self,
                 env: 'Environment',
                 module_name: str,
                 name: str,
                 tree: lark.Tree,
                 variables: list):
        super().__init__()

        self._env = env
        self._module = sys.modules[module_name]
        self._name = name
        self._tree = tree
        self._variables = set(variables)

    def compile(self):
        rhs = self.transform(self._tree)
        variables = ' '.join(f'?{v}' for v in self._variables)
        code = textwrap.dedent(reconstructor.reconstruct_code(rhs))
        compiled = compile(code, self._name, 'exec')

        ACTION_MAP[self._name] = Action(self._env, compiled, self._module, self._variables)

        return f'  (py-action {self._name} {variables})'

    def rhs_stmt(self, node):
        return node[0]


class Bind(str):
    def __new__(cls, value):
        return super().__new__(cls, value)


class Binder(str):
    def __new__(cls, value):
        return super().__new__(cls, value)


class Comparator(str):
    def __new__(cls, value):
        return super().__new__(cls, value)


class GetAttr(str):
    def __new__(cls, value):
        return super().__new__(cls, value)


class Function(str):
    module: str = None
    slot: str = None
    varname: str = None
    variables: list = None

    def __new__(cls: type,
                code: str,
                module: str,
                slot: str = None,
                varname: str = None,
                variables: str = None):
        obj = super().__new__(cls, code)
        obj.module = module
        obj.slot = slot
        obj.varname = varname
        obj.variables = variables if variables is not None else []

        return obj

    def clips_string(self, slot=True) -> str:
        function = f'py-eval {self.module} "{self}"'
        variables = ' '.join([f'{v} ?{v}' for v in self.variables])

        if self.slot is not None:
            variables += f' {self.slot} {self.varname}'

            if slot:
                return f'({self.slot} {self.varname}&:({function} {variables}))'

            return f'({function} {variables})'

        return f'({function} {variables})'


class CLIPSComparison(str):
    def __new__(cls, value):
        return super().__new__(cls, value)


class PythonComparison(Function):
    pass


class Operation(Function):
    pass


class Constraints(str):
    def __new__(cls, value):
        return super().__new__(cls, value)


class Fact(str):
    def __new__(cls, value):
        return super().__new__(cls, value)


class String(str):
    def __new__(cls, value):
        return super().__new__(cls, value)


class Number(str):
    def __new__(cls, value):
        return super().__new__(cls, value)


class Boolean(str):
    def __new__(cls, value):
        return super().__new__(cls, value)


class Variable(str):
    def __new__(cls, value):
        return super().__new__(cls, value)


class Action(NamedTuple):
    env: 'Environment'
    code: 'code'
    module: str
    varnames: list


class RuleData(NamedTuple):
    module: str
    variables: list


def is_constant_constraint(cmp: str, variables: list, data: RuleData) -> bool:
    return (cmp == '==' and
            any(is_slot(c, data) or c in data.variables for c in variables) and
            any(isinstance(c, CLIPS_TYPE) or c in data.variables for c in variables))


def is_clips_constraint(left: str, right: str) -> bool:
    return any(isinstance(c, CLIPS_TYPE) for c in (left, right))


def find_slot(function: str, arguments: list, data: RuleData) -> list:
    if is_slot_method(function, data):
        return qualname_root(function), f'?{random_name(6)}'

    for argument in arguments:
        if is_slot_method(argument, data):
            return qualname_root(function), f'?{random_name(6)}'
        if is_slot(argument, data):
            return argument, f'?{random_name(6)}'
        if isinstance(argument, Function) and argument.slot is not None:
            return argument.slot, argument.varname

    return None, None


def find_variables(variables: list, data: RuleData) -> iter:
    """Returns a flattened list of variables."""
    variables = flatten((getattr(v, 'variables', v) for v in variables))

    return filter(lambda v: v in data.variables, variables)


def is_slot_method(function: str, data: RuleData) -> bool:
    return isinstance(function, GetAttr) and is_slot(function, data)


def is_slot(name: str, data: RuleData) -> bool:
    if isinstance(name, GetAttr):
        name = Variable(qualname_root(name))

    return (isinstance(name, Variable) and
            name not in data.variables and
            name not in sys.modules.keys() and
            name not in sys.modules[data.module].__dict__)


def random_name(length: int) -> str:
    return ''.join(random.choice(string.ascii_lowercase) for _ in range(length))


def qualname_root(name: str) -> str:
    return name.split('.')[0]


def flatten(list_of_strings: iter) -> iter:
    """["foo", ["bar", "baz"]] -> ["foo", "bar", "baz"]."""
    return itertools.chain.from_iterable(itertools.repeat(v, 1)
                                         if isinstance(v, str) else v
                                         for v in list_of_strings)


ACTION_MAP = {}
CLIPS_TYPE = String, Number, Boolean
COMPARATOR_MAP = {'<': '<',
                  '<=': '<=',
                  '>': '>',
                  '>=': '>=',
                  '==': '==',
                  '!=': '<>',
                  'is': 'eq'}
