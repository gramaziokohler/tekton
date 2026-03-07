# Dlubal RFEM / RSTAB (API v2) - Python Cheatsheet

Summary of lessons learned for the **Dlubal API v2 (via gRPC/Protobuf)**, specifically built for the `ct_dlubal` (COMPAS Timber) workflow. 

---

## 1. Connection & Data Transfer (gRPC)
Always use the `with` statement to connect to the application. If your script crashes without closing the connection, the gRPC port stays open in the background and blocks future connections (`RESOURCE_EXHAUSTED` error).
Instead of creating objects one-by-one (which is slow and unstable), collect them in a normal Python list and push them all at once.

```python
from dlubal.api.rfem import Application

# 1. Use 'with' to ensure the connection closes cleanly
with Application(api_key_value="YOUR_API_KEY") as app:
    
    # 2. Safest way to avoid ID conflicts: delete all first
    app.delete_all_objects()
    
    objects = []
    # (... append nodes, members, etc. to 'objects' list here ...)
    
    # 3. Push everything in one single network stroke
    app.create_object_list(objects)
```

## 2. Coordinate Systems & Z-Axis
Dlubal uses a **Z-Down** coordinate system (gravity points towards positive Z). COMPAS Timber uses a **Z-Up** system. 
You must invert the Z-coordinate when creating nodes, otherwise your model will be upside down.

```python
# coordinate_3 stands for the Z-axis in Dlubal
node = core.Node(
    no=node_id, 
    coordinate_1=pt.x, 
    coordinate_2=pt.y, 
    coordinate_3=-pt.z  # invert this!
)
```

**Member Rotation (Beta Angle):**
Because we flip the Z-axis, we are mirroring the coordinate space. When calculating the rotation angle (`beta`) for beams, map your axes perfectly into the Dlubal space first (e.g. `z_D = -z_C`) and calculate the rotation around the X-axis against Dlubal's default horizontal Y-vector.

## 3. Protobuf Enums (Finding the right ints)
The Dlubal API uses compiled Protobuf. Pproperties (like material types, element types, load categories) expect a specific **integer ID**, not a string.
Find these numbers dynamically by looking into the object's `DESCRIPTOR` property or hardcode them once found.

```python
# Example: Finding the integer for a RIGID member type
from dlubal.api.rfem import structure_core as core
member_enum = core.Member.DESCRIPTOR.fields_by_name['type'].enum_type
rigid_int = member_enum.values_by_name['TYPE_RIGID'].number # returns 2
```

## 4. Materials
If you create a material, Dlubal assumes it is "Concrete" by default. If your catalogue name is a timber material (like `GL24h`), the API will fail to match it and crash during calculation.
You **must** override the `material_type` flag to tell Dlubal it is timber (usually ID 1).

```python
# Get the timber integer ID safely
timber_type_id = core.Material.DESCRIPTOR.fields_by_name['material_type'].enum_type.values_by_name['MATERIAL_TYPE_TIMBER'].number

mat = core.Material(
    no=1, 
    name="GL24h | EN 14080:2013-09", # Exact catalogue string needed
    material_type=timber_type_id     # Critical!
)
```

## 5. Cross Sections
Cross sections are generated via simple strings. For parametric timber, you must provide dimensions in **millimeters** (even if the rest of your model uses meters).

```python
width_mm = 120
height_mm = 240
# Valid Dlubal prefix for parametric rectangular timber sections is 'R_M1'
cs_name = f"R_M1 {width_mm}/{height_mm}" 

cross_section = core.CrossSection(no=1, name=cs_name, material=1)
```

## 6. Members & Connectors (Rigid vs. Hinged)
Members connect a start Node ID with an end Node ID. Their behavior depends heavily on the chosen `type`.

```python
# 1. Standard Beam (Requires a cross section)
beam = core.Member(
    no=1,
    type=1, # 1 = TYPE_BEAM
    node_start=10, 
    node_end=11,
    cross_section_start=1, 
    cross_section_end=1,
    is_rotated=True,
    rotation_specification_type=0, # By angle
    rotation_angle=0.52 # radians!
)

# 2. Fully Rigid Connector (No cross section needed)
# Good for blocky nodes / pure volume overlaps
rigid_link = core.Member(no=2, type=2, node_start=11, node_end=12) # 2 = TYPE_RIGID

# 3. Hinged Connector (No cross section needed)
# Virtual beam with My and Mz released at both ends! Great for pegged connections.
hinged_link = core.Member(no=3, type=24, node_start=12, node_end=13) # 24 = TYPE_COUPLING_HINGE_HINGE
```

## 7. Nodal Supports (Auflager)
To fix a node to the ground, use `NodalSupport` from the `types_for_nodes` module. 
Instead of booleans, Dlubal models supports as springs. To make a direction totally rigid, specify `math.inf` for the spring stiffness.

```python
import math
from dlubal.api.rfem import types_for_nodes as tfn

# Attach this rigid support to nodes 1, 2, and 3
support = tfn.NodalSupport(
    no=1,
    nodes=[1, 2, 3],
    spring_x=math.inf,
    spring_y=math.inf,
    spring_z=math.inf,
    rotational_restraint_x=math.inf,
    rotational_restraint_y=math.inf,
    rotational_restraint_z=math.inf
)
```

## 8. Load Cases & Settings
A structural model cannot be calculated without loads. A Load Case always requires a **Static Analysis Settings** rule first.
We usually create Load Case 1 as the essential "Self-Weight".

```python
from dlubal.api.rfem import loading

# 1. Provide analysis rules (0 = Geometrically Linear Analysis)
sas = loading.StaticAnalysisSettings(no=1, name="Linear Analysis", analysis_type=0)

# 2. Define the Load Case (11 = Permanent Action, 1 = Static Analysis)
lc = loading.LoadCase(
    no=1, 
    name="Self-Weight", 
    action_category=11, 
    analysis_type=1,
    self_weight_active=True,
    self_weight_factor_x=0.0,
    self_weight_factor_y=0.0,
    self_weight_factor_z=1.0 # 1.0 = Gravity points downwards
)

# 3. Link them together
lc.static_analysis_settings = 1 
```
