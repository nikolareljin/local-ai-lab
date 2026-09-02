# Lesson 15 · Documentation from Sprint Changes

**PDF:** [this lesson](https://nikolareljin.github.io/local-ai-lab/pdf/LESSON15.pdf) · **Install (Linux · macOS · Windows):** [guide](../INSTALL.md) · [PDF](https://nikolareljin.github.io/local-ai-lab/pdf/INSTALL.pdf)

> **Part of [local-ai-lab](https://nikolareljin.github.io/local-ai-lab/)** - a hands-on course for building local AI.
>
> **Course home:** https://nikolareljin.github.io/local-ai-lab/
> **Source:** https://github.com/nikolareljin/local-ai-lab
>
> **Lessons:** [1 · RAG](../LESSON1.md) → [2 · MCP](../LESSON2.md) → [3 · Hybrid retrieval](../lessons/03-hybrid-retrieval-reranking/README.md) → [4 · RAG safety](../lessons/04-rag-safety-prompt-injection/README.md) → [5 · RAG evaluation](../lessons/05-rag-evaluation-regression-testing/README.md) → 6 · Repo assistant → [7 · LangChain](../lessons/07-langchain-rag/README.md) → [8 · LangGraph](../lessons/08-langgraph/README.md) → [9 · Ollama tools](./LESSON9-ollama.md) → 10 · Semantic Kernel → 11 · Bedrock → 12 · Google ADK → [13 · AI-assisted testing](./LESSON13-ai-assisted-testing.md) → [14 · AI code review](./LESSON14-ai-code-review.md) → **15 · Docs from changes (you are here)**
>
> **Status: planned.** Outline below; full step-by-step coming later. ⭐ the repo to follow along.

---

## The idea

Point a model at a sprint's commits and ask for release notes and you get a tidied-up list of commit
subjects. That is not documentation. **A changelog written from commit subjects is a list of commit
subjects**, and the reader wanted to know what changed *for them*.

Getting further means giving the pipeline more than the log: the diff, the pull request discussion,
and the issue it closed - which together carry the *why* that a commit subject drops. And it means
letting the pipeline **refuse**, because a sprint full of refactors and dependency bumps has no
user-visible changes, and saying so is the correct output rather than a failure.

## What you'll learn

- **Source across commits, pull requests and issues** - the reason for a change is almost never in
  the commit message
- **Group by audience, not by file** - "what changed for an API consumer" is a useful heading;
  "changes in `src/utils/`" is not
- **The no-user-visible-change filter** - the hardest and most valuable step, and the one every tool
  in this space skips
- **Cite back to pull request numbers** - the course's citation contract, one last time: every claim
  in the notes traceable to the change that produced it
- **Write into the format the repo already has** - a generator that invents its own changelog shape
  will be quietly reverted by the first human who edits it

## Builds on

| Concept | From |
|---------|------|
| grounded answers with citations | [Lesson 1](../LESSON1.md) |
| repo-aware retrieval | [Lesson 6](../lessons/06-repo-aware-assistant/README.md) |
| "is the output any good?" as a tracked number | [Lesson 5](../lessons/05-rag-evaluation-regression-testing/README.md) |
| **refusing to describe what did not change** | **Lesson 15 (this one)** |

> **The worked example is this repository.** `CHANGELOG.md` and `.github/workflows/release.yml`
> already turn a changelog section into a tagged release - so the last thing the course does is
> generate the input to a pipeline you have been reading since Lesson 1.

## Prerequisites

[Lesson 1](../LESSON1.md), and a repository with a few sprints of history. Language-agnostic: the
input is your version control, not your source.

## The end of the course

That is Lesson 15, and the end of the curriculum. Go back to the [syllabus](../SYLLABUS.md) for the
whole arc - or pick the one thing here you would actually use, and point it at your own repository.
The last exercise in every lesson has been the same one.

---

*Course: [nikolareljin.github.io/local-ai-lab](https://nikolareljin.github.io/local-ai-lab/) · Author: [Nik Reljin](https://www.linkedin.com/in/nikolareljin)*
