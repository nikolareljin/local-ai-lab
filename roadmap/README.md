# Roadmap - planned lesson outlines

These are **outline guides for lessons that aren't built yet**, numbered to their place in the
[course curriculum](../README.md#curriculum). They sketch what each lesson will cover and how it
maps back to the primitives you build in Lessons 1-2 and 3-9 - but they have no runnable code yet.

| # | Outline | Topic |
|---|---------|-------|
| 11 | [LESSON11-semantic-kernel.md](./LESSON11-semantic-kernel.md) | Microsoft Semantic Kernel (C# / .NET) |
| 12 | [LESSON12-bedrock.md](./LESSON12-bedrock.md) | AWS Bedrock Agents |
| 13 | [LESSON13-google-adk.md](./LESSON13-google-adk.md) | Google AI Development Kit (ADK) |
| 14 | [LESSON14-ai-assisted-testing.md](./LESSON14-ai-assisted-testing.md) | AI-assisted testing |
| 15 | [LESSON15-ai-code-review.md](./LESSON15-ai-code-review.md) | AI code review & issue detection |
| 16 | [LESSON16-docs-from-changes.md](./LESSON16-docs-from-changes.md) | Documentation from sprint changes |

**Live lessons live elsewhere:** Lessons 1-2 are hand-authored at the repo root
([`LESSON1.md`](../LESSON1.md), [`LESSON2.md`](../LESSON2.md)); Lessons 3-10 are config-driven under
[`lessons/`](../lessons/). When a roadmap lesson is implemented it graduates to a full
`lessons/NN-slug/` lesson and leaves this directory.

Lessons 11-13 finish the **framework tour** - the same agent, rebuilt on somebody else's runtime.
Lessons 14-16 are **applied dev workflows**: they add no new primitives, they point the ones you
already have at your own repository, and each one ends by asking you to run it there.

## Planned, not outlined yet

Ideas for lessons after 16, in no fixed order. Each will get an outline here before it is built.

- **MongoDB vector search** - the Lesson 1 and 3 retriever on MongoDB Community, then on Atlas.
- **LoRA fine-tuning** - train a small local model for one task, and compare it with prompting and with a System One model.
- **Structured outputs and constrained decoding** - JSON schemas in Ollama and llama.cpp grammars: making an LLM return only valid types.
- **Observability** - tracing the course's RAG, tool and agent loops with OpenTelemetry and Langfuse, self-hosted.
- **Local speech and vision** - whisper.cpp and vision models on CPU, feeding the same loops.

Also planned, as a separate download rather than a lesson: **AI developer tools** - OpenRouter,
Cursor, AWS Kiro CLI and Claude Code: what each is, where your code and data go, and when to use
it next to this course.
