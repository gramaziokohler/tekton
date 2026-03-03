import math
from compas.geometry import Point, Frame, Vector
from ct_dlubal.utils import NodeManager, calculate_dlubal_rotation
from ct_dlubal.mapping import DlubalMapper

def test_node_manager():
    nm = NodeManager(tolerance=0.01)
    n1 = nm.get_node_number(Point(0, 0, 0))
    n2 = nm.get_node_number(Point(0.005, 0, 0)) # Should be same as n1 due to tol
    n3 = nm.get_node_number(Point(1, 0, 0))
    
    assert n1 == 1
    assert n2 == 1
    assert n3 == 2
    assert len(nm.nodes) == 2

def test_mapping():
    mapper = DlubalMapper(
        material_map={"wood": "Timber GL24h"},
        cross_section_map={"beam": "Rect 200/400"}
    )
    
    assert mapper.map_material("wood") == "Timber GL24h"
    assert mapper.map_material("unknown") == "unknown"
    assert mapper.map_cross_section("beam") == "Rect 200/400"
    assert mapper.map_cross_section("120x240") == "Rect 120/240"

def test_rotation_beta():
    # Horizontal beam along X, zaxis points up (COMPAS default)
    # Dlubal's default z points DOWN. 
    # So rotation should be pi (180 degrees)
    f1 = Frame(Point(0,0,0), Vector(1,0,0), Vector(0,1,0)) # xaxis=1,0,0; yaxis=0,1,0; zaxis=0,0,1
    beta = calculate_dlubal_rotation(f1)
    assert math.isclose(beta, math.pi) or math.isclose(beta, -math.pi)

    # Beam along X, zaxis points right (Y positive)
    f2 = Frame(Point(0,0,0), Vector(1,0,0), Vector(0,0,-1)) # yaxis=0,0,-1; zaxis=0,1,0
    beta2 = calculate_dlubal_rotation(f2)
    # default_z for Dlubal is 0,0,1. To get to 0,1,0 around 1,0,0, we rotate -90 deg (or 270)
    assert math.isclose(beta2, -math.pi/2)

