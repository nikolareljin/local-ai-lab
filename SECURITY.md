# Security Policy

`local-ai-lab` is a teaching project that runs locally, but it ships real code (a Flask web UI, an
MCP server, document parsing, and provider integrations) and a whole lesson on **RAG safety &
prompt injection** (Lesson 4). Security reports are taken seriously.

## Reporting a vulnerability

**Please report privately — do not open a public issue or PR for a security problem.**

Email **nikola.reljin@gmail.com** with:

- a description of the issue and the impact you foresee,
- the affected file(s) / lesson / component,
- steps to reproduce or a minimal proof of concept,
- any suggested fix, if you have one.

You can expect an acknowledgement within **5 business days**. Once the issue is confirmed, a fix is
prepared and released before the details are made public. Please give a reasonable window for a fix
before any public disclosure, and avoid accessing or modifying data that isn't yours while testing.

## Scope

In scope: the `localrag` package (web UI, MCP server, extraction/retrieval), the build/maintenance
tooling under `tools/`, and CI workflow configuration.

Out of scope: vulnerabilities in third-party dependencies or model providers (report those
upstream), and findings that require a compromised local machine to exploit.

## Good to know

Lessons run entirely on your machine and use placeholder corpora. Never commit real secrets — copy
the provided `.env.example` to a local `.env`, and keep API keys out of documents you index.
