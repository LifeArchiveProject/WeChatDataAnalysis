---
name: wechat-mcp-copilot
version: "1.0.0"
description: Use WeChatDataAnalysis MCP to inspect local WeChat accounts, contacts, sessions, messages, Moments, media, and analytics through a small routed playbook. Trigger when the user asks to search, summarize, diagnose, or reason over local WeChat data.
---

# WeChat MCP Copilot

Use WeChatDataAnalysis MCP like an investigator: start broad, resolve fuzzy targets, then fetch only the context needed to answer.

## Core Rules

1. Start with `references/routing.md`.
2. Load only one domain reference after routing.
3. Load `references/pagination-budget.md` before broad searches or multi-page scans.
4. Use `references/failure-recovery.md` when MCP, database readiness, or empty results are unclear.
5. For phone, ScreenMemo, or external MCP clients, prefer `wechat.mobile.*` facade tools before low-level tools.
6. Do not load the full tool catalog unless the user asks about available tools.

## References

- `references/routing.md`: first-hop intent routing.
- `references/mobile.md`: phone-friendly facade tools and compact response rules.
- `references/target-resolution.md`: fuzzy contact/session resolution.
- `references/chats.md`: chat sessions, messages, search, and context.
- `references/moments.md`: Moments timeline, posters, likes, comments, media.
- `references/media.md`: images, videos, emoji, files, voice resources without transcription.
- `references/analytics.md`: wrapped cards, counts, rankings, and aggregate analysis.
- `references/pagination-budget.md`: limits, cursors, result clipping, stopping rules.
- `references/failure-recovery.md`: empty result, not-ready database, ambiguous targets, retries.
