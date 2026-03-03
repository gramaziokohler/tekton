
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

    def run(self, timber_model, model_name="Import"):
        print("gathering model data from compas...")
        members_data = []

        # 1. process standard beams
        for beam in timber_model.beams:
            segments = timber_model.get_beam_structural_segments(beam)
            
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
        for joint in timber_model.joints:
            if len(joint.elements) == 2:
                beam_a, beam_b = joint.elements
                for segment in timber_model.get_structural_connector_segments(beam_a, beam_b):
                    n1 = self.node_manager.get_node_number(segment.segment.start)       
                    n2 = self.node_manager.get_node_number(segment.segment.end)
                    
                    members_data.append({
                        "node_start": n1, 
                        "node_end": n2, 
                        "is_rigid": True
                    })

        # 3. connect to dlubal and process data
        print(f"connecting to dlubal (target: {self.app_type})...")
        
        if self.app_type.lower() == "rstab":
            from dlubal.api import rstab
            AppClass = rstab.Application
            Core = rstab.structure_core
        else:
            from dlubal.api import rfem
            AppClass = rfem.Application
            Core = rfem.structure_core

        # with statement automatically opens and CLOSES the connection safely
        with AppClass(api_key_value=self.api_key) as app:
            print("model connected successfully.")
            
            # no close model call, as leads to UNIMPLEMENTED error... to be fixed later
            # print("DEBUG: calling app.delete_all_objects()...")
            # # delete_all_objects existiert oft schon in leicht älteren versionen. 
            # app.delete_all_objects()

            print("DEBUG: preparing objects list in python...")
            
            # create the objects list using exactly the simple syntax from the example
            objects = []
            
            # nodes
            for node_id, pt in self.node_manager.nodes:
                objects.append(Core.Node(
                    no=node_id, 
                    coordinate_1=pt.x, 
                    coordinate_2=pt.y, 
                    coordinate_3=pt.z
                ))
                
            # timber material
            objects.append(Core.Material(
                no=self.material_id, 
                name=self.material_name
            ))

            # cross sections
            # note: in the python client, the class is actually 'Section', not 'CrossSection' as in the C# example
            for name, sec_id in self.sections_cache.items():
                objects.append(Core.Section(
                    no=sec_id, 
                    name=name, 
                    material=self.material_id
                ))

            # members
            for index, m in enumerate(members_data):
                member_id = index + 1
                if m["is_rigid"]:
                    # In python generated protobuffers, the enums are mapped to strings/ints without standard dot notation.
                    # 'type' is typically expected as an int, where rigid is usually 13, and beam is 0 or 1.
                    objects.append(Core.Member(
                        no=member_id, 
                        node_start=m['node_start'], 
                        node_end=m['node_end'], 
                        type=Core.MemberType.MEMBER_TYPE_RIGID if hasattr(Core, 'MemberType') else 13
                    ))
                else:
                    objects.append(Core.Member(
                        no=member_id, 
                        node_start=m["node_start"], 
                        node_end=m["node_end"],
                        section_start=m["section_id"], 
                        section_end=m["section_id"],
                        rotation_angle=m["rotation"],
                        type=Core.MemberType.MEMBER_TYPE_BEAM if hasattr(Core, 'MemberType') else 0
                    ))
            
            # push one by one

            # up until here, it all works fine, the connection is established, objects are created in python
            
            print(f"DEBUG: creating {len(objects)} objects one by one...")
            for i, obj in enumerate(objects):
                try:
                    # but this ***** does not work yet!!
                    app.create_object(obj)
                except Exception as e:
                    print(f"DEBUG: Error creating object {i} ({type(obj)}): {e}")
                    raise
            print("import completed.")
