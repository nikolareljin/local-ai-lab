# Lessons — authoring & running guide (internal)

Lessons are added **incrementally — one per pull request**. From **Lesson 3 onward** each lesson is
**config-driven**: a single `lesson.json` describes how to run it *and* how to present it. Lessons 1–2
keep their bespoke handlers in [`../run`](../run).

## Layout

```
lessons/NN-slug/        # the NN- prefix IS the lesson number → reordering is a directory rename
  lesson.json           # the single source of truth (run + show)
  README.md             # the written lesson (teaching prose)
  python/ node/ dotnet/  # code, per language (only what the lesson needs)
  data/  story/  media/  # corpora / assets referenced by elements
  expected-output.txt    # optional canonical output
```

## `lesson.json`

Top-level: `title`, `slug`, `status` (`working` | `guide` | `planned`), `summary`, `cluster`,
`priority`, `languages`, `defaultLanguage`, `defaultAction`, and **`elements`** — an ordered list of
typed items (they may be intermingled):

| `type` | fields | drives |
|--------|--------|--------|
| `command` | `action`, `lang?`, `shell`, `venv?`, `note?` | **running** — `./run -l N <action>` executes every command with that `action` (and matching/`null` `lang`), in order |
| `code` | `file`, `lang?`, `note?` | show a code file |
| `config` | `file`, `note?` | show a config / data file |
| `text` | `title?`, `text` \| `file` | copy/paste block (e.g. a prompt) |
| `note` | `title?`, `text` \| `file` | instruction text |
| `image` / `video` / `media` | `file` \| `url`, `kind?`, `alt?`, `note?` | rendered **in-place** in the HTML preview |

Any element may be `lang`-tagged for per-language walkthroughs. File paths are relative to the lesson
directory. Add code/commands/media by dropping files and referencing them here — no engine changes.

## Running & previewing (`./run`)

```bash
./run list                       # all lessons (1-2 + the config-driven registry)
./run -l N                       # the lesson's defaultAction
./run -l N <action>              # e.g. demo · test · web   (any command action in lesson.json)
./run -l N --lang node|csharp    # pick a language

# Operation B — go through the instructions (no GitHub Pages needed):
./run -l N show                  # terminal walkthrough of every element
./run -l N show --lang node      # filtered to one language
./run -l N preview               # serve the rendered instructions at http://127.0.0.1:<port>
./run -l N show --html > x.html  # standalone HTML page (open in a browser)
```

### Testing the instructions locally without GitHub Pages

`./run -l N preview` renders the lesson as the **same step-by-step slideshow** the published lessons
use (deep-linkable `#step-N`, dots, prev/next, copy buttons) and serves it on localhost. It is
**template-driven**: [`tools/templates/lesson-preview.html`](../tools/templates/lesson-preview.html)
*references* the real `docs/assets/style.css` + `slider.js` (not inlined) and is filled from
`lesson.json` — one step per element, with `code`/`config` steps reading their files. So a local
preview equals what gets published, with nothing deployed. `show` is the quick terminal version;
`show --html` writes a standalone file (assets referenced by absolute path).

## Authoring a new lesson

```bash
tools/new-lesson.sh NN slug "Title"   # scaffold from lessons/_template/
# add code under python/ node/ dotnet/, reference it in lesson.json elements
./run -l NN show                      # check the walkthrough
./run -l NN preview                   # check the rendered page
tools/sync-curriculum.sh              # regenerate lessons/CURRICULUM.md
```

## Reordering

The number lives only in the directory prefix, so reordering is a rename:

```bash
tools/renumber-lessons.sh swap 5 6    # swap two lessons
tools/renumber-lessons.sh move 7 4    # move a lesson to a free number
```

Cross-lesson links use slugs (not numbers) so they survive a renumber.

## Engine

[`../tools/lesson.py`](../tools/lesson.py) — `list` · `run` · `show` (with `--html`) · `preview`. The
bash [`../run`](../run) is a thin entry point: Lessons 1–2 use bespoke handlers; lessons 3+ delegate
to the engine. Reuses [`../scripts/include.sh`](../scripts/include.sh) (`PYTHON_BIN`, `ensure_venv`).
