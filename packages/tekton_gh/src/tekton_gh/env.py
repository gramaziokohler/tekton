"""Pfad- und Umgebungs-Setup für die Rhino-Seite.

Das Problem, das dieses Modul löst: Rhinos Python findet `compas_timber_fea`
nicht, weil das Paket im Monorepo liegt und nicht installiert ist. Und die
Rhino-Session hat womöglich schon ein *anderes* `compas_timber` importiert
(das offizielle GH-Plugin, Version 1.0.5) — Tekton braucht aber die
`structural_graph_plates`-Branch, die `compas_timber.structural` mitbringt.

Reihenfolge zählt: `sys.path.insert(0, ...)` und, falls nötig, ein Purge der
bereits geladenen Module.
"""

import os
import sys

# Wird von den Komponenten überschrieben, wenn das Repo woanders liegt.
# Reihenfolge: explizites Argument > Umgebungsvariable > dieser Default.
DEFAULT_REPO_ENV_VAR = "TEKTON_REPO"

#: Pakete des Monorepos, die in Rhino laufen dürfen (reine Python-Schicht).
#: `compas_dlubal` und `compas_saf` fehlen hier bewusst — die brauchen
#: grpc/pandas/vtk und laufen nur im Worker (siehe worker.py).
IN_PROCESS_PACKAGES = ("compas_timber_fea",)


def _valid(candidate):
    """Ist das eine Monorepo-Wurzel?"""
    if not candidate:
        return None
    candidate = os.path.expanduser(str(candidate))
    return candidate if os.path.isdir(os.path.join(candidate, "packages")) else None


def remember_repo_root(root):
    """Repo-Wurzel für die restliche Rhino-Sitzung merken.

    Nur wenige Komponenten haben einen `repo`-Input — es wäre Unfug, ihn an
    jede der zwanzig zu verkabeln. Wer ihn hat und einen gültigen Pfad
    bekommt, hinterlegt ihn hier; alle anderen finden ihn wieder.

    Abgelegt wird in ``os.environ``, weil das prozessweit gilt und der
    Worker-Subprozess es ohnehin erbt. Der Pfad überlebt damit auch das
    Schliessen der Definition, aber nicht den Rhino-Neustart — was der
    Erwartung entspricht: ein Canvas arbeitet an einem Repo.
    """
    root = _valid(root)
    if root:
        os.environ[DEFAULT_REPO_ENV_VAR] = root
    return root


def tekton_repo_root(explicit=None):
    """Wurzel des Tekton-Monorepos ermitteln.

    Reihenfolge: expliziter Input > was sich die Sitzung gemerkt hat >
    Umgebungsvariable. Die ersten beiden fallen in derselben Variablen
    zusammen, weil `remember_repo_root` dorthin schreibt.

    Parameters
    ----------
    explicit : str, optional
        Vom Nutzer gesetzter Pfad (Komponenten-Input). Gewinnt, wenn gesetzt.

    Returns
    -------
    str or None
    """
    return _valid(explicit) or _valid(os.environ.get(DEFAULT_REPO_ENV_VAR))


def ensure_tekton_path(repo_root=None, purge_conflicting=True):
    """`compas_timber_fea` importierbar machen.

    Parameters
    ----------
    repo_root : str, optional
        Repo-Wurzel; wenn None, via :func:`tekton_repo_root` gesucht.
    purge_conflicting : bool
        Bereits geladene `compas_timber`-Module aus `sys.modules` entfernen,
        damit die Branch-Version aus dem aktiven venv gewinnt. In Rhino ist
        das der Normalfall — das offizielle COMPAS-Timber-Plugin lädt sonst
        1.0.5, und `compas_timber.structural` existiert dort nicht.

    Returns
    -------
    str
        Die verwendete Repo-Wurzel.

    Raises
    ------
    RuntimeError
        Wenn das Repo nicht gefunden wird. Bewusst laut: eine Komponente, die
        still nichts tut, ist schlimmer als eine, die rot wird.
    """
    root = tekton_repo_root(repo_root)
    if root is not None:
        remember_repo_root(root)
    if root is None:
        raise RuntimeError(
            "Tekton-Repo nicht gefunden. Setze den Input 'repo' der Komponente "
            "oder die Umgebungsvariable {}.".format(DEFAULT_REPO_ENV_VAR)
        )

    if purge_conflicting:
        _purge("compas_timber")
        _purge("compas_timber_fea")

    for package in IN_PROCESS_PACKAGES:
        src = os.path.join(root, "packages", package, "src")
        if not os.path.isdir(src):
            raise RuntimeError("Erwarteter Pfad fehlt: {}".format(src))
        if src in sys.path:
            sys.path.remove(src)
        sys.path.insert(0, src)

    return root


def _purge(top_level):
    """Ein Top-Level-Paket und alle Submodule aus `sys.modules` werfen."""
    for name in [m for m in list(sys.modules) if m == top_level or m.startswith(top_level + ".")]:
        del sys.modules[name]


def diagnose(repo_root=None):
    """Zustandsbericht für die Info-Komponente.

    Beantwortet die Frage, die bei jedem Support-Fall zuerst kommt: welches
    Python, welches compas_timber, ist die structural-Branch da, findet er das
    Repo, gibt es ein Worker-Env.

    Returns
    -------
    list of str
    """
    lines = ["Python {}".format(sys.version.split()[0])]

    root = tekton_repo_root(repo_root)
    lines.append("Repo: {}".format(root or "NICHT GEFUNDEN"))

    try:
        import compas

        lines.append("compas {}".format(compas.__version__))
    except ImportError as exc:
        lines.append("compas fehlt ({})".format(exc))

    try:
        import compas_timber

        lines.append("compas_timber {}".format(compas_timber.__version__))
    except ImportError as exc:
        lines.append("compas_timber fehlt ({})".format(exc))
        return lines

    try:
        import compas_timber.structural  # noqa: F401

        lines.append("compas_timber.structural: OK")
    except ImportError:
        lines.append(
            "compas_timber.structural FEHLT — falsche compas_timber-Version. "
            "Tekton braucht die 'structural_graph_plates'-Branch; siehe README."
        )

    try:
        import compas_timber_fea  # noqa: F401

        lines.append("compas_timber_fea: OK")
    except ImportError as exc:
        lines.append("compas_timber_fea nicht importierbar ({})".format(exc))

    return lines
