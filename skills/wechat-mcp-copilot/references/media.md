# Media

Use this for image, video, emoji, file, link, and voice resources.

## Tools

- `wechat.media.get_avatar_url`
- `wechat.media.get_chat_image_url`
- `wechat.media.get_chat_emoji_url`
- `wechat.media.get_chat_video_thumb_url`
- `wechat.media.get_chat_video_url`
- `wechat.media.get_chat_voice_url`
- `wechat.media.get_decrypted_resource_url`
- `wechat.media.get_proxy_image_url`
- `wechat.media.get_favicon_url`
- `wechat.biz.get_proxy_image_url`
- `wechat.moments.get_media_url`
- `wechat.moments.get_article_thumb_url`
- `wechat.moments.get_remote_video_url`
- `wechat.moments.get_local_video_url`

## Rules

- Media tools return URLs or resource metadata; they do not inline large binary payloads.
- Voice resources are files only. Do not transcribe voice messages.
- For phone clients, prefer `wechat.mobile.get_media_links` first.
- MCP does not open local folders or download media into cache; use returned URLs in the client.
- Locate the message first, then fetch media URL by message fields such as `server_id`, `username`, `md5`, or returned media references.
- 聊天图片默认使用 `prefer_live=true`，比较本地候选图片的实际尺寸，避免重复读取旧缩略图。返回 URL 不等于已读取图片，客户端需访问 URL 并查看实际图片。
- 需要高清图时，调用 `wechat.media.get_chat_image_url`，传入 `fetch_remote=true` 及原消息的 `server_id`、`username`、`account` 和已有的 `md5`/`file_id`。本地有大图时优先使用本地文件，否则尝试 CDN 补下载；下载可能消耗服务端额度。
- 保留消息返回的 `src_create_time`、`file_size`、`record_index`、`record_index_path`、`record_attach` 等定位字段，尤其是合并转发中的图片。
- 补图失败时按实际错误说明原因，不要承诺恢复高清图，也不要把缩略图当成原图。
- For Moments, prefer local media URL fields from timeline records. Use remote video/article helpers only when the timeline record has a remote URL or article URL.
