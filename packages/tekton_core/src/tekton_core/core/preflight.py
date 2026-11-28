"""Sanity checks before a model goes to analysis.

Designers hand over unpolished models; the failure modes are predictable and
cheap to detect. Better one readable report here than an opaque solver error
in RFEM - or worse, a calculation that silently runs on a mechanism.

Errors are conditions under which an analysis is meaningless (no supports,
dangling references). Warnings are conditions worth a look (disconnected
parts, unused load cases). Nothing here blocks an export - a push without
supports is legitimate when the engineer adds them in RFEM - but the caller
gets the report and can decide.
"""

from dataclasses import dataclass
from dataclasses import field
from typing import List


@dataclass
class PreflightReport:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self):
        return not self.errors

    def __iter__(self):
        for message in self.errors:
            yield ("error", message)
        for message in self.warnings:
            yield ("warning", message)

    def summary(self):
        lines = [f"[error] {m}" for m in self.errors] + [f"[warning] {m}" for m in self.warnings]
        return "\n".join(lines) if lines else "preflight: no findings"


def preflight(model):
    """Check a StructuralModel for the predictable failure modes.

    Returns a :class:`PreflightReport`; nothing is raised.
    """
    report = PreflightReport()
    node_ids = {node.id for node in model.nodes}
    section_ids = {section.id for section in model.sections}
    thickness_ids = {thickness.id for thickness in model.thicknesses}
    load_case_ids = {case.id for case in model.load_cases}

    _check_emptiness(model, report)
    _check_supports(model, node_ids, report)
    _check_references(model, node_ids, section_ids, thickness_ids, report)
    _check_materials(model, report)
    _check_loads(model, load_case_ids, report)
    _check_connectivity(model, report)

    return report


def _check_emptiness(model, report):
    if not model.members and not model.surfaces:
        report.errors.append("model contains no members and no surfaces")


def _check_supports(model, node_ids, report):
    line_supports = getattr(model, "line_supports", None) or []
    if not model.supports and not line_supports:
        report.errors.append(
            "model has no supports - calculating it would solve a mechanism. "
            "Mark support_points on beams, support a plate edge, or add supports "
            "in the target software before running."
        )
        return
    for support in model.supports:
        missing = [n for n in support.nodes if n not in node_ids]
        if missing:
            report.errors.append(f"support {support.id} references missing node(s) {missing}")

    for support in line_supports:
        nodes = support.nodes or []
        if len(nodes) < 2:
            # One node is a point support written in the wrong place: the
            # per-metre stiffnesses have no length to act over.
            report.errors.append(
                f"line support {support.id} has {len(nodes)} node(s) - a line needs at least two"
            )
            continue
        missing = [n for n in nodes if n not in node_ids]
        if missing:
            report.errors.append(f"line support {support.id} references missing node(s) {missing}")
            continue
        points = {node.id: node.point for node in model.nodes}
        length = sum(
            points[a].distance_to_point(points[b]) for a, b in zip(nodes, nodes[1:])
        )
        if length < 1e-9:
            report.errors.append(
                f"line support {support.id} has zero length - its nodes are all in one place"
            )


def _check_references(model, node_ids, section_ids, thickness_ids, report):
    for member in model.members:
        for label, node in (("start", member.node_start), ("end", member.node_end)):
            if node not in node_ids:
                report.errors.append(f"member {member.id} references missing {label} node {node}")
        if member.section_id not in section_ids:
            report.errors.append(f"member {member.id} references missing section {member.section_id}")

    for surface in model.surfaces:
        missing = [n for n in surface.nodes if n not in node_ids]
        if missing:
            report.errors.append(f"surface {surface.id} references missing node(s) {missing}")
        if surface.thickness_id not in thickness_ids:
            report.errors.append(f"surface {surface.id} references missing thickness {surface.thickness_id}")


def _check_materials(model, report):
    material_ids = set(model.materials)
    for section in model.sections:
        if section.material_id not in material_ids:
            report.errors.append(f"section {section.id} ({section.name}) references missing material {section.material_id}")
    for thickness in model.thicknesses:
        if thickness.material_id not in material_ids:
            report.errors.append(f"thickness {thickness.id} references missing material {thickness.material_id}")


def _check_loads(model, load_case_ids, report):
    for load in model.point_loads:
        if load.load_case_id not in load_case_ids:
            report.errors.append(f"point load {load.id} references missing load case {load.load_case_id}")
    for load in model.member_loads:
        if load.load_case_id not in load_case_ids:
            report.errors.append(f"member load {load.id} references missing load case {load.load_case_id}")
    for combination in model.load_combinations:
        missing = [case for case in combination.factors if case not in load_case_ids]
        if missing:
            report.errors.append(f"combination {combination.id} ({combination.name}) references missing load case(s) {missing}")


def _check_connectivity(model, report):
    """Union-find over everything that shares nodes; separate islands are suspicious."""
    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        parent[find(a)] = find(b)

    for node in model.nodes:
        find(node.id)
    for member in model.members:
        union(member.node_start, member.node_end)
    for surface in model.surfaces:
        for first, second in zip(surface.nodes, surface.nodes[1:]):
            union(first, second)
    # A surface connection ties two plates together even though they share no
    # nodes; reflect that in the connectivity graph.
    surfaces_by_source = {}
    for surface in model.surfaces:
        if surface.source_element_id:
            surfaces_by_source[surface.source_element_id] = surface
    for connection in model.surface_connections:
        anchors = [surfaces_by_source[guid].nodes[0] for guid in connection.source_element_ids if guid in surfaces_by_source]
        if connection.nodes:
            anchors.append(connection.nodes[0])
        for first, second in zip(anchors, anchors[1:]):
            union(first, second)

    islands = {find(node.id) for node in model.nodes}
    if len(islands) > 1:
        report.warnings.append(
            f"model splits into {len(islands)} disconnected parts - loads on one part cannot reach supports on another"
        )
