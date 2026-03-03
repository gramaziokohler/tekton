from compas.itertools import pairwise
from compas.geometry import Point, closest_point_on_segment, distance_point_point, Line, intersection_segment_segment
from compas.scene import Scene
from compas_timber.connections import XLapJoint, LLapJoint

TOLERANCE = 0.05

a = []

# ----- Create structural elements -----

def create_structural_centerlines(beam, timber_model):
    # 1. Get all joints connecting to this beam
    joints = timber_model.get_interactions_for_element(beam)
    
    split_points_with_distances = []
    
    for joint in joints:
        # Each joint.interactions[0] is a tuple: (beam_a, beam_b)
        if not joint.interactions:
            continue
        # print(f"joint: {joint} joint.interactions: {joint.interactions}")
            
        beams_in_joint = joint.interactions[0]
        
        # Identify which beam is 'the other one'
        other_beam = beams_in_joint[1] if beams_in_joint[0] == beam else beams_in_joint[0]
        
        # 2. Intersect this beam with the other beam
        # point_a is on beam.centerline, point_b is on other_beam.centerline
        point_on_this_beam, _ = intersection_segment_segment(beam.centerline, other_beam.centerline, TOLERANCE)
        
        # 3. Calculate distance from start for sorting
        dist_from_start = distance_point_point(beam.centerline.start, point_on_this_beam)
        dist_from_end = distance_point_point(beam.centerline.end, point_on_this_beam)
        
        # Avoid splitting exactly at the start or end (prevents 0-length segments)
        if dist_from_start > TOLERANCE and dist_from_end > TOLERANCE:
            split_points_with_distances.append((dist_from_start, point_on_this_beam))

    # 4. Sort points along the centerline and filter duplicates
    split_points_with_distances.sort(key=lambda x: x[0])
    
    unique_split_points = []
    last_dist = -1.0
    for dist, pt in split_points_with_distances:
        if dist - last_dist > TOLERANCE:
            unique_split_points.append(pt)
            last_dist = dist

    # 5. Create the actual Line segments
    split_segments = []
    nodes = [beam.centerline.start] + unique_split_points + [beam.centerline.end]
    
    for p1, p2 in pairwise(nodes):
        if distance_point_point(p1, p2) > TOLERANCE:
            split_segments.append(Line(p1, p2))

    # Store in attributes for the Grasshopper script to pick up
    beam.attributes["structural_centerlines"] = split_segments

# ----- Create virtual structural elements -----

def create_virtual_structural_elements(timber_model):

    for joint in timber_model.joints:

        if not isinstance(joint, XLapJoint):
            continue

        beam_a, beam_b = joint.interactions[0]

        point_a, point_b = intersection_segment_segment(beam_a.centerline, beam_b.centerline, TOLERANCE)

        virtual_element = Line(point_a, point_b, 0.005)
        joint.virtual_beam = Line(point_a, point_b)


# --- disassemble structural model ---
    
def disassemble_structural_model(timber_model):
    pass



# def create_fea2_problem(timber_model):
#     import os

#     import compas_fea2
#     from compas.data import json_load
#     from compas.geometry import Frame
#     from compas.geometry import Plane
#     from compas_fea2.model import Model
#     from compas_fea2.model import Part
#     from compas_fea2.model import RectangularSection
#     from compas_fea2.model import Timber
#     from compas_fea2.problem import Problem
#     from compas_fea2.problem import StaticStep
#     from compas_fea2.results import DisplacementFieldResults

#     import compas_timber
#     from compas_timber.model import TimberModel

#     compas_fea2.set_backend("abaqus")


#     PATH = os.path.join(compas_timber.DATA, "static", "model.json")

#     timber_model: TimberModel = json_load(PATH)

#     HERE = os.path.dirname(__file__)
#     TEMP = os.path.join(HERE, "_temp")

#     lines = []
#     for beam in timber_model.beams:
#         lines.extend(beam.attributes["attributes"]["structural_centerlines"])


#     material = Timber.C14()
#     section = RectangularSection(w=60, h=80, material=material)

#     # NOTE: this seems to not properly connect all the segments together
#     # we'd likely have to implement our own `from_compas_lines` to have more control on elements and nodes
#     part = Part.from_compas_lines(lines, section=section)

#     model = Model()

#     model.add_part(part)

#     # This is just the XY plane at the lowest point of the reciprocal frame
#     floor = Frame([-1589.09, 4519.88, 1869.43], [1, 0, 0], [0, 1, 0])
#     model.add_fix_bc(part.find_nodes_on_plane(Plane.from_frame(floor)))

#     problem = model.add_problem(Problem("timber_problem"))

#     # TODO: we are likely missing some loads here...
#     step = StaticStep()

#     problem.add_step(step)

#     # Apply 1 neuton of force in z direction to all nodes
#     step.add_uniform_forcefield(part.nodes, z=1.0)

#     step.add_field_outputs([DisplacementFieldResults()])

#     problem.analyse_and_extract(TEMP)
