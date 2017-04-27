import ast
import inspect
from types import ModuleType


class Fact:
    pass


def fact_lookup(module: ModuleType, node: (ast.Attribute, ast.Name)) -> Fact:
    """Returns the referenced Fact if found within the node."""
    reference = module

    for name in names_lookup(node):
        try:
            reference = getattr(reference, name)
        except AttributeError:
            return None

        if inspect.isclass(reference) and issubclass(reference, Fact):
            return reference


def translate_fact(module: ModuleType, node: (ast.Attribute, ast.Name), names: dict) -> ast.AST:
    if name in names and isinstance(names[name], Fact):
        new_name = '__Fact_' + names[name].__name__

        return ast.copy_location(ast.Name(id=new_name, ctx=node.ctx), node)

    fact = fact_lookup(next(names_lookup(node)), module)
    if fact is not None:
        new_name = '__Fact_' + fact.__name__

        return ast.copy_location(ast.Name(id=new_name, ctx=node.ctx), node)

    return node


def names_lookup(node: (ast.Attribute, ast.Name)) -> str:
    """Inspect a node yielding all qualified names."""
    if isinstance(node, ast.Name):
        yield node.id
    elif isinstance(node, ast.Attribute):
        yield from names_lookup(node.value)

        yield node.attr
