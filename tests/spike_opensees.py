"""Spike: does OpenSees express what the neutral model needs?

Manual script - needs ``pip install openseespy`` (not a Tekton dependency).
This script is the evidence for the findings. Every check prints the OpenSees number next to a closed-form
reference, so a regression in either is visible at a glance.

Units: kN and m, like the neutral model, so E goes in as MPa * 1000 (kN/m2).
Z-up, like the neutral model - OpenSees has no convention of its own.

Run: ``uv run --with openseespy tests/spike_opensees.py``
"""

import platform
import traceback

try:
    import openseespy.opensees as ops
except RuntimeError as exc:
    # The meta-package refuses ARM64 hosts even when the interpreter is an
    # AMD64 build running under emulation - which loads the DLL just fine.
    if "ARM64" not in str(exc) or not platform.system() == "Windows":
        raise
    import openseespywin.opensees as ops

# C24, 120 x 240 section
E = 11000 * 1000.0  # kN/m2
G = 690 * 1000.0
b, h = 0.12, 0.24
A = b * h
Iy = b * h**3 / 12  # strong axis: load in z bends about y
Iz = h * b**3 / 12
J = 0.229 * b**3 * h  # rectangle, h/b = 2
RHO = 420.0  # kg/m3
G_ACC = 9.81


def fresh():
    ops.wipe()
    ops.model("basic", "-ndm", 3, "-ndf", 6)


def solve():
    ops.system("BandGeneral")
    ops.numberer("RCM")
    ops.constraints("Transformation")
    ops.integrator("LoadControl", 1)
    ops.algorithm("Linear")
    ops.analysis("Static")
    # analyze() does not raise; a non-zero return is the only failure signal.
    assert ops.analyze(1) == 0, "analyze failed"
    ops.reactions()


def check(name, fn):
    print(f"\n=== {name}")
    try:
        fn()
    except Exception:
        traceback.print_exc()


# Local axes with vecxz = global Z: x along the member, y = vecxz x x, z = x x y.
# For a member along +X that gives y = +Y, z = +Z - the neutral model's frame.
VECXZ_UP = (0, 0, 1)


def simply_supported_udl():
    """Two elements, UDL in -z. Reference: 5qL^4/384EI, qL/2, qL^2/8."""
    fresh()
    L, q = 4.0, 5.0
    ops.node(1, 0, 0, 0); ops.node(2, L / 2, 0, 0); ops.node(3, L, 0, 0)
    ops.fix(1, 1, 1, 1, 1, 0, 0)
    ops.fix(3, 0, 1, 1, 1, 0, 0)
    ops.geomTransf("Linear", 1, *VECXZ_UP)
    ops.element("elasticBeamColumn", 1, 1, 2, A, E, G, J, Iy, Iz, 1)
    ops.element("elasticBeamColumn", 2, 2, 3, A, E, G, J, Iy, Iz, 1)
    ops.timeSeries("Constant", 1); ops.pattern("Plain", 1, 1)
    ops.eleLoad("-ele", 1, 2, "-type", "-beamUniform", 0.0, -q, 0.0)  # Wy Wz Wx, LOCAL
    solve()
    print(f"midspan w {ops.nodeDisp(2, 3):.6f}   ref {-5 * q * L**4 / (384 * E * Iy):.6f}")
    print(f"reactions Fz {ops.nodeReaction(1)[2]:.3f} {ops.nodeReaction(3)[2]:.3f}   ref {q * L / 2:.3f}")
    print(f"ele1 localForce My at j {ops.eleResponse(1, 'localForce')[10]:.3f}   "
          f"ref |{q * L**2 / 8:.3f}| - sign convention to calibrate")


