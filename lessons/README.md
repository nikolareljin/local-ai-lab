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
| `code` | `file`, `lang?`, `note?`, `notes?` | show a code file (referenced, never pasted), syntax-highlighted; `notes` is a list of remarks shown **under** the snippet |
| `config` | `file`, `note?`, `notes?` | show a config / data file (same note rules) |
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
./run -l N build                 # write the publishable docs/lesson-N-slug.html (GitHub Pages)
./run -l N show --html > x.html  # standalone HTML page (open in a browser)
```

The preview is the **same step slideshow as Lessons 1-2** (language selector, dots, prev/next,
`#step-N` deep links, copy buttons). `build` emits a page into `docs/` that references `./assets`
relatively, so once committed it renders on GitHub Pages exactly like the hand-authored lessons.

### Testing the instructions locally without GitHub Pages

`./run -l N preview` renders the lesson as the **same step-by-step slideshow** the published lessons
use (deep-linkable `#step-N`, dots, prev/next, copy buttons) and serves it on localhost. It is
**template-driven**: [`tools/templates/lesson-preview.html`](../tools/templates/lesson-preview.html)
*references* the real `docs/assets/style.css` + `slider.js` (not inlined) and is filled from
`lesson.json` — one step per element, with `code`/`config` steps reading their files. So a local
preview equals what gets published, with nothing deployed. `show` is the quick terminal version;
`show --html` writes a standalone file (assets referenced by absolute path).

## Experiment GUI (the shared `web` action)

A lesson can ship a **local, interactive GUI** — the same dark, Lesson-1-style page every lesson
shares — so a cloned-repo user can **tune parameters and watch the results (and the numbers behind
them) change live, without editing any code**. The GitHub Pages page stays static; the experimenting
happens locally.

It is a thin convention, not new engine machinery:

1. Add a `python/web.py` that imports the shared scaffold and supplies three things the lesson owns —
   its tunable **PARAMS**, a few **EXAMPLES**, and a `search(query, values)` that runs the lesson's
   own compute and returns rankings + a "why" breakdown. Start from
   [`_template/python/web.py`](_template/python/web.py).
2. Declare a `web` command element in `lesson.json`:
   ```json
   { "type": "command", "action": "web", "lang": "python", "venv": true, "shell": "python python/web.py" }
   ```
3. To make `./run -l N` open the GUI by default (like Lesson 1), set `"defaultAction": "web"`. Keep the
   byte-checked one-shot reachable as `./run -l N demo`.

The look, the live sliders/toggles, the `/api/config` + `/api/search` wiring, and the score-breakdown
renderer all live once in [`../tools/lesson_web.py`](../tools/lesson_web.py) +
[`../tools/templates/lesson-gui.html`](../tools/templates/lesson-gui.html). `serve(...)` takes the param
spec + `search` fn; `search` returns `{"arms": [...], "blocks": [...]}` where each block is a
`stats` / `tokens` / `table` / `note` (see the scaffold's module docstring). Lesson 3
([`03-hybrid-retrieval-reranking/python/web.py`](03-hybrid-retrieval-reranking/python/web.py)) is the
reference implementation: BM25 `k1`/`b`, the RRF `k`, and a synonyms toggle, with a per-document
score breakdown. The GUI is Python-only by convention; cross-language **algorithm** parity stays in
the byte-checked `demo` ports.

## Authoring a new lesson

```bash
tools/new-lesson.sh NN slug "Title"   # scaffold from lessons/_template/
# add code under python/ node/ dotnet/, reference it in lesson.json elements
./run -l NN show                      # check the walkthrough
./run -l NN preview                   # check the rendered page
tools/sync-curriculum.sh              # regenerate lessons/CURRICULUM.md
python tools/build_lesson_pdfs.py     # build the PDF (lessons are auto-discovered → docs/pdf/LESSONNN.pdf)
python tools/sync-readme-downloads.py # refresh the README "Lessons & downloads" table
```

Both `build_lesson_pdfs.py` and `sync-readme-downloads.py` **auto-discover** lessons from disk
(root `LESSON<n>.md`, `lessons/<NN>-slug/README.md`, `roadmap/LESSON<n>-slug.md`) — so a new lesson is
picked up with no edits to either tool. Run `sync-readme-downloads.py --check` in CI to fail when the
README table is stale.

## Reordering

The number lives only in the directory prefix, so reordering is a rename:

```bash
tools/renumber-lessons.sh swap 5 6    # swap two lessons
tools/renumber-lessons.sh move 7 4    # move a lesson to a free number
```

A published page's filename is `lesson-<number>-<slug>.html` and the nav links to it by that name, so
renumbering changes the URL. After a `swap`/`move`, rebuild the affected pages (`./run -l N build`) and
update any cross-lesson links — the directory rename alone isn't enough.

## Engine

[`../tools/lesson.py`](../tools/lesson.py) — `list` · `run` · `show` (with `--html`) · `preview`. The
bash [`../run`](../run) is a thin entry point: Lessons 1–2 use bespoke handlers; lessons 3+ delegate
to the engine. Reuses [`../scripts/include.sh`](../scripts/include.sh) (`PYTHON_BIN`, `ensure_venv`).
