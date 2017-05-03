from types import ModuleType
from functools import lru_cache
from collections import defaultdict, namedtuple

from psyche.facts import Fact
from psyche.compiler import RuleCompiler
from psyche.common import RuleStatements


CACHE_SIZE = 64
<<<<<<< HEAD
WME = namedtuple('wme', ('fact', 'globals', 'locals'))


class ReteNode:
    __slots__ = 'statement'
=======
WME = namedtuple('WME', ('fact', 'globals', 'locals'))


class ReteNode:
    __slots__ = 'statement', 'children'
>>>>>>> 3cb06802ab65e159012cf8b8bfd5f557c2f03651

    def __init__(self, statement):
        self.children = set()
        self.statement = statement

    def __str__(self):
        return str(self.statement)

    def __hash__(self):
        return hash(self.statement)

    def __eq__(self, element):
        return hash(self.statement) == hash(element)

    def evaluate(self, wme: WME) -> bool:
        return self.statement.evaluate(wme.globals, wme.locals)


class AlphaNode(ReteNode):
    __slots__ = 'statement', 'children'

    def visit(self, wme: WME) -> bool:
        if self.evaluate(wme):
            for child in self.children:
                child.visit(wme)


class BetaNode(ReteNode):
    __slots__ = 'statement', 'children', 'parents'

    def __init__(self, statement, parent_nodes):
        super().__init__(statement)
        self.parents = {n: [] for n in parent_nodes}

    def visit(self, token: list, parent: ReteNode) -> bool:
        for node in self.parents:
            if node != parent:
                break

        for token in self.parents[node]:
            if self.evaluate(wme):
                for child in self.children:
                    child.visit(wme)
        else:
            self.parents[parent].append(wme)


class AndNode:

    def visit(self, wme: WME) -> bool:
        pass


class OrNode:
    def __init__(self):
        self.left = {}
        self.right = {}

    def visit(self, wme: WME) -> bool:
        pass


class Rete:
    __slots__ = 'facts', 'alpha_nodes', 'alpha_network', 'beta_network'

    def __init__(self):
        self.facts = {}  # FactClass: FactHash
        self.alpha_nodes = {}  # Statement: ReteNode
        self.alpha_network = defaultdict(set)  # Fact: ReteNode

    def load(self, rules: list, module: ModuleType):
        for rule in rules:
            compiler = RuleCompiler(rule, module)
            statements = compiler.compile_condition()

            # self.facts.update(compiler.facts)
            # self._load_alpha_nodes(statements)

    def _load_alpha_nodes(self, rule_statements: RuleStatements):
        nodes = self.alpha_nodes
        network = self.alpha_network

        for fact, statements in rule_statements.alpha.items():
            node = nodes.setdefault(statements[0], ReteNode(statements[0]))
            network[fact].add(node)

            for statement in statements[1:]:
                new_node = nodes.setdefault(statement, ReteNode(statement))
                network[node].add(new_node)
                node = new_node

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
        for fact in (f for f in self.alpha_network if f in self.facts):
            yield '.'.join((fact.__module__, fact.__name__)), 0

            for node in self.alpha_network[fact]:
                yield from self._visit(node, 0)

    def _visit(self, root: ReteNode, depth: int):
        depth += 1

        yield translate_facts(str(root), self.facts), depth

        for node in self.alpha_network[root]:
            yield from self._visit(node, depth)
