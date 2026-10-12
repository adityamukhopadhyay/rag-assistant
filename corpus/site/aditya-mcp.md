---
title: "Aditya MCP — agents auditing agents"
slug: "site-aditya-mcp"
kind: "portfolio"
site_slug: "aditya-mcp"
page_url: "https://adityamukhopadhyay.vercel.app/work/aditya-mcp"
source: "site/projects.ts"
themes: ["MCP", "Agents", "Pipelines"]
---
# Aditya MCP — agents auditing agents

A read-only MCP server that mines my own AI coding sessions, git history and handoff docs across every project, and powers scheduled routines that keep documentation honest.

Period: 2026 · personal. Stack: Python, MCP (stdio), git, Claude Code scheduled tasks.

## Headline numbers

- **7** — read-only tools
- **26 / 27** — repos / handoff docs found live
- **0** — network calls, secrets, writes

## Context

I run many projects, each with a handoff doc that a new session reads first. Docs go stale; sessions get forgotten; "what did I do yesterday" becomes an archaeology task. This server answers it from ground truth: it walks two folders on every call, discovers every git repo, every `*HANDOFF*.md`, and every Claude Code session whose recorded working directory falls under them — **nothing project-specific is a static list**.

It powers two scheduled routines: a daily cross-project work report, and a companion that detects handoff docs older than their project's last activity and messages the responsible session to fix them.

## How it works

### Fully dynamic discovery

Drop a new project folder under a scan root and it's covered immediately — no config edit, no restart of the discovery logic. Same-named docs in different worktrees are labelled by relative path so they never collide. Sessions are matched by peeking each candidate's recorded `cwd`, not by folder naming, which is how a session started from a brand-new folder gets caught.

### Correct about its own blind spots

`git log` cannot see uncommitted work, which in worktrees can be thousands of lines. A session that was resumed inside the window but whose content is from another day should not count. The server's own handoff documents a known omission in one date-range query rather than hiding it, and instructs every consumer to reconcile its session list against a second, independent source before reporting "no activity".

### Dashboard links that discover themselves

A curated, human-labelled link map is the only hand-maintained part. Every other production URL on an allow-listed domain found inside a handoff doc or README is surfaced automatically, grouped by project — so a new project's prod URL shows up the moment it's written down.

## Measured results

- **26 / 27** — git repos / handoff docs discovered (Live scan result on 2026-08-22, across two scan roots. The number changes whenever a folder appears.)
- **7** — tools (sessions, commits, handoff entries, freshness, known projects, dashboard links, and one bundled work-report call.)
- **0** — network calls, secrets, writes (Local only — `git log` and file reads; nothing leaves the machine.)

## What the numbers do and do not claim

This is infrastructure for my own workflow, not a product; its value is that the reports it produces are verified against git and session logs rather than remembered. Its one known defect is documented in its own handoff.

## Lessons

- A report you can't verify is a story.
- Tell consumers what you cannot see.

