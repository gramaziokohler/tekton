
from .utils import NodeManager, calculate_dlubal_rotation

class DlubalImporter:
    """iterate over compas timber model, gather sections, nodes and members, then connect to dlubal and push objects one by one"""
    def __init__(self, app_type="rfem", api_key=None, override_objects=True, delete_all=False, material_preset="C16", connector_mode="rigid"):
        self.app_type = app_type
        self.api_key = api_key
        self.override_objects = override_objects
        self.delete_all = delete_all
        self.connector_mode = connector_mode
        
        self.node_manager = NodeManager()
        self.sections_cache = {}
        
        # Mapping for common timber materials
        self.material_library = {
            "GL24h": "GL24h | EN 14080:2013-09",
            "GL24c": "GL24c | EN 14080:2013-09",
            "GL28c": "GL28c | EN 14080:2013-09",
            "GL30c": "GL30c | EN 14080:2013-09",
            "C14": "C14 | EN 338:2016-04",
            "C16": "C16 | EN 338:2016-04",
            "C24": "C24 | EN 338:2016-04",
            "C30": "C30 | EN 338:2016-04"
        }
        
        # Get exact string or fall back to preset string if not found
        self.material_id = 1
        self.material_name = self.material_library.get(material_preset, material_preset)

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
        
        import math
        if self.app_type.lower() == "rstab":
            from dlubal.api import rstab
            AppClass = rstab.Application
            Core = rstab.structure_core
            TFN = rstab.types_for_nodes
        else:
            from dlubal.api import rfem
            AppClass = rfem.Application
            Core = rfem.structure_core
            TFN = rfem.types_for_nodes

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
            support_nodes = []
            
            # nodes (invert Z-axis since RFEM's Z-axis points downwards by default)
            for node_id, pt in self.node_manager.nodes:
                node = Core.Node(no=node_id, coordinate_1=pt.x, coordinate_2=pt.y, coordinate_3=-pt.z)
                objects.append(node)
                
                # identify base nodes via Z approx 0 (tolerance 1cm)
                if abs(pt.z) <= 0.01:
                    support_nodes.append(node_id)
            
            # add nodal supports for base nodes
            if support_nodes:
                print(f"DEBUG: creating NodalSupport for {len(support_nodes)} nodes (Z ≈ 0)")
                # Evaluate ID 1 or higher if we try to override/update and Dlubal bugs out 
                # (RFEM requires elements like NodalSupports to be uniquely registered, 
                # if we have no unique mapping, deleting all or managing IDs strictly is required)
                
                # Rigid support for translation and rotation (in Protobuf math.inf means rigidly fixed)
                support = TFN.NodalSupport(
                    no=1,
                    user_defined_name_enabled=True,
                    name="Base Support Rigid",
                    nodes=support_nodes,
                    spring_x=math.inf,
                    spring_y=math.inf,
                    spring_z=math.inf,
                    rotational_restraint_x=math.inf,
                    rotational_restraint_y=math.inf,
                    rotational_restraint_z=math.inf
                )
                
                # If override_objects=True, we use update_object (or app.create_object) individually for supports if they exist
                # But to keep `create_object_list` simple, let's just make sure delete_all is handled or we expect it to fail if it exists.
                if self.override_objects:
                    # In update mode, `create_object_list` might fail for NodalSupport if it already exists or if it tries to recreate it.
                    pass
                
                objects.append(support)
                
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
                    # 'type' is typically expected as an int.
                    # 2 = TYPE_RIGID (starr, default)
                    # 24 = TYPE_COUPLING_HINGE_HINGE (Koppelstab mit Gelenken)
                    c_type = 24 if self.connector_mode == "hinged" else 2
                    
                    objects.append(Core.Member(
                        no=member_id, 
                        type=c_type,
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

                    #     is_rotated=True, # Hardcoded for testing
                    #     rotation_specification_type=0, # 0 = ROTATION_SPECIFICATION_TYPE_BY_ANGLE
                    #     rotation_angle=0.523598775 # Hardcoded 30 degrees in radians for testing
            
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
