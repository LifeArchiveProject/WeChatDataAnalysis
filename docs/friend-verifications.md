# 好友申请状态查询

`GET /api/general/friend-verifications` 分页读取好友验证记录，并返回每条记录的处理状态。

只查询待我处理的申请：

```http
GET /api/general/friend-verifications?account=project-account&source=realtime&pendingOnly=true&limit=20&offset=0
```

`pendingOnly` 默认为 `false`。原有的 `account`、`q`、`source`、`limit`、`offset` 参数保持不变。过滤先于分页执行，`total` 和 `hasMore` 都对应过滤后的记录；滚动加载时继续使用 `offset` 获取下一页。

记录包含以下状态字段：

| 字段 | 含义 |
|---|---|
| `verificationState` | `pending`、`accepted`、`expired`、`outgoing` 或 `unknown` |
| `isPending` | 是否为当前待我处理的申请 |

| 状态 | 含义 |
|---|---|
| `pending` | 对方发起、当前不是好友、申请尚未过期 |
| `accepted` | 当前联系人已是好友 |
| `expired` | 申请已经过期 |
| `outgoing` | 本人发出、当前未成为好友且尚未过期的申请，不属于待我处理 |
| `unknown` | 不是好友申请类型，或状态数据不足以判断 |

```json
{
  "status": "success",
  "account": "project-account",
  "total": 1,
  "hasMore": false,
  "dataSource": "realtime",
  "items": [
    {
      "userName": "wxid_requester",
      "scene": 14,
      "isSender": false,
      "verificationState": "pending",
      "isPending": true
    }
  ]
}
```

当前好友关系优先返回 `accepted`。对于能读取详情状态的其余记录，申请超过 3 天或已保存过期标志时返回 `expired`；未过期时，根据发起方向返回 `pending` 或 `outgoing`。联系人记录缺失或详情状态无法判定时返回 `unknown`。`pendingOnly=true` 只保留 `isPending=true`，不会包含本人发出的申请或状态未知的记录。

状态按所选数据源计算。实时查询与联系人状态使用同一类数据源；`decrypted` 表示已解密快照，不代表当前在线状态。请求实时数据时应检查响应中的 `dataSource` 和既有回退信息。

状态规则已在 Windows 微信 4.1.13.12 核对。本接口只读取数据，不执行通过好友申请或其他联系人修改操作。
