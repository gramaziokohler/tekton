# Releasing Tekton

A release takes one version number through PyPI first, then the Rhino package
manager (Yak). Order matters: the released components name
`tekton-gh>=X.Y.Z` in their `# r:` header, and Rhino installs that from PyPI
on first use, so a Yak package whose PyPI version does not exist yet breaks on
every machine that installs it. A version published once can never be reused
on PyPI or Yak.

```text
bump + changelog -> tag vX.Y.Z -> release.yml (PyPI) -> publish_yak (test)
                 -> clean-Rhino test -> publish_yak (prod) -> GitHub release, Food4Rhino
```

## What gets published

| Where | What |
| --- | --- |
| PyPI | `tekton-core`, `tekton-gh` (Rhino side, Python 3.9+); `tekton-dlubal`, `tekton-opensees`, `tekton-saf`, `tekton-app` (worker, 3.10+/3.12) |
| Yak (`tekton`, `rh8`) | the 29 `.ghuser` components, icon, README, LICENSE |

All packages share one version (`[tool.bumpversion]` in `pyproject.toml`) and
pin each other exactly.
The PyPI name and the import name are the same, `-` for `_`
(`tekton-core` imports as `tekton_core`).

## Two modes, one source

The component source stays in **development mode**: `# venv: tekton-test`,
`# r: compas, compas_timber`, and each component finds the repo on disk.
`publish_yak.yml` switches its own checkout to the **release header**
(`invoke gh-headers --release`: `# venv: tekton`, `# r: tekton-gh>=X.Y.Z`)
just before it builds. An installed component finds the packages Rhino
installed and searches for no repo; a repo named explicitly (a `repo` input,
or `TEKTON_REPO`) still wins.

The worker of an installed Tekton lives in `~/.tekton/worker` (Python 3.12,
`tekton-app` + `tekton-opensees` at the same version), and reads the Dlubal
key from `TEKTON_API_KEY`/`DLUBAL_API_KEY` or `~/.tekton/.env`.
`TEKTON_WORKER_PYTHON` overrides the location. `Tekton Info` reports both.

## Every release

Tooling: `uv sync --extra dev --extra release`.

1. `uv run invoke bump --part patch` (or `minor`/`major`) - every
   `pyproject.toml`, the internal pins, `__version__`, then `uv lock`.
2. `CHANGELOG.md`: rename `## [Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD`,
   open a new empty `## [Unreleased]` above it.
3. `uv run invoke check-release` - versions agree, no user paths or API keys
   in tracked files (Grasshopper writes the repo path into `.ghx` path panels
   on every save), lint, tests.
4. `git commit -am "Release X.Y.Z"`, `git tag vX.Y.Z`,
   `git push origin main vX.Y.Z`.
5. The tag runs `release.yml`: verify, build, check that `tekton-gh`
   installs on Python 3.9 from the wheels, publish to PyPI (trusted
   publishing, environment `pypi`). Wait for green.
6. *Actions -> publish_yak -> Run workflow*, `test`. It refuses unless
   `X.Y.Z` is on PyPI.
7. In a clean Rhino 8 (no checkout, no `TEKTON_REPO`): `_TestPackageManager`,
   install `tekton`, restart, run an example with the OpenSees backend; with
   an RFEM licence on Windows, the RFEM backend too.
8. *publish_yak* again, `prod`.
9. `gh release create vX.Y.Z` with the changelog section; update the
   Food4Rhino listing.

A broken release is never overwritten: `yak yank tekton X.Y.Z` and yank on
pypi.org, then release `X.Y.(Z+1)` through every step above.

## One-time setup still open

- `compas_timber` with the plate API released to PyPI; replace the git pin
  in `pyproject.toml` and `requirements.txt`, and lift the `compas < 2.16`
  cap in `tekton_core`. `release.yml` refuses to publish until the git
  pin is gone.
- PyPI: a trusted publisher per project (repository
  `gramaziokohler/tekton`, workflow `release.yml`, environment `pypi`), and
  the `pypi` environment in the repository settings.
- Yak: confirm which McNeel account owns `YAK_DF_TOKEN` - the first push
  makes it the owner of `tekton`.
- The worker bootstrap: something that creates `~/.tekton/worker` for the
  user (a setup component, or `install.py` installing from PyPI).
- A real package icon (`packages/tekton_gh/yak_template/icon.png` is the
  Display icon as a placeholder).
