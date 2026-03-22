<script>
import { defineComponent, h, ref, watch } from 'vue'
import miniProgramIconUrl from '~/assets/images/wechat/mini-program.svg'

export default defineComponent({
  name: 'LinkCard',
  props: {
    href: { type: String, default: '' },
    heading: { type: String, default: '' },
    abstract: { type: String, default: '' },
    preview: { type: String, default: '' },
    fromAvatar: { type: String, default: '' },
    from: { type: String, default: '' },
    linkType: { type: String, default: '' },
    isSent: { type: Boolean, default: false },
    badge: { type: String, default: '' },
    variant: { type: String, default: 'default' }
  },
  setup(props) {
    const fromAvatarImgOk = ref(false)
    const fromAvatarImgError = ref(false)

    watch(
      () => String(props.fromAvatar || '').trim(),
      () => {
        fromAvatarImgOk.value = false
        fromAvatarImgError.value = false
      },
      { immediate: true }
    )

    const getFromText = () => {
      const raw = String(props.from || '').trim()
      if (raw) return raw
      try {
        const href = String(props.href || '').trim()
        if (!/^https?:\/\//i.test(href)) return ''
        return String(new URL(href).hostname || '').trim()
      } catch {
        return ''
      }
    }

    return () => {
      const fromText = getFromText()
      const href = String(props.href || '').trim()
      const canNavigate = /^https?:\/\//i.test(href)
      const badgeText = String(props.badge || '').trim()
      const fromAvatarText = (() => {
        const text = String(fromText || '').trim()
        return text ? (Array.from(text)[0] || '') : ''
      })()
      const fromAvatarUrl = String(props.fromAvatar || '').trim()
      const isMiniProgram = String(props.linkType || '').trim() === 'mini_program'
      const isCoverVariant = !isMiniProgram && String(props.variant || '').trim() === 'cover'
      const Tag = canNavigate ? 'a' : 'div'

      const showFromAvatarImg = Boolean(fromAvatarUrl) && !fromAvatarImgError.value
      const showFromAvatarText = (!fromAvatarUrl) || (!fromAvatarImgOk.value)
      const fromAvatarStyle = fromAvatarImgOk.value
        ? {
            background: isCoverVariant ? 'rgba(255, 255, 255, 0.92)' : '#fff',
            color: 'transparent'
          }
        : null
      const miniProgramAvatarStyle = fromAvatarImgOk.value
        ? {
            background: '#fff',
            color: 'transparent'
          }
        : null
      const onFromAvatarLoad = () => {
        fromAvatarImgOk.value = true
        fromAvatarImgError.value = false
      }
      const onFromAvatarError = () => {
        fromAvatarImgOk.value = false
        fromAvatarImgError.value = true
      }

      if (isCoverVariant) {
        const fromRow = h('div', { class: 'wechat-link-cover-from' }, [
          h('div', { class: 'wechat-link-cover-from-avatar', style: fromAvatarStyle, 'aria-hidden': 'true' }, [
            showFromAvatarText ? (fromAvatarText || '\u200B') : null,
            showFromAvatarImg
              ? h('img', {
                  src: fromAvatarUrl,
                  alt: '',
                  class: 'wechat-link-cover-from-avatar-img',
                  referrerpolicy: 'no-referrer',
                  onLoad: onFromAvatarLoad,
                  onError: onFromAvatarError
                })
              : null
          ].filter(Boolean)),
          h('div', { class: 'wechat-link-cover-from-name', style: { flex: '1 1 auto', minWidth: '0' } }, fromText || '\u200B'),
          badgeText ? h('div', { class: 'wechat-link-cover-badge' }, badgeText) : null
        ].filter(Boolean))

        return h(
          Tag,
          {
            ...(canNavigate ? { href, target: '_blank', rel: 'noreferrer' } : { role: 'group', 'aria-disabled': 'true' }),
            class: [
              'wechat-link-card-cover',
              !canNavigate ? 'wechat-link-card--disabled' : '',
              'wechat-special-card',
              'msg-radius',
              props.isSent ? 'wechat-special-sent-side' : ''
            ].filter(Boolean).join(' '),
            style: {
              width: '137px',
              minWidth: '137px',
              maxWidth: '137px',
              display: 'flex',
              flexDirection: 'column',
              boxSizing: 'border-box',
              flex: '0 0 auto',
              background: 'var(--merged-history-bg)',
              border: 'none',
              boxShadow: 'none',
              textDecoration: 'none',
              outline: 'none'
            }
          },
          [
            props.preview
              ? h('div', { class: 'wechat-link-cover-image-wrap' }, [
                  h('img', {
                    src: props.preview,
                    alt: props.heading || '链接封面',
                    class: 'wechat-link-cover-image',
                    referrerpolicy: 'no-referrer'
                  }),
                  fromRow
                ])
              : fromRow,
            h('div', { class: 'wechat-link-cover-title' }, props.heading || href)
          ].filter(Boolean)
        )
      }

      const headingText = String(props.heading || href || '').trim()
      let abstractText = String(props.abstract || '').trim()
      if (abstractText && headingText && abstractText === headingText) abstractText = ''

      if (isMiniProgram) {
        return h(
          Tag,
          {
            ...(canNavigate ? { href, target: '_blank', rel: 'noreferrer' } : { role: 'group', 'aria-disabled': 'true' }),
            class: [
              'wechat-link-card',
              'wechat-link-card--mini-program',
              !canNavigate ? 'wechat-link-card--disabled' : '',
              'wechat-special-card',
              'msg-radius',
              props.isSent ? 'wechat-special-sent-side' : ''
            ].filter(Boolean).join(' '),
            style: {
              width: '210px',
              minWidth: '210px',
              maxWidth: '210px',
              maxHeight: '270px',
              height: '270px',
              display: 'flex',
              flexDirection: 'column',
              boxSizing: 'border-box',
              flex: '0 0 auto',
              background: 'var(--merged-history-bg)',
              border: 'none',
              boxShadow: 'none',
              textDecoration: 'none',
              outline: 'none'
            }
          },
          [
            h('div', { class: 'wechat-link-mini-body' }, [
              h('div', { class: 'wechat-link-mini-header' }, [
                h('div', { class: 'wechat-link-mini-header-avatar', style: miniProgramAvatarStyle, 'aria-hidden': 'true' }, [
                  showFromAvatarText ? (fromAvatarText || '\u200B') : null,
                  showFromAvatarImg
                    ? h('img', {
                        src: fromAvatarUrl,
                        alt: '',
                        class: 'wechat-link-mini-header-avatar-img',
                        referrerpolicy: 'no-referrer',
                        onLoad: onFromAvatarLoad,
                        onError: onFromAvatarError
                      })
                    : null
                ].filter(Boolean)),
                h('div', { class: 'wechat-link-mini-header-name' }, fromText || '\u200B')
              ]),
              h('div', { class: 'wechat-link-mini-title' }, headingText || abstractText || href),
              h('div', { class: ['wechat-link-mini-preview', !props.preview ? 'wechat-link-mini-preview--empty' : ''].filter(Boolean).join(' ') }, [
                props.preview
                  ? h('img', {
                      src: props.preview,
                      alt: props.heading || '小程序预览',
                      class: 'wechat-link-mini-preview-img',
                      referrerpolicy: 'no-referrer'
                    })
                  : null
              ].filter(Boolean))
            ]),
            h('div', { class: 'wechat-link-mini-footer' }, [
              h('img', {
                src: miniProgramIconUrl,
                alt: '',
                class: 'wechat-link-mini-footer-icon',
                'aria-hidden': 'true'
              }),
              h('span', { class: 'wechat-link-mini-footer-text' }, '小程序')
            ])
          ]
        )
      }

      return h(
        Tag,
        {
          ...(canNavigate ? { href, target: '_blank', rel: 'noreferrer' } : { role: 'group', 'aria-disabled': 'true' }),
          class: [
            'wechat-link-card',
            !canNavigate ? 'wechat-link-card--disabled' : '',
            'wechat-special-card',
            'msg-radius',
            props.isSent ? 'wechat-special-sent-side' : ''
          ].filter(Boolean).join(' '),
          style: {
            width: '210px',
            minWidth: '210px',
            maxWidth: '210px',
            display: 'flex',
            flexDirection: 'column',
            boxSizing: 'border-box',
            flex: '0 0 auto',
            background: 'var(--merged-history-bg)',
            border: 'none',
            boxShadow: 'none',
            textDecoration: 'none',
            outline: 'none'
          }
        },
        [
          h('div', { class: 'wechat-link-content' }, [
            h('div', { class: 'wechat-link-title' }, headingText || href),
            (abstractText || props.preview)
              ? h('div', { class: 'wechat-link-summary' }, [
                  abstractText ? h('div', { class: 'wechat-link-desc' }, abstractText) : null,
                  props.preview
                    ? h('div', { class: 'wechat-link-thumb' }, [
                        h('img', {
                          src: props.preview,
                          alt: props.heading || '链接预览',
                          class: 'wechat-link-thumb-img',
                          referrerpolicy: 'no-referrer'
                        })
                      ])
                    : null
                ].filter(Boolean))
              : null
          ].filter(Boolean)),
          h('div', { class: 'wechat-link-from' }, [
            h('div', { class: 'wechat-link-from-avatar', style: fromAvatarStyle, 'aria-hidden': 'true' }, [
              showFromAvatarText ? (fromAvatarText || '\u200B') : null,
              showFromAvatarImg
                ? h('img', {
                    src: fromAvatarUrl,
                    alt: '',
                    class: 'wechat-link-from-avatar-img',
                    referrerpolicy: 'no-referrer',
                    onLoad: onFromAvatarLoad,
                    onError: onFromAvatarError
                  })
                : null
            ].filter(Boolean)),
            h('div', { class: 'wechat-link-from-name', style: { flex: '1 1 auto', minWidth: '0' } }, fromText || '\u200B'),
            badgeText ? h('div', { class: 'wechat-link-badge' }, badgeText) : null
          ].filter(Boolean))
        ].filter(Boolean)
      )
    }
  }
})
</script>
