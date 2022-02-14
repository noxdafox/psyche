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
        self._facts = {}
        self._env = clips.Environment()
        self._env.define_function(python_action, name='py-action')
        self._env.define_function(python_method, name='py-method')
        self._env.define_function(python_function, name='py-function')
        self._env.define_function(python_eval, name='py-eval')

    @property
    def facts(self):
        return self._facts.values()

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
                self, module_name, rule.name, rule.lhs, rule.rhs)
            # print(clips_rule)
            self._env.build(clips_rule)

        return module

    def insert_fact(self, fact):
        cls = fact.__class__
        template = self._env.find_template(cls.__name__)
        slots = {n: getattr(fact, n) for n in cls.__annotations__}

        fact_ptr = template.assert_fact(**slots)
        fact._env = self
        fact._fact = fact_ptr
        self._facts[fact_ptr] = fact

        return fact

    def run(self):
        self._env.run()

    def reset(self):
        self._env.reset()
        self._facts = {}


def insert_fact(fact):
    return PSYCHE.insert_fact(fact)


def python_action(name, *args):
    action = compiler.ACTION_MAP[name]
    args = [action.env._facts[a]
            if isinstance(a, clips.TemplateFact)
            else a
            for a in args]
    glbls = action.module.__dict__ | dict(zip(action.varnames, args))

    # Globals are set when the function is defined, not when it's called
    global PSYCHE
    PSYCHE = action.env

    exec(action.code, glbls)


def python_eval(modname: str, code: str, *varmap: list) -> type:
    glbls = sys.modules[modname].__dict__

    for name, value in grouper(varmap, 2):
        glbls[name] = value

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


def find_function(string: str) -> callable:
    """Resolve a root.stem.stem.stem returning the actual function."""
    root, *stem = string.split('.')
    function = sys.modules[root]

    for element in stem:
        function = getattr(function, element)

    return function


def grouper(iterable, size):
    """Collect data into non-overlapping fixed-length chunks or blocks."""
    args = [iter(iterable)] * size

    return zip(*args)


PSYCHE = None
