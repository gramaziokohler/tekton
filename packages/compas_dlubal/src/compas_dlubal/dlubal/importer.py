import warnings

from compas_timber_fea.core.preflight import preflight

from compas_dlubal.dlubal.client import DlubalClient
from compas_dlubal.dlubal.design_setup import create_or_update
from compas_dlubal.dlubal.design_setup import disable_timber_design
from compas_dlubal.dlubal.design_setup import set_classification
from compas_dlubal.dlubal.design_setup import setup_timber_design
from compas_dlubal.dlubal.mappers.mapper_nodes import NodeMapper
from compas_dlubal.dlubal.mappers.mapper_members import MemberMapper
from compas_dlubal.dlubal.mappers.mapper_supports import SupportMapper
from compas_dlubal.dlubal.mappers.mapper_loads import LoadMapper
from compas_dlubal.dlubal.mappers.mapper_thicknesses import ThicknessMapper
from compas_dlubal.dlubal.mappers.mapper_surfaces import SurfaceMapper
# Translator removed here, handled upstream

class DlubalImporter:
    """Orchestrates the export from the neutral structural model to Dlubal via gRPC."""
    
    def __init__(self, app_type="rfem", api_key=None, delete_all=False, design=False, service_class=1, mesh_size=None, map_path=None, port=None, **legacy):
        """
        Parameters
        ----------
        app_type : str
            "rfem" or "rstab".
        api_key : str, optional
            Dlubal machine key.
        delete_all : bool
            Wipe the active model before pushing.
        design : bool
            Set up the timber design add-on after the push (service class,
            ULS configuration, combination wizard, ULS design situation) so
            that ``DlubalResultReader.read(design=True)`` finds a ratio
            table. See ``design_setup.py`` for the one GUI step it needs.
        service_class : int
            EN 1995 service class for every timber member when ``design``.

        Loading, material and joint idealisation are properties of the neutral
        model, decided during translation. The former material_preset,
        connector_mode and load_cases arguments are accepted and ignored so
        existing callers keep working.
        """
        self.app_type = app_type
        self.api_key = api_key
        self.port = port
        self.delete_all = delete_all
        self.design = design
        self.service_class = service_class
        self.mesh_size = mesh_size
        #: Where the neutral-id -> RFEM-number map is kept between sessions.
        #: Without one the numbering still works, it just starts fresh every
        #: push - which is fine while delete_all is the default.
        self.map_path = map_path
        self.backend_map = self._load_map()
        #: Filled by run() when design is on: what the add-on setup did.
        self.design_report = None

        if legacy:
            names = ", ".join(sorted(legacy))
            warnings.warn(
                f"DlubalImporter ignores {names}: loading, material and joint idealisation "
                "are decided during translation and travel in the structural model.",
                DeprecationWarning,
                stacklevel=2,
            )

    def _load_map(self):
        """The numbering from a previous push, or a fresh one."""
        from compas_dlubal.dlubal.backend_map_io import load_map

        return load_map(self.map_path, self.app_type)

    def _save_map(self):
        if self.map_path:
            self.backend_map.save(self.map_path)

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
        with DlubalClient(app_type=self.app_type, api_key=self.api_key, port=self.port) as conn:
            if self.delete_all:
                conn.delete_all_objects()

            # Design situations exist only with the "load case classification
            # and combination wizard" add-on; authored combinations need it.
            if structural_model.load_combinations:
                set_classification(conn)

            # Collect node coordinates for the MemberMapper
            nodes_cache = {n.id: n.point for n in structural_model.nodes}

            # Neutral ids are hashes over 2^31 (stable across edits); RFEM
            # holds 999,999 objects per category. The numbering allocates
            # dense numbers and remembers them, which is also what lets a
            # later push update the engineer's objects instead of replacing
            # them. Every mapper translates through the same one.
            from compas_dlubal.dlubal.numbering import Numbering
            from compas_dlubal.dlubal.numbering import number_model

            number_model(structural_model, self.backend_map)
            numbering = Numbering(self.backend_map)

            # Initialize Mappers (Software-specific)
            node_mapper = NodeMapper(conn.api.structure_core, numbering=numbering)
            member_mapper = MemberMapper(
                conn.api.structure_core,
                nodes_cache=nodes_cache,
                types_for_members=conn.api.types_for_members,
                numbering=numbering,
            )
            support_mapper = SupportMapper(conn.api.types_for_nodes, numbering=numbering)
            load_mapper = LoadMapper(conn.api.loading, Loads=conn.api.loads, numbering=numbering)
            thickness_mapper = ThicknessMapper(conn.api.structure_core)
            surface_mapper = SurfaceMapper(
                conn.api.structure_core,
                types_for_lines=conn.api.types_for_lines,
                numbering=numbering,
            )

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

            # Line supports come after the surfaces, because a support on a
            # plate edge must reference the line the surface already made -
            # a parallel line of its own would hold nothing.
            for line_support in getattr(structural_model, "line_supports", None) or []:
                objects.append(surface_mapper.map_line_support(line_support, objects))

            # Load cases, loads and combinations come from the neutral model, so
            # every backend applies the same loading.
            objects.extend(load_mapper.map_load_cases(structural_model.load_cases))

            for point_load in structural_model.point_loads:
                objects.append(load_mapper.map_point_load(point_load))

            for member_load in structural_model.member_loads:
                objects.extend(load_mapper.map_member_load(member_load))

            for surface_load in getattr(structural_model, "surface_loads", None) or []:
                objects.extend(load_mapper.map_surface_load(surface_load))

            # A combination needs its design situation to exist first - and
            # activating the classification add-on creates no. 1 by itself,
            # so these go one by one, created or updated, ahead of the list.
            for situation in load_mapper.map_design_situations(structural_model.load_combinations):
                create_or_update(conn.application, situation)
            for combination in structural_model.load_combinations:
                objects.append(load_mapper.map_load_combination(combination))

            for load_case_id, category in load_mapper.unmapped_categories:
                print("Load case {}: action category {!r} has no equivalent under the active "
                      "standard - RFEM will treat it as permanent.".format(load_case_id, category))

            # 4. Push to Dlubal
            try:
                conn.create_object_list(objects)
                print(f"Successfully exported {len(objects)} objects to Dlubal.")
            except Exception as e:
                print(f"Export error: {e}")
                raise

            # Only once the push succeeded: a map naming objects that were
            # never created would make the next push update nothing.
            self._save_map()

            if self.mesh_size:
                settings = conn.application.get_mesh_settings()
                settings.general_target_length_of_fe = float(self.mesh_size)
                conn.application.set_mesh_settings(mesh_settings=settings)

            # 5. Plate stiffness: the library's orthotropic variant is a one-way
            # slab; the neutral plate is isotropic (see plate_material_values).
            if structural_model.surfaces:
                self._set_plate_material_values(conn, structural_model, member_mapper)

            # 6. Design add-on, once the structure and the load cases exist.
            # Base data outlives delete_all, and an active timber add-on with
            # nothing configured makes RFEM calculate nothing - so it is
            # switched off explicitly when design is not asked for.
            if self.design:
                self.design_report = setup_timber_design(conn, structural_model, service_class=self.service_class)
                print("Timber design: " + ", ".join(f"{k}={v}" for k, v in self.design_report.items()))
            else:
                disable_timber_design(conn)
            return True

    @staticmethod
    def _set_plate_material_values(conn, structural_model, member_mapper):
        """Overwrite the surface variant's stiffness tree with the neutral (isotropic) values.

        The tree only exists once RFEM has created the material, so this is a
        get / set / update per material, after the push.
        """
        from dlubal.api import common

        Material = conn.api.structure_core.Material
        for mat_id, material in structural_model.materials.items():
            no = member_mapper.surface_material_id(mat_id)
            current = conn.application.get_object(Material(no=no))
            tree = current.material_values.rows[0].material_values_tree
            for key, value in member_mapper.plate_material_values(material).items():
                common.tree_table.set_values_by_key(tree=tree, key=key, values=[value])
            conn.application.update_object(Material(
                no=no, user_defined=True,
                material_values=current.material_values,
                standard_parameters=current.standard_parameters))

