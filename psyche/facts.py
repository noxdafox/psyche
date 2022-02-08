import os

from typing import List
from types import ModuleType

import clips


class MetaFact(type):
    def __init__(cls, name, bases, dct):
        super(MetaFact, cls).__init__(name, bases, dct)

        cls.__init__ = cls.__class__.make_init()
        cls.__setattr__ = cls.__class__.make_setattr()

    @classmethod
    def make_init(cls):
        def initializer(self, **kwargs):
            for attr in self.__annotations__:
                self.__dict__[attr] = kwargs.get(attr, None)

        return initializer

    @classmethod
    def make_setattr(cls):
        def setter(self, name, *_):
            raise TypeError(f"Property {name} is immutable")

        return setter

    @classmethod
    def make_repr(cls):
        def repr(self):
            return f'<{self.__class__} object at {id(self)}>'

        return repr


class Fact(metaclass=MetaFact):
    pass


class ClipsFact:
    def __init__(self, fact: clips.TemplateFact):
        self._fact = fact

    def __getattr__(self, name: str):
        return self._fact[name]


def compile_facts(module: ModuleType) -> List[str]:
    return [compile_fact(f)
            for f in module.__dict__.values()
            if isinstance(f, type)
            and issubclass(f, Fact)
            and f.__module__ == module.__name__]


def compile_fact(fact: Fact) -> str:
    slots = os.linesep.join(
        SLOT.format(slot_name=n, slot_type=TYPE_MAP.get(t, 'EXTERNAL-ADDRESS'))
        for n, t in fact.__annotations__.items())

    return DEFTEMPLATE.format(name=fact.__name__, slots=slots)


DEFTEMPLATE = """(deftemplate {name}
{slots})
"""
SLOT = """  (slot {slot_name} (type {slot_type}))"""
TYPE_MAP = {str: 'STRING',
            int: 'INTEGER',
            float: 'FLOAT'}
