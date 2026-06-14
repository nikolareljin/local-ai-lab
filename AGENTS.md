# AGENTS.md

Guidance for agents working in `local-ai-lab` — a hands-on course for building local AI. Lesson 1
(RAG) ships as a working Python app; the course site lives in `docs/`.

## Project Structure & Module Organization
- `localrag/` — Lesson 1 application code.
  - `__main__.py` — CLI (`index`, `ask`, `web`); `config.py` — env/.env config (no hard-coded paths).
  - `extract.py` · `chunk.py` · `store.py` · `retriever.py` · `prompts.py` · `engine.py`.
  - `providers/` — pluggable LLMs: `claude_code`, `ollama`, `gemini`, `openai`.
  - `web.py` + `templates/index.html` — Flask drag-and-drop UI.
- `documents/` — the RAG corpus (drop files here). Committed samples: `sample_manual.md`, `rag_tutorial.md`.
- `docs/` — GitHub Pages course site: `index.html`, `lesson-1-rag.html`, `lesson-2-mcp.html`, `assets/`.
- `scripts/` — `script-helpers` submodule + `include.sh`; root `start`/`stop`/`status`/`update`.
- `tests/` — offline smoke tests.

## Build, Test, and Development Commands
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pytest -q                              # offline tests
python -m localrag ask "your question" # one-shot RAG query
python -m localrag web                 # drag-and-drop UI on :5000
./update && ./start                    # sync submodule, launch the app
./run -l N show | preview              # walk through / preview a config-driven lesson (no Pages)
```

Lessons 3+ are config-driven (`lessons/NN-slug/lesson.json`); see
[`lessons/README.md`](lessons/README.md) for the element model and the run/show/preview engine.

## Coding Style & Naming Conventions
- Python, PEP 8, 4-space indent, type hints. `snake_case` functions, `PascalCase` classes.
- Keep it **tiny and readable** — this is a teaching repo. Prefer small, composable functions.
- Never hard-code paths; read them from `config.py` / environment.
- Guard heavy/optional imports (`numpy`, provider SDKs) inside the functions that use them.
- Course site is plain static HTML/CSS/JS (no build step); `docs/.nojekyll` disables Jekyll.

## Testing Guidelines
- Tests in `tests/test_*.py` must stay **offline** (no network, no LLM). Cover the retrieval core.

## Commit & Pull Request Guidelines
- Conventional Commits: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `ci:`.
- Author is **Nik Reljin** only. Do **not** add `Co-Authored-By`, `Signed-off-by`, or any
  AI-attribution trailer.

## Security & Configuration
- Never commit `.env`, API keys, or user documents. `.gitignore` keeps `documents/*` (except the
  committed samples) and `.localrag/` out of git. Mirror new settings in `.env.example`.
