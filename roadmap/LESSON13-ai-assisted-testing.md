# Lesson 13 · AI-Assisted Testing

**PDF:** [this lesson](https://nikolareljin.github.io/local-ai-lab/pdf/LESSON13.pdf) · **Install (Linux · macOS · Windows):** [guide](../INSTALL.md) · [PDF](https://nikolareljin.github.io/local-ai-lab/pdf/INSTALL.pdf)

> **Part of [local-ai-lab](https://nikolareljin.github.io/local-ai-lab/)** - a hands-on course for building local AI.
>
> **Course home:** https://nikolareljin.github.io/local-ai-lab/
> **Source:** https://github.com/nikolareljin/local-ai-lab
>
> **Lessons:** [1 · RAG](../LESSON1.md) → [2 · MCP](../LESSON2.md) → [3 · Hybrid retrieval](../lessons/03-hybrid-retrieval-reranking/README.md) → [4 · RAG safety](../lessons/04-rag-safety-prompt-injection/README.md) → [5 · RAG evaluation](../lessons/05-rag-evaluation-regression-testing/README.md) → 6 · Repo assistant → [7 · LangChain](../lessons/07-langchain-rag/README.md) → [8 · LangGraph](../lessons/08-langgraph/README.md) → [9 · Ollama tools](./LESSON9-ollama.md) → 10 · Semantic Kernel → 11 · Bedrock → 12 · Google ADK → **13 · AI-assisted testing (you are here)** → 14 · AI code review → 15 · Docs from changes
>
> **Status: planned.** Outline below; full step-by-step coming later. ⭐ the repo to follow along.

---

## The idea

Every lesson in this course ships a test, and you have been reading them all along. This lesson turns
the model on the test suite itself: generate tests from a change, run them, read the failures, and let
the failure guide the fix.

The uncomfortable part first, because it is the whole lesson: **a generated test that passes is
worthless.** It tells you the code does what it currently does. What you want is a test that **fails
for the right reason** before you fix anything - and a model asked to "write tests for this file" will
almost never give you one, because it reads the implementation and describes it back to you.

## What you'll learn

- **Generate from a diff, not a repo** - the change is the specification; the rest of the file is noise
- **Fail first** - make the model write the test against the *intended* behaviour, run it red, then fix
- **Judge a suite by what it catches** - break a line on purpose and see whether anything goes red.
  A suite that survives a deliberate bug is decoration, however many tests it has
- **Keep the model out of the assertion** - it proposes, you approve. An assertion nobody read is a
  future false green
- **Where it genuinely wins** - edge cases, boundary values, and the table-driven cases people skip

## Builds on

| Concept | From |
|---------|------|
| golden sets and regression gates | [Lesson 5](../lessons/05-rag-evaluation-regression-testing/README.md) |
| indexing a repo into cited passages | [Lesson 6](../lessons/06-repo-aware-assistant/README.md) |
| shipping it as a callable tool | [Lesson 2](../LESSON2.md) |
| **generated tests, and what they are worth** | **Lesson 13 (this one)** |

## Prerequisites

[Lesson 1](../LESSON1.md). Lessons 5 and 6 help: a generated suite needs the same regression
discipline as a golden set, and the generator needs to read your repo before it can test it.

## Next lesson

[**Lesson 14 · AI Code Review & Issue Detection →**](./LESSON14-ai-code-review.md)

---

*Course: [nikolareljin.github.io/local-ai-lab](https://nikolareljin.github.io/local-ai-lab/) · Author: [Nik Reljin](https://www.linkedin.com/in/nikolareljin)*
