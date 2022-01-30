import os
import sys
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


def compile_rule(name, lhs: lark.Tree, rhs: lark.Tree):
    lhs_compiler = LHSCompiler(name, lhs)
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
    def __init__(self, name: str, tree: lark.Tree):
        super().__init__()

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
        return Constraints(' '.join(node))

    def python__comparison(self, node):
        left, comparator, right = node
        if comparator == 'eq':
            string = f'({left} {right})'
        else:
            string = f'({comparator} {left} {right})'

        return Comparison(string, comparator, left, right)

    def python__var(self, node):
        return Variable(str(node[0]))

    def python__string(self, node):
        string = str(node[0]).strip('"').strip("'")

        return String(f'"{string}"')

    def python__comp_op(self, node):
        return Comparator(COMPARATOR_MAP[str(node[0])])


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

        return f'  (python_action {self._name} {variables})'

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


class Comparison(str):
    def __new__(cls, value, comparator, left, right):
        cls.comparator = comparator
        cls.left = left
        cls.right = right

        return super().__new__(cls, value)


class Constraints(str):
    def __new__(cls, value):
        return super().__new__(cls, value)


class Fact(str):
    def __new__(cls, value):
        return super().__new__(cls, value)


class String(str):
    def __new__(cls, value):
        return super().__new__(cls, value)


class Variable(str):
    def __new__(cls, value):
        return super().__new__(cls, value)


class Action(NamedTuple):
    code: 'code'
    varnames: list


ACTION_MAP = {}
COMPARATOR_MAP = {'<': '<',
                  '<=': '<=',
                  '>': '>',
                  '>=': '>=',
                  '==': 'eq',
                  '!=': '<>',
                  'is': 'eq'}
