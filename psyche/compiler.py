import ast
import sys
import inspect
import importlib
from types import ModuleType
from functools import reduce
from itertools import accumulate, chain
from tempfile import NamedTemporaryFile

from psyche.facts import Fact
from psyche.common import RuleSource


def import_source_code(source, module_name):
    with NamedTemporaryFile(buffering=0, suffix='.py') as module_file:
        module_file.write(source)

        spec = importlib.util.spec_from_file_location(
            module_name, module_file.name)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules[module_name] = module

        return module


class RuleCompiler(ast.NodeVisitor):
    def __init__(self, rule: RuleSource, module: ModuleType):
        self.rule = rule
        self.module = module

        self._facts = set()    # FactClass
        self._names = {}       # varname: Name | Attribute.Name
        self._variables = {}   # varname: Call( FactClass )

    def compile_condition(self):
        condition = ast.parse(
            self.rule.condition, filename='<%s>' % self.rule.name, mode='exec')

        self.visit(condition)

    def visit_Assign(self, node: ast.AST) -> ast.AST:
        facts = self.node_facts(node)
        if not facts or len(facts) > 1:
            syntax_error("Assignment must have one fact", node, self.rule)

        if isinstance(node.value, (ast.Attribute, ast.Name)):
            self._names.update({t.id: facts[0] for t in node.targets})
        else:
            # TODO Alpha Namespace Node
            NamespaceStatement(translate_facts(node, self._names, self.module))
            self._variables.update({t.id: facts[0] for t in node.targets})

        # TODO: AND Beta node

    def visit_Expr(self, node: ast.AST):
        facts = self.node_facts(node)

        if not facts:
            syntax_error("No Fact found in Expression", node, self.rule)
        elif len(facts) == 1:
            # TODO Alpha Node
            Statement(translate_facts(node, self._names, self.module))
        else:
            # TODO Beta Node
            Statement(translate_facts(node, self._names, self.module))

        # TODO: AND Beta node

    def node_facts(self, node: ast.AST) -> tuple:
        """Return a list of FactClass referred within the statement."""
        names = tuple(node_names(node))

        facts = [name_to_fact(n, self.module) for n in names]
        facts += [self._names.get(c) for n in names for c in n.split('.')]
        facts += [self._variables.get(c) for n in names for c in n.split('.')]
        facts = tuple(set(filter(None, facts)))

        self._facts.update(facts)

        return facts


class Statement:
    __slots__ = '_ast', '_code'

    def __init__(self, syntax_tree: ast.AST):
        self._code = None
        self._ast = syntax_tree

    def __str__(self):
        return ast.dump(self._ast)

    def __hash__(self):
        return hash(str(self))

    def __eq__(self, element):
        return hash(self) == hash(element)

    def evaluate(self, global_namespace, local_namespace):
        if self._code is None:
            self._code = compile(self._ast, filename='<statement>', mode='eval')

        return eval(self._code, global_namespace, local_namespace)


class NamespaceStatement(Statement):
    __slots__ = '_ast', '_code'

    def evaluate(self, global_namespace, local_namespace):
        if self._code is None:
            self._code = compile(self._ast, filename='<statement>', mode='exec')

        exec(self._code, global_namespace, local_namespace)

        return True


def name_to_fact(name: str, module: ModuleType) -> Fact:
    """Return the Fact Class if name is a fact, None otherwise."""
    dotjoin = lambda parent, child: parent + '.' + child

    for reference in (n for n in accumulate(name.split('.'), dotjoin)):
        try:
            fact = reduce(getattr, reference.split('.'), module)
        except AttributeError:
            return None

        if inspect.isclass(fact) and issubclass(fact, Fact):
            return fact


def node_names(node: ast.AST) -> str:
    """Inspect a node yielding all qualified names."""
    if isinstance(node, ast.Name):
        yield node.id
    elif isinstance(node, ast.Attribute):
        yield next(node_names(node.value)) + '.' + node.attr
    else:
        for _, value in ast.iter_fields(node):
            if isinstance(value, ast.AST):
                yield from node_names(value)
            elif isinstance(value, list):
                yield from chain.from_iterable(
                    node_names(e) for e in value if isinstance(e, ast.AST))


def translate_facts(node: ast.AST, names: dict, module: ModuleType) -> ast.AST:
    """Translate facts referred within a node with __Fact_<Class Name>."""
    if isinstance(node, ast.Name):
        return translate_fact(node, node.id, names, module)
    elif isinstance(node, ast.Attribute):
        node.value = translate_facts(node.value, names, module)
        return translate_fact(node, node_names(node), names, module)
    else:
        for field, value in ast.iter_fields(node):
            if isinstance(value, ast.AST):
                setattr(node, field, translate_facts(value, names, module))
            elif isinstance(value, list):
                value[:] = [translate_facts(v, names, module)
                            for v in value if isinstance(v, ast.AST)]

        return node


def translate_fact(node: ast.AST, name: str,
                   names: dict, module: ModuleType) -> ast.AST:
    if name in names:
        new_name = '__Fact_' + names[name].__name__

        return ast.copy_location(ast.Name(id=new_name, ctx=node.ctx), node)

    fact = name_to_fact(next(node_names(node)), module)
    if fact is not None:
        new_name = '__Fact_' + fact.__name__

        return ast.copy_location(ast.Name(id=new_name, ctx=node.ctx), node)

    return node



def syntax_error(message: str, node: ast.AST, rule: RuleSource):
    error = SyntaxError(message)
    error.filename = rule.name
    error.lineno = node.lineno
    error.offset = node.col_offset
    error.text = rule.condition.splitlines()[node.lineno - 1]

    raise error
