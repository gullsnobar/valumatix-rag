# AI usage

## Tools and models

| Tool | Model | Use |
| --- | --- | --- |
| Claude by Anthropic, claude.ai chat | Claude Opus 5.5 | Planning, architecture decisions, writing Codex prompts, drafting the fictional corpus and golden set, and reviewing results |
| OpenAI Codex in VS Code | model: TBD, fill in from the Codex settings | Implementing code from the prompts and helping verify changes |

## Configuration

The observed Codex session used a workspace-write sandbox with write access to the repository, restricted network access, and automatic review for requests to run outside the sandbox. The documentation task was restricted to documentation edits and excluded Git commands.

## How AI was used

The author planned the project with Claude and implemented it through Codex. The author reviewed the changes, ran each step locally, and fixed issues found during testing and evaluation. The design and evaluation documents tie decisions and reported results to repository evidence.

## Prompt log

The [prompt log](prompts.md) exists and currently contains a heading and introductory sentence. It has no logged prompts for setup, corpus audit, corpus swap, extraction, chunking, chunk tuning, ingestion API, ask engine, evaluation, evaluation fixes, auth, frontend, redesign, or documentation.

## Claude chat history

The export destination for the full Claude conversation is [claude_chat_history.md](claude_chat_history.md). The file currently contains a placeholder for the author's export.
