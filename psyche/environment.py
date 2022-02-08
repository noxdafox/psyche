import sys
import builtins

from pathlib import Path
from tempfile import NamedTemporaryFile

import clips

from psyche import facts
from psyche import parser
from psyche import compiler


class Environment:
    def __init__(self):
        self._env = clips.Environment()
        self._env.define_function(python_action, name='py-action')
        self._env.define_function(python_method, name='py-method')
        self._env.define_function(python_function, name='py-function')
        self._env.define_function(python_compare, name='py-compare')
        self._env.define_function(python_eval, name='py-eval')

    def load(self, path: Path):
        with path.open() as file:
            return self.loads(file.read(), module_name=path.name)

    def loads(self, string: str, module_name: str = None):
        code, rules = parser.parse_rules_string(string)

        if module_name is None:
            with NamedTemporaryFile() as tmpfile:
                module_name = Path(tmpfile.name).name

        module = compiler.import_source_code(code, module_name)
        deftemplates = facts.compile_facts(module)
        for deftemplate in deftemplates:
            self._env.build(deftemplate)

        for rule in rules:
            clips_rule = compiler.compile_rule(
                module, rule.name, rule.lhs, rule.rhs)
            print(clips_rule)
            self._env.build(clips_rule)

        return module

    def insert_fact(self, fact: facts.Fact) -> facts.Fact:
        cls = fact.__class__
        template = self._env.find_template(cls.__name__)
        slots = {n: getattr(fact, n) for n in cls.__annotations__}

        template.assert_fact(**slots)

        return fact

    def run(self):
        self._env.run()


def python_action(name, *args):
    action = compiler.ACTION_MAP[name]
    args = [facts.ClipsFact(a)
            if isinstance(a, clips.TemplateFact) else a
            for a in args]
    glbls = {k: v for k, v in zip(action.varnames, args)}

    exec(action.code, glbls)


def python_eval(modname: str, code: str, slot: str, value: type) -> type:
    glbls = sys.modules[modname].__dict__

    if slot is not None:
        glbls[slot] = value
        return eval(code, glbls)
    else:
        return eval(code, glbls)


def python_function(modname: str, funcname: str, *args: list):
    if hasattr(builtins, funcname):
        function = getattr(builtins, funcname)
    else:
        function = find_function('.'.join((modname, funcname)))

    return function(*args)


def python_method(name, method: str, *args: list):
    function = getattr(name, method)

    return bool(function(*args))


def python_compare(comparator: str, left: type, right: type) -> bool:
    return COMPARATOR_MAP[comparator](left, right)


def find_function(string: str) -> callable:
    """Resolve a root.stem.stem.stem returning the actual function."""
    root, *stem = string.split('.')
    function = sys.modules[root]

    for element in stem:
        function = getattr(function, element)

    return function


COMPARATOR_MAP = {'<': lambda l, r: l < r,
                  '<=': lambda l, r: l <= r,
                  '>': lambda l, r: l > r,
                  '>=': lambda l, r: l >= r,
                  '==': lambda l, r: l == r,
                  '!=': lambda l, r: l != r,
                  'eq': lambda l, r: l is r}
