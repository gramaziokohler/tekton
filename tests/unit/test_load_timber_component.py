"""`Tekton Load Timber`: a TimberModel from a file, and what it reports.

The component itself is a Grasshopper script body and cannot be imported here
(it reads `ghenv`), so the two functions worth testing are exercised through
the same source file.

Why they are worth testing. The unit a timber model was authored in is **not
recorded in the file**, and getting it wrong is the classic silent failure of
this pipeline: a model in millimetres translated as metres solves as a 4 km
beam, which does not fail - it just gives a deflection nobody reads twice. The
component cannot fix that, but it can say what the model looks like.
"""

import pathlib
import types

import pytest

from compas.data import json_load
from compas.geometry import Line
from compas.geometry import Point

from compas_timber.elements import Beam
from compas_timber.model import TimberModel

COMPONENT = pathlib.Path("packages/tekton_gh/components/tekton_load_timber/code.py")


@pytest.fixture(scope="module")
def helpers():
    """The helper functions, lifted out of the Grasshopper script body.

    Everything above the INPUTS marker is plain Python; below it the body
    expects `ghenv` and the wired inputs.
    """
    source = COMPONENT.read_text().split("# --------------------- INPUTS")[0]
    # The bootstrap half talks to Rhino; only the helpers are wanted.
    start = source.index("def _extent(")
    module = types.ModuleType("load_timber_helpers")
    exec(compile(source[start:], str(COMPONENT), "exec"), module.__dict__)
    return module


def _beams(*spans):
    model = TimberModel()
    for start, end in spans:
        model.add_element(
            Beam.from_centerline(Line(Point(*start), Point(*end)), width=0.1, height=0.2))
    return model


# --- the extent -----------------------------------------------------------

def test_the_extent_is_the_largest_span(helpers):
    model = _beams(((0, 0, 0), (4, 0, 0)), ((0, 0, 0), (0, 9, 0)))

    assert helpers._extent(list(model.beams), []) == pytest.approx(9.0)


def test_it_measures_in_three_dimensions(helpers):
    model = _beams(((0, 0, 0), (1, 0, 0)), ((0, 0, 0), (0, 0, 7)))

    assert helpers._extent(list(model.beams), []) == pytest.approx(7.0)


def test_an_empty_model_has_no_extent(helpers):
    assert helpers._extent([], []) is None


def test_plates_count_towards_the_extent(helpers):
    """A model can be plates only - the hypar shells are."""
    from compas.geometry import Polyline
    from compas_timber.elements import Plate

    a = Polyline([Point(0, 0, 0), Point(6, 0, 0), Point(6, 6, 0), Point(0, 6, 0), Point(0, 0, 0)])
    b = Polyline([Point(0, 0, 0.2), Point(6, 0, 0.2), Point(6, 6, 0.2), Point(0, 6, 0.2), Point(0, 0, 0.2)])
    plate = Plate.from_outlines(a, b)

    assert helpers._extent([], [plate]) == pytest.approx(6.0)


# --- the unit guess -------------------------------------------------------

def test_a_building_sized_number_reads_as_millimetres(helpers):
    """12000 units is a 12 m building in millimetres, not a 12 km one."""
    guess = helpers._unit_guess(12000.0)

    assert "millimetre" in guess
    assert "12 m" in guess


def test_a_plain_building_size_reads_as_metres(helpers):
    assert helpers._unit_guess(12.0) == "metres"


def test_an_ambiguous_size_says_so_rather_than_guessing(helpers):
    """Half a metre, or half a millimetre? Neither is a building. Saying
    'unclear' is more use than picking one."""
    assert "unclear" in helpers._unit_guess(0.5)


def test_a_degenerate_model_is_named_as_such(helpers):
    assert "point" in helpers._unit_guess(0.0)


# --- against the real fixtures -------------------------------------------

def test_the_sticks_fixture_is_recognised_as_metres(helpers):
    """It is authored in metres - 8.2 units across, with 0.08 x 0.1 sections.

    Worth pinning, because the two shipped fixtures differ: this one is in
    metres and the plate one in millimetres. That is exactly the confusion
    the hint exists to surface."""
    model = json_load("tests/timber_model_sticks.json")

    extent = helpers._extent(list(model.beams), list(model.plates))
    assert extent == pytest.approx(8.159, abs=0.01)
    assert helpers._unit_guess(extent) == "metres"


def test_the_plate_fixture_is_recognised_as_millimetres(helpers):
    model = json_load("tests/timber_model_plates_2.json")

    extent = helpers._extent(list(model.beams), list(model.plates))
    assert "millimetre" in helpers._unit_guess(extent)


def test_a_metre_model_is_recognised_as_metres(helpers):
    model = _beams(((0, 0, 0), (8, 0, 0)))

    assert helpers._unit_guess(helpers._extent(list(model.beams), [])) == "metres"


# --- the component file itself -------------------------------------------

def test_it_declares_the_dependencies_rhino_needs():
    """Without the `# r:` pragma the script component cannot import compas."""
    source = COMPONENT.read_text()

    assert "# r: compas, compas_timber" in source


def test_it_does_not_touch_the_canvas():
    """Self-attaching value lists crash Rhino; no component may do it."""
    source = COMPONENT.read_text()

    assert "ScheduleSolution" not in source
    assert "OnPingDocument().Objects" not in source
