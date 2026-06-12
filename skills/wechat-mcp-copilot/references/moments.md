# Moments

Use this for 朋友圈, posts, likes, comments, shared links, and Moments media.

## Flow

1. If the clue is a person, resolve with `wechat.contacts.resolve_contact`.
2. Use `wechat.moments.list_users` when you need poster candidates.
3. Use `wechat.moments.list_timeline` or `wechat.moments.search_moments`.
4. Use `wechat.moments.get_media_url` only when the user needs a media resource.

## Rules

- Person names must be resolved to username before filtering timeline by `usernames`.
- Keyword search is for post content/topic, not poster identity.
- Do not request raw XML by default.
- Realtime/local sync tools are not exposed through MCP; ask the user to refresh data in the app when Moments data looks stale.
