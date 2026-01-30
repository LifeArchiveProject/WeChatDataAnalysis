<template>
  <div class="bg-white rounded-2xl border border-[#EDEDED] p-5 sm:p-6">
    <div class="flex flex-col gap-4">
      <div class="flex flex-col sm:flex-row gap-3 sm:items-end sm:justify-between">
        <div class="flex flex-col sm:flex-row gap-3 sm:items-end">
          <div v-if="showAccount">
            <div class="text-xs font-medium text-[#00000099] mb-1">账号</div>
            <select
              class="w-full sm:w-56 px-3 py-2 rounded-lg border border-[#EDEDED] bg-white text-sm focus:outline-none focus:ring-2 focus:ring-[#07C160]"
              :disabled="accountsLoading || accounts.length === 0"
              :value="modelAccount"
              @change="$emit('update:account', $event.target.value || '')"
            >
              <option value="" :disabled="accounts.length > 0">默认（自动选择）</option>
              <option v-for="a in accounts" :key="a" :value="a">{{ a }}</option>
            </select>
          </div>

          <div>
            <div class="text-xs font-medium text-[#00000099] mb-1">年份</div>
            <select
              class="w-full sm:w-40 px-3 py-2 rounded-lg border border-[#EDEDED] bg-white text-sm focus:outline-none focus:ring-2 focus:ring-[#07C160]"
              :value="String(modelYear)"
              @change="$emit('update:year', Number($event.target.value))"
            >
              <option v-for="y in yearOptions" :key="y" :value="String(y)">{{ y }}年</option>
            </select>
          </div>

          <label class="inline-flex items-center gap-2 select-none">
            <input
              type="checkbox"
              class="h-4 w-4 rounded border-[#EDEDED] text-[#07C160] focus:ring-[#07C160]"
              :checked="modelRefresh"
              @change="$emit('update:refresh', !!$event.target.checked)"
            />
            <span class="text-sm text-[#7F7F7F]">强制刷新（忽略缓存）</span>
          </label>
        </div>

        <div class="flex gap-2">
          <button
            class="inline-flex items-center justify-center px-4 py-2 rounded-lg bg-[#07C160] text-white text-sm font-medium hover:bg-[#06AD56] disabled:opacity-60 disabled:cursor-not-allowed transition"
            :disabled="loading"
            @click="$emit('reload')"
          >
            <span v-if="!loading">生成报告</span>
            <span v-else>生成中...</span>
          </button>
        </div>
      </div>

      <div v-if="accountsLoading" class="text-xs text-[#7F7F7F]">
        {{ showAccount ? '正在加载账号列表...' : '正在检查数据...' }}
      </div>
      <div v-else-if="accounts.length === 0" class="text-xs text-[#B37800]">
        {{ showAccount ? '未发现已解密账号（请先解密数据库）。' : '未发现可用数据（请先解密数据库）。' }}
      </div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  accounts: { type: Array, default: () => [] },
  accountsLoading: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  modelYear: { type: Number, required: true },
  modelAccount: { type: String, default: '' },
  modelRefresh: { type: Boolean, default: false },
  showAccount: { type: Boolean, default: true }
})

defineEmits(['update:year', 'update:account', 'update:refresh', 'reload'])

const yearOptions = computed(() => {
  const now = new Date().getFullYear()
  const years = []
  for (let i = 0; i < 8; i++) years.push(now - i)
  // Ensure selected year is present
  if (props.modelYear && !years.includes(props.modelYear)) years.unshift(props.modelYear)
  return years
})
</script>
