# Routing

Use this first for every WeChatDataAnalysis MCP task.

## First Calls

- Phone, ScreenMemo, mobile app, or compact external client: load `mobile.md` and start with `wechat.mobile.get_overview`.
- Status, readiness, "why can't I find anything": `wechat.core.get_status`, or `wechat.mobile.get_overview` for phone clients.
- Available tools or packages: `wechat.core.list_tools`.
- Account selection: `wechat.core.list_accounts`, then `wechat.core.get_account_info`.
- Backend health, logs, MCP LAN access, port, system settings, key/decrypt/import/data preparation, index/cache build, export, realtime sync, local editing, or data deletion requests: explain that these operations are not exposed through MCP and should be handled in the desktop/web app.
- Fuzzy person/group/official account: load `target-resolution.md`.
- Chat content, recent messages, keyword search: load `chats.md`.
- Moments / 朋友圈 / likes / comments / post media: load `moments.md`.
- Images, videos, emoji, files, voice resources: load `media.md`.
- Rankings, yearly summary, activity stats: load `analytics.md`; if Wrapped cache is missing, ask the user to generate it in the app.
- Empty results or readiness errors: load `failure-recovery.md`.

## Mixed Intent

Resolve the target first, then load only the main domain reference. Do not load chats, moments, media, and analytics together unless the user explicitly asks for a broad audit.

For phone clients, keep using `mobile.md` until the user needs a low-level fallback such as raw fields or special media URL construction.
