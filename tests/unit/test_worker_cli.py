"""The worker CLI: the process boundary between Grasshopper and the backends.

Rhino 8 runs CPython 3.9; dlubal-api needs >= 3.10 and pulls grpc/pandas/vtk.
So the backends run in a separate process and the two sides talk through the
neutral model's JSON. These tests cover that contract without touching RFEM:
argument parsing, the SAF path (offline), and the guarantee that results
survive the boundary.
"""

import json
import subprocess
import sys

import pytest
from compas.geometry import Point
from compas.geometry import Vector

from compas_timber_fea.core.model import StructuralMember
from compas_timber_fea.core.model import StructuralMemberResult
from compas_timber_fea.core.model import StructuralModel
from compas_timber_fea.core.model import StructuralNode
from compas_timber_fea.core.model import StructuralNodeResult
from compas_timber_fea.core.model import StructuralResultSet
from compas_timber_fea.core.model import StructuralSection

from tekton_app.worker import parse_load_cases


@pytest.fixture
def model():
    model = StructuralModel()
    model.nodes = [
        StructuralNode(id=1, point=Point(0, 0, 0)),
        StructuralNode(id=2, point=Point(3, 0, 0)),
    ]
    model.sections = [StructuralSection(id=1, name="R 0.1/0.2", material_id=1, width=0.1, height=0.2)]
    model.members = [
        StructuralMember(id=1, node_start=1, node_end=2, section_id=1, orientation_vector=Vector(0, 0, 1))
    ]
    model.materials = {1: "C24"}
    return model


def test_load_cases_are_parsed_from_a_comma_list():
    assert parse_load_cases("1,3, 7") == [1, 3, 7]


def test_empty_load_cases_mean_all_of_them():
    # None is the "read every case in the model" signal, not "read none".
    assert parse_load_cases("") is None
    assert parse_load_cases(None) is None


def test_non_numeric_load_cases_are_refused():
    # Silently dropping a bad id would calculate the wrong thing.
    with pytest.raises(SystemExit):
        parse_load_cases("1,ULS")


def run_worker(*arguments):
    return subprocess.run(
        [sys.executable, "-m", "tekton_app.worker"] + list(arguments),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def test_saf_backend_writes_a_spreadsheet(model, tmp_path):
    source = tmp_path / "model.json"
    target = tmp_path / "export.xlsx"
    model.to_json(str(source))

    result = run_worker(str(source), "--backend", "saf", "--out", str(target))

    assert result.returncode == 0, result.stdout
    assert target.is_file()
    assert target.stat().st_size > 0


def test_a_missing_input_file_fails_loudly(tmp_path):
    result = run_worker(str(tmp_path / "nope.json"), "--backend", "saf", "--out", str(tmp_path / "out.xlsx"))

    assert result.returncode != 0
    assert "nicht gefunden" in result.stdout


def test_out_is_required(model, tmp_path):
    source = tmp_path / "model.json"
    model.to_json(str(source))

    result = run_worker(str(source), "--backend", "saf")

    assert result.returncode != 0


def test_the_api_key_never_reaches_the_log(model, tmp_path, monkeypatch):
    # The log is surfaced in Grasshopper and saved with the definition.
    source = tmp_path / "model.json"
    target = tmp_path / "export.xlsx"
    model.to_json(str(source))
    monkeypatch.setenv("TEKTON_API_KEY", "super-secret-value")

    result = subprocess.run(
        [sys.executable, "-m", "tekton_app.worker", str(source), "--backend", "saf", "--out", str(target)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    assert "super-secret-value" not in result.stdout


def test_results_survive_the_process_boundary(model, tmp_path):
    """What the worker writes back is what Grasshopper reads - numbers included."""
    model.results = {
        1: StructuralResultSet(
            load_case_id=1,
            name="Load Case 1",
            member_results={
                1: [
                    StructuralMemberResult(
                        member_id=1,
                        load_case_id=1,
                        position=0.5,
                        axial=-12.5,
                        moment_y=8.1,
                        displacement=0.004,
                    )
                ]
            },
            node_results={
                1: StructuralNodeResult(
                    node_id=1,
                    load_case_id=1,
                    displacement=Vector(0, 0, -0.004),
                    reaction_force=Vector(0, 0, 15.2),
                )
            },
            metadata={"source": "dlubal", "model_fingerprint": "abc123"},
        )
    }

    path = tmp_path / "with_results.json"
    model.to_json(str(path))
    restored = StructuralModel.from_json(str(path))

    member_result = restored.results[1].member_results[1][0]
    assert member_result.axial == pytest.approx(-12.5)
    assert member_result.moment_y == pytest.approx(8.1)
    assert restored.results[1].node_results[1].reaction_force[2] == pytest.approx(15.2)
    # The provenance stamp is what lets the results component spot stale numbers.
    assert restored.results[1].metadata["model_fingerprint"] == "abc123"


def test_the_exchanged_file_carries_a_format_version(model, tmp_path):
    """The boundary is a versioned document, not an ad-hoc dump.

    Grasshopper side and worker side can be updated independently, so the
    format has to say which shape it is.
    """
    path = tmp_path / "model.json"
    model.to_json(str(path))

    with open(path) as handle:
        data = json.load(handle)

    assert data["format_version"] == 1
    assert data["model"]["value"]["nodes"]
