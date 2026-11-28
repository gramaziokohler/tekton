"""Offline tests for the Dlubal result reader.

The reader is exercised against a stub whose signatures mirror the pinned
dlubal-api, so calling conventions are checked without a running RFEM.
"""

import inspect

import pytest

from tekton_dlubal.dlubal.result_reader import DlubalResultReader

rfem = pytest.importorskip("dlubal.api.rfem", reason="dlubal-api not installed")


class ApplicationStub:
    """Mimics the real Application.calculate_all signature (keyword-only, required)."""

    def __init__(self, has_results=True):
        self.calls = []
        self._has_results = has_results

    def calculate_all(self, *, skip_warnings: bool, model_id=None):
        self.calls.append({"skip_warnings": skip_warnings, "model_id": model_id})
        return "ok"

    def has_results(self):
        return self._has_results


class ConnStub:
    """The reader takes the client connection, not the bare application."""

    def __init__(self, application):
        self.application = application
        self.api = rfem


def test_stub_matches_real_api_signature():
    """Guard: if dlubal changes the signature, this stub (and the reader) must follow."""
    real = inspect.signature(rfem.Application.calculate_all)
    stub = inspect.signature(ApplicationStub.calculate_all)

    assert list(real.parameters) == list(stub.parameters)
    assert real.parameters["skip_warnings"].kind is inspect.Parameter.KEYWORD_ONLY
    assert real.parameters["skip_warnings"].default is inspect.Parameter.empty


def test_calculate_passes_required_skip_warnings():
    application = ApplicationStub()

    method_name = DlubalResultReader()._calculate(ConnStub(application), [1])

    assert method_name == "calculate_all"
    assert application.calls == [{"skip_warnings": True, "model_id": None}]


def test_calculate_reports_missing_method_clearly():
    class Empty:
        pass

    with pytest.raises(AttributeError, match="No known Dlubal calculation method"):
        DlubalResultReader()._calculate(ConnStub(Empty()), [1])


def test_calculate_without_results_is_an_error():
    """RFEM reports a failed calculation only through has_results(), never by raising."""
    with pytest.raises(RuntimeError, match="no results"):
        DlubalResultReader()._calculate(ConnStub(ApplicationStub(has_results=False)), [1])


# --- timber design ratios (WP1) ------------------------------------------------

class ResultStub:
    def __init__(self, data):
        self.data = data
        self.warning = ""


class DesignApplicationStub:
    """get_results answers the timber ratio table, or raises like RFEM without design results."""

    def __init__(self, frame=None):
        self.frame = frame
        self.requested = []

    def get_results(self, results_type, **filters):
        self.requested.append((results_type, filters))
        if self.frame is None:
            raise RuntimeError("Results are not available.")
        return ResultStub(self.frame)


def ratio_frame():
    import pandas as pd

    return pd.DataFrame(
        {
            "member_no": [1, 1, 1, 2],
            "location_x": [0.0, 0.0, 2.0, 0.0],
            "loading": ["LK1", "LK1", "LK1", "LK1"],
            "design_situation_no": [1, 1, 1, 1],
            "design_check_type": ["SP3100.00", "SP6300.00", "SP6300.00", "SP0100.00"],
            "design_ratio": [0.05, 0.30, 0.20, 0.0],
            "design_check_description": ["Querkraft 6.1.7", "Doppelbiegung und Druck 6.2.4", "Doppelbiegung und Druck 6.2.4", "vernachlaessigbar"],
        }
    )


def test_design_ratios_are_merged_into_every_result_set():
    from tekton_core.core.model import StructuralMemberResult, StructuralResultSet

    stations = {1: [StructuralMemberResult(1, 1, position=0.0, axial=-1.0), StructuralMemberResult(1, 1, position=1.0)]}
    result_sets = {1: StructuralResultSet(load_case_id=1, name="LC1", member_results=stations, metadata={})}
    application = DesignApplicationStub(ratio_frame())

    DlubalResultReader()._read_design_ratios(ConnStub(application), result_sets, {1: 2.0, 2: 3.0})

    assert application.requested[0][0] == rfem.results.ResultsType.TIMBER_DESIGN_MEMBERS_DESIGN_RATIOS_BY_LOCATION
    assert application.requested[0][1] == {}  # every design loading, not "LC1" - the ratio belongs to the combination
    first, last = result_sets[1].member_results[1]
    assert first.axial == -1.0  # the force station survived the merge
    assert first.metadata["utilization"] == pytest.approx(0.30)
    assert first.metadata["governing_check"] == "Doppelbiegung und Druck 6.2.4"
    assert last.metadata["utilization"] == pytest.approx(0.20)
    assert result_sets[1].member_results[2][0].metadata["utilization"] == 0.0
    assert result_sets[1].metadata["design"]["loadings"] == ["LK1"]
    assert result_sets[1].metadata["design"]["rows"] == 4


def test_missing_design_results_are_reported_not_raised():
    from tekton_core.core.model import StructuralResultSet

    result_sets = {1: StructuralResultSet(load_case_id=1, name="LC1", member_results={}, metadata={})}

    DlubalResultReader()._read_design_ratios(ConnStub(DesignApplicationStub(None)), result_sets, {})

    note = result_sets[1].metadata["design"]
    assert "Results are not available" in note["error"]
    assert "Basis + Holz" in note["hint"]