def hinge_release_codes():
    """-releasey on elasticBeamColumn. Rule: a node where every member releases the
    same rotation holds that DOF with nothing -> singular. Keep one side continuous
    or fix the DOF at the node; both give the two-cantilever answer."""
    L, P = 4.0, 10.0
    w_ref = -(P / 2) * L**3 / (3 * E * Iy)

    def build(release_both):
        fresh()
        ops.node(1, 0, 0, 0); ops.node(2, L, 0, 0); ops.node(3, 2 * L, 0, 0)
        ops.fix(1, 1, 1, 1, 1, 1, 1); ops.fix(3, 1, 1, 1, 1, 1, 1)
        ops.geomTransf("Linear", 1, *VECXZ_UP)
        ops.element("elasticBeamColumn", 1, 1, 2, A, E, G, J, Iy, Iz, 1, "-releasey", 2)
        if release_both:
            ops.fix(2, 0, 0, 0, 0, 1, 0)  # nobody holds ry at node 2 otherwise
            ops.element("elasticBeamColumn", 2, 2, 3, A, E, G, J, Iy, Iz, 1, "-releasey", 1)
        else:
            ops.element("elasticBeamColumn", 2, 2, 3, A, E, G, J, Iy, Iz, 1)
        ops.timeSeries("Constant", 1); ops.pattern("Plain", 1, 1)
        ops.load(2, 0, 0, -P, 0, 0, 0)
        solve()

    build(release_both=False)
    print(f"one side released: w {ops.nodeDisp(2, 3):.6f}  (propped: ele2 stays continuous, no reference)")
    build(release_both=True)
    print(f"both released, ry fixed at node: w {ops.nodeDisp(2, 3):.6f}   ref {w_ref:.6f}; "
          f"ry reaction {ops.nodeReaction(2)[4]:.1e} (~0)")


def spring_release():
    """Finite rotational spring at a member end: duplicate node + zeroLength(-orient)
    for the spring DOF + equalDOF for the rest. Reference: PL^3/3EI + PL^2/k."""
    fresh()
    L, P, k = 4.0, 10.0, 2000.0  # kNm/rad
    ops.node(1, 0, 0, 0); ops.node(11, 0, 0, 0); ops.node(2, L, 0, 0)
    ops.fix(1, 1, 1, 1, 1, 1, 1)
    ops.geomTransf("Linear", 1, *VECXZ_UP)
    ops.element("elasticBeamColumn", 1, 11, 2, A, E, G, J, Iy, Iz, 1)
    ops.equalDOF(1, 11, 1, 2, 3, 4, 6)
    ops.uniaxialMaterial("Elastic", 1, k)
    # -orient x y: the zeroLength's local axes = the member's local axes, dir 5 = ry
    ops.element("zeroLength", 100, 1, 11, "-mat", 1, "-dir", 5, "-orient", 1, 0, 0, 0, 1, 0)
    ops.timeSeries("Constant", 1); ops.pattern("Plain", 1, 1)
    ops.load(2, 0, 0, -P, 0, 0, 0)
    solve()
    print(f"tip w {ops.nodeDisp(2, 3):.6f}   ref {-(P * L**3 / (3 * E * Iy) + P * L * L / k):.6f}")
    print(f"spring moment {ops.eleResponse(100, 'localForce')[0]:.3f}   ref {P * L:.3f}")


def rigid_member():
    """rigidLink moves the slave rigidly but the retained node reports no reaction
    (reactions are summed from element forces only). A stiff beam does both."""
    fresh()
    ops.node(1, 0, 0, 0); ops.node(2, 0, 0, 1.0); ops.node(3, 4, 0, 1.0)
    ops.fix(1, 1, 1, 1, 1, 1, 1)
    ops.rigidLink("beam", 1, 2)
    ops.geomTransf("Linear", 1, *VECXZ_UP)
    ops.element("elasticBeamColumn", 1, 2, 3, A, E, G, J, Iy, Iz, 1)
    ops.timeSeries("Constant", 1); ops.pattern("Plain", 1, 1); ops.load(3, 0, 0, -10, 0, 0, 0)
    solve()
    print(f"rigidLink: slave disp {[round(v, 6) for v in ops.nodeDisp(2)]}  base reaction {ops.nodeReaction(1)}  (want Fz 10, My -40)")

    fresh()
    ops.node(1, 0, 0, 0); ops.node(2, 0, 0, 1.0); ops.node(3, 4, 0, 1.0)
    ops.fix(1, 1, 1, 1, 1, 1, 1)
    ops.geomTransf("Linear", 1, *VECXZ_UP)
    ops.geomTransf("Linear", 2, 1, 0, 0)  # vertical member: vecxz must not be parallel to x
    f = 1e4
    ops.element("elasticBeamColumn", 9, 1, 2, A * f, E, G, J * f, Iy * f, Iz * f, 2)
    ops.element("elasticBeamColumn", 1, 2, 3, A, E, G, J, Iy, Iz, 1)
    ops.timeSeries("Constant", 1); ops.pattern("Plain", 1, 1); ops.load(3, 0, 0, -10, 0, 0, 0)
    solve()
    print(f"stiff beam: base reaction {[round(v, 3) for v in ops.nodeReaction(1)]}  "
          f"tip w {ops.nodeDisp(3, 3):.6f} ref {-10 * 64 / (3 * E * Iy):.6f}")


