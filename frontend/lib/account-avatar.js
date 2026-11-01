const clean = (value) => String(value || '').trim()


const normalizeWeFlowAccountDirectory = (value) => {
  const account = clean(value)
  if (!account) return ''

  if (account.toLowerCase().startsWith('wxid_')) {
    return account.match(/^(wxid_.+)_([a-f0-9]{4})$/i)?.[1] || account
  }

  return account.match(/^(.+)_([a-f0-9]{4})$/i)?.[1] || account
}


export const resolveAccountSelfUsername = (account, info = null) => {
  const source = info && typeof info === 'object' ? info : {}
  const realtime = source.realtime && typeof source.realtime === 'object'
    ? source.realtime
    : {}
  const explicit = [
    source.selfUsername,
    source.self_username,
    source.nativeWxid,
    source.native_wxid,
    realtime.nativeWxid,
    realtime.native_wxid,
  ].map(clean).find(Boolean)

  return explicit || normalizeWeFlowAccountDirectory(account)
}


export const buildAccountAvatarUrl = (apiBase, account, info = null) => {
  const accountName = clean(account)
  const username = resolveAccountSelfUsername(accountName, info)
  if (!accountName || !username) return ''

  const base = clean(apiBase).replace(/\/+$/, '')
  return `${base}/chat/avatar?account=${encodeURIComponent(accountName)}&username=${encodeURIComponent(username)}`
}
