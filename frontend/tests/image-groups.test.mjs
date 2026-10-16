import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildImageGroupKey,
  deriveImageGroupMessages,
  findImageGroupKeyByMessageId,
  normalizeImageGroupMetadata
} from '../lib/chat/image-groups.js'

const GROUP_ID = '019fa474-3e37-75d0-850c-0ac04a9019db'

const image = (id, overrides = {}) => ({
  id,
  renderType: 'image',
  imageUrl: `data:image/png,${id}`,
  imageGroupType: '1',
  imageGroupId: GROUP_ID,
  imageGroupCount: 4,
  ...overrides
})

test('buildImageGroupKey requires the exact validated tuple', () => {
  assert.equal(buildImageGroupKey(image('a')), `1:${GROUP_ID}:4`)
  assert.equal(buildImageGroupKey(image('a', { renderType: 'video' })), '')
  assert.equal(buildImageGroupKey(image('a', { imageGroupId: 'not-a-uuid' })), '')
  assert.equal(buildImageGroupKey(image('a', { imageGroupCount: 1 })), '')
  assert.equal(buildImageGroupKey(image('a', { imageGroupType: '' })), '')
})

test('normalization canonicalizes API group metadata for the message normalizer', () => {
  assert.deepEqual(normalizeImageGroupMetadata(image('a', {
    imageGroupId: GROUP_ID.toUpperCase(),
    imageGroupCount: '4'
  })), {
    imageGroupType: '1',
    imageGroupId: GROUP_ID,
    imageGroupCount: 4
  })
  assert.deepEqual(normalizeImageGroupMetadata(image('a', { imageGroupId: 'invalid' })), {
    imageGroupType: '',
    imageGroupId: '',
    imageGroupCount: 0
  })
})

test('collapsed groups keep their first position and preserve unrelated messages', () => {
  const messages = [
    { id: 'before', renderType: 'text' },
    image('a'),
    { id: 'between', renderType: 'text' },
    image('b'),
    image('c'),
    { id: 'after', renderType: 'text' }
  ]

  const output = deriveImageGroupMessages(messages)
  assert.deepEqual(output.map((item) => item.id), ['before', 'a', 'between', 'after'])
  assert.equal(output[1].imageGroupCollapsed, true)
  assert.deepEqual(output[1].imageGroupItems.map((item) => item.id), ['a', 'b', 'c'])
  assert.equal(output[1].imageGroupProtocolCount, 4)
})

test('type, id, and count all participate in grouping', () => {
  const messages = [
    image('a'),
    image('different-type', { imageGroupType: '2' }),
    image('different-count', { imageGroupCount: 3 }),
    image('different-id', { imageGroupId: '019fa474-3e37-75d0-850c-0ac04a9019dc' })
  ]

  assert.deepEqual(deriveImageGroupMessages(messages).map((item) => item.id), messages.map((item) => item.id))
})

test('expanded groups restore every loaded message in original group order', () => {
  const messages = [image('a'), { id: 'between', renderType: 'text' }, image('b'), image('c')]
  const key = buildImageGroupKey(messages[0])
  const output = deriveImageGroupMessages(messages, new Set([key]))

  assert.deepEqual(output.map((item) => item.id), ['a', 'between', 'b', 'c'])
  assert.ok(output.filter((item) => item.renderType === 'image').every((item) => item.imageGroupExpanded))
  assert.equal(output[0].imageGroupIsFirst, true)
  assert.equal(output[2].imageGroupIsFirst, false)
  assert.deepEqual(
    output.filter((item) => item.imageGroupExpanded).map((item) => item.imageGroupItemIndex),
    [0, 1, 2]
  )
})

test('pagination completion automatically adds newly loaded group members', () => {
  const partial = deriveImageGroupMessages([image('a'), image('b')])
  const completed = deriveImageGroupMessages([image('older'), image('a'), image('b')])

  assert.deepEqual(partial[0].imageGroupItems.map((item) => item.id), ['a', 'b'])
  assert.deepEqual(completed[0].imageGroupItems.map((item) => item.id), ['older', 'a', 'b'])
})

test('locating a hidden member resolves its group key', () => {
  const messages = [image('a'), image('b')]
  assert.equal(findImageGroupKeyByMessageId(messages, 'b'), buildImageGroupKey(messages[0]))
  assert.equal(findImageGroupKeyByMessageId(messages, 'missing'), '')
})
