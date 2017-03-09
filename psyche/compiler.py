import ast
import sys
import inspect
import importlib
from types import ModuleType
from functools import reduce
from itertools import accumulate
from collections import defaultdict
from tempfile import NamedTemporaryFile

from psyche.facts import Fact
from psyche.common import encode_number, RuleStatements, RuleSource


def import_source_code(source, module_name):
    with NamedTemporaryFile(buffering=0, suffix='.py') as module_file:
        module_file.write(source)

        spec = importlib.util.spec_from_file_location(
            module_name, module_file.name)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules[module_name] = module

        return module


class Statement:
    __slots__ = 'ast', 'mode', '_code'

    def __init__(self, syntax_tree):
        self._code = None
        self.ast = syntax_tree
        self.mode = 'exec' if isinstance(self.ast, ast.Assign) else 'eval'

    def __str__(self):
        return ast.dump(self.ast)

    def __hash__(self):
        return hash(ast.dump(self.ast))

    def __eq__(self, element):
        return hash(self) == hash(element)

    @property
    def code(self):
        if self._code is None:
            if self.mode == 'exec':
                source = ast.Module([self.ast])
            else:
                source = ast.Expression(self.ast.body[0].value)

            self._code = compile(source, filename='<alpha>', mode=self.mode)

        return self._code


class RuleCompiler:
    __slots__ = 'rule', 'module', 'translator'

    def __init__(self, rule: RuleSource, module: ModuleType):
        self.rule = rule
        self.module = module
        self.translator = RulesTranslator(module)

    @property
    def facts(self) -> dict:
        return {v: k for k, v in self.translator.facts.items()}

    def compile_condition(self) -> RuleStatements:
        """Compiles the rule condition."""
        condition = ast.parse(
            self.rule.condition, filename='<%s>' % self.rule.name, mode='exec')

        self.translator.translate(condition)

        visitor = ConditionVisitor(self.module, self.rule,
                                   self.translator.facts)
        visitor.visit(condition)

        return RuleStatements(visitor.alpha, visitor.beta)

    def compile_action(self):
        pass


class RulesTranslator(ast.NodeTransformer):
    """Visits a code tree translating all Fact names and assignment targets
    with unique hashes.

    """
    __slots__ = 'facts', '_name', '_module', '_variables' '_attribute'

    def __init__(self, module: ModuleType):
        self.facts = {}  # FactHash: FactClass
        self._name = None
        self._variables = {}
        self._module = module
        self._attribute = False
        self.translate = self.visit

    def visit_Assign(self, node: ast.AST) -> ast.AST:
        self._variables.update(hash_assignment(node))
        self.generic_visit(node)
        return node

    def visit_Attribute(self, node: ast.AST) -> ast.AST:
        self._attribute = True
        node.value = self.visit(node.value)
        self._name += '.' + node.attr

        return self.translate_fact(node)

    def visit_Name(self, node: ast.AST) -> ast.AST:
        self._name = node.id
        self._attribute = False

        if node.id in self._variables:
            return ast.copy_location(
                ast.Name(id=self._variables[node.id], ctx=node.ctx), node)
        else:
            return self.translate_fact(node)

    def translate_fact(self, node: ast.AST) -> ast.AST:
        fact = modulefact(self._module, self._name)

        if fact is not None:
            fact_hash = encode_number(hash(fact))
            node = ast.copy_location(ast.Name(id=fact_hash, ctx=node.ctx), node)

            self.facts[fact_hash] = fact

        return node


class ConditionVisitor(ast.NodeVisitor):
    __slots__ = 'rule', 'facts', 'module', 'alpha', 'beta', '_assignments'

    def __init__(self, module: ModuleType, rule: RuleSource, facts: dict):
        self.rule = rule
        self.facts = facts  # FactHash: FactClass
        self.module = module

        self.alpha = defaultdict(list)
        self.beta = []

        self._assignments = {}  # VarHash: FactClass

    def visit_Assign(self, node):
        visitor = NamesVisitor()
        visitor.visit(node.value)

        facts = [self.facts[n] for n in visitor.names if n in self.facts]
        assignments = [n.split('.')[0] for n in visitor.names
                       if self.assignment(n)]

        if len(facts) > 1 or len(assignments) > 1 or facts and assignments:
            raise_syntax_error("Max one Fact per assignment", node, self.rule)

        if facts:
            fact = facts[0]

            self.alpha[fact].append(Statement(node))
            self._assignments.update({t.id: fact for t in node.targets})
        elif assignments:
            fact = self._assignments[assignments[0]]
            self.alpha[fact].append(Statement(node))
        else:
            raise_syntax_error("No Fact found in Assignment", node, self.rule)

    def visit_Expr(self, node):
        visitor = NamesVisitor()
        visitor.visit(node)

        facts = [self.facts[n] for n in visitor.names if n in self.facts]
        assignments = [n.split('.')[0] for n in visitor.names if
                       self.assignment(n)]
        variables = tuple(set(facts + assignments))

        if not variables:
            raise_syntax_error("No Fact found in Expression", node, self.rule)
        elif len(variables) == 1:
            self.alpha[variables[0]].append(Statement(node))
        elif len(variables) > 1:
            self.beta.append((variables, Statement(node)))

    def assignment(self, name):
        dotjoin = lambda parent, child: parent + '.' + child

        return any(n for n in accumulate(name.split('.'), dotjoin)
                   if n in self._assignments)


class NamesVisitor(ast.NodeVisitor):
    """Visits an assignment or an expression storing the names."""
    __slots__ = 'names', '_attribute'

    def __init__(self):
        self.names = set()
        self._attribute = False

    def visit_Attribute(self, node):
        if self._attribute:
            return self.visit(node.value) + '.' + node.attr
        else:
            self._attribute = True
            self.names.add(self.visit(node.value) + '.' + node.attr)

    def visit_Name(self, node):
        if self._attribute:
            self._attribute = False
            return node.id
        else:
            self.names.add(node.id)


def modulefact(module: ModuleType, name: str) -> Fact:
    """Returns the Fact Class if name is a fact, None otherwise."""
    dotjoin = lambda parent, child: parent + '.' + child

    for reference in [n for n in accumulate(name.split('.'), dotjoin)]:
        try:
            fact = reduce(getattr, reference.split('.'), module)
        except AttributeError:
            return None

        if inspect.isclass(fact) and issubclass(fact, Fact):
            return fact


def hash_assignment(assignment: ast.Assign) -> dict:
    """Generate unique hashes for the targets of a given Assignment.

    Returns a dictionary containing the target and the related hash.

    """
    value = hash(ast.dump(assignment.value))
    targets = tuple(set(name.id for node in assignment.targets
                        for name in ast.walk(node)
                        if isinstance(name, ast.Name)))

    return {targets[index]: encode_number(value + index)
            for index in range(len(targets))}


def raise_syntax_error(message: str, node: ast.AST, rule: RuleSource):
    error = SyntaxError(message)
    error.filename = rule.name
    error.lineno = node.lineno
    error.offset = node.col_offset
    error.text = rule.condition.splitlines()[node.lineno]

    raise error
