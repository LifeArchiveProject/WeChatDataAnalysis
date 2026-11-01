<template>
  <aside ref="panelRef" id="group-members-sidebar" class="resource-sidebar relative flex h-full shrink-0 flex-col border-l" :style="{ width: `${panelWidth}px` }" aria-label="群成员">
    <div
      class="absolute -left-1 top-0 bottom-0 z-10 w-2 cursor-col-resize touch-none hover:bg-[#07C160]/20"
      :class="{ 'bg-[#07C160]/20': resizing }"
      role="separator"
      tabindex="0"
      aria-label="调整群成员栏宽度"
      aria-orientation="vertical"
      :aria-valuemin="minWidth"
      :aria-valuemax="maxWidth"
      :aria-valuenow="panelWidth"
      title="拖动调整宽度"
      @pointerdown="startResize"
      @lostpointercapture="finishResize"
      @keydown="resizeKeyboard"
    />
    <div class="resource-sidebar-header border-b px-4 py-4">
      <h3 class="resource-sidebar-title text-sm font-medium">群成员</h3>
    </div>
    <div ref="scrollRef" class="min-h-0 flex-1 overflow-y-auto p-4 scrollbar-custom" @scroll.passive="onScroll">
      <div class="grid grid-cols-[repeat(auto-fill,minmax(42px,1fr))] gap-x-2 gap-y-3">
        <div v-for="member in members" :key="member.username" class="min-w-0 text-center" :class="{ 'privacy-blur': privacyMode }" @mouseenter="onMemberMouseEnter($event, member)" @mouseleave="state.onMessageAvatarMouseLeave">
          <div class="mx-auto flex h-8 w-8 items-center justify-center overflow-hidden rounded-md bg-gray-200 text-xs text-gray-500">
            <img v-if="member.avatar" :src="member.avatar" :alt="member.displayName" class="h-full w-full object-cover" loading="lazy" referrerpolicy="no-referrer" @error="member.avatar = ''" />
            <span v-else>{{ member.displayName.charAt(0) }}</span>
          </div>
          <div class="mt-1 truncate text-[11px]">{{ member.displayName }}</div>
        </div>
      </div>
      <ErrorNotice v-if="error" :message="error" compact class="mt-3 text-xs" />
      <div v-if="loading" class="resource-sidebar-muted py-4 text-center text-xs">加载中...</div>
      <div v-else-if="!members.length && !error" class="resource-sidebar-muted py-4 text-center text-xs">暂无群成员</div>
    </div>
  </aside>
  <Teleport to="body">
    <div v-if="memberProfileOpen" ref="profileHost" class="fixed z-[160] w-[400px] max-w-[92vw]" :style="profileStyle">
      <ContactProfileCard :state="state" />
    </div>
  </Teleport>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, unref, watch } from 'vue'
import { useApi } from '~/composables/useApi'
import { useAgentPanelResize } from '~/composables/useAgentPanelResize'
import ContactProfileCard from '~/components/chat/ContactProfileCard.vue'

const props = defineProps({
  account: { type: String, required: true },
  username: { type: String, required: true },
  privacyMode: { type: Boolean, default: false },
  state: { type: Object, required: true }
})
const api = useApi()
const panelRef = ref(null)
const { width: panelWidth, minimum: minWidth, maximum: maxWidth, resizing, start: startResize, finish: finishResize, keyboard: resizeKeyboard } = useAgentPanelResize(panelRef, ref(false), {
  storageKey: 'chat-group-members-width', defaultWidth: 280, minWidth: 220
})
const scrollRef = ref(null)
const members = ref([])
const loading = ref(false)
const error = ref('')
const hasMore = ref(true)
let nextOffset = 0
const controller = new AbortController()
const profileHost = ref(null)
const profileStyle = ref({})
const memberCardPrefix = `group-member:${props.username}:`
const memberProfileOpen = computed(() => unref(props.state.contactProfileCardOpen)
  && String(unref(props.state.contactProfileCardMessageId)).startsWith(memberCardPrefix))
let memberAnchor = null
let profileObserver = null

const updateProfilePosition = () => {
  if (!profileHost.value || !memberAnchor) return
  const card = profileHost.value.getBoundingClientRect()
  profileStyle.value = {
    left: `${Math.max(8, memberAnchor.left - card.width - 8)}px`,
    top: `${Math.max(8, Math.min(memberAnchor.top, window.innerHeight - card.height - 8))}px`
  }
}
watch(profileHost, (element) => {
  profileObserver?.disconnect()
  if (!element) return
  updateProfilePosition()
  profileObserver = new ResizeObserver(updateProfilePosition)
  profileObserver.observe(element)
})

const onMemberMouseEnter = (event, member) => {
  const cardId = memberCardPrefix + member.username
  if (unref(props.state.contactProfileCardMessageId) !== cardId) props.state.closeContactProfileCard()
  memberAnchor = event.currentTarget.getBoundingClientRect()
  updateProfilePosition()
  props.state.onMessageAvatarMouseEnter({
    id: cardId,
    senderUsername: member.username,
    senderDisplayName: member.displayName,
    avatar: member.avatar,
    isGroup: false
  })
}

const loadMore = async () => {
  if (loading.value || !hasMore.value || controller.signal.aborted) return
  loading.value = true
  error.value = ''
  try {
    const result = await api.getChatGroupMembers({
      account: props.account,
      username: props.username,
      offset: nextOffset,
      signal: controller.signal
    })
    if (controller.signal.aborted) return
    members.value.push(...result.members)
    nextOffset = result.nextOffset
    hasMore.value = result.hasMore
  } catch (err) {
    if (!controller.signal.aborted) error.value = err?.message || '群成员加载失败'
  } finally {
    loading.value = false
  }
  await nextTick()
  const el = scrollRef.value
  if (!error.value && el && el.scrollHeight <= el.clientHeight) void loadMore()
}

const onScroll = (event) => {
  props.state.closeContactProfileCard()
  const el = event.currentTarget
  if (el.scrollHeight - el.scrollTop - el.clientHeight < 120) void loadMore()
}

watch(resizing, async (active) => {
  props.state.closeContactProfileCard()
  if (active) return
  await nextTick()
  const el = scrollRef.value
  if (el && el.scrollHeight <= el.clientHeight) void loadMore()
})

onMounted(loadMore)
onUnmounted(() => {
  controller.abort()
  profileObserver?.disconnect()
  props.state.closeContactProfileCard()
})
</script>
