# tekton-dlubal

Imported as `compas_dlubal`. Dlubal RFEM 6 / RSTAB 9 adapter for Tekton: pushes a Tekton `StructuralModel`
through the Dlubal gRPC API (`dlubal-api`), runs the calculation and the timber
design add-on, and reads the results back. Needs a Dlubal licence and API key;
RFEM runs on Windows.

Part of [Tekton](https://github.com/gramaziokohler/tekton), which carries a [COMPAS Timber](https://github.com/gramaziokohler/compas_timber)
design into structural analysis and brings the results back onto the beams and
plates. All Tekton packages are released together under one version; install
the same version of each. Documentation, issues and the other packages:
https://github.com/gramaziokohler/tekton.

MIT licence, Gramazio Kohler Research, ETH Zurich.
