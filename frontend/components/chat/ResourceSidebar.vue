<template>
  <transition name="sidebar-slide">
    <aside
      v-if="resourceSidebarOpen"
      class="resource-sidebar flex h-full w-[640px] max-w-[55vw] flex-shrink-0 flex-col border-l"
    >
      <div class="resource-sidebar-header flex items-center gap-2 border-b px-4 py-3">
        <div class="min-w-0 flex-1">
          <div class="resource-sidebar-title flex items-center gap-2 text-sm font-medium">
            <svg class="resource-sidebar-icon h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="4" width="18" height="16" rx="2" />
              <circle cx="8.5" cy="9" r="1.5" />
              <path d="M21 15l-5-5L5 20" />
              <path d="M14 7l4 2.5-4 2.5V7z" />
            </svg>
            <span>图片和视频资源</span>
          </div>
          <div class="resource-sidebar-muted mt-0.5 text-[11px]" :class="{ 'privacy-blur': privacyMode }">
            {{ resourceItems.length }} 个资源
            <span v-if="resourceHasMore"> · 向下滚动继续加载</span>
          </div>
        </div>
        <select
          v-model="resourceTimeGroup"
          class="resource-sidebar-select rounded-md border px-2 py-1 text-[12px] outline-none focus:border-[#03C160] focus:ring-1 focus:ring-[#03C160]/20"
          title="选择时间分割间隔"
        >
          <option v-for="opt in resourceGroupOptions" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
        <button
          type="button"
          class="resource-sidebar-close rounded-md p-1.5 transition-colors"
          title="关闭"
          @click="closeResourceSidebar"
        >
          <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div
        ref="resourceScrollRef"
        class="resource-sidebar-results min-h-0 flex-1 overflow-y-auto px-3 py-3 scrollbar-custom"
        @scroll.passive="onResourceSidebarScroll"
      >
        <div v-if="resourceError" class="resource-sidebar-error mb-3 rounded-lg border px-3 py-2 text-[12px]">
          {{ resourceError }}
        </div>

        <div
          v-if="groupedResourceItems.length"
          class="grid"
          :style="resourceGridStyle"
        >
          <template v-for="row in groupedResourceItems" :key="row.key">
            <div
              v-if="row.type === 'divider'"
              class="resource-group-divider col-span-full sticky top-0 z-10 -mx-1 rounded-md px-1 py-1 text-[12px] font-medium backdrop-blur"
            >
              {{ row.label }}
            </div>
            <button
              v-else
              type="button"
              class="resource-card group relative aspect-square overflow-hidden border text-left"
              :class="resourceCardClass"
              :title="row.item.kind === 'video' ? '打开视频' : `打开图片（${row.item.variant}）`"
              style="content-visibility: auto; contain-intrinsic-size: 80px 80px;"
              @click="openResourcePreview(row.item)"
            >
              <img
                v-if="row.item.thumbUrl"
                :src="row.item.thumbUrl"
                alt="资源"
                class="h-full w-full object-cover"
                :class="[resourceImageClass, { 'privacy-blur': privacyMode }]"
                loading="lazy"
                decoding="async"
                fetchpriority="low"
              >
              <div v-else class="resource-empty flex h-full w-full items-center justify-center text-[11px]">
                无预览
              </div>
              <div
                class="absolute left-1 top-1 rounded bg-black/55 text-white"
                :class="resourceBadgeClass"
                :title="row.item.variant"
              >
                {{ resourceTimeGroup === 'year' ? row.item.variantShort : row.item.variant }}
              </div>
              <div
                v-if="row.item.kind === 'video'"
                class="absolute inset-0 flex items-center justify-center"
              >
                <div
                  class="flex items-center justify-center rounded-full bg-black/45 text-white"
                  :class="resourceTimeGroup === 'year' ? 'h-5 w-5' : 'h-9 w-9'"
                >
                  <svg :class="resourceTimeGroup === 'year' ? 'h-3 w-3' : 'h-5 w-5'" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M8 5v14l11-7z" />
                  </svg>
                </div>
              </div>
              <div
                v-if="resourceTimeGroup !== 'year'"
                class="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/60 to-transparent px-1.5 pb-1 pt-5 text-[10px] text-white/90 opacity-0 transition group-hover:opacity-100"
                :class="{ 'privacy-blur': privacyMode }"
              >
                {{ formatMessageFullTime(row.item.createTime) }}
              </div>
            </button>
          </template>
        </div>

        <div v-else-if="!resourceLoading" class="resource-empty flex h-full min-h-[220px] items-center justify-center text-center text-[13px]">
          当前会话暂无图片或视频资源
        </div>
        <div v-if="resourceLoading" class="resource-status py-4 text-center text-[12px]">加载中...</div>
        <div v-else-if="resourceHasMore && resourceItems.length" class="py-4 text-center">
          <button
            type="button"
            class="resource-load-more rounded-full border px-3 py-1.5 text-[12px] transition-colors"
            @click="loadResourceItems()"
          >
            继续加载
          </button>
        </div>
        <div v-else-if="!resourceHasMore && resourceItems.length" class="resource-status py-4 text-center text-[12px]">已加载全部资源</div>
      </div>
    </aside>
  </transition>
