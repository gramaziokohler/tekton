"""Offline tests for the Dlubal result reader.

The reader is exercised against a stub whose signatures mirror the pinned
dlubal-api, so calling conventions are checked without a running RFEM.
"""

import inspect

import pytest

from compas_dlubal.dlubal.result_reader import DlubalResultReader

rfem = pytest.importorskip("dlubal.api.rfem", reason="dlubal-api not installed")


class ApplicationStub:
    """Mimics the real Application.calculate_all signature (keyword-only, required)."""

    def __init__(self):
        self.calls = []

    def calculate_all(self, *, skip_warnings: bool, model_id=None):
        self.calls.append({"skip_warnings": skip_warnings, "model_id": model_id})
        return "ok"


def test_stub_matches_real_api_signature():
    """Guard: if dlubal changes the signature, this stub (and the reader) must follow."""
    real = inspect.signature(rfem.Application.calculate_all)
    stub = inspect.signature(ApplicationStub.calculate_all)

    assert list(real.parameters) == list(stub.parameters)
    assert real.parameters["skip_warnings"].kind is inspect.Parameter.KEYWORD_ONLY
    assert real.parameters["skip_warnings"].default is inspect.Parameter.empty


def test_calculate_passes_required_skip_warnings():
    application = ApplicationStub()

    method_name = DlubalResultReader()._calculate(application)

    assert method_name == "calculate_all"
    assert application.calls == [{"skip_warnings": True, "model_id": None}]


def test_calculate_reports_missing_method_clearly():
    class Empty:
        pass

    with pytest.raises(AttributeError, match="No known Dlubal calculation method"):
        DlubalResultReader()._calculate(Empty())