def partial_udl_and_self_weight():
    """Partial load (a/L, b/L) on a 3D elasticBeamColumn; self-weight as a line load."""
    fresh()
    L, q = 4.0, 5.0
    ops.node(1, 0, 0, 0); ops.node(2, L, 0, 0)
    ops.fix(1, 1, 1, 1, 1, 1, 1)
    ops.geomTransf("Linear", 1, *VECXZ_UP)
    ops.element("elasticBeamColumn", 1, 1, 2, A, E, G, J, Iy, Iz, 1)
    ops.timeSeries("Constant", 1); ops.pattern("Plain", 1, 1)
    ops.eleLoad("-ele", 1, "-type", "-beamUniform", 0.0, -q, 0.0, 0.5, 1.0, 0.0, -q, 0.0)
    solve()
    r = ops.nodeReaction(1)
    print(f"partial UDL: Fz {r[2]:.3f} ref {q * L / 2:.3f}; My {r[4]:.3f} ref -{q * L / 2 * 3 * L / 4:.3f}")

    ops.remove("loadPattern", 1); ops.wipeAnalysis(); ops.reset()
    w = RHO * A * G_ACC / 1000.0
    ops.pattern("Plain", 2, 1)
    ops.eleLoad("-ele", 1, "-type", "-beamUniform", 0.0, -w, 0.0)
    solve()
    print(f"self weight {w:.4f} kN/m: Fz {ops.nodeReaction(1)[2]:.4f} ref {w * L:.4f}")


def forces_along_member():
    """forceBeamColumn + Elastic section + Lobatto(N): section forces at N stations."""
    fresh()
    L, q, N = 4.0, 5.0, 5
    ops.node(1, 0, 0, 0); ops.node(2, L, 0, 0)
    ops.fix(1, 1, 1, 1, 1, 0, 0); ops.fix(2, 0, 1, 1, 1, 0, 0)
    ops.geomTransf("Linear", 1, *VECXZ_UP)
    ops.section("Elastic", 1, E, A, Iz, Iy, G, J)
    ops.beamIntegration("Lobatto", 1, 1, N)
    ops.element("forceBeamColumn", 1, 1, 2, 1, 1)
    ops.timeSeries("Constant", 1); ops.pattern("Plain", 1, 1)
    ops.eleLoad("-ele", 1, "-type", "-beamUniform", 0.0, -q, 0.0)
    solve()
    for s, x in enumerate(ops.sectionLocation(1), start=1):
        # Elastic 3D section dofs: P, Mz, My, T
        print(f"  station {s} x/L {x / L:.3f}: My {ops.sectionForce(1, s, 3):8.3f}   ref |{q * x * (L - x) / 2:.3f}|")


def multiple_load_cases():
    """One pattern per case; remove + wipeAnalysis + reset between runs keeps them independent."""
    fresh()
    ops.node(1, 0, 0, 0); ops.node(2, 4.0, 0, 0)
    ops.fix(1, 1, 1, 1, 1, 1, 1)
    ops.geomTransf("Linear", 1, *VECXZ_UP)
    ops.element("elasticBeamColumn", 1, 1, 2, A, E, G, J, Iy, Iz, 1)
    ops.timeSeries("Constant", 1)
    out = {}
    for case, (fy, fz) in {1: (0.0, -10.0), 2: (3.0, 0.0)}.items():
        ops.pattern("Plain", case, 1)
        ops.load(2, 0, fy, fz, 0, 0, 0)
        solve()
        out[case] = (round(ops.nodeDisp(2, 2), 6), round(ops.nodeDisp(2, 3), 6))
        ops.remove("loadPattern", case); ops.wipeAnalysis(); ops.reset()
    print(f"(uy, uz) per case: {out}   -> case 2 must have uz == 0")


