"""Pytest bootstrap for unittest-style test classes that forget to inherit.

The shipped test classes use ``self.assert*`` methods (and sometimes
``setUp``) without subclassing ``unittest.TestCase``.  Directly mutating the
class bases is not allowed (CPython refuses because TestCase has a custom
deallocator), so instead we copy the assertion machinery onto such classes
and make pytest's ``setup_method`` invoke their ``setUp`` when present.

Only plain classes whose test methods take no arguments are touched;
pytest-style classes that rely on fixtures are left completely alone.
"""

import inspect
import unittest


# Capture the equality-func dispatch table that TestCase normally builds in
# __init__ (in modern CPython it is an instance attribute).
try:
    _TYPE_FUNCS = dict(unittest.TestCase()._type_equality_funcs)
except Exception:  # pragma: no cover - defensive fallback
    _TYPE_FUNCS = {
        dict: "assertDictEqual",
        list: "assertListEqual",
        tuple: "assertTupleEqual",
        set: "assertSetEqual",
        frozenset: "assertSetEqual",
        str: "assertMultiLineEqual",
    }

_HELPER_NAMES = {
    "_formatMessage",
    "_getAssertEqualityFunc",
    "_truncateMessage",
    "_baseAssertEqual",
    "_AssertRaisesContext",
    "_AssertWarnsContext",
}


def _takes_fixtures(cls):
    for value in vars(cls).values():
        if callable(value) and getattr(value, "__name__", "").startswith("test"):
            try:
                params = list(inspect.signature(value).parameters)
            except (TypeError, ValueError):
                continue
            if len(params) > 1:
                return True
    return False


def _setup_method(self, method):
    self._type_equality_funcs = dict(_TYPE_FUNCS)
    setUp = getattr(self, "setUp", None)
    if callable(setUp):
        setUp()


def _teardown_method(self, method):
    tearDown = getattr(self, "tearDown", None)
    if callable(tearDown):
        tearDown()


def _setup_class(cls):
    setUpClass = getattr(cls, "setUpClass", None)
    if callable(setUpClass):
        setUpClass()


def _teardown_class(cls):
    tearDownClass = getattr(cls, "tearDownClass", None)
    if callable(tearDownClass):
        tearDownClass()


def _inject_assertions(cls):
    if issubclass(cls, unittest.TestCase) or _takes_fixtures(cls):
        return
    has_test = any(
        callable(v) and getattr(v, "__name__", "").startswith("test")
        for v in vars(cls).values()
    )
    if not has_test:
        return
    for name in dir(unittest.TestCase):
        if name.startswith("assert") or name in _HELPER_NAMES:
            if not hasattr(cls, name):
                setattr(cls, name, getattr(unittest.TestCase, name))
    for name, value in (
        ("failureException", AssertionError),
        ("longMessage", True),
        ("maxDiff", 80 * 8),
        ("_diffThreshold", 2 ** 16),
    ):
        if not hasattr(cls, name):
            setattr(cls, name, value)
    if not hasattr(cls, "setup_method"):
        cls.setup_method = _setup_method
    if not hasattr(cls, "teardown_method"):
        cls.teardown_method = _teardown_method
    if not hasattr(cls, "setup_class"):
        cls.setup_class = classmethod(_setup_class)
    if not hasattr(cls, "teardown_class"):
        cls.teardown_class = classmethod(_teardown_class)


def pytest_pycollect_makeitem(collector, name, obj):
    # Runs while the module is being collected, before pytest's Class
    # collector registers its xunit fixtures -- early enough that an
    # injected ``setup_method`` is picked up.
    if isinstance(obj, type) and name.startswith("Test"):
        _inject_assertions(obj)
    return None


def pytest_collection_modifyitems(items):
    # Backstop for classes collected through other paths.
    seen = set()
    for item in items:
        cls = getattr(item, "cls", None)
        if cls is not None and cls not in seen:
            seen.add(cls)
            _inject_assertions(cls)
