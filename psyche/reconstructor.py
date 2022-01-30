import os

from lark import lark
from lark import indenter
from lark import reconstruct


def reconstruct_code(tree: lark.Tree) -> str:
    with open(GRAMMAR_PATH) as grammar_file:
        parser = lark.Lark(grammar_file,
                           parser='lalr',
                           start=['file_input'],
                           maybe_placeholders=False,
                           postlex=indenter.PythonIndenter())

    reconstructor = reconstruct.Reconstructor(parser, TERMINAL_SUB)

    return reconstructor.reconstruct(tree, postproc)


def postproc(items):
    """TODO: figure out and rework this."""
    stack = [os.linesep]
    actions = []
    last_was_whitespace = True

    for item in items:
        if isinstance(item, lark.Token) and item.type == 'SPECIAL':
            actions.append(item.value)
        else:
            if actions:
                assert actions[0] == '_NEWLINE' and '_NEWLINE' not in actions[1:], actions

                for a in actions[1:]:
                    if a == '_INDENT':
                        stack.append(stack[-1] + ' ' * 4)
                    else:
                        assert a == '_DEDENT'
                        stack.pop()
                actions.clear()
                yield stack[-1]
                last_was_whitespace = True
            if not last_was_whitespace:
                if item[0] in SPACE_BEFORE:
                    yield ' '
            yield item
            last_was_whitespace = item[-1].isspace()
            if not last_was_whitespace:
                if item[-1] in SPACE_AFTER:
                    yield ' '
                    last_was_whitespace = True

    yield os.linesep


GRAMMAR_PATH = '/home/noxdafox/development/psyche/grammar/rules.lark'
TERMINAL_SUB = {'_NEWLINE': lambda s: lark.Token('SPECIAL', s.name),
                '_DEDENT': lambda s: lark.Token('SPECIAL', s.name),
                '_INDENT': lambda s: lark.Token('SPECIAL', s.name)}
SPACE_AFTER = set(',+-*/~@<>="|:')
SPACE_BEFORE = (SPACE_AFTER - set(',:')) | set('\'')
