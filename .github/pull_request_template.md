<!-- Describe the change in a few sentences: what it does, and why. -->
<!-- Erase whatever does not apply. -->

### What kind of change is this?

- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change (the neutral model, a component's inputs, or a file format changes shape)
- [ ] Other (docs, configuration, tooling)

### Before merging

- [ ] `uv run pytest` is green.
- [ ] `uv run ruff check .` is clean.
- [ ] New behaviour has a test that would fail without the change.
- [ ] `CHANGELOG.md` has a line under `Unreleased` (if the change is worth remembering).

### If this touches analysis results

Numbers coming out of a solver are the part of this project that can be wrong
without anything failing. If your change affects them, say here how you know
they are right — a closed-form comparison, a cross-check against another
backend, or a recorded fixture.

- [ ] Not applicable.
