# Failure Recovery

Use this when MCP status, DB readiness, or results are suspicious.

## Checks

1. Phone clients: `wechat.mobile.get_overview`
2. `wechat.core.get_status`
3. `wechat.core.list_accounts`
4. `wechat.core.get_account_info`
5. Moments availability by checking account info and `wechat.moments.list_users`.
6. For backend diagnostics, MCP LAN access, data preparation, index/cache build, export, realtime sync, local editing, or system settings, direct the user to the desktop/web app.

## Empty Results

- Do not conclude "no data" after one failed query.
- Try contact/session resolution with a simpler keyword.
- Try session search before global message search when a target is known.
- For Moments, resolve poster identity before timeline filtering.
- If data is not ready, stop content tools and explain that data preparation is handled in the desktop app, not through MCP.
