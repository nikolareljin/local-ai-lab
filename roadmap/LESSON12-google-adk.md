# Lesson 12 · Google AI Development Kit (ADK)

**PDF:** [this lesson](https://nikolareljin.github.io/local-ai-lab/pdf/LESSON12.pdf) · **Install (Linux · macOS · Windows):** [guide](../INSTALL.md) · [PDF](https://nikolareljin.github.io/local-ai-lab/pdf/INSTALL.pdf)

> **Part of [local-ai-lab](https://nikolareljin.github.io/local-ai-lab/)** - a hands-on course for building local AI.
>
> **Course home:** https://nikolareljin.github.io/local-ai-lab/
> **Source:** https://github.com/nikolareljin/local-ai-lab
>
> **Lessons:** [1 · RAG](../LESSON1.md) → [2 · MCP](../LESSON2.md) → [3 · Hybrid retrieval](../lessons/03-hybrid-retrieval-reranking/README.md) → [4 · RAG safety](../lessons/04-rag-safety-prompt-injection/README.md) → [5 · RAG evaluation](../lessons/05-rag-evaluation-regression-testing/README.md) → 6 · Repo assistant → [7 · LangChain](./LESSON7-langchain.md) → [8 · LangGraph](./LESSON8-langgraph.md) → [9 · Ollama tools](./LESSON9-ollama.md) → [10 · Semantic Kernel](./LESSON10-semantic-kernel.md) → [11 · Bedrock Agents](./LESSON11-bedrock.md) → **12 · Google ADK (you are here)**
>
> **Status: planned.** Outline below; full published slideshow lesson + step-by-step coming later.
> ADK **runs locally** (`adk run` / `adk web`) against Gemini. ⭐ the repo to follow along.

---

## The idea

**Google's Agent Development Kit (ADK)** is an open-source framework for building, evaluating, and
deploying agents, designed around **Gemini** but model-agnostic. In this final lesson you rebuild the
document agent with ADK and run it locally - closing the loop on "the same agent, six different ways."

## What you'll learn

- **ADK agents** - defining an `Agent` with instructions, a model, and tools
- **Tools** - exposing a Python function (your `search_docs`) as an ADK tool
- **Sessions & runners** - running the agent locally with `adk run` (CLI) or `adk web` (dev UI)
- **Gemini integration** - using `gemini-2.5-flash`, plus how to point ADK at other models
- **Evaluation** - ADK's built-in eval harness for checking agent behavior

## The design we'll build

```python
from google.adk.agents import Agent
from localrag.config import load_config
from localrag.engine import get_retriever

def search_docs(query: str) -> str:
    """Search the user's local documents and return cited passages."""
    hits = get_retriever(load_config()).search(query, 5)
    return "\n\n".join(f"[{h['source']}:{h['page_number']}] {h['text']}" for h in hits)

root_agent = Agent(
    name="docs_agent",
    model="gemini-2.5-flash",
    instruction="Answer from search_docs results and cite [source:page]. "
                "If it's not in the documents, say so.",
    tools=[search_docs],
)
# Run locally:  adk run .   (or)   adk web
```

> **The finale:** the `search_docs` function is, once again, Lesson 1's retriever. Across MCP,
> Ollama, Semantic Kernel, Bedrock, and ADK, the *capability* never changed - only the framework
> wrapping it. That's the whole point of the course: master the primitives, and every framework is
> just syntax.

## Builds on

| Concept | From |
|---------|------|
| `search_docs` retriever tool | [Lesson 1](../LESSON1.md) |
| function/tool calling | [Lesson 9](./LESSON9-ollama.md) |
| agent frameworks compared | [Lessons 7](./LESSON7-langchain.md), [8](./LESSON8-langgraph.md), [10](./LESSON10-semantic-kernel.md) |
| **ADK agents, tools, runners, eval** | **Lesson 12 (this one)** |

## Prerequisites

Python, a Gemini API key (`GEMINI_API_KEY`), and `pip install google-adk`. [Lesson 1](../LESSON1.md)
provides the retriever the agent calls.

## Course complete

You've built the same local-first document agent six ways - from a hand-rolled RAG pipeline up
through MCP, local function calling, Semantic Kernel, Bedrock Agents, and ADK - and you understand
every layer. Back to [the course home](https://nikolareljin.github.io/local-ai-lab/).

---

*Course: [nikolareljin.github.io/local-ai-lab](https://nikolareljin.github.io/local-ai-lab/) · Author: [Nik Reljin](https://www.linkedin.com/in/nikolareljin)*
