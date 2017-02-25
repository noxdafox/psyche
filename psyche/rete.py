from types import ModuleType
from functools import lru_cache
from collections import defaultdict, namedtuple

from psyche.facts import Fact
from psyche.common import Statements
from psyche.compiler import RuleCompiler


CACHE_SIZE = 64
WME = namedtuple('wme', ('fact', 'globals', 'locals'))


class Rete:
    __slots__ = 'facts', 'alpha_nodes', 'alpha_network', 'beta_network'

    def __init__(self):
        self.facts = {}  # FactClass: FactHash
        self.alpha_nodes = {}  # ReteNode: ReteNode
        self.alpha_network = {}  # Fact: NamespaceNode: ReteNode

    def load(self, rules: list, module: ModuleType):
        for rule in rules:
            compiler = RuleCompiler(rule, module)
            statements = compiler.compile_condition()

            self.facts.update(compiler.facts)
            self._load_alpha_nodes(statements, module)

    def _load_alpha_nodes(self, statements: Statements, module: ModuleType):
        namespace = NamespaceNode(statements.constants, module)

        for fact, stmts in statements.alpha.items():
            self.alpha_network.setdefault(fact, [])
            self.alpha_network[fact].append(namespace)

            node = self.alpha_nodes.setdefault(stmts[0], ReteNode(stmts[0]))

            self.alpha_network.setdefault(namespace, set())
            self.alpha_network[namespace].add(node)

            for stmt in stmts[1:]:
                statement = self.alpha_nodes.setdefault(stmt, ReteNode(stmt))
                self.alpha_network.setdefault(node, set())
                self.alpha_network[node].add(statement)
                node = statement

    def insert(self, fact):
        for namespace_node in self.alpha_network[fact]:
            wme = WME(fact, {}, {})

            self._insert(namespace_node, wme)

    def _insert(self, root, wme):
        if not root.evaluate(wme):
            return

        for node in self.alpha_network[root]:
            self._insert(node, wme)

    def visit(self):
        """Depth-first rete visitor.

        Yields each node and its depth in the network.

        """
        for fact in (f for f in self.alpha_network if f in self.facts):
            yield '.'.join((fact.__module__, fact.__name__)), 0

            for namespace_node in self.alpha_network[fact]:
                for node in self.alpha_network[namespace_node]:
                    yield from self._visit(node, 0)

    def _visit(self, root, depth):
        depth += 1

        yield str(root), depth

        for node in self.alpha_network[root]:
            yield from self._visit(node, depth)


class ReteNode:
    __slots__ = 'statement'

    def __init__(self, statement):
        self.statement = statement

    def __str__(self):
        return str(self.statement)

    def __hash__(self):
        return hash(self.statement)

    def __eq__(self, element):
        return hash(self.statement) == hash(element)

    def visit(self, wme):
        if self.statement.mode == 'exec':
            self.execute(wme)

            return True
        else:
            return self.evaluate(wme)

    @lru_cache(maxsize=CACHE_SIZE)
    def evaluate(self, wme):
        """Evaluate the expression and returns its value."""
        return eval(self.statement.code, wme.globals, wme.locals)

    @lru_cache(maxsize=CACHE_SIZE)
    def execute(self, wme):
        """Execute the code and stores the results in the WME."""
        exec(self.statement.code, wme.globals, wme.locals)


class NamespaceNode(ReteNode):
    __slots__ = 'globals'

    def __init__(self, constants, module):
        super().__init__(constants)
        self.globals = dir(module)

    def visit(self, wme):
        wme.globals.update(self.globals)
        self.execute(wme)
        return True
