from pathlib import Path
from tokenize import tokenize, untokenize
from tokenize import NAME, INDENT, DEDENT, NEWLINE, COMMENT


from psyche.common import RuleSource, ParsedRules


def parse_rules_file(path: str) -> ParsedRules:
    """Parse a rule file."""
    rules = []
    source = []

    tokenizer = Tokenizer(path)

    for token in tokenizer:
        if token.type == NAME and token.string == 'rule':
            rules.append(parse_rule(tokenizer))
        else:
            source.append((token.type, token.string))

    return ParsedRules(
        tokenizer.file_name, tokenizer.module_name, untokenize(source), rules)


class Tokenizer:
    __slots__ = 'path', 'file', 'tokens'

    def __init__(self, path):
        self.path = Path(path)
        self.file = self.path.open('rb')
        self.tokens = tokenize(self.file.readline)

    def __iter__(self):
        return self

    def __next__(self):
        return next(self.tokens)

    @property
    def file_name(self):
        return self.path.name

    @property
    def module_name(self):
        return self.path.stem


def parse_rule(tokenizer):
    name = parse_rule_name(tokenizer)

    token = next(tokenizer)
    if token.type != INDENT:
        raise_syntax_error("Wrong indentation", token, tokenizer.file_name)

    for token in tokenizer:
        if token.type == NAME and token.string == 'condition':
            condition = parse_rule_logic(tokenizer)
        elif token.type == NAME and token.string == 'action':
            action = parse_rule_logic(tokenizer)
        elif token.type == COMMENT:
            continue
        elif token.type == DEDENT:
            break
        else:
            raise_syntax_error("Invalid syntax", token, tokenizer.file_name)

    return RuleSource(name, condition, action)


def parse_rule_name(tokenizer):
    token = next(tokenizer)
    if token.type != NAME:
        raise_syntax_error("Invalid syntax", token, tokenizer.file_name)

    rule_name = token.string

    colon_newline(tokenizer)

    return rule_name


def parse_rule_logic(tokenizer):
    tokens = []

    colon_newline(tokenizer)

    for token in tokenizer:
        if token.type == INDENT:
            break

    for token in tokenizer:
        if token.type == DEDENT:
            break
        else:
            tokens.append(token)

    return ''.join(uniq(t.line.lstrip() for t in tokens))


def colon_newline(tokenizer):
    token = next(tokenizer)
    if token.string != ':':
        raise_syntax_error("Invalid syntax", token, tokenizer.file_name)
    token = next(tokenizer)
    if token.type != NEWLINE:
        raise_syntax_error("Invalid syntax", token, tokenizer.file_name)


def raise_syntax_error(message, token, filename):
    error = SyntaxError(message)
    error.filename = filename
    error.lineno = token.start[0]
    error.offset = token.start[1]
    error.text = token.line

    raise error


def uniq(sequence):
    seq = set()
    add = seq.add
    return [e for e in sequence if not (e in seq or add(e))]
