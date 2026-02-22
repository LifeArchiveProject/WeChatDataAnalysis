<template>
  <Teleport to="body">
    <div v-if="open && info" class="fixed inset-0 z-[9999] flex items-center justify-center">
      <div class="absolute inset-0 bg-black/40" @click="onBackdropClick" />

      <div class="relative w-[min(520px,calc(100vw-32px))] rounded-lg bg-white shadow-xl border border-gray-200">
        <button
          class="absolute right-3 top-3 h-8 w-8 rounded-md text-gray-500 hover:bg-gray-100 hover:text-gray-700"
          type="button"
          @click="emitClose"
          aria-label="Close"
        >
          <span class="text-xl leading-none">&times;</span>
        </button>

        <div class="px-5 pt-5 pb-4">
          <div class="text-xs text-gray-500">
            {{ readyToInstall ? '更新已下载完成' : '发现新版本' }}
          </div>
          <div class="mt-1 text-lg font-semibold text-gray-900">
            {{ info.version || '—' }}
          </div>

          <div v-if="readyToInstall" class="mt-2 text-xs text-gray-600">
            你可以选择现在重启安装，或稍后再安装。
          </div>

          <div class="mt-4 rounded-md border border-gray-200 bg-gray-50 p-3">
            <div class="text-xs font-medium text-gray-700">更新内容</div>
            <div
              ref="notesViewportRef"
              class="mt-2 max-h-48 overflow-y-auto pr-1 text-xs text-gray-700"
              @scroll="onNotesScroll"
            >
              <div class="relative" :style="{ height: `${virtualTotalHeight}px` }">
                <div
                  class="absolute left-0 right-0 top-0"
                  :style="{ transform: `translateY(${virtualOffsetTop}px)` }"
                >
                  <div
                    v-for="item in virtualVisibleItems"
                    :key="item.key"
                    class="h-6 leading-6 truncate"
                    :title="item.text"
                  >
                    {{ item.text }}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div v-if="error" class="mt-3 text-xs text-red-600 whitespace-pre-wrap break-words">
            {{ error }}
          </div>

          <div v-if="isDownloading" class="mt-4">
            <div class="flex items-center justify-between gap-3 text-xs text-gray-600">
              <span v-if="speedText">{{ speedText }}</span>
              <span v-else>下载中...</span>
              <span>{{ percentText }}</span>
              <span v-if="remainingText">剩余 {{ remainingText }}</span>
            </div>
            <div class="mt-2 h-2 w-full rounded bg-gray-200 overflow-hidden">
              <div class="h-2 bg-wechat-green" :style="{ width: `${percent}%` }" />
            </div>
          </div>

          <div v-if="isDownloading" class="mt-5 flex items-center justify-end gap-2">
            <button
              class="px-3 py-1.5 rounded-md border border-gray-200 bg-white text-sm text-gray-700 hover:bg-gray-50"
              type="button"
              @click="emitClose"
            >
              后台下载
            </button>
          </div>

          <div v-else class="mt-5 flex items-center justify-end gap-2">
            <button
              class="px-3 py-1.5 rounded-md border border-gray-200 bg-white text-sm text-gray-700 hover:bg-gray-50"
              type="button"
              @click="emitClose"
            >
              稍后
            </button>

            <button
              v-if="readyToInstall"
              class="px-3 py-1.5 rounded-md bg-wechat-green text-white text-sm hover:bg-wechat-green-hover"
              type="button"
              @click="emitInstall"
            >
              立即重启安装
            </button>

            <template v-else>
              <button
                v-if="hasIgnore"
                class="px-3 py-1.5 rounded-md border border-gray-200 bg-white text-sm text-gray-700 hover:bg-gray-50"
                type="button"
                @click="emitIgnore"
              >
                忽略此版本
              </button>
              <button
                class="px-3 py-1.5 rounded-md bg-wechat-green text-white text-sm hover:bg-wechat-green-hover"
                type="button"
                @click="emitUpdate"
              >
                立即更新
              </button>
            </template>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
const props = defineProps({
  open: { type: Boolean, default: false },
  info: { type: Object, default: null }, // { version, releaseNotes }
  isDownloading: { type: Boolean, default: false },
  readyToInstall: { type: Boolean, default: false },
  progress: { type: [Number, Object], default: () => ({ percent: 0 }) },
  error: { type: String, default: "" },
  hasIgnore: { type: Boolean, default: true },
});

