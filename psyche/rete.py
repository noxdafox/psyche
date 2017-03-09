from types import ModuleType
from functools import lru_cache
from collections import defaultdict, namedtuple

from psyche.facts import Fact
from psyche.compiler import RuleCompiler
from psyche.common import RuleStatements, translate_facts


WME = namedtuple('wme', ('fact', 'globals', 'locals'))


class ReteNode:
    __slots__ = 'statement'
    CACHE_SIZE = 64

    def __init__(self, statement):
        self.statement = statement

    def __str__(self):
        return str(self.statement)

    def __hash__(self):
        return hash(self.statement)

    def __eq__(self, element):
        return hash(self.statement) == hash(element)

    def visit(self, wme: WME) -> bool:
        if self.statement.mode == 'exec':
            self.execute(wme)

            return True
        else:
            return self.evaluate(wme)

    @lru_cache(maxsize=CACHE_SIZE)
    def evaluate(self, wme: WME) -> bool:
        """Evaluate the expression and returns its value."""
        return eval(self.statement.code, wme.globals, wme.locals)

    @lru_cache(maxsize=CACHE_SIZE)
    def execute(self, wme: WME) -> bool:
        """Execute the code and stores the results in the WME."""
        exec(self.statement.code, wme.globals, wme.locals)


class Rete:
    __slots__ = 'facts', 'alpha_nodes', 'alpha_network', 'beta_network'

    def __init__(self):
        self.facts = {}  # FactClass: FactHash
        self.alpha_nodes = {}  # statement: ReteNode
        self.alpha_network = defaultdict(set)  # Fact: ReteNode

    def load(self, rules: list, module: ModuleType):
        for rule in rules:
            compiler = RuleCompiler(rule, module)
            statements = compiler.compile_condition()

            self.facts.update(compiler.facts)
            self._load_alpha_nodes(statements)

    def _load_alpha_nodes(self, rule_statements: RuleStatements):
        nodes = self.alpha_nodes
        network = self.alpha_network

        for fact, statements in rule_statements.alpha.items():
            node = nodes.setdefault(statements[0], ReteNode(statements[0]))
            network[fact].add(node)

            for statement in statements[1:]:
                stmt = nodes.setdefault(statement, ReteNode(statement))
                network[node].add(stmt)
                node = stmt

    def insert(self, fact: Fact):
        for node in self.alpha_network[fact]:
            wme = WME(fact, {}, {})

            self._insert(node, wme)

    def _insert(self, root: ReteNode, wme: WME):
        if not root.evaluate(wme):
            return

        for node in self.alpha_network[root]:
            self._insert(node, wme)

    def visit(self):
        """Depth-first rete visitor.

        Yields each node and its depth in the network.

        """
        for fact in [f for f in self.alpha_network if f in self.facts]:
            yield '.'.join((fact.__module__, fact.__name__)), 0

            for node in self.alpha_network[fact]:
                yield from self._visit(node, 0)

    def _visit(self, root: ReteNode, depth: int):
        depth += 1

        yield translate_facts(str(root), self.facts), depth

        for node in self.alpha_network[root]:
            yield from self._visit(node, depth)
