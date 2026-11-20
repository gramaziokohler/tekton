# compas_timber_fea

The neutral layer of Tekton: the `TimberToStructural` translator from a COMPAS
Timber model to a `StructuralModel`, the joint and plate policies, units,
preflight checks, EN 1995 design checks, JSON serialisation, and putting
results back onto the timber model. Pure Python; it also runs inside Rhino 8
(CPython 3.9).

Part of [Tekton](https://github.com/gramaziokohler/tekton), which carries a [COMPAS Timber](https://github.com/gramaziokohler/compas_timber)
design into structural analysis and brings the results back onto the beams and
plates. All Tekton packages are released together under one version; install
the same version of each. Documentation, issues and the other packages:
https://github.com/gramaziokohler/tekton.

MIT licence, Gramazio Kohler Research, ETH Zurich.
