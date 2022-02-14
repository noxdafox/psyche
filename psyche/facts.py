import os

from typing import List
from types import ModuleType

import clips


class MetaFact(type):
    def __init__(cls, name, bases, dct):
        super(MetaFact, cls).__init__(name, bases, dct)

        cls.__init__ = cls.__class__.make_init()
        cls.__repr__ = cls.__class__.make_repr()
        cls.__getattr__ = cls.__class__.make_getattr()
        cls.__setattr__ = cls.__class__.make_setattr()

    @classmethod
    def make_init(cls):
        def initializer(self, **kwargs):
            for attr in self.__annotations__:
                self.__dict__[attr] = kwargs.get(attr, None)

        return initializer

    @classmethod
    def make_repr(cls):
        def rep(self):
            return f'<{self.__class__} object at {id(self)}>'

        return rep

    @classmethod
    def make_getattr(cls):
        def getter(self, name):
            if self.__dict__['_fact'] is not None:
                return self.__dict__['_fact'][name]

            return self.__dict__[name]

        return getter

    @classmethod
    def make_setattr(cls):
        def setter(self, name, value):
            if name in self.__annotations__:
                raise TypeError(f"Property {name} is immutable")

            self.__dict__[name] = value

        return setter


class Fact(metaclass=MetaFact):
    _env: 'Environment'
    _fact: clips.TemplateFact

    def pretty(self) -> str:
        """Returns the pretty representation of the Fact."""
        args = ', '.join((f'{n}={getattr(self, n)}' for n in self.__annotations__))

        return f'{self.__class__.__name__}({args})'

    def modify(self, **kwargs):
        if self._fact is None:
            raise RuntimeError("Cannot modify a fact which is not inserted")

        self._fact.modify_slots(**kwargs)

    def retract(self):
        if self._fact is None:
            raise RuntimeError("Cannot retract a fact which is not inserted")

        self._fact.retract()

        del self._env._facts[self._fact]


class ClipsFact:
    def __init__(self, fact: clips.TemplateFact):
        self._fact = fact

    def __getattr__(self, name: str):
        return self._fact[name]

    def retract(self):
        self._fact.retract()


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
            bool: 'SYMBOL',
            int: 'INTEGER',
            float: 'FLOAT'}
