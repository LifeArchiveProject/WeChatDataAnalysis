import { describe, expect, it } from 'vitest'
import { createChatHistoryRecordNormalizer } from '../lib/chat/chat-history'
import { createMessageNormalizer } from '../lib/chat/message-normalizer'

describe('聊天图片缓存升级', () => {
  it('普通图片首次显示也避开旧浏览器缓存，并保留已有媒体刷新版本', () => {
    let mediaVersion = 0
    const normalize = createMessageNormalizer({
      apiBase: 'http://localhost:10392/api',
      getSelectedAccount: () => 'wxid_test',
      getSelectedContact: () => ({ username: 'wxid_friend' }),
      getLocalMediaVersion: () => mediaVersion
    })
    const message = { renderType: 'image', imageMd5: 'a'.repeat(32), serverId: '123456789' }
    let url = new URL(normalize(message).imageUrl)
    expect(url.searchParams.get('v')).toBe('local-quality-1')
    expect(url.searchParams.has('fetch_remote')).toBe(false)
    mediaVersion = 12345
    url = new URL(normalize(message).imageUrl)
    expect(url.searchParams.get('v')).toBe('12345')
  })
  it('转发图片使用新缓存版本，保留原消息定位参数', () => {
    const normalize = createChatHistoryRecordNormalizer({
      apiBase: 'http://localhost:10392/api',
      getSelectedAccount: () => 'wxid_test',
      getSelectedContact: () => ({ username: 'wxid_friend' })
    })
    const message = normalize({
      renderType: 'image', fullmd5: 'a'.repeat(32), fromnewmsgid: '123456789',
      recordIndexPath: '1_2', srcMsgCreateTime: '1791194400'
    })
    const url = new URL(message.imageUrl)
    expect(url.searchParams.get('v')).toBe('local-quality-1')
    expect(url.searchParams.get('md5')).toBe('a'.repeat(32))
    expect(url.searchParams.get('server_id')).toBe('123456789')
    expect(url.searchParams.get('record_index_path')).toBe('1_2')
    expect(url.searchParams.has('fetch_remote')).toBe(false)
  })
})
