# Contributing

## Getting set up

The repository is a `uv` workspace, and `install.py` is the short way in — it
checks every part of the setup, installs what is missing, and runs the test
suite as proof that it worked.

```bash
git clone https://github.com/gramaziokohler/tekton.git
cd tekton
python3 install.py --fix
```

The manual route, which is what `--fix` calls underneath:

```bash
uv sync --extra dev
```

Everything then runs through `uv run`:

```bash
uv run pytest          # the automated suite, offline, no RFEM needed
uv run ruff check .    # lint
uv run tekton --help   # the CLI
```

The [README](README.md) covers the two-Python setup (Rhino's CPython 3.9 for
the Grasshopper side, a 3.12 worker for the backends) and the Grasshopper
components.

## Making a change

1. Fork the repository and branch off **main**.
2. Make the change, with a test that would fail without it.
3. `uv run pytest` and `uv run ruff check .`.
4. Add a line to `CHANGELOG.md` under `Unreleased`, if the change is worth
   remembering later.
5. Open a pull request.

## What tests exist, and what they are for

`tests/unit/` is the automated suite: offline, deterministic, and run by CI on
every push. It builds real Dlubal protobuf messages and solves real OpenSees
models, so it catches more than a mock would.

The scripts directly under `tests/` are **manual**. They need a running
RFEM/RSTAB instance and an API key, and they report by printing rather than
asserting. `pytest` does not collect them — `testpaths` in `pyproject.toml`
points at `tests/unit` only.

## The one thing worth being careful about

Numbers coming out of a solver can be wrong without anything failing. A unit
error, a sign convention, a released degree of freedom — all of them produce
entirely plausible output. So if a change affects results, the pull request
should say how you know they are right: a closed-form comparison, a cross-check
against the other backend, or a recorded fixture.

The same applies to the code tables in `tekton_core.design` and
`core/load_catalogue.py`. They were transcribed from the standards by a
developer, not checked by an engineer, and the tests assert against the same
transcriptions — so the tests cannot catch a wrong value either. Treat an edit
there as a change that needs a second pair of eyes on the standard itself.

## Reporting a bug

Please include your operating system, whether the problem is on the Rhino side
or the worker side, and the steps to reproduce it. `python3 install.py` prints
a setup summary that is usually the fastest way to show what is installed.

## Proposing a feature

Say what it would do and keep the scope narrow. If it touches the neutral
`StructuralModel`, say why it belongs there rather than in a backend adapter —
the rule of thumb is that anything depending on which software you are talking
to belongs in the adapter, and anything depending on engineering judgment
belongs in the neutral layer as an explicit, reported policy.
