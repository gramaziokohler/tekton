
from .utils import NodeManager, calculate_dlubal_rotation

class DlubalImporter:
    """iterate over compas timber model, gather sections, nodes and members, then connect to dlubal and push objects one by one"""
    def __init__(self, app_type="rfem", api_key=None, override_objects=True, delete_all=False):
        self.app_type = app_type
        self.api_key = api_key
        self.override_objects = override_objects
        self.delete_all = delete_all
        
        self.node_manager = NodeManager()
        self.sections_cache = {}
        
        # default material for the whole model (use exact Dlubal EN string format)
        self.material_id = 1
        self.material_name = "GL24h | EN 14080:2013-09"

    def get_section_id(self, cross_section_name):
        # assign a new id if the section doesn't exist yet
        if cross_section_name not in self.sections_cache:
            new_id = len(self.sections_cache) + 1
            self.sections_cache[cross_section_name] = new_id
            
        return self.sections_cache[cross_section_name]

    def run(self, timber_model, model_name="Import"):
        print("gathering model data from compas...")
        members_data = []

        # extract rotation enum type to prevent attribute errors
        from dlubal.api.rfem import structure_core
        rotation_spec_enum = structure_core.Member.DESCRIPTOR.fields_by_name['rotation_specification_type'].enum_type
        rotation_by_angle_id = rotation_spec_enum.values_by_name['ROTATION_SPECIFICATION_TYPE_BY_ANGLE'].number

        # 1. process standard beams
        for beam in timber_model.beams:
            segments = timber_model.get_beam_structural_segments(beam)
            
            for segment in segments:
                # get cross section directly from beam dimensions (convert meters to mm, round to nearest integer)
                width_mm = float(beam.width)
                height_mm = float(beam.height)
                print(f"DEBUG: processing beam segment with width {width_mm} mm and height {height_mm} mm...")

                print(f"original beam width: {beam.width} m, height: {beam.height} m")
                
                # RFEM standard keyword for parametric rectangular sections (Timber)
                cs_name = f"R_M1 {width_mm}/{height_mm}"
                    
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

            # implement optional delete all logic before starting
            if self.delete_all:
                print("DEBUG: parameter delete_all=True ... deleting all existing model objects...")
                try:
                    app.delete_all_objects()
                except Exception as e:
                    print(f"DEBUG: Could not execute delete_all_objects: {e}")
            
            print("DEBUG: preparing objects list in python...")
            
            # create the objects list using exactly the simple syntax from the example
            objects = []
            #from dlubal.api.rfem.structure_core import Node
            from dlubal.api.rfem import structure_core
            # nodes (invert Z-axis since RFEM's Z-axis points downwards by default)
            for node_id, pt in self.node_manager.nodes:
                node = structure_core.Node(no=node_id, coordinate_1=pt.x, coordinate_2=pt.y, coordinate_3=-pt.z)
                objects.append(node)
                
            # fetch the integer value for the TIMBER enum to avoid it defaulting to CONCRETE
            mat_enum_desc = Core.Material.DESCRIPTOR.fields_by_name['material_type'].enum_type
            timber_type_id = mat_enum_desc.values_by_name['MATERIAL_TYPE_TIMBER'].number

            # timber material
            objects.append(Core.Material(
                no=self.material_id, 
                name=self.material_name,
                material_type=timber_type_id
            ))

            # cross sections
            # note: in the python client, the class is actually 'Section', not 'CrossSection' as in the C# example
            for name, sec_id in self.sections_cache.items():
                objects.append(Core.CrossSection(
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
                        node_end=m['node_end']
                    ))
                else:
                    objects.append(Core.Member(
                        no=member_id, 
node_start=m["node_start"], 
                        node_end=m["node_end"],
                        cross_section_start=m["section_id"], 
                        cross_section_end=m["section_id"],
                        is_rotated=bool(m["rotation"] != 0.0),
                        rotation_specification_type=0, # 0 = ROTATION_SPECIFICATION_TYPE_BY_ANGLE
                        rotation_angle=float(m["rotation"])
                    ))
            
            # push all at once
            if self.override_objects:
                print(f"DEBUG: override_objects=True ... updating {len(objects)} objects at once using create_object_list (which usually overwrites in RFEM)...")
                try:
                    # In newer RFEM API versions, create_object_list often acts as "create or replace" by ID,
                    # whereas update_object_list throws an error if ANY single object in the list doesn't already exist.
                    app.create_object_list(objects)
                    print("import/update completed.")
                except Exception as e:
                    print(f"DEBUG: Error creating/updating objects list: {e}")
                    raise
            else:
                print(f"DEBUG: creating {len(objects)} objects at once using create_object_list...")
                try:
                    app.create_object_list(objects)
                    print("import completed.")
                except Exception as e:
                    print(f"DEBUG: Error creating objects list: {e}")
                    raise
