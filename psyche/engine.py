from psyche.rete import Rete
from psyche.facts import Fact
from psyche.parser import parse_rules_file
from psyche.compiler import import_source_code


class Engine:
    __slots__ = '_facts', '_rete', '_rules'

    def __init__(self):
        self._facts = []
        self._rules = []
        self._rete = Rete()

    def load_rules(self, path):
        parsed = parse_rules_file(path)
        module = import_source_code(parsed.python_source, parsed.module_name)

        self._rules.extend([r for r in parsed.rules_source])
        self._rete.load(parsed.rules_source, module)

        return module

    def assert_fact(self, fact):
        if not isinstance(fact, Fact):
            raise TypeError("Fact expected got %s" % type(fact))

        self._facts.append(fact)
        self._rete.insert(fact)

    def update_fact(self, fact):
        pass

    def retract_fact(self, fact):
        pass

    def run(self, limit):
        pass

    def visit_rete(self):
        for node, depth in self._rete.visit():
            yield '\t' * depth + str(node)
