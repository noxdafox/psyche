from collections import namedtuple

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