const emit = defineEmits(["close", "update", "install", "ignore"]);

const DEFAULT_RELEASE_NOTE = "修复了一些已知问题，提升了稳定性。";
const NOTE_ROW_HEIGHT = 24;
const NOTE_OVERSCAN = 6;
const NOTE_FALLBACK_VIEWPORT_HEIGHT = 192; // 8 rows * 24px

const notesViewportRef = ref(null);
const notesScrollTop = ref(0);

const sanitizeReleaseNotes = (input) => {
  const raw = String(input || "").replace(/\r\n?/g, "\n");
  if (!raw.trim()) return "";
  return raw
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/gi, "$1")
    .replace(/\s*\((https?:\/\/[^)]+)\)/gi, "")
    .replace(/<https?:\/\/[^>]+>/gi, "")
    .replace(/https?:\/\/\S+/gi, "")
    .replace(/[ \t]+$/gm, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
};

const releaseNoteLines = computed(() => {
  const sanitized = sanitizeReleaseNotes(props.info?.releaseNotes || "");
  const lines = sanitized
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .filter((line) => !/^更新内容\s*(\(|（)/.test(line))
    .filter((line) => !/^完整变更[:：]?\s*$/.test(line));
  if (!lines.length) return [DEFAULT_RELEASE_NOTE];
  return lines;
});

const viewportHeight = computed(() => {
  const h = Number(notesViewportRef.value?.clientHeight || 0);
  return h > 0 ? h : NOTE_FALLBACK_VIEWPORT_HEIGHT;
});

const virtualStartIndex = computed(() => {
  const start = Math.floor(notesScrollTop.value / NOTE_ROW_HEIGHT) - NOTE_OVERSCAN;
  return Math.max(0, start);
});

const virtualEndIndex = computed(() => {
  const count = Math.ceil(viewportHeight.value / NOTE_ROW_HEIGHT) + NOTE_OVERSCAN * 2;
  return Math.min(releaseNoteLines.value.length, virtualStartIndex.value + count);
});

const virtualVisibleItems = computed(() => {
  const start = virtualStartIndex.value;
  return releaseNoteLines.value.slice(start, virtualEndIndex.value).map((text, idx) => ({
    key: `${start + idx}-${text}`,
    text,
  }));
});

const virtualOffsetTop = computed(() => virtualStartIndex.value * NOTE_ROW_HEIGHT);
const virtualTotalHeight = computed(() => releaseNoteLines.value.length * NOTE_ROW_HEIGHT);

const onNotesScroll = (event) => {
  notesScrollTop.value = Number(event?.target?.scrollTop || 0);
};

watch(
  () => [props.open, props.info?.version, props.info?.releaseNotes],
  () => {
    notesScrollTop.value = 0;
    if (notesViewportRef.value) {
      notesViewportRef.value.scrollTop = 0;
    }
  }
);

const safeProgress = computed(() => {
  if (typeof props.progress === "number") return { percent: props.progress };
  if (props.progress && typeof props.progress === "object") return props.progress;
  return { percent: 0 };
});

const percent = computed(() => {
  const p = Number(safeProgress.value?.percent || 0);
  if (!Number.isFinite(p)) return 0;
  return Math.max(0, Math.min(100, p));
});

const percentText = computed(() => `${percent.value.toFixed(0)}%`);

const formatBytes = (bytes) => {
  const b = Number(bytes || 0);
  if (!Number.isFinite(b) || b <= 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(b) / Math.log(k));
  const idx = Math.max(0, Math.min(i, sizes.length - 1));
  return `${(b / Math.pow(k, idx)).toFixed(1)} ${sizes[idx]}`;
};

const speedText = computed(() => {
  const bps = safeProgress.value?.bytesPerSecond;
  if (bps == null) return "";
  return `${formatBytes(bps)}/s`;
});

const remainingText = computed(() => {
  const s = safeProgress.value?.remaining;
  const sec = Number(s);
  if (!Number.isFinite(sec)) return "";
  if (sec < 60) return `${Math.ceil(sec)} 秒`;
  const min = Math.floor(sec / 60);
  const rem = Math.ceil(sec % 60);
  return `${min} 分 ${rem} 秒`;
});

const emitClose = () => emit("close");
const emitUpdate = () => emit("update");
const emitInstall = () => emit("install");
const emitIgnore = () => emit("ignore");

const onBackdropClick = () => {
  emitClose();
};
</script>
