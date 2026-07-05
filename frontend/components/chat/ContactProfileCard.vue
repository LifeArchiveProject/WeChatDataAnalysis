<template>
  <div
    class="chat-contact-card"
    @mouseenter="onContactCardMouseEnter"
    @mouseleave="onMessageAvatarMouseLeave"
  >
    <div class="contact-card-title">联系人资料</div>

    <div v-if="contactProfileLoading" class="contact-card-body">
      <div class="contact-card-head">
        <div class="skeleton skeleton-avatar"></div>
        <div class="min-w-0 flex-1">
          <div class="skeleton skeleton-name"></div>
          <div class="skeleton skeleton-username"></div>
        </div>
      </div>
      <div class="contact-card-fields">
        <div v-for="idx in 6" :key="idx" class="contact-field">
          <div class="skeleton skeleton-label"></div>
          <div class="skeleton skeleton-value"></div>
        </div>
      </div>
    </div>

    <div v-else-if="contactProfileError" class="contact-card-body">
      <div class="contact-error">{{ contactProfileError }}</div>
    </div>

    <div v-else class="contact-card-body">
      <div class="contact-card-head">
        <div class="contact-avatar" :class="{ 'privacy-blur': privacyMode }">
          <img
            v-if="contactProfileResolvedAvatar"
            :src="contactProfileResolvedAvatar"
            alt="联系人头像"
            class="w-full h-full object-cover"
            referrerpolicy="no-referrer"
          />
          <div v-else class="contact-avatar-fallback">{{ contactProfileResolvedName.charAt(0) || '?' }}</div>
        </div>
        <div class="min-w-0 flex-1" :class="{ 'privacy-blur': privacyMode }">
          <div class="contact-name">{{ contactProfileResolvedName || '未知联系人' }}</div>
          <div class="contact-username" :title="contactProfileResolvedUsername">{{ contactProfileResolvedUsername }}</div>
        </div>
      </div>

      <div class="contact-card-fields">
        <div class="contact-field">
          <div class="contact-label">昵称</div>
          <div class="contact-value" :class="{ 'privacy-blur': privacyMode }">{{ contactProfileResolvedNickname || '-' }}</div>
        </div>
        <div class="contact-field">
          <div class="contact-label">微信号</div>
          <div class="contact-value contact-code" :class="{ 'privacy-blur': privacyMode }">{{ contactProfileResolvedAlias || '-' }}</div>
        </div>
        <div class="contact-field">
          <div class="contact-label">性别</div>
          <div class="contact-value" :class="{ 'privacy-blur': privacyMode }">{{ contactProfileResolvedGender || '-' }}</div>
        </div>
        <div class="contact-field">
          <div class="contact-label">地区</div>
          <div class="contact-value" :class="{ 'privacy-blur': privacyMode }">{{ contactProfileResolvedRegion || '-' }}</div>
        </div>
        <div class="contact-field">
          <div class="contact-label">备注</div>
          <div class="contact-value" :class="{ 'privacy-blur': privacyMode }">{{ contactProfileResolvedRemark || '-' }}</div>
        </div>
        <div class="contact-field">
          <div class="contact-label">签名</div>
          <div class="contact-value whitespace-pre-wrap" :class="{ 'privacy-blur': privacyMode }">{{ contactProfileResolvedSignature || '-' }}</div>
        </div>
        <div class="contact-field" :title="contactProfileResolvedSourceScene != null ? `来源场景码：${contactProfileResolvedSourceScene}` : ''">
          <div class="contact-label">来源</div>
          <div class="contact-value" :class="{ 'privacy-blur': privacyMode }">{{ contactProfileResolvedSource || '-' }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { defineComponent } from 'vue'

export default defineComponent({
  name: 'ContactProfileCard',
  props: {
    state: { type: Object, required: true }
  },
  setup(props) {
    return {
      ...props.state
    }
  }
})
</script>

<style scoped>
.chat-contact-card {
  /* 不设置 position：外层 MessageItem 传入的 absolute 不能被覆盖，否则会挤乱消息流。 */
  overflow: hidden;
  border-radius: 10px;
  background: var(--app-surface-bg);
  border: 1px solid var(--app-border);
  color: var(--app-text-primary);
  box-shadow: 0 12px 36px rgba(15, 23, 42, 0.14);
}

.contact-card-title {
  padding: 11px 14px;
  border-bottom: 1px solid var(--app-border);
  color: var(--app-text-primary);
  font-size: 14px;
  font-weight: 500;
  line-height: 1.3;
  background: var(--app-surface-bg);
}

.contact-card-body {
  padding: 12px;
  background: var(--app-surface-soft);
}

.contact-card-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: 8px;
  background: var(--app-surface-bg);
  border: 1px solid var(--app-border);
}

.contact-avatar {
  width: 54px;
  height: 54px;
  flex: 0 0 auto;
  overflow: hidden;
  border-radius: 8px;
  background: var(--app-border-soft);
}

.contact-avatar-fallback {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  background: #6b7280;
  font-size: 18px;
  font-weight: 600;
}

.contact-name {
  color: var(--app-text-primary);
  font-size: 16px;
  font-weight: 500;
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.contact-username {
  margin-top: 3px;
  color: var(--app-text-muted);
  font-size: 12px;
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.contact-card-fields {
  margin-top: 8px;
  overflow: hidden;
  border-radius: 8px;
  background: var(--app-surface-bg);
  border: 1px solid var(--app-border);
}

.contact-field {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr);
  gap: 10px;
  padding: 10px 12px;
  min-height: 39px;
}

.contact-field + .contact-field {
  border-top: 1px solid var(--app-border);
}

.contact-label {
  color: var(--app-text-muted);
  font-size: 13px;
  line-height: 1.45;
}

.contact-value {
  min-width: 0;
  color: var(--app-text-primary);
  font-size: 13px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.contact-code {
  font-variant-numeric: tabular-nums;
}

.contact-error {
  padding: 12px;
  border-radius: 8px;
  color: #dc2626;
  background: rgba(254, 242, 242, 0.9);
  border: 1px solid rgba(248, 113, 113, 0.22);
  font-size: 13px;
  line-height: 1.5;
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
  width: 54px;
  height: 54px;
  flex: 0 0 auto;
  border-radius: 8px;
}

.skeleton-name {
  width: 42%;
  height: 16px;
  margin-bottom: 8px;
}

.skeleton-username {
  width: 66%;
  height: 12px;
}

.skeleton-label {
  width: 36px;
  height: 13px;
  align-self: center;
}

.skeleton-value {
  width: 70%;
  height: 13px;
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
</style>
