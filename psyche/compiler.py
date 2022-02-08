import os
import sys
import random
import string
import textwrap
import importlib

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


def compile_rule(module: ModuleType, name, lhs: lark.Tree, rhs: lark.Tree):
    lhs_compiler = LHSCompiler(module, name, lhs)
    lhs_string, variables = lhs_compiler.compile()
    rhs_compiler = RHSCompiler(name, rhs, variables)
    rhs_string = rhs_compiler.compile()

    return os.linesep.join(
        (f'(defrule {name}',
         lhs_string,
         '  =>',
         rhs_string,
         ')'))


class LHSCompiler(visitors.Transformer):
    def __init__(self, module: ModuleType, name: str, tree: lark.Tree):
        super().__init__()

        self._module_name = module.__name__
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
            raise SyntaxError(
                f"Rule: {self._name} - Variable <{var}> already defined")

        self._variables.append(var)

        variable = Variable(f'?{var}')

        if isinstance(value, Fact):
            return Bind(f'{variable} {operator} {value}')
        elif isinstance(value, Variable):
            return Bind(f'({value} {variable})')
        elif isinstance(value, Comparison):
            comp = value.comparator
            left = value.left
            right = value.right

            return Bind(f'({left} {variable}&:({comp} {variable} {right}))')
        else:
            SyntaxError(f"Rule: {self._name} - Invalid Syntax: {node}")

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

        args = ', '.join(arguments).replace('"', '\'')
        function = f'{funcname}({args})'
        slot, variable = find_function_slot(funcname, arguments, self._variables)

        return Function(function, self._module_name, slot, variable)

    def python__getattr(self, node):
        name, attr = node
        string = f'{name}.{attr}'

        if isinstance(name, Function):
            return Function(string, self._module_name, slot=name.slot, variable=name.variable)

        return GetAttr(string, name, attr)

    def python__arguments(self, node):
        return node

    def python__comparison(self, node):
        left, comparator, right = node

        if is_constant_constraint(left, comparator, right, self._variables):
            string = f'({left} {right})'
        elif is_clips_constraint(left, comparator, right, self._variables):
            lslot, lvar, left = find_comparison_slot(left, self._variables)
            rslot, rvar, right = find_comparison_slot(right, self._variables)
            slot = lslot if lslot is not None else rslot
            variable = lvar if lvar is not None else rvar

            string = f'({slot} {variable}&:({comparator} {left} {right}))'
        else:
            lslot, lvar, left = find_comparison_slot(left, self._variables)
            rslot, rvar, right = find_comparison_slot(right, self._variables)
            slot = lslot if lslot is not None else rslot
            variable = lvar if lvar is not None else rvar

            string = (f'({slot} {variable}&:' +
                      f'(py-compare {comparator} {left} {right}))')

        return Comparison(string, comparator, left, right)

    def python__comp_op(self, node):
        return Comparator(COMPARATOR_MAP[str(node[0])])

    def python__var(self, node):
        return Variable(str(node[0]))

    def python__string(self, node):
        string = str(node[0]).strip('"').strip("'")

        return String(f'"{string}"')

    def python__number(self, node):
        return Number(str(node[0]))


class RHSCompiler(visitors.Transformer):
    def __init__(self, name: str, tree: lark.Tree, variables: list):
        super().__init__()

        self._name = name
        self._tree = tree
        self._variables = set(variables)

    def compile(self):
        rhs = self.transform(self._tree)
        variables = ' '.join(f'?{v}' for v in self._variables)
        code = textwrap.dedent(reconstructor.reconstruct_code(rhs))

        ACTION_MAP[self._name] = Action(compile(code, self._name, 'exec'),
                                        self._variables)

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
    def __new__(cls, value, name, attr):
        cls.root = name.split('.')[0]
        cls.name = name
        cls.attr = attr

        return super().__new__(cls, value)


class Function(str):
    def __new__(cls, value, module, slot=None, variable=None):
        obj = super().__new__(cls, value)
        obj.module = module
        obj.slot = slot
        obj.variable = variable

        return obj

    def clips_string(self, slot=True) -> str:
        string = f'py-eval {self.module} "{self}"'

        if self.slot is not None:
            if slot:
                return (f'({self.slot} {self.variable}&:' +
                        f'({string} {self.slot} {self.variable}))')
            else:
                return f'({string} {self.slot} {self.variable})'

        return f'({string} nil nil)'


class Comparison(str):
    def __new__(cls, value, comparator, left, right):
        obj = super().__new__(cls, value)
        obj.comparator = comparator
        obj.left = left
        obj.right = right

        return obj


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


class Variable(str):
    def __new__(cls, value):
        return super().__new__(cls, value)


class Action(NamedTuple):
    code: 'code'
    varnames: list


def is_slot(name: str, variables: list) -> bool:
    return isinstance(name, Variable) and name not in variables


def is_slot_method(function: str, variables: list) -> bool:
    return (isinstance(function, GetAttr) and
            function.root not in sys.modules.keys() and
            function.root not in variables)


def is_constant_constraint(left: str, cmp: str, right: str, vrs: list) -> bool:
    return (cmp == '==' and
            any(is_slot(c, vrs) for c in (left, right)) and
            any(isinstance(c, (String, Number)) for c in (left, right)))


def is_clips_constraint(left: str, cmp: str, right: str, vrs: list) -> bool:
    return any(isinstance(c, (String, Number)) for c in (left, right))


def find_function_slot(function: str, arguments: list, variables: list) -> tuple:
    if is_slot_method(function, variables):
        return function.root, f'?{random_name(6)}'

    for argument in arguments:
        if is_slot_method(argument, variables):
            return argument.root, f'?{random_name(6)}'
        if is_slot(argument, variables):
            return argument, f'?{random_name(6)}'
        if isinstance(argument, Function):
            return argument.slot, argument.variable
    else:
        return None, None


def find_comparison_slot(name: str, variables) -> tuple:
    if is_slot(name, variables):
        variable = f'?{random_name(6)}'

        return name, variable, variable
    if isinstance(name, Function):
        variable = name.variable if name.variable is not None else f'?{random_name(6)}'

        return name.slot, variable, name.clips_string(slot=False)

    return None, None, name


def random_name(length: int) -> str:
    return ''.join(random.choice(string.ascii_lowercase) for _ in range(length))


ACTION_MAP = {}
COMPARATOR_MAP = {'<': '<',
                  '<=': '<=',
                  '>': '>',
                  '>=': '>=',
                  '==': '==',
                  '!=': '<>',
                  'is': 'eq'}