def shell_plate():
    """Pre-meshed square plate, simply supported. Element loads are silently ignored
    by most shells (warning on stdout, zero result) - nodal tributary loads work."""
    a, t, n, q = 4.0, 0.12, 8, 5.0
    D = E * t**3 / 12
    w_ref = -0.00406 * q * a**4 / D  # Timoshenko coefficient for nu = 0.3, close enough for nu = 0

    def grid(eltype):
        fresh()
        ops.section("ElasticMembranePlateSection", 1, E, 0.0, t, RHO / 1000.0)  # rho in t/m3 = kN s2/m4
        tag, k = {}, 1
        for j in range(n + 1):
            for i in range(n + 1):
                ops.node(k, i * a / n, j * a / n, 0.0); tag[(i, j)] = k; k += 1
        e = 1
        for j in range(n):
            for i in range(n):
                n1, n2, n3, n4 = tag[(i, j)], tag[(i + 1, j)], tag[(i + 1, j + 1)], tag[(i, j + 1)]
                if eltype == "ShellDKGT":
                    ops.element(eltype, e, n1, n2, n3, 1); e += 1
                    ops.element(eltype, e, n1, n3, n4, 1); e += 1
                else:
                    ops.element(eltype, e, n1, n2, n3, n4, 1); e += 1
        for (i, j), nd in tag.items():
            if i in (0, n) or j in (0, n):
                ops.fix(nd, 1, 1, 1, 0, 0, 0)
        ops.timeSeries("Constant", 1)
        return tag, e

    tag, e = grid("ShellDKGT")
    ops.pattern("Plain", 1, 1)
    da = (a / n) ** 2
    for (i, j), nd in tag.items():
        if 0 < i < n and 0 < j < n:
            ops.load(nd, 0, 0, -q * da, 0, 0, 0)
    solve()
    mid = tag[(n // 2, n // 2)]
    print(f"ShellDKGT, nodal loads: centre w {ops.nodeDisp(mid, 3):.6f}   ref ~{w_ref:.6f}")
    stresses = ops.eleResponse(1, "stresses")
    print(f"  'stresses' has {len(stresses)} values = 4 GP x [n11 n22 n12 m11 m22 m12 q13 q23]; GP1: {[round(v, 3) for v in stresses[:8]]}")

    for eltype in ("ShellDKGQ", "ShellMITC4", "ASDShellQ4"):
        for args in (("-surfaceLoad", -q), ("-selfWeight", 0.0, 0.0, -G_ACC)):
            tag, e = grid(eltype)
            ops.pattern("Plain", 1, 1)
            for el in range(1, e):
                ops.eleLoad("-ele", el, "-type", *args)
            solve()
            total = sum(ops.nodeReaction(nd)[2] for nd in tag.values())
            expect = q * a * a if args[0] == "-surfaceLoad" else RHO / 1000.0 * G_ACC * t * a * a
            print(f"  {eltype:11s} {args[0]:13s} sum Fz {total:8.3f}   ref |{expect:.3f}|   "
                  f"{'ACTS' if abs(total) > 1e-6 else 'IGNORED (see stdout warnings)'}")

    # CLT-ready: orthotropic plate fibres in a layered shell section
    ops.nDMaterial("ElasticOrthotropic", 2, 11000e3, 370e3, 370e3, 0.0, 0.0, 0.0, 690e3, 69e3, 69e3, RHO / 1000.0)
    ops.nDMaterial("PlateFiber", 3, 2)
    ops.section("LayeredShell", 2, 3, 3, t / 3, 3, t / 3, 3, t / 3)
    print("  LayeredShell over PlateFiber(ElasticOrthotropic): defined")


if __name__ == "__main__":
    print(f"openseespy {ops.version()} on {platform.system()} {platform.machine()}")
    check("simply supported beam, UDL", simply_supported_udl)
    check("hinge via -releasey", hinge_release_codes)
    check("rotational spring via zeroLength", spring_release)
    check("rigid member: rigidLink vs stiff beam", rigid_member)
    check("partial UDL, self weight", partial_udl_and_self_weight)
    check("forces along a member", forces_along_member)
    check("multiple load cases", multiple_load_cases)
    check("shell plate, element loads, orthotropy", shell_plate)
