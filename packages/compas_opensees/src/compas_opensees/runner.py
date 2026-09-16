"""Build, solve every load case, read - the OpenSees counterpart of DlubalImporter + DlubalResultReader.

openseespy holds one model per process, so a run always starts with
``wipe()``. Under the worker that is a fresh process anyway; from a long-lived
process (tests) it is what keeps runs independent.
"""

import platform

from compas_timber_fea.core.preflight import preflight

from compas_opensees.analysis import apply_case
from compas_opensees.analysis import clear_case
from compas_opensees.analysis import solve_case
from compas_opensees.builder import ModelBuilder
from compas_opensees.result_reader import read_case


def load_opensees():
    """``openseespy.opensees``, with the Windows-on-ARM detour.

    The meta-package refuses to import on an ARM64 host even when the
    interpreter is an AMD64 build running under emulation - which loads the
    AMD64 DLL just fine. ``openseespywin.opensees`` bypasses the host check.
    """
    try:
        import openseespy.opensees as ops
        return ops
    except RuntimeError as exc:
        if platform.system() == "Windows" and "ARM64" in str(exc):
            import openseespywin.opensees as ops
            return ops
        raise


class OpenSeesRunner:
    """Solve a neutral StructuralModel with OpenSees.

    Parameters
    ----------
    structural_model : StructuralModel
    stations : int
        Lobatto integration points per beam member = result stations along
        the member. OpenSees caps Lobatto at 10; 9 gives a station at
        midspan (odd count), which is where a beam's moment peaks.
    ops : module, optional
        An ``openseespy.opensees``-compatible module; defaults to the real one.
    """

    def __init__(self, structural_model, stations=9, ops=None, mesh_target_length=None):
        self.model = structural_model
        self.stations = stations
        self.mesh_target_length = mesh_target_length
        self.ops = ops or load_opensees()
        self.built = None
        self.log = []

    def run(self, load_cases=None):
        """Returns {load case id: StructuralResultSet}. Raises on a solver failure."""
        report = preflight(self.model)
        for line in report.summary().splitlines():
            if line.strip():
                self.log.append(line)
        if report.errors:
            raise RuntimeError("Preflight blocks the run:\n" + report.summary())

        self.built = ModelBuilder(
            self.ops, self.model, stations=self.stations,
            mesh_target_length=self.mesh_target_length).build()
        self.log.extend(self.built.warnings)
        shells = sum(len(tags) for tags in self.built.surface_elements.values())
        self.log.append("OpenSees {}: {} nodes, {} elements ({} beams, {} rigid), {} release springs".format(
            self._version(),
            len(self.built.node_tags) + len(self.built.mesh_points),
            len(self.built.member_elements) + shells,
            sum(1 for k in self.built.member_kind.values() if k == "beam"),
            sum(1 for k in self.built.member_kind.values() if k == "rigid"),
            len(self.built.release_elements)))
        if shells:
            self.log.append("  {} surface(s) meshed into {} shells".format(
                len(self.built.surface_elements), shells))

        cases = list(self.model.load_cases)
        if load_cases:
            wanted = set(int(c) for c in load_cases)
            cases = [c for c in cases if c.id in wanted]
        if not cases:
            raise RuntimeError("The model has no load cases to solve.")

        self.ops.timeSeries("Constant", 1)
        results = {}
        for case in cases:
            tag = apply_case(self.ops, self.model, self.built, case)
            solve_case(self.ops, tag, case.name)
            results[case.id] = read_case(self.ops, self.model, self.built, case, self.stations)
            clear_case(self.ops, tag)
            self.log.append("  load case {} '{}': {} members, {} nodes".format(
                case.id, case.name, len(results[case.id].member_results), len(results[case.id].node_results)))
        return results

    def _version(self):
        try:
            return self.ops.version()
        except Exception:
            return "?"


def run_model(structural_model, load_cases=None, stations=9, ops=None):
    """Convenience: solve and attach the results to the model; returns the runner (for its log)."""
    runner = OpenSeesRunner(structural_model, stations=stations, ops=ops)
    structural_model.results = runner.run(load_cases)
    return runner


__all__ = ["OpenSeesRunner", "run_model", "load_opensees"]
