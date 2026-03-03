
from dlubal.api.rfem import Application
from dlubal.api.rfem.structure_core import node_pb2, material_pb2, section_pb2, member_pb2
from .utils import NodeManager, calculate_dlubal_rotation

class DlubalImporter:
    def __init__(self, app_type="rfem", api_key=None):
        self.app_type = app_type
        self.api_key = api_key
        self.node_manager = NodeManager()
        self.sections_cache = {}
        
        # default material for the whole model
        self.material_id = 1
        self.material_name = "Timber GL24h"

    def get_section_id(self, cross_section_name):
        # assign a new id if the section doesn't exist yet
        if cross_section_name not in self.sections_cache:
            new_id = len(self.sections_cache) + 1
            self.sections_cache[cross_section_name] = new_id
            
        return self.sections_cache[cross_section_name]

    def run(self, structural_model, model_name="Import"):
        print("gathering model data from compas...")
        members_data = []

        # 1. process standard beams
        for beam in structural_model.beams:
            segments = structural_model.get_beam_structural_segments(beam)
            
            for segment in segments:
                # get cross section directly from beam dimensions
                width = beam.width
                height = beam.height
                cs_name = f"Rect {width}/{height}"
                    
                cs_id = self.get_section_id(cs_name)
                    
                # generate node numbers for start and end points
                n1 = self.node_manager.get_node_number(segment.segment.start)
                n2 = self.node_manager.get_node_number(segment.segment.end) 
                
                # calculate rotation of the member
                beta = calculate_dlubal_rotation(segment.frame)
                
                members_data.append({
                    "node_start": n1, 
                    "node_end": n2, 
                    "section_id": cs_id, 
                    "rotation": beta, 
                    "is_rigid": False
                })

        # 2. process  connectors given by compas timber
        for joint in structural_model.joints:
            if len(joint.elements) == 2:
                beam_a, beam_b = joint.elements
                for segment in structural_model.get_structural_connector_segments(beam_a, beam_b):
                    n1 = self.node_manager.get_node_number(segment.segment.start)       
                    n2 = self.node_manager.get_node_number(segment.segment.end)
                    
                    members_data.append({
                        "node_start": n1, 
                        "node_end": n2, 
                        "is_rigid": True
                    })

        # 3. connect to dlubal
        print("connecting to dlubal...")
        app = Application(api_key_value=self.api_key) 
        active_model = app.get_active_model()
        print("model connected successfully.")
        
        # 4. generate the actual dlubal objects
        print("creating objects in dlubal...")
        
        # nodes
        nodes_list = []
        for node_id, pt in self.node_manager.nodes:
            nodes_list.append(node_pb2.Node(no=node_id, coordinate_1=pt.x, coordinate_2=pt.y, coordinate_3=pt.z))
            
        # timber material
        timber_material = material_pb2.Material(no=self.material_id, name=self.material_name)

        # cross sections linked to the material
        sections_list = []
        for name, sec_id in self.sections_cache.items():
            sections_list.append(section_pb2.Section(no=sec_id, name=name, material=self.material_id))

        # members
        members_list = []
        for index, m in enumerate(members_data):
            member_id = index + 1
            if m["is_rigid"]:
                # type 13 stands for rigid link in dlubal
                members_list.append(member_pb2.Member(
                    no=member_id, 
                    node_start=m['node_start'], 
                    node_end=m['node_end'], 
                    type=13
                ))
            else:
                # normal timber member
                members_list.append(member_pb2.Member(
                    no=member_id, 
                    node_start=m["node_start"], 
                    node_end=m["node_end"],
                    section_start=m["section_id"], 
                    section_end=m["section_id"],
                    rotation_angle=m["rotation"]
                ))
        
        # 5. push everything to the active model
        if nodes_list:
            app.create_object_list(nodes_list, model_id=active_model)
            
        app.create_object(timber_material, model_id=active_model)
        
        if sections_list:
            app.create_object_list(sections_list, model_id=active_model)
            
        if members_list:
            app.create_object_list(members_list, model_id=active_model)
            
        print("import completed.")
