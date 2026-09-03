# Roadmap - planned lesson outlines

These are **outline guides for lessons that aren't built yet**, numbered to their place in the
[course curriculum](../README.md#curriculum). They sketch what each lesson will cover and how it
maps back to the primitives you build in Lessons 1-2 and 3-8 - but they have no runnable code yet.

| # | Outline | Topic |
|---|---------|-------|
| 9 | [LESSON9-ollama.md](./LESSON9-ollama.md) | Ollama + function calling |
| 10 | [LESSON10-semantic-kernel.md](./LESSON10-semantic-kernel.md) | Microsoft Semantic Kernel (C# / .NET) |
| 11 | [LESSON11-bedrock.md](./LESSON11-bedrock.md) | AWS Bedrock Agents |
| 12 | [LESSON12-google-adk.md](./LESSON12-google-adk.md) | Google AI Development Kit (ADK) |
| 13 | [LESSON13-ai-assisted-testing.md](./LESSON13-ai-assisted-testing.md) | AI-assisted testing |
| 14 | [LESSON14-ai-code-review.md](./LESSON14-ai-code-review.md) | AI code review & issue detection |
| 15 | [LESSON15-docs-from-changes.md](./LESSON15-docs-from-changes.md) | Documentation from sprint changes |

**Live lessons live elsewhere:** Lessons 1-2 are hand-authored at the repo root
([`LESSON1.md`](../LESSON1.md), [`LESSON2.md`](../LESSON2.md)); Lessons 3-8 are config-driven under
[`lessons/`](../lessons/). When a roadmap lesson is implemented it graduates to a full
`lessons/NN-slug/` lesson and leaves this directory.

Lessons 9-12 finish the **framework tour** - the same agent, rebuilt on somebody else's runtime.
Lessons 13-15 are **applied dev workflows**: they add no new primitives, they point the ones you
already have at your own repository, and each one ends by asking you to run it there.
