from typing import NamedTuple

from lark import lark
from lark import indenter
from lark import visitors

from psyche import reconstructor


def parse_rules_string(string: str) -> (str, list):
    with open(GRAMMAR_PATH) as grammar_file:
        parser = lark.Lark(grammar_file,
                           parser='lalr',
                           start=['file_input'],
                           maybe_placeholders=False,
                           postlex=indenter.PythonIndenter())

    tree = parser.parse(string)
    transformer = RulesTransformer(tree)
    tree, rules = transformer.filter_rules()
    code = reconstructor.reconstruct_code(tree)

    return code, rules


class RulesTransformer(visitors.Transformer):
    """Filter all `rule` statements from the code."""

    def __init__(self, tree: lark.Tree, visit_tokens: str = False):
        super().__init__(visit_tokens)

        self._rules = []
        self._tree = tree

    def filter_rules(self) -> list:
        """Return the given tree with all the rules set aside."""
        return self.transform(self._tree), self._rules

    def rule_stmt(self, rule: list) -> visitors.Discard:
        name, lhs, rhs = rule

        self._rules.append(Rule(name, lhs, rhs))

        return visitors.Discard


class Rule(NamedTuple):
    name: lark.Token
    lhs: lark.Tree
    rhs: lark.Tree


GRAMMAR_PATH = '/home/noxdafox/development/psyche/grammar/rules.lark'
