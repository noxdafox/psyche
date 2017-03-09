import array

from collections import namedtuple
from string import ascii_lowercase, ascii_uppercase

# Parser
RuleSource = namedtuple('RuleSource', ('name', 'condition', 'action'))
ParsedRules = namedtuple('ParsedRules', ('file_name',
                                         'module_name',
                                         'python_source',
                                         'rules_source'))
# Compiler
RuleStatements = namedtuple('RuleStatements', ('alpha', 'beta'))

# Rules
RuleNodes = namedtuple('RuleNodes', ('alpha', 'beta'))
RuleNamespace = namedtuple('RuleNamespace', ('constants', 'module'))
RuleCode = namedtuple('RuleCode', ('assignments', 'nodes', 'action'))


def translate_facts(statement: str, facts: dict) -> str:
    """Given a statement string, it translates all the encoded facts."""
    for fact_class, fact_hash in facts.items():
        statement = statement.replace(
            fact_hash, '.'.join((fact_class.__module__, fact_class.__name__)))

    return statement


def encode_number(number: int) -> str:
    if not number:
        return ALPHABET[0]
    if number < 0:
        return SIGN_CHARACTER + encode_number(abs(number))

    string = array.array('u')

    while number:
        number, modulo = divmod(number, BASE)
        string.append(ALPHABET[modulo])

    return ''.join(reversed(string))


def decode_number(string: str) -> int:
    if string[0] == SIGN_CHARACTER:
        return -decode_number(string[1:])

    number = 0

    for character in string:
        number = number * BASE + ALPHABET_REVERSE[character]

    return number


ALPHABET = ascii_lowercase + ascii_uppercase
ALPHABET_REVERSE = dict((c, i) for (i, c) in enumerate(ALPHABET))
BASE = len(ALPHABET)
SIGN_CHARACTER = '_'
