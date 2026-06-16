# Contributing to local-ai-lab

Thanks for your interest! This is a hands-on course for building local, private AI **from
scratch**. Contributions that keep lessons small, readable, and runnable on a laptop - no Docker,
no cloud requirement - are very welcome.

By participating you agree to abide by our [Code of Conduct](./CODE_OF_CONDUCT.md).

## Ways to contribute

- **Fix a bug or a typo** in a lesson, the `localrag` package, or the tooling.
- **Improve an existing lesson** - clearer prose, a better example, a missing edge case.
- **Propose a new lesson.** Open a [lesson request](https://github.com/nikolareljin/local-ai-lab/issues/new/choose)
  first so we can agree on scope and where it fits the curriculum before you write it.

## One lesson per pull request

Lessons are added **incrementally - one per pull request** (see
[`lessons/README.md`](./lessons/README.md)). From **Lesson 3 onward** each lesson is
**config-driven** via a single `lesson.json`. Keep a PR focused on one lesson or one concern; this
keeps reviews fast and the history readable.

## Development setup

```bash
git clone https://github.com/nikolareljin/local-ai-lab.git
cd local-ai-lab
git submodule update --init --recursive   # pulls the script-helpers submodule

python -m venv venv
source venv/bin/activate                   # Windows: see INSTALL.md (Activate.ps1 / activate.bat)
pip install -e '.[dev]'                     # installs localrag + pytest; in cmd.exe drop the quotes
```

Run a lesson with the wrapper script:

```bash
./run -l 1                 # launch Lesson 1 (web UI by default)
./run -l 3 --lang node     # a lesson in another language, where supported
./run -l 1 test            # run that lesson's tests
```

## Running tests

```bash
pytest -q                  # the full offline test suite (no network / API keys needed)
```

CI mirrors this: it syntax-checks every module with `py_compile` and runs `pytest -q`. The
README "Lessons & downloads" table is generated - if you add a lesson or rebuild PDFs, run
`python3 tools/sync-readme-downloads.py` to regenerate it (and `--check` to verify it's up to
date before you commit).

## Coding style

- **Commits:** [Conventional Commits](https://www.conventionalcommits.org/) - `feat:`, `fix:`,
  `docs:`, `chore:`, `refactor:`, with an optional scope like `feat(lessons):`.
- **Python:** PEP 8, 4-space indent, `snake_case` functions, type hints on public functions.
- Keep examples **small and readable** - the teaching value is in code a reader can follow. This is a
  teaching demo, so prefer the simplest version that makes the point; see
  [PRODUCTION_NOTES.md](./PRODUCTION_NOTES.md) for what's intentionally left out (and why).
- Update `CHANGELOG.md` (under `## [Unreleased]`) when you change observable behavior.

## Pull request checklist

- [ ] One lesson / one concern per PR
- [ ] `pytest -q` passes and `py_compile` is clean
- [ ] Docs and the generated README table updated if behavior changed
- [ ] A `CHANGELOG.md` entry under `## [Unreleased]`
