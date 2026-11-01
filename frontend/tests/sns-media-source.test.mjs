import assert from 'node:assert/strict'
import test from 'node:test'

import {
  getSnsOriginalImageSource,
  getSnsThumbnailImageSource,
  selectSnsImageSource,
} from '../lib/sns-media-source.js'

const image = {
  type: 2,
  url: 'https://mmsns.qpic.cn/sns/item/0',
  thumb: 'https://mmsns.qpic.cn/sns/item/150',
  token: 'origin-token',
  key: 'origin-key',
  thumbToken: 'thumb-token',
  thumbKey: 'thumb-key',
  urlAttrs: { token: 'origin-attrs-token', key: 'origin-attrs-key' },
  thumbAttrs: { token: 'thumb-attrs-token', key: 'thumb-attrs-key' },
}

test('thumbnail URL is paired only with thumbnail token and key', () => {
  assert.deepEqual(getSnsThumbnailImageSource(image), {
    kind: 'thumbnail',
    url: image.thumb,
    token: 'thumb-token',
    key: 'thumb-key',
  })
  assert.deepEqual(selectSnsImageSource(image, image.thumb), {
    kind: 'thumbnail',
    url: image.thumb,
    token: 'thumb-token',
    key: 'thumb-key',
    variant: '',
  })
})

test('full preview is paired only with original URL token and key', () => {
  assert.deepEqual(getSnsOriginalImageSource(image), {
    kind: 'origin',
    url: image.url,
    token: 'origin-token',
    key: 'origin-key',
  })
  assert.deepEqual(selectSnsImageSource(image, image.thumb, { preferFull: true }), {
    kind: 'origin',
    url: image.url,
    token: 'origin-token',
    key: 'origin-key',
    variant: 'full',
  })
})

test('missing per-source credentials never fall back across thumbnail and origin', () => {
  const value = {
    type: 2,
    url: image.url,
    thumb: image.thumb,
    urlAttrs: { token: 'origin-only-token', key: 'origin-only-key' },
  }
  assert.deepEqual(getSnsThumbnailImageSource(value), {
    kind: 'thumbnail',
    url: image.thumb,
    token: '',
    key: '',
  })
  assert.deepEqual(getSnsOriginalImageSource(value), {
    kind: 'origin',
    url: image.url,
    token: 'origin-only-token',
    key: 'origin-only-key',
  })
})

test('comment /60 thumbnails preserve their own source selection', () => {
  const comment = {
    type: 2,
    url: 'https://wxapp.tc.qq.com/comment/0',
    thumbUrl: 'https://wxapp.tc.qq.com/comment/60',
    urlAttrs: { token: 'comment-origin-token', key: 'comment-origin-key' },
    thumbAttrs: { token: 'comment-thumb-token', key: 'comment-thumb-key' },
  }
  const selected = selectSnsImageSource(comment, comment.thumbUrl)
  assert.equal(selected.url, comment.thumbUrl)
  assert.equal(selected.token, 'comment-thumb-token')
  assert.equal(selected.key, 'comment-thumb-key')
  assert.equal(selected.variant, '')
})

test('video body URL is never selected as an image when no cover exists', () => {
  assert.deepEqual(
    selectSnsImageSource({
      type: 6,
      url: 'https://snsvideodownload.video.qq.com/body.mp4',
      videoKey: 'video-key',
    }),
    { kind: 'placeholder', url: '', token: '', key: '', variant: '' },
  )
})

test('video cover uses thumb token and explicit video decryption key', () => {
  assert.deepEqual(
    selectSnsImageSource({
      type: 6,
      url: 'https://snsvideodownload.video.qq.com/body.mp4',
      thumb: 'https://wxapp.tc.qq.com/video-cover/150',
      videoKey: 'video-key',
      thumbAttrs: { token: 'thumb-token', key: '0' },
    }),
    {
      kind: 'thumbnail',
      url: 'https://wxapp.tc.qq.com/video-cover/150',
      token: 'thumb-token',
      key: 'video-key',
      variant: '',
    },
  )
})
