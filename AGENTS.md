# AGENTS.md

Guidance for agents working in `local-ai-lab` - a hands-on course for building local AI. Lesson 1
(RAG) ships as a working Python app; the course site lives in `docs/`.

## Project Structure & Module Organization
- `localrag/` - Lesson 1 application code.
  - `__main__.py` - CLI (`index`, `ask`, `web`); `config.py` - env/.env config (no hard-coded paths).
  - `extract.py` · `chunk.py` · `store.py` · `retriever.py` · `prompts.py` · `engine.py`.
  - `providers/` - pluggable LLMs: `claude_code`, `ollama`, `gemini`, `openai`.
  - `web.py` + `templates/index.html` - Flask drag-and-drop UI.
- `documents/` - the RAG corpus (drop files here). Committed samples: `sample_manual.md`, `rag_tutorial.md`.
- `docs/` - GitHub Pages course site: `index.html`, `lesson-1-rag.html`, `lesson-2-mcp.html`, `assets/`.
- `scripts/` - `script-helpers` submodule + `include.sh`; root `start`/`stop`/`status`/`update`.
- `tests/` - offline smoke tests.

## Build, Test, and Development Commands
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pytest -q                              # offline tests
python -m localrag ask "your question" # one-shot RAG query
python -m localrag web                 # drag-and-drop UI on :5000
./update && ./start                    # sync submodule, launch the app
./run -l N lesson                      # read a lesson locally in a browser (any lesson, no Pages)
./run -l N demo | test                 # run it without a model / run its offline test
./run -l N show                        # walk a config-driven lesson's code + configs (Lessons 3+)
```

Lessons 3+ are config-driven (`lessons/NN-slug/lesson.json`); see
[`lessons/README.md`](lessons/README.md) for the element model and the run/show/lesson engine.

## Coding Style & Naming Conventions
- Python, PEP 8, 4-space indent, type hints. `snake_case` functions, `PascalCase` classes.
- Keep it **tiny and readable** - this is a teaching repo. Prefer small, composable functions.
- Never hard-code paths; read them from `config.py` / environment.
- Guard heavy/optional imports (`numpy`, provider SDKs) inside the functions that use them.
- Course site is plain static HTML/CSS/JS (no build step); `docs/.nojekyll` disables Jekyll.

## Code Excerpts In Lesson Pages - recompute after every edit
A lesson page shows code by line range: `"file": "python/policy.py", "lines": "26-45",
"symbol": "decide"` in `lesson.json`. **Never type or adjust a `lines` value by hand.** Every code
step names a `symbol`; `tools/lesson_lines.py` computes `lines` from it.

After changing **any** file a lesson shows (Python, Node.js or C#), in this order:

```bash
python3 tools/lesson_lines.py --write   # recompute every range from its symbol
./run -l N build                        # rebuild the page of each lesson you touched
python3 tools/check_docs.py             # must pass: ranges, and pages that match them
npm --prefix e2e test                   # the same, as a browser sees it (after `npm --prefix e2e ci`)
```

- A new code step needs a `symbol`: a function, class or constant (`decide`), a method
  (`Replay.next`), a span (`rank..rrf`), `marker:<text>` or `around:<text>`. See the header of
  `tools/lesson_lines.py`.
- Renaming or deleting a function a lesson shows breaks the check on purpose. Update the `symbol`.
- Do this for every language of the step. A range that is right in Python and stale in C# is
  the same bug.

Why: an edit above a function moves it, the range keeps pointing at the old lines, and the page
shows the wrong code without failing anything. Lessons 6, 7 and 8 were published that way.

## Testing Guidelines
- Tests in `tests/test_*.py` must stay **offline** (no network, no LLM). Cover the retrieval core.

## Commit & Pull Request Guidelines
- Conventional Commits: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `ci:`.
- Author is **Nik Reljin** only. Do **not** add `Co-Authored-By`, `Signed-off-by`, or any
  AI-attribution trailer.

## Security & Configuration
- Never commit `.env`, API keys, or user documents. `.gitignore` keeps `documents/*` (except the
  committed samples) and `.localrag/` out of git. Mirror new settings in `.env.example`.
