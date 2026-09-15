from compas_timber_fea.core.materials import Material as NeutralMaterial
from compas_timber_fea.core.model import StructuralMember, StructuralSection

from compas_dlubal.dlubal.conventions import calculate_beta_from_vector

class MemberMapper:
    """Konvertiert neutrale Member/Sections in Dlubal PB Objekte"""
    
    # Grade name -> RFEM library identifier. Resolving against RFEM's own
    # library gives the full native material; the neutral Material's physical
    # properties are the fallback story for backends without a library.
    MATERIAL_LIBRARY = {
        "GL24h": "GL24h | EN 14080:2013-09",
        "GL24c": "GL24c | EN 14080:2013-09",
        "GL28h": "GL28h | EN 14080:2013-09",
        "GL28c": "GL28c | EN 14080:2013-09",
        "GL30c": "GL30c | EN 14080:2013-09",
        "GL32h": "GL32h | EN 14080:2013-09",
        "C14": "C14 | EN 338:2016-04",
        "C16": "C16 | EN 338:2016-04",
        "C18": "C18 | EN 338:2016-04",
        "C24": "C24 | EN 338:2016-04",
        "C30": "C30 | EN 338:2016-04"
    }

    def __init__(self, Core, nodes_cache=None, types_for_members=None):
        self.Core = Core
        # Wir brauchen Zugriff auf die Knotenkoordinaten für die Winkelberechnung
        self.nodes_cache = nodes_cache or {}
        # MemberHinge lives in a separate proto module than the structure core.
        self.types_for_members = types_for_members
        self._hinge_id_counter = 1
        self._hinges_map = {}
        #: (member_id, "start"|"end") -> Dlubal hinge number
        self.hinge_numbers = {}

    # ... (map_section and map_material remain similar)

    def map_hinge(self, release):
        """Create a Dlubal MemberHinge for a neutral MemberRelease.

        RFEM's release fields hold a spring stiffness per degree of freedom,
        with 0 fully released and inf fully restrained - the same convention
        the neutral model uses, so the values pass through unchanged.

        Identical releases share one hinge object, the way an engineer would
        define a hinge type once and reference it from many members. Returns
        (hinge_or_None, hinge_no); the hinge is None when an equivalent one was
        already created and only needs referencing.
        """
        if self.types_for_members is None:
            raise AttributeError("MemberMapper needs types_for_members to create member hinges")

        key = tuple(getattr(release, dof) for dof in ("ux", "uy", "uz", "rx", "ry", "rz"))
        if key in self._hinges_map:
            return None, self._hinges_map[key]

        hinge_no = self._hinge_id_counter
        hinge = self.types_for_members.MemberHinge(
            no=hinge_no,
            name=release.name or f"Hinge {hinge_no}",
            axial_release_n=float(release.ux),
            axial_release_vy=float(release.uy),
            axial_release_vz=float(release.uz),
            moment_release_mt=float(release.rx),
            moment_release_my=float(release.ry),
            moment_release_mz=float(release.rz),
        )
        self._hinges_map[key] = hinge_no
        self._hinge_id_counter += 1
        return hinge, hinge_no

    def map_member(self, member: StructuralMember):
        if member.member_type == "RIGID":
            # Dlubal Type 2 is RIGID. 
            return self.Core.Member(
                no=member.id,
                type=2, # TYPE_RIGID
                node_start=member.node_start,
                node_end=member.node_end
            )
        
        if member.member_type == "COUPLING":
            hinge_start = self.hinge_numbers.get((member.id, "start"))
            hinge_end = self.hinge_numbers.get((member.id, "end"))

            # A spring cannot be expressed by the coupling type, which is a
            # plain hinge-hinge link, so a springy connector becomes a rigid
            # member carrying explicit hinges instead.
            if self._has_spring(member):
                kwargs = dict(
                    no=member.id,
                    type=2,  # TYPE_RIGID
                    node_start=member.node_start,
                    node_end=member.node_end,
                )
                if hinge_start is not None:
                    kwargs["member_hinge_start"] = hinge_start
                if hinge_end is not None:
                    kwargs["member_hinge_end"] = hinge_end
                return self.Core.Member(**kwargs)

            # Dlubal's coupling types are rigid links with the hinges built
            # into the type, one per end: 21 rigid-rigid, 22 rigid-hinge,
            # 23 hinge-rigid, 24 hinge-hinge. Which ends are hinged follows
            # from the releases the translator put there. 24 is a pendulum
            # bar (axial force only) - the translator never produces it, but
            # a hand-built model may.
            hinged_start = self._is_hinged(member.release_start)
            hinged_end = self._is_hinged(member.release_end)
            coupling_type = {
                (False, False): 21,  # TYPE_COUPLING_RIGID_RIGID
                (False, True): 22,   # TYPE_COUPLING_RIGID_HINGE
                (True, False): 23,   # TYPE_COUPLING_HINGE_RIGID
                (True, True): 24,    # TYPE_COUPLING_HINGE_HINGE
            }[(hinged_start, hinged_end)]
            return self.Core.Member(
                no=member.id,
                type=coupling_type,
                node_start=member.node_start,
                node_end=member.node_end
            )


        # Standard BEAM (Type 1 is default)
        p1 = self.nodes_cache.get(member.node_start)
        p2 = self.nodes_cache.get(member.node_end)
        beta = 0.0
        if p1 and p2:
            beta = calculate_beta_from_vector(p1, p2, member.orientation_vector)

        kwargs = dict(
            no=member.id,
            node_start=member.node_start,
            node_end=member.node_end,
            cross_section_start=member.section_id,
            cross_section_end=member.section_id,
            is_rotated=bool(beta != 0.0),
            rotation_specification_type=0,
            rotation_angle=float(beta),
        )

        # Anchor the source element GUID in RFEM itself, so results and objects
        # remain traceable to the design model even across sessions.
        if member.source_element_id:
            kwargs["id_for_export_import"] = member.source_element_id

        # End releases, if the joint policy produced any for this member.
        hinge_no = self.hinge_numbers.get((member.id, "start"))
        if hinge_no is not None:
            kwargs["member_hinge_start"] = hinge_no
        hinge_no = self.hinge_numbers.get((member.id, "end"))
        if hinge_no is not None:
            kwargs["member_hinge_end"] = hinge_no

        return self.Core.Member(**kwargs)

    @staticmethod
    def _is_hinged(release):
        """True if the end releases any rotation (None or fully rigid is not a hinge)."""
        return release is not None and not release.is_rigid()

    @staticmethod
    def _has_spring(member):
        """True if any end condition is a finite spring rather than rigid/free."""
        for end in ("start", "end"):
            release = getattr(member, f"release_{end}", None)
            if release is None:
                continue
            for dof in ("ux", "uy", "uz", "rx", "ry", "rz"):
                value = getattr(release, dof)
                if value not in (0.0, float("inf")):
                    return True
        return False

    def _needs_explicit_hinge(self, member):
        """Whether this member must reference a MemberHinge object.

        A COUPLING member carries its hinges in the type (21-24), so it only
        needs an explicit hinge when a spring stiffness has to be expressed.
        """
        if member.member_type == "RIGID":
            return False
        if member.member_type == "COUPLING":
            return self._has_spring(member)
        return True

    def map_hinges_for_members(self, members):
        """Create the hinge objects a set of members needs, and record their numbers.

        Returns the list of new MemberHinge objects to push; call before
        map_member so the members can reference them.
        """
        hinges = []
        for member in members:
            if not self._needs_explicit_hinge(member):
                continue
            for end in ("start", "end"):
                release = getattr(member, f"release_{end}", None)
                if release is None or release.is_rigid():
                    continue
                hinge, hinge_no = self.map_hinge(release)
                if hinge is not None:
                    hinges.append(hinge)
                self.hinge_numbers[(member.id, end)] = hinge_no
        return hinges

    #: Offset for the surface variant of a material (see map_material).
    SURFACE_MATERIAL_OFFSET = 1000

    @classmethod
    def surface_material_id(cls, mat_id: int) -> int:
        return mat_id + cls.SURFACE_MATERIAL_OFFSET

    def map_material(self, mat_id: int, material, for_surfaces: bool = False):
        """Map a neutral material (Material object or grade-name string).

        RFEM resolves the name against its own library; the neutral object's
        physical properties are not pushed here - the library material is the
        richer native representation.

        ``for_surfaces`` asks for the variant a plate can use. The library's
        timber grades come with the 1D timber model (E and G, no Poisson's
        ratio), which is fine for members but leaves a surface without a
        stiffness matrix: RFEM then refuses to calculate and reports nothing
        in its errors table. Observed live on 2026-09-15 with C24 on a CLT
        box - S235 calculated, C24 did not, C24 as ORTHOTROPIC_2D did. So a
        model with surfaces gets a second material per grade, orthotropic 2D,
        numbered ``mat_id + SURFACE_MATERIAL_OFFSET``, and the thicknesses
        reference that one.
        """
        material = NeutralMaterial.resolve(material)

        desc = self.Core.Material.DESCRIPTOR.fields_by_name['material_type'].enum_type
        timber_type_id = desc.values_by_name['MATERIAL_TYPE_TIMBER'].number

        # Resolve full name using library or use fallback
        full_name = self.MATERIAL_LIBRARY.get(material.name, material.name)

        kwargs = dict(no=mat_id, name=full_name, material_type=timber_type_id)
        if for_surfaces:
            models = self.Core.Material.DESCRIPTOR.fields_by_name['material_model'].enum_type
            kwargs["no"] = self.surface_material_id(mat_id)
            kwargs["material_model"] = models.values_by_name['MATERIAL_MODEL_ORTHOTROPIC_2D'].number
        return self.Core.Material(**kwargs)

    def map_section(self, section: StructuralSection):
        # In RSTAB heißt es CrossSection, in RFEM oft auch Section
        section_attr = getattr(self.Core, "CrossSection", getattr(self.Core, "Section", None))
        if not section_attr:
             raise AttributeError(f"Dlubal StructureCore has no CrossSection or Section: {dir(self.Core)}")

        # Protobuf Objekte akzeptieren oft nur die ID für verknüpfte Objekte
        return section_attr(
            no=section.id,
            name=section.name, 
            material=section.material_id # RSTAB nutzt 'material', RFEM 'material_no'
        )
