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
    __slots__ = 'rule', 'module', '_facts'

    def __init__(self, rule: RuleSource, module: ModuleType):
        self.rule = rule
        self.module = module

        self._facts = {}

    @property
    def facts(self) -> dict:
        return {v: k for k, v in self._facts.items()}

    def compile_condition(self) -> RuleStatements:
        """Compiles the rule condition."""
        condition = ast.parse(
            self.rule.condition, filename='<%s>' % self.rule.name, mode='exec')

        translator = RulesTranslator(self.module, self._facts)
        translator.translate(condition)

        visitor = ConditionVisitor(self.module, self.rule, self._facts)
        visitor.visit(condition)

        return RuleStatements(visitor.alpha, visitor.beta)

    def compile_action(self):
        pass


class RulesTranslator(ast.NodeTransformer):
    """Visit a code tree translating all Fact names and assignment targets
    with unique hashes.

    Expand all facts assignments.
    Translate all fact types with unique hashes.
    Translate all complex assignments targets with unique hashes.

    """
    __slots__ = 'facts', '_vars', '_name', '_names', '_module'

    def __init__(self, module: ModuleType, facts: dict):
        self.facts = facts     # FactHash: FactClass
        self._vars = {}        # varname: hash(assignment)
        self._names = {}       # varname: Name | Attribute.Name
        self._name = None
        self._module = module
        self.translate = self.visit

    def visit_Assign(self, node: ast.AST) -> ast.AST:
        if isinstance(node.value, (ast.Attribute, ast.Name)):
            value = self.visit(node.value)
            self._names.update({t.id: value for t in node.targets})
        else:
            self._vars.update(hash_assignment(node))
            return self.generic_visit(node)

    def visit_Attribute(self, node: ast.AST) -> ast.AST:
        node.value = self.visit(node.value)
        self._name += '.' + node.attr

        return self.hash_fact(node)

    def visit_Name(self, node: ast.AST) -> ast.AST:
        self._name = node.id

        if node.id in self._names:
            return ast.copy_location(self._names[node.id], node)
        if node.id in self._vars:
            return ast.copy_location(
                ast.Name(id=self._vars[node.id], ctx=node.ctx), node)
        else:
            return self.hash_fact(node)

    def hash_fact(self, node: ast.AST) -> ast.AST:
        fact = name_to_fact(self._name, self._module)

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

        self.alpha = defaultdict(list)  # FactClass: Statement
        self.beta = []

        self._variables = {}  # VarHash: FactClass

    def visit_Assign(self, node: ast.AST):
        facts = self.node_facts(node)

        if not facts:
            raise_syntax_error("No Fact found in Assignment", node, self.rule)
        elif len(facts) > 1:
            raise_syntax_error("Max one Fact per assignment", node, self.rule)
        else:
            self.alpha[facts[0]].append(Statement(node))
            self._variables.update({t.id: facts[0] for t in node.targets})

    def visit_Expr(self, node: ast.AST):
        facts = self.node_facts(node)

        if not facts:
            raise_syntax_error("No Fact found in Expression", node, self.rule)
        elif len(facts) == 1:
            self.alpha[facts[0]].append(Statement(node))
        else:
            self.beta.append((facts, Statement(node)))

    def node_facts(self, node: ast.AST) -> tuple:
        """Return a list of FactClass referred within the statement."""
        names = tuple(n.id for n in ast.walk(node) if isinstance(n, ast.Name))

        facts = [self.facts[n] for n in names if n in self.facts]
        facts += [self._variables[n] for n in names if n in self._variables]

        return tuple(set(facts))


def name_to_fact(name: str, module: ModuleType) -> Fact:
    """Returns the Fact Class if name is a fact, None otherwise."""
    dotjoin = lambda parent, child: parent + '.' + child

    for reference in (n for n in accumulate(name.split('.'), dotjoin)):
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
    error.text = rule.condition.splitlines()[node.lineno - 1]

    raise error
