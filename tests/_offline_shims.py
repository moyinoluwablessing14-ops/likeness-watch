"""
TEST-ONLY. Minimal stand-ins for pydantic.BaseModel/Field and
google.adk.agents.Agent, injected into sys.modules so agent.py and schema.py
can be imported and executed for real in an offline sandbox. Cloud Shell will
use the real packages — this exists purely to let me verify the actual logic
right now without network access.
"""

import sys
import types
import typing

_MISSING = object()


class FieldInfo:
    def __init__(self, default=_MISSING, default_factory=None, description=None):
        self.default = default
        self.default_factory = default_factory


def Field(default=_MISSING, default_factory=None, description=None):
    return FieldInfo(default=default, default_factory=default_factory, description=description)


def _coerce(value, typ):
    origin = typing.get_origin(typ)
    if origin is list:
        (inner,) = typing.get_args(typ)
        return [_coerce(v, inner) for v in value]
    if isinstance(typ, type) and issubclass(typ, BaseModel) and isinstance(value, dict):
        return typ(**value)
    if origin is typing.Literal:
        allowed = typing.get_args(typ)
        if value not in allowed:
            raise ValueError(f"{value!r} not in allowed values {allowed}")
        return value
    return value


class BaseModel:
    def __init__(self, **data):
        anns = {}
        for klass in reversed(type(self).__mro__):
            anns.update(getattr(klass, "__annotations__", {}))
        for name, typ in anns.items():
            if name in data:
                val = data[name]
            else:
                default = getattr(type(self), name, _MISSING)
                if isinstance(default, FieldInfo):
                    if default.default_factory is not None:
                        val = default.default_factory()
                    elif default.default is not _MISSING:
                        val = default.default
                    else:
                        raise TypeError(f"missing required field: {name}")
                elif default is not _MISSING:
                    val = default
                else:
                    raise TypeError(f"missing required field: {name}")
            setattr(self, name, _coerce(val, typ))

    def model_dump(self):
        out = {}
        anns = {}
        for klass in reversed(type(self).__mro__):
            anns.update(getattr(klass, "__annotations__", {}))
        for name in anns:
            v = getattr(self, name)
            if isinstance(v, BaseModel):
                out[name] = v.model_dump()
            elif isinstance(v, list):
                out[name] = [i.model_dump() if isinstance(i, BaseModel) else i for i in v]
            else:
                out[name] = v
        return out

    def __repr__(self):
        return f"{type(self).__name__}({self.model_dump()})"


fake_pydantic = types.ModuleType("pydantic")
fake_pydantic.BaseModel = BaseModel
fake_pydantic.Field = Field
sys.modules["pydantic"] = fake_pydantic


class FakeAgent:
    """Stand-in for google.adk.agents.Agent — just stores kwargs, does nothing."""
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


fake_google = types.ModuleType("google")
fake_google_adk = types.ModuleType("google.adk")
fake_google_adk_agents = types.ModuleType("google.adk.agents")
fake_google_adk_agents.Agent = FakeAgent
sys.modules.setdefault("google", fake_google)
sys.modules["google.adk"] = fake_google_adk
sys.modules["google.adk.agents"] = fake_google_adk_agents

fake_parallel = types.ModuleType("parallel")


class FakeParallel:
    def __init__(self, api_key=None):
        self.api_key = api_key

    def search(self, objective, search_queries):
        raise RuntimeError("Live search called during offline test — should be monkeypatched")


fake_parallel.Parallel = FakeParallel
sys.modules["parallel"] = fake_parallel