</template>

<script>
import { computed, defineComponent, nextTick, ref, watch } from 'vue'

const readMaybeRef = (value) => {
  if (value && typeof value === 'object' && 'value' in value) return value.value
  return value
}

export default defineComponent({
  name: 'ResourceSidebar',
  props: {
    state: { type: Object, required: true }
  },
  setup(props) {
    const resourceScrollRef = ref(null)
    let ensureScheduled = false

    const getResourceMode = () => String(readMaybeRef(props.state.resourceTimeGroup) || 'day')

    const resourceCardClass = computed(() => {
      const mode = getResourceMode()
      if (mode === 'year') return 'rounded-sm resource-card-year'
      if (mode === 'month') return 'rounded-md resource-card-compact'
      return 'rounded-lg resource-card-normal'
    })

    const resourceImageClass = computed(() => {
      const mode = getResourceMode()
      if (mode === 'year') return ''
      return 'transition duration-150 group-hover:scale-[1.03]'
    })

    const resourceBadgeClass = computed(() => {
      const mode = getResourceMode()
      if (mode === 'year') return 'px-1 py-0 text-[9px] leading-3'
      if (mode === 'month') return 'px-1 py-0.5 text-[9px] leading-3'
      return 'px-1.5 py-0.5 text-[10px] leading-4'
    })

    const ensureResourceViewportFilled = async () => {
      await nextTick()
      const el = resourceScrollRef.value
      if (!el) return
      if (!readMaybeRef(props.state.resourceSidebarOpen)) return
      if (!readMaybeRef(props.state.resourceHasMore)) return
      if (readMaybeRef(props.state.resourceLoading)) return

      const mode = getResourceMode()
      const maxAutoLoads = mode === 'year' ? 1 : (mode === 'month' ? 4 : 3)
      let count = 0
      while (
        count < maxAutoLoads
        && readMaybeRef(props.state.resourceSidebarOpen)
        && readMaybeRef(props.state.resourceHasMore)
        && !readMaybeRef(props.state.resourceLoading)
        && Number(el.scrollHeight || 0) <= Number(el.clientHeight || 0) + 160
      ) {
        count += 1
        await props.state.loadResourceItems?.()
        await nextTick()
      }
    }

    const scheduleEnsureResourceViewportFilled = () => {
      if (ensureScheduled) return
      ensureScheduled = true
      const run = () => {
        ensureScheduled = false
        void ensureResourceViewportFilled()
      }
      if (typeof window !== 'undefined' && typeof window.requestAnimationFrame === 'function') {
        window.requestAnimationFrame(run)
      } else {
        setTimeout(run, 16)
      }
    }

    watch(
      () => getResourceMode(),
      async () => {
        await nextTick()
        if (resourceScrollRef.value) resourceScrollRef.value.scrollTop = 0
        scheduleEnsureResourceViewportFilled()
      }
    )

    watch(
      () => [
        !!readMaybeRef(props.state.resourceSidebarOpen),
        Number(readMaybeRef(props.state.resourceItems)?.length || 0),
        !!readMaybeRef(props.state.resourceHasMore),
        !!readMaybeRef(props.state.resourceLoading)
      ],
      () => scheduleEnsureResourceViewportFilled(),
      { flush: 'post' }
    )

    return {
      ...props.state,
      resourceScrollRef,
      resourceCardClass,
      resourceImageClass,
      resourceBadgeClass
    }
  }
})
</script>
