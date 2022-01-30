from pathlib import Path
from tempfile import NamedTemporaryFile

import clips

from psyche import facts
from psyche import parser
from psyche import compiler


class Environment:
    def __init__(self):
        self._env = clips.Environment()
        self._env.define_function(python_action)

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
            clips_rule = compiler.compile_rule(rule.name, rule.lhs, rule.rhs)
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
    glbls = {k: v for k, v in zip(action.varnames, args)}

    exec(action.code, glbls)
