| Feature | Karamba3D / Grasshopper | Ansys (MAPDL/PyAnsys) | SOFiSTiK (CADINP) | Unser Modell |
|---------|-------------------------|----------------------|-------------------|--------------|
| Nodes | Point3d | N, id, x, y, z | KNOT NO X Y Z | ✅ (StructuralNode) |
| Orientation | Local Axis / Orientation Vector | Orientation Node / Vector | VECS / Local Axis | ✅ (orientation_vector) |
| Sections | Cross Section Names | SECTYPE / Beam Props | QUER | ✅ (Rectangular dims) |
| Materials | Material Name/ID | MP (EX, PRXY...) | MATE | ✅ (Material ID/Name) |
| Supports | Support BCs (0/1) | D, node, ALL | FEST | ✅ (StructuralSupport) |