# Analytics

Use this for annual summaries, rankings, counts, and aggregate questions.

## Tools

- `wechat.analytics.get_wrapped_meta`
- `wechat.analytics.get_wrapped_card`
- `wechat.analytics.get_wrapped_annual`
- `wechat.chat.get_daily_message_counts`
- `wechat.biz.get_pay_records`

## Rules

- Prefer `get_wrapped_meta` then `get_wrapped_card` for mobile or constrained contexts.
- Wrapped annual tools read existing generated cache only; if a cache is missing, ask the user to open Wrapped in the desktop/web app first.
- Use `get_wrapped_annual` only when the user needs the whole annual dataset.
- For broad statistics, prefer aggregate tools or targeted searches over full message pagination.
- Always state the account, time range, and metric basis when answering.
