<template>
  <div
    class="chat-contact-card"
    @mouseenter="onContactCardMouseEnter"
    @mouseleave="onMessageAvatarMouseLeave"
  >
    <div v-if="contactProfileInitialLoading" class="contact-card-body">
      <div class="contact-card-head">
        <div class="skeleton skeleton-avatar"></div>
        <div class="min-w-0 flex-1">
          <div class="skeleton skeleton-name"></div>
          <div class="skeleton skeleton-username"></div>
        </div>
      </div>
      <div class="contact-profile-section">
        <div v-for="idx in 6" :key="idx" class="contact-field">
          <div class="skeleton skeleton-label"></div>
          <div class="skeleton skeleton-value"></div>
        </div>
      </div>
    </div>

    <div v-else class="contact-card-body">
      <div class="contact-card-head">
        <div class="contact-avatar" :class="{ 'privacy-blur': privacyMode }">
          <img
            v-if="contactProfileResolvedAvatar"
            :src="contactProfileResolvedAvatar"
            alt="联系人头像"
            class="h-full w-full object-cover"
            referrerpolicy="no-referrer"
          />
          <div v-else class="contact-avatar-fallback" :style="{ backgroundColor: contactProfileResolvedAvatarColor }">{{ contactProfileResolvedName.charAt(0) || '?' }}</div>
        </div>
        <div class="min-w-0 flex-1" :class="{ 'privacy-blur': privacyMode }">
          <div class="contact-name-row">
            <div class="contact-name">{{ contactProfileResolvedName || '未知联系人' }}</div>
            <span v-if="contactProfileResolvedGender" class="contact-inline-pill">{{ contactProfileResolvedGender }}</span>
            <span v-if="contactProfileResolvedRegion" class="contact-inline-region">{{ contactProfileResolvedRegion }}</span>
          </div>
          <div class="contact-subtitle">{{ contactProfileResolvedHeaderSubtitle }}</div>
        </div>
      </div>

      <ErrorNotice v-if="contactProfileError" :message="contactProfileError" compact class="contact-error" />

      <div
        v-if="contactProfileResolvedGroupNickname || contactProfileResolvedNickname || contactProfileResolvedRemark || contactProfileResolvedAlias"
        class="contact-profile-section"
      >
        <div v-if="contactProfileResolvedGroupNickname" class="contact-field">
          <div class="contact-label">群昵称</div>
          <div class="contact-value" :class="{ 'privacy-blur': privacyMode }">{{ contactProfileResolvedGroupNickname }}</div>
        </div>
        <div v-if="contactProfileResolvedNickname" class="contact-field">
          <div class="contact-label">昵称</div>
          <div class="contact-value" :class="{ 'privacy-blur': privacyMode }">{{ contactProfileResolvedNickname }}</div>
        </div>
        <div v-if="contactProfileResolvedRemark" class="contact-field">
          <div class="contact-label">备注</div>
          <div class="contact-value" :class="{ 'privacy-blur': privacyMode }">{{ contactProfileResolvedRemark }}</div>
        </div>
        <div v-if="contactProfileResolvedAlias" class="contact-field contact-field-copy">
          <div class="contact-label">微信号</div>
          <div class="contact-value contact-code" :class="{ 'privacy-blur': privacyMode }">{{ contactProfileResolvedAlias }}</div>
          <button type="button" class="contact-copy" title="复制微信号" @click.stop="copyContactProfileText(contactProfileResolvedAlias, 'alias')">
            <svg v-if="copiedField === 'alias'" class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
            </svg>
            <svg v-else class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M8 7V5a2 2 0 012-2h7a2 2 0 012 2v7a2 2 0 01-2 2h-2M5 9h7a2 2 0 012 2v7a2 2 0 01-2 2H5a2 2 0 01-2-2v-7a2 2 0 012-2z" />
            </svg>
          </button>
        </div>
      </div>

      <div v-if="contactProfileResolvedSignature" class="contact-profile-section">
        <div class="contact-field contact-field-tall">
          <div class="contact-label">签名</div>
          <div class="contact-value contact-signature" :class="{ 'privacy-blur': privacyMode }">{{ contactProfileResolvedSignature }}</div>
        </div>
      </div>

      <div
        v-if="contactProfileIsFriend && (contactProfileVerificationLoading || contactProfileFriendVerifications.length)"
        class="contact-profile-section contact-verification-section"
      >
        <div class="contact-verification-head">
          <div class="contact-label">好友验证</div>
          <span v-if="contactProfileVerificationLoading">加载中...</span>
          <span v-else>{{ contactProfileFriendVerifications.length }} 条</span>
        </div>
        <div v-if="contactProfileFriendVerifications.length" class="contact-verification-list">
          <article
            v-for="(record, index) in contactProfileFriendVerifications"
            :key="`${record.timestamp || 0}-${index}`"
            class="contact-verification-item"
          >
            <div class="contact-verification-meta">
              <span :class="record.isSender ? 'is-outgoing' : 'is-incoming'">
                {{ record.isSender ? '我方发起' : '对方发起' }}
              </span>
              <time v-if="record.timeText">{{ record.timeText }}</time>
            </div>
            <p v-if="record.content || record.remark" :class="{ 'privacy-blur': privacyMode }">
              <template v-for="(segment, segmentIndex) in verificationContentSegments(record.content || record.remark)" :key="segmentIndex">
                <button
                  v-if="segment.type === 'link'"
                  type="button"
                  class="contact-verification-link"
                  :title="`在默认浏览器打开 ${segment.url}`"
                  @click.stop="openVerificationUrl(segment.url)"
                >
                  {{ segment.text }}
                </button>
                <span v-else>{{ segment.text }}</span>
              </template>
            </p>
            <p v-else class="contact-verification-empty">未保存验证消息</p>
          </article>
        </div>
      </div>

      <div
        v-if="contactProfileHasMoreInfo"
        class="contact-profile-section compact"
        :class="{ 'compact--with-groups': contactProfileResolvedCommonChatrooms.length }"
      >
        <div v-if="contactProfileResolvedCommonChatrooms.length" class="contact-common-groups">
          <div class="contact-common-groups-head">
            <div class="contact-label">共同群聊</div>
            <div class="contact-common-groups-count">
              {{ contactProfileResolvedCommonChatroomCount ?? contactProfileResolvedCommonChatrooms.length }} 个
            </div>
          </div>
          <div class="contact-common-groups-list">
            <button
              v-for="group in contactProfileResolvedCommonChatrooms"
              :key="group.username"
              type="button"
              class="contact-common-group"
              :title="`进入${group.displayName}的会话`"
              @click.stop="openCommonChatroom(group)"
            >
              <span class="contact-common-group-avatar" :class="{ 'privacy-blur': privacyMode }">
                <img
                  v-if="group.avatar"
                  :src="group.avatar"
                  :alt="`${group.displayName}群头像`"
                  loading="lazy"
                  decoding="async"
                  referrerpolicy="no-referrer"
                />
                <span v-else :style="{ backgroundColor: group.avatarColor }">群</span>
              </span>
              <span class="contact-common-group-name" :class="{ 'privacy-blur': privacyMode }">{{ group.displayName }}</span>
              <i class="fa-solid fa-chevron-right" aria-hidden="true"></i>
            </button>
          </div>
        </div>
        <div v-if="contactProfileResolvedSource" class="contact-field" :title="contactProfileResolvedSourceScene != null ? `来源场景码：${contactProfileResolvedSourceScene}` : ''">
          <div class="contact-label">来源</div>
          <div class="contact-value" :class="{ 'privacy-blur': privacyMode }">{{ contactProfileResolvedSource }}</div>
        </div>
        <div v-if="contactProfileResolvedAddTime" class="contact-field">
          <div class="contact-label">添加时间</div>
          <div class="contact-value contact-code" :class="{ 'privacy-blur': privacyMode }">{{ contactProfileResolvedAddTime }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { defineComponent, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'

export default defineComponent({
  name: 'ContactProfileCard',
  props: {
    state: { type: Object, required: true }
  },
  setup(props) {
    const router = useRouter()
    const copiedField = ref('')
    let copiedTimer = null

    const copyContactProfileText = async (value, field) => {
      const text = String(value || '').trim()
      if (!text) return
      try {
        if (process.client && typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(text)
        }
      } catch {}
      copiedField.value = String(field || '')
      if (copiedTimer) clearTimeout(copiedTimer)
      copiedTimer = setTimeout(() => {
        copiedField.value = ''
        copiedTimer = null
      }, 1200)
    }

    const openCommonChatroom = async (group) => {
      const username = String(group?.username || '').trim()
      if (!username) return
      if (typeof props.state?.closeContactProfileCard === 'function') {
        props.state.closeContactProfileCard()
      }
      await router.push(`/chat/${encodeURIComponent(username)}`)
    }

    const verificationContentSegments = (value) => {
      const text = String(value || '')
      if (!text) return []
      const segments = []
      const pattern = /(?:https?:\/\/|www\.)[^\s<>"']+/giu
      let lastIndex = 0
      for (const match of text.matchAll(pattern)) {
        const index = Number(match.index || 0)
        if (index > lastIndex) segments.push({ type: 'text', text: text.slice(lastIndex, index) })
        let linkText = String(match[0] || '')
        let trailing = ''
        while (linkText && /[.,;:!?，。；：！？）)】\]]/u.test(linkText.at(-1))) {
          trailing = linkText.at(-1) + trailing
          linkText = linkText.slice(0, -1)
        }
        if (linkText) {
          segments.push({
            type: 'link',
            text: linkText,
            url: /^www\./i.test(linkText) ? `https://${linkText}` : linkText
          })
        }
        if (trailing) segments.push({ type: 'text', text: trailing })
        lastIndex = index + String(match[0] || '').length
      }
      if (lastIndex < text.length) segments.push({ type: 'text', text: text.slice(lastIndex) })
      return segments.length ? segments : [{ type: 'text', text }]
    }

    const openVerificationUrl = async (value) => {
      const url = String(value || '').trim()
      if (!/^https?:\/\//i.test(url)) return
      if (process.client && typeof window !== 'undefined' && window.wechatDesktop?.openExternalUrl) {
        try {
          await window.wechatDesktop.openExternalUrl(url)
          return
        } catch {}
      }
      try { window.open(url, '_blank', 'noopener,noreferrer') } catch {}
    }

    onUnmounted(() => {
      if (copiedTimer) clearTimeout(copiedTimer)
      copiedTimer = null
    })

    return {
      ...props.state,
      copiedField,
      copyContactProfileText,
      openCommonChatroom,
      verificationContentSegments,
      openVerificationUrl
    }
  }
})
</script>

<style scoped>
.chat-contact-card {
  /* 不设置 position：外层 MessageItem 传入的 absolute 不能被覆盖，否则会挤乱消息流。 */
  --contact-profile-radius: 0.375rem; /* 对齐当前聊天头像的 rounded-md 圆角 */
  --contact-profile-surface: #f8faf8;
  --contact-profile-border: #d4dad5;
  overflow: visible;
  border-radius: var(--contact-profile-radius);
  background: var(--contact-profile-surface);
  border: 1px solid var(--contact-profile-border);
  color: var(--app-text-primary);
  box-shadow: none;
}

.contact-card-body {
  max-height: min(680px, calc(100vh - 120px));
  overflow-y: auto;
  padding: 14px;
}

.contact-card-head {
  display: flex;
  align-items: center;
  gap: 13px;
  min-height: 78px;
  padding: 0 0 14px 0;
  border-bottom: 1px solid var(--app-border);
}

.contact-avatar {
  width: 64px;
  height: 64px;
  flex: 0 0 auto;
  overflow: hidden;
  border-radius: var(--contact-profile-radius);
  background: var(--app-border-soft);
}

.contact-avatar-fallback {
  display: flex;
  height: 100%;
  width: 100%;
  align-items: center;
  justify-content: center;
  color: #fff;
  background: #6b7280;
  font-size: 20px;
  font-weight: 650;
}

.contact-name-row {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.contact-name {
  min-width: 0;
  overflow: hidden;
  flex: 0 1 auto;
  color: var(--app-text-primary);
  font-size: 19px;
  font-weight: 650;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.contact-inline-pill,
.contact-inline-region {
  min-width: 0;
  flex: 0 1 auto;
  color: var(--app-text-muted);
  font-size: 12px;
  font-weight: 500;
  line-height: 1.35;
}

.contact-inline-pill {
  flex: 0 0 auto;
}

.contact-inline-region {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.contact-subtitle {
  margin-top: 6px;
  overflow: hidden;
  color: var(--app-text-muted);
  font-size: 13px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.contact-profile-section {
  padding: 12px 0;
  border-bottom: 1px solid var(--app-border);
}

.contact-profile-section.compact {
  padding-bottom: 8px;
}

.contact-profile-section.compact--with-groups {
  padding-top: 0;
}

.contact-common-groups {
  padding: 2px 0 8px;
}

.compact--with-groups .contact-common-groups {
  padding-top: 0;
}

.contact-common-groups-head {
  display: flex;
  min-height: 30px;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.compact--with-groups .contact-common-groups-head {
  min-height: 44px;
}

.contact-common-groups-count {
  color: var(--app-text-muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.contact-common-groups-list {
  border-top: 1px solid var(--app-border);
}

.contact-common-group {
  display: grid;
  width: 100%;
  min-height: 44px;
  grid-template-columns: 32px minmax(0, 1fr) 16px;
  align-items: center;
  gap: 9px;
  padding: 6px 2px;
  border: 0;
  border-bottom: 1px solid var(--app-border);
  border-radius: 0;
  color: var(--app-text-primary);
  background: transparent;
  cursor: pointer;
  text-align: left;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.contact-common-group:hover {
  color: var(--app-accent-hover);
  background: var(--app-surface-soft);
}

.contact-common-group:last-child {
  border-bottom: 0;
}

.contact-common-group-avatar {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  overflow: hidden;
  border-radius: 5px;
  color: #fff;
  background: var(--app-border-soft);
  font-size: 12px;
}

.contact-common-group-avatar img,
.contact-common-group-avatar > span {
  width: 100%;
  height: 100%;
}

.contact-common-group-avatar img {
  object-fit: cover;
}

.contact-common-group-avatar > span {
  display: grid;
  place-items: center;
}

.contact-common-group-name {
  min-width: 0;
  overflow: hidden;
  font-size: 13px;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.contact-common-group > i {
  color: var(--app-text-muted);
  font-size: 10px;
}

.contact-profile-section:last-child {
  border-bottom: 0;
  padding-bottom: 2px;
}

.contact-field {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  min-height: 31px;
  align-items: center;
  gap: 10px;
  color: var(--app-text-muted);
  font-size: 13px;
  line-height: 1.4;
}

.contact-field-copy {
  grid-template-columns: 72px minmax(0, 1fr) 24px;
}

.contact-field-tall {
  align-items: start;
  padding-top: 5px;
}

.contact-label {
  color: var(--app-text-muted);
  font-size: 13px;
}

.contact-value {
  min-width: 0;
  overflow: hidden;
  color: var(--app-text-primary);
  font-size: 13px;
  font-weight: 500;
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.contact-signature {
  max-height: 60px;
  overflow: hidden;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.contact-code {
  font-variant-numeric: tabular-nums;
}

.contact-copy {
  display: flex;
  height: 24px;
  width: 24px;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--app-text-muted);
  transition: background 0.16s ease, color 0.16s ease;
}

.contact-copy:hover {
  background: var(--app-surface-soft);
  color: var(--app-text-primary);
}

.contact-error {
  margin-top: 10px;
  padding: 9px 10px;
  border-radius: 8px;
  color: #dc2626;
  background: rgba(254, 242, 242, 0.9);
  border: 1px solid rgba(248, 113, 113, 0.22);
  font-size: 12px;
  line-height: 1.45;
  white-space: pre-wrap;
}

.skeleton {
  position: relative;
  overflow: hidden;
  border-radius: 999px;
  background: var(--app-border-soft);
}

.skeleton::after {
  content: "";
  position: absolute;
  inset: 0;
  transform: translateX(-100%);
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.55), transparent);
  animation: skeleton-shimmer 1.2s infinite;
}

.skeleton-avatar {
  width: 64px;
  height: 64px;
  flex: 0 0 auto;
  border-radius: var(--contact-profile-radius);
}

.skeleton-name {
  width: 46%;
  height: 18px;
  margin-bottom: 9px;
}

.skeleton-username {
  width: 68%;
  height: 13px;
}

.skeleton-label {
  width: 40px;
  height: 13px;
  align-self: center;
}

.skeleton-value {
  width: 72%;
  height: 13px;
  justify-self: end;
  align-self: center;
}

@keyframes skeleton-shimmer {
  100% {
    transform: translateX(100%);
  }
}

html[data-theme='dark'] .contact-error {
  color: #fca5a5;
  background: rgba(127, 29, 29, 0.18);
  border-color: rgba(248, 113, 113, 0.18);
}

.contact-verification-section {
  padding-top: 10px;
}

.contact-verification-head,
.contact-verification-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.contact-verification-head {
  min-height: 28px;
}

.contact-verification-head > span,
.contact-verification-meta time {
  color: var(--app-text-muted);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.contact-verification-list {
  margin-top: 4px;
}

.contact-verification-item {
  padding: 9px 0;
  border-top: 1px solid var(--app-border);
}

.contact-verification-meta > span {
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}

.contact-verification-meta .is-incoming {
  color: #167548;
  background: #e9f8ef;
}

.contact-verification-meta .is-outgoing {
  color: #576b95;
  background: #eef1f6;
}

.contact-verification-item p {
  margin: 7px 0 0;
  color: var(--app-text-primary);
  font-size: 12px;
  line-height: 1.55;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.contact-verification-link {
  display: inline;
  padding: 0;
  border: 0;
  color: #2474c8;
  background: transparent;
  cursor: pointer;
  font: inherit;
  text-align: left;
  text-decoration: none;
  overflow-wrap: anywhere;
}

.contact-verification-link:hover {
  color: #165da5;
  text-decoration: underline;
}

.contact-verification-item .contact-verification-empty {
  color: var(--app-text-muted);
}

html[data-theme='dark'] .chat-contact-card {
  --contact-profile-surface: #292d2a;
  --contact-profile-border: #414842;
}
</style>
