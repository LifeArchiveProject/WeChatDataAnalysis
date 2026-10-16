const firstString = (...values) => {
  for (const value of values) {
    const text = String(value ?? '').trim()
    if (text) return text
  }
  return ''
}

const canonicalUrl = (value) => {
  const raw = String(value ?? '').trim()
  if (!raw) return ''
  try {
    const parsed = new URL(raw)
    parsed.protocol = parsed.protocol.toLowerCase()
    parsed.hostname = parsed.hostname.toLowerCase()
    return parsed.toString()
  } catch {
    return raw
  }
}

export const getSnsOriginalImageSource = (media) => {
  const value = media && typeof media === 'object' ? media : {}
  const attrs = value.urlAttrs && typeof value.urlAttrs === 'object' ? value.urlAttrs : {}
  return {
    kind: 'origin',
    url: firstString(
      value.url,
      value.originUrl,
      value.originalUrl,
      value.origin_url,
      value.original_url,
    ),
    token: firstString(value.token, value.urlToken, value.url_token, attrs.token),
    key: firstString(value.key, attrs.key),
  }
}

export const getSnsThumbnailImageSource = (media) => {
  const value = media && typeof media === 'object' ? media : {}
  const attrs = value.thumbAttrs && typeof value.thumbAttrs === 'object' ? value.thumbAttrs : {}
  const isVideo = Number(value.type || 0) === 6
  return {
    kind: 'thumbnail',
    url: firstString(value.thumb, value.thumbUrl, value.thumb_url),
    token: firstString(
      value.thumbToken,
      value.thumbUrlToken,
      value.thumb_url_token,
      attrs.token,
    ),
    // WeChat video covers share the explicit videoKey with the video body.
    // thumbAttrs.key is commonly "0" and is not a usable decryption key.
    key: isVideo
      ? firstString(value.videoKey, value.thumbKey, value.thumb_key, attrs.key)
      : firstString(value.thumbKey, value.thumb_key, attrs.key),
  }
}

export const selectSnsImageSource = (media, rawUrl = '', { preferFull = false } = {}) => {
  const value = media && typeof media === 'object' ? media : {}
  const isVideo = Number(value.type || 0) === 6
  const origin = getSnsOriginalImageSource(value)
  const thumbnail = getSnsThumbnailImageSource(value)

  // A video download URL is never a valid image cover. Missing covers render a
  // placeholder and the video endpoint remains responsible for the body bytes.
  if (isVideo && !thumbnail.url) {
    return { kind: 'placeholder', url: '', token: '', key: '', variant: '' }
  }
  if (isVideo) {
    return { ...thumbnail, variant: '' }
  }

  if (preferFull && origin.url) {
    return { ...origin, variant: 'full' }
  }

  const requested = canonicalUrl(rawUrl)
  if (thumbnail.url && requested && requested === canonicalUrl(thumbnail.url)) {
    return { ...thumbnail, variant: '' }
  }
  if (origin.url && requested && requested === canonicalUrl(origin.url)) {
    return { ...origin, variant: preferFull ? 'full' : '' }
  }
  if (thumbnail.url && !requested) {
    return { ...thumbnail, variant: '' }
  }
  if (origin.url) {
    return { ...origin, variant: preferFull ? 'full' : '' }
  }
  if (thumbnail.url) {
    return { ...thumbnail, variant: '' }
  }
  return { kind: 'placeholder', url: '', token: '', key: '', variant: '' }
}
