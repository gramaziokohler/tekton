import warnings

from compas_timber_fea.core.preflight import preflight

from compas_dlubal.dlubal.client import DlubalClient
from compas_dlubal.dlubal.mappers.mapper_nodes import NodeMapper
from compas_dlubal.dlubal.mappers.mapper_members import MemberMapper
from compas_dlubal.dlubal.mappers.mapper_supports import SupportMapper
from compas_dlubal.dlubal.mappers.mapper_loads import LoadMapper
from compas_dlubal.dlubal.mappers.mapper_thicknesses import ThicknessMapper
from compas_dlubal.dlubal.mappers.mapper_surfaces import SurfaceMapper
# Translator removed here, handled upstream

class DlubalImporter:
    """Orchestrates the export from the neutral structural model to Dlubal via gRPC."""
    
    def __init__(self, app_type="rfem", api_key=None, delete_all=False, **legacy):
        """
        Parameters
        ----------
        app_type : str
            "rfem" or "rstab".
        api_key : str, optional
            Dlubal machine key.
        delete_all : bool
            Wipe the active model before pushing.

        Loading, material and joint idealisation are properties of the neutral
        model, decided during translation. The former material_preset,
        connector_mode and load_cases arguments are accepted and ignored so
        existing callers keep working.
        """
        self.app_type = app_type
        self.api_key = api_key
        self.delete_all = delete_all

        if legacy:
            names = ", ".join(sorted(legacy))
            warnings.warn(
                f"DlubalImporter ignores {names}: loading, material and joint idealisation "
                "are decided during translation and travel in the structural model.",
                DeprecationWarning,
                stacklevel=2,
            )

    def _remove_zero_length_members(self, structural_model, tol=1e-6):
        nodes_by_id = {node.id: node for node in structural_model.nodes}
        valid_members = []
        removed_member_ids = set()

        for member in structural_model.members:
            start_node = nodes_by_id.get(member.node_start)
            end_node = nodes_by_id.get(member.node_end)

            if not start_node or not end_node:
                valid_members.append(member)
                continue

            if start_node.point.distance_to_point(end_node.point) <= tol:
                removed_member_ids.add(member.id)
                continue

            valid_members.append(member)

        if removed_member_ids:
            structural_model.members = valid_members
            structural_model.member_loads = [load for load in structural_model.member_loads if load.member_id not in removed_member_ids]
            print(f"{len(removed_member_ids)} elements with 0 length removed.")

    def run(self, structural_model, model_name="Import"):
        self._remove_zero_length_members(structural_model)

        # Surface the predictable problems before RFEM turns them into opaque
        # errors (or worse, silently calculates a mechanism). Findings do not
        # block the push - adding supports inside RFEM is a legitimate workflow.
        report = preflight(structural_model)
        if report.errors or report.warnings:
            print(report.summary())

        # 1. Connect to Dlubal via Client Module
        with DlubalClient(app_type=self.app_type, api_key=self.api_key) as conn:
            if self.delete_all:
                conn.delete_all_objects()

            # Collect node coordinates for the MemberMapper
            nodes_cache = {n.id: n.point for n in structural_model.nodes}

            # Initialize Mappers (Software-specific)
            node_mapper = NodeMapper(conn.api.structure_core)
            member_mapper = MemberMapper(
                conn.api.structure_core,
                nodes_cache=nodes_cache,
                types_for_members=conn.api.types_for_members,
            )
            support_mapper = SupportMapper(conn.api.types_for_nodes)
            load_mapper = LoadMapper(conn.api.loading, Loads=conn.api.loads)
            thickness_mapper = ThicknessMapper(conn.api.structure_core)
            surface_mapper = SurfaceMapper(conn.api.structure_core, types_for_lines=conn.api.types_for_lines)

            # 3. Mapping from neutral -> Dlubal objects
            objects = []
            
            # Materials - and, when there are surfaces, the plate-capable
            # variant of each (see MemberMapper.map_material).
            for mat_id, mat_name in structural_model.materials.items():
                objects.append(member_mapper.map_material(mat_id, mat_name))
                if structural_model.surfaces:
                    objects.append(member_mapper.map_material(mat_id, mat_name, for_surfaces=True))

            # Nodes
            for n in structural_model.nodes:
                objects.append(node_mapper.map(n))

            # Thicknesses reference the surface variant of their material
            for t in structural_model.thicknesses:
                objects.append(thickness_mapper.map(t, material_id=member_mapper.surface_material_id(t.material_id)))

            # Sections
            for s in structural_model.sections:
                objects.append(member_mapper.map_section(s))

            # Member hinges must exist before the members that reference them.
            objects.extend(member_mapper.map_hinges_for_members(structural_model.members))

            # Members
            for m in structural_model.members:
                objects.append(member_mapper.map_member(m))

            # Surfaces
            for su in structural_model.surfaces:
                objects.extend(surface_mapper.map(su))

            # Plate-to-plate edge connections, once the lines they reference exist.
            objects.extend(surface_mapper.map_connections(structural_model.surface_connections))

            # Supports
            for su in structural_model.supports:
                objects.append(support_mapper.map(su))

            # Load cases, loads and combinations come from the neutral model, so
            # every backend applies the same loading.
            objects.extend(load_mapper.map_load_cases(structural_model.load_cases))

            for point_load in structural_model.point_loads:
                objects.append(load_mapper.map_point_load(point_load))

            for member_load in structural_model.member_loads:
                objects.extend(load_mapper.map_member_load(member_load))

            for combination in structural_model.load_combinations:
                objects.append(load_mapper.map_load_combination(combination))

            # 4. Push to Dlubal
            try:
                conn.create_object_list(objects)
                print(f"Successfully exported {len(objects)} objects to Dlubal.")
                return True
            except Exception as e:
                print(f"Export error: {e}")
                raise

