# Mobile Facade

Use this for phone, ScreenMemo, and external MCP clients unless the user needs a low-level operation.

## Default Tools

- `wechat.mobile.get_overview`: first call after initialize. Returns readiness, accounts, health, and suggested next tools.
- `wechat.mobile.get_home_snapshot`: small account/session/Moments snapshot for a home screen.
- `wechat.mobile.resolve_target`: resolve fuzzy people, groups, sessions, Moments users, or official accounts.
- `wechat.mobile.search_chat`: message search with optional tiny context windows.
- `wechat.mobile.get_chat_context`: recent, day, or around-anchor chat context.
- `wechat.mobile.get_session_bundle`: session metadata plus a page of messages.
- `wechat.mobile.search_moments`: compact Moments search.
- `wechat.mobile.get_media_links`: URL-only media lookup.
- `wechat.mobile.get_analytics`: compact analytics by metric.

## Budget Rules

- Keep `limit` at 10-20 for first calls.
- Use `offset` or returned cursor fields for paging.
- Do not call full annual analytics by default; use `metric=digest` or a single card. Wrapped annual data is cache-only through MCP.
- Do not fetch binary media through MCP. Use returned URLs in the app.
- Use low-level tools only for debugging, raw fields, or unusual media URL construction.
- Data preparation, index/cache build, export, realtime sync, local editing, system settings, and data deletion tools are not exposed through MCP.

## Recovery

- If `ready=false`, stop content tools and direct the user to the desktop/web app for data preparation or backend diagnostics.
- If target resolution is ambiguous, ask for one clarifying clue or show top candidates.
- If search returns nothing, try `resolve_target` and then `get_chat_context` before declaring no data.
