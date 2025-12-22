<template>
  <div class="min-h-screen flex items-center justify-center py-8">
    
    <div class="max-w-4xl mx-auto px-6 w-full">
      <!-- 步骤指示器 -->
      <div class="mb-8">
        <Stepper :steps="steps" :current-step="currentStep" />
      </div>

      <!-- 步骤1: 数据库解密 -->
      <div v-if="currentStep === 0" class="bg-white rounded-2xl border border-[#EDEDED]">
        <div class="p-8">
          <div class="flex items-center mb-6">
            <div class="w-12 h-12 bg-[#07C160] rounded-lg flex items-center justify-center mr-4">
              <svg class="w-7 h-7 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"/>
              </svg>
            </div>
            <div>
              <h2 class="text-xl font-bold text-[#000000e6]">数据库解密</h2>
              <p class="text-sm text-[#7F7F7F]">输入密钥和路径开始解密</p>
            </div>
          </div>
          
          <form @submit.prevent="handleDecrypt" class="space-y-6">
            <!-- 密钥输入 -->
            <div>
              <label for="key" class="block text-sm font-medium text-[#000000e6] mb-2">
                <svg class="w-4 h-4 inline mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z"/>
                </svg>
                解密密钥 <span class="text-red-500">*</span>
              </label>
              <div class="relative">
                <input
                  id="key"
                  v-model="formData.key"
                  type="text"
                  placeholder="请输入64位十六进制密钥"
                  class="w-full px-4 py-3 bg-white border border-[#EDEDED] rounded-lg font-mono text-sm focus:outline-none focus:ring-2 focus:ring-[#07C160] focus:border-transparent transition-all duration-200"
                  :class="{ 'border-red-500': formErrors.key }"
                  required
                />
                <div v-if="formData.key" class="absolute right-3 top-1/2 transform -translate-y-1/2">
                  <span class="text-xs text-[#7F7F7F]">{{ formData.key.length }}/64</span>
                </div>
              </div>
              <p v-if="formErrors.key" class="mt-1 text-sm text-red-600 flex items-center">
                <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
                {{ formErrors.key }}
              </p>
              <p class="mt-2 text-xs text-[#7F7F7F] flex items-center">
                <svg class="w-4 h-4 mr-1 text-[#10AEEF]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
                使用 <a href="https://github.com/gzygood/DbkeyHook" target="_blank" class="text-[#07C160] hover:text-[#06AD56]">DbkeyHook</a> 等工具获取的64位十六进制字符串
              </p>
            </div>
            
            <!-- 数据库路径输入 -->
            <div>
              <label for="dbPath" class="block text-sm font-medium text-[#000000e6] mb-2">
                <svg class="w-4 h-4 inline mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
                </svg>
                数据库存储路径 <span class="text-red-500">*</span>
              </label>
              <input
                id="dbPath"
                v-model="formData.db_storage_path"
                type="text"
                placeholder="例如: D:\wechatMSG\xwechat_files\wxid_xxx\db_storage"
                class="w-full px-4 py-3 bg-white border border-[#EDEDED] rounded-lg font-mono text-sm focus:outline-none focus:ring-2 focus:ring-[#07C160] focus:border-transparent transition-all duration-200"
                :class="{ 'border-red-500': formErrors.db_storage_path }"
                required
              />
              <p v-if="formErrors.db_storage_path" class="mt-1 text-sm text-red-600 flex items-center">
                <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
                {{ formErrors.db_storage_path }}
              </p>
              <p class="mt-2 text-xs text-[#7F7F7F] flex items-center">
                <svg class="w-4 h-4 mr-1 text-[#10AEEF]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
                请输入数据库文件所在的绝对路径
              </p>
            </div>
            
            <!-- 提交按钮 -->
            <div class="pt-4 border-t border-[#EDEDED]">
              <div class="flex items-center justify-center">
                <button
                  type="submit"
                  :disabled="loading"
                  class="inline-flex items-center px-8 py-3 bg-[#07C160] text-white rounded-lg text-base font-medium hover:bg-[#06AD56] transform hover:scale-105 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <svg v-if="!loading" class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 11V7a4 4 0 118 0m-4 8v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2z"/>
                  </svg>
                  <svg v-if="loading" class="w-5 h-5 mr-2 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  {{ loading ? '解密中...' : '开始解密' }}
                </button>
              </div>
            </div>
          </form>
        </div>
      </div>

      <!-- 步骤2: 图片密钥获取 -->
      <div v-if="currentStep === 1" class="bg-white rounded-2xl border border-[#EDEDED]">
        <div class="p-8">
          <div class="flex items-center mb-6">
            <div class="w-12 h-12 bg-[#10AEEF] rounded-lg flex items-center justify-center mr-4">
              <svg class="w-7 h-7 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z"/>
              </svg>
            </div>
            <div>
              <h2 class="text-xl font-bold text-[#000000e6]">图片密钥</h2>
              <p class="text-sm text-[#7F7F7F]">获取图片解密所需的密钥</p>
            </div>
          </div>

          <!-- 密钥信息显示 -->
          <div class="space-y-4 mb-6">
            <div class="bg-gray-50 rounded-lg p-4">
              <div class="flex justify-between items-center mb-2">
                <span class="text-sm font-medium text-[#000000e6]">XOR 密钥</span>
                <button
                  type="button"
                  class="font-mono text-sm px-3 py-1 bg-white rounded border border-[#EDEDED] transition-colors"
                  :class="mediaKeys.xor_key ? 'cursor-pointer hover:bg-gray-50' : 'cursor-not-allowed opacity-60'"
                  :title="mediaKeys.xor_key ? '点击复制' : ''"
                  @click="copyKey('XOR 密钥', mediaKeys.xor_key)"
                >
                  {{ mediaKeys.xor_key || '未获取' }}
                </button>
              </div>
              <div class="flex justify-between items-center">
                <span class="text-sm font-medium text-[#000000e6]">AES 密钥</span>
                <button
                  type="button"
                  class="font-mono text-sm px-3 py-1 bg-white rounded border border-[#EDEDED] transition-colors"
                  :class="mediaKeys.aes_key ? 'cursor-pointer hover:bg-gray-50' : 'cursor-not-allowed opacity-60'"
                  :title="mediaKeys.aes_key ? '点击复制' : ''"
                  @click="copyKey('AES 密钥', mediaKeys.aes_key)"
                >
                  {{ mediaKeys.aes_key || '未获取' }}
                </button>
              </div>
            </div>

            <div v-if="mediaKeys.message" class="text-sm text-[#7F7F7F] flex items-start">
              <svg class="w-4 h-4 mr-2 mt-0.5 flex-shrink-0 text-[#10AEEF]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
              </svg>
              {{ mediaKeys.message }}
            </div>

            <div v-if="copyMessage" class="text-sm text-[#07C160] flex items-start">
              <svg class="w-4 h-4 mr-2 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
              </svg>
              {{ copyMessage }}
            </div>
          </div>

          <!-- 操作按钮 -->
          <div class="flex gap-3 justify-center pt-4 border-t border-[#EDEDED]">
            <button
              @click="fetchMediaKeys(false)"
              :disabled="mediaLoading"
              class="inline-flex items-center px-6 py-3 bg-[#10AEEF] text-white rounded-lg font-medium hover:bg-[#0D9BD9] transition-all duration-200 disabled:opacity-50"
            >
              <svg v-if="mediaLoading" class="w-5 h-5 mr-2 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
              </svg>
              <svg v-else class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
              </svg>
              {{ mediaLoading ? '获取中...' : '获取密钥' }}
            </button>
            <button
              @click="fetchMediaKeys(true)"
              :disabled="mediaLoading"
              class="inline-flex items-center px-6 py-3 bg-white text-[#10AEEF] border border-[#10AEEF] rounded-lg font-medium hover:bg-gray-50 transition-all duration-200 disabled:opacity-50"
            >
              强制重新提取
            </button>
            <button
              v-if="mediaKeys.xor_key"
              @click="goToStep(2)"
              class="inline-flex items-center px-6 py-3 bg-[#07C160] text-white rounded-lg font-medium hover:bg-[#06AD56] transition-all duration-200"
            >
              下一步
              <svg class="w-5 h-5 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
              </svg>
            </button>
          </div>

          <!-- 跳过按钮 -->
          <div class="text-center mt-4">
            <button @click="skipToChat" class="text-sm text-[#7F7F7F] hover:text-[#07C160] transition-colors">
              跳过图片解密，直接查看聊天记录 →
            </button>
          </div>
        </div>
      </div>

      <!-- 步骤3: 批量解密图片 -->
      <div v-if="currentStep === 2" class="bg-white rounded-2xl border border-[#EDEDED]">
        <div class="p-8">
          <div class="flex items-center justify-between mb-6">
            <div class="flex items-center">
              <div class="w-12 h-12 bg-[#91D300] rounded-lg flex items-center justify-center mr-4">
                <svg class="w-7 h-7 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/>
                </svg>
              </div>
              <div>
                <h2 class="text-xl font-bold text-[#000000e6]">批量解密图片</h2>
                <p class="text-sm text-[#7F7F7F]">仅解密加密的图片文件(.dat)，其他文件无需解密</p>
              </div>
            </div>
            <!-- 进度计数 -->
            <div v-if="mediaDecrypting && decryptProgress.total > 0" class="text-right">
              <div class="text-lg font-bold text-[#91D300]">{{ decryptProgress.current }} / {{ decryptProgress.total }}</div>
              <div class="text-xs text-[#7F7F7F]">已处理 / 总图片</div>
            </div>
          </div>

          <!-- 实时进度条 -->
          <div v-if="mediaDecrypting || decryptProgress.total > 0" class="mb-6">
            <!-- 进度条 -->
            <div class="mb-3">
              <div class="flex justify-between text-xs text-[#7F7F7F] mb-1">
                <span>解密进度</span>
                <span>{{ progressPercent }}%</span>
              </div>
              <div class="w-full bg-gray-200 rounded-full h-2.5 overflow-hidden">
                <div 
                  class="h-2.5 rounded-full transition-all duration-300 ease-out"
                  :class="decryptProgress.status === 'complete' ? 'bg-[#07C160]' : 'bg-[#91D300]'"
                  :style="{ width: progressPercent + '%' }"
                ></div>
              </div>
            </div>

            <!-- 当前文件名 -->
            <div v-if="decryptProgress.current_file" class="flex items-center text-sm text-[#7F7F7F] mb-3">
              <svg class="w-4 h-4 mr-2 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14"/>
              </svg>
              <span class="truncate font-mono text-xs">{{ decryptProgress.current_file }}</span>
              <span 
                class="ml-2 px-2 py-0.5 rounded text-xs"
                :class="{
                  'bg-green-100 text-green-700': decryptProgress.fileStatus === 'success',
                  'bg-gray-100 text-gray-600': decryptProgress.fileStatus === 'skip',
                  'bg-red-100 text-red-700': decryptProgress.fileStatus === 'fail'
                }"
              >
                {{ decryptProgress.fileStatus === 'success' ? '解密成功' : decryptProgress.fileStatus === 'skip' ? '已存在' : decryptProgress.fileStatus === 'fail' ? '失败' : '' }}
              </span>
            </div>

            <!-- 实时统计 -->
            <div class="grid grid-cols-4 gap-3 text-center bg-gray-50 rounded-lg p-3">
              <div>
                <div class="text-xl font-bold text-[#10AEEF]">{{ decryptProgress.total }}</div>
                <div class="text-xs text-[#7F7F7F]">总图片</div>
              </div>
              <div>
                <div class="text-xl font-bold text-[#07C160]">{{ decryptProgress.success_count }}</div>
                <div class="text-xs text-[#7F7F7F]">成功</div>
              </div>
              <div>
                <div class="text-xl font-bold text-[#7F7F7F]">{{ decryptProgress.skip_count }}</div>
                <div class="text-xs text-[#7F7F7F]">跳过(已解密)</div>
              </div>
              <div>
                <div class="text-xl font-bold text-[#FA5151]">{{ decryptProgress.fail_count }}</div>
                <div class="text-xs text-[#7F7F7F]">失败</div>
              </div>
            </div>
          </div>

          <!-- 完成后的结果 -->
          <div v-if="mediaDecryptResult && !mediaDecrypting" class="mb-6">
            <div class="bg-green-50 border border-green-200 rounded-lg p-4">
              <div class="flex items-center mb-2">
                <svg class="w-5 h-5 text-green-600 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
                </svg>
                <span class="font-medium text-green-700">解密完成</span>
              </div>
              <div class="text-sm text-green-600">
                输出目录: <code class="bg-white px-2 py-1 rounded text-xs">{{ mediaDecryptResult.output_dir }}</code>
              </div>
            </div>
          </div>

          <!-- 失败原因说明 -->
          <div v-if="decryptProgress.fail_count > 0" class="mb-6">
            <details class="text-sm">
              <summary class="cursor-pointer text-[#7F7F7F] hover:text-[#000000e6]">
                <span class="ml-1">查看失败原因说明</span>
              </summary>
              <div class="mt-2 bg-gray-50 rounded-lg p-3 text-xs text-[#7F7F7F]">
                <p class="mb-2">可能的失败原因：</p>
                <ul class="list-disc list-inside space-y-1">
                  <li><strong>解密后非有效图片</strong>：文件不是图片格式(如视频缩略图损坏)</li>
                  <li><strong>V4-V2版本需要AES密钥</strong>：需要微信运行，且部分环境需以管理员身份运行后端才能提取</li>
                  <li><strong>未知加密版本</strong>：新版微信使用了不支持的加密方式</li>
                  <li><strong>文件为空</strong>：原始文件损坏或为空文件</li>
                </ul>
              </div>
            </details>
          </div>

          <!-- 操作按钮 -->
          <div class="flex gap-3 justify-center pt-4 border-t border-[#EDEDED]">
            <button
              @click="decryptAllImages"
              :disabled="mediaDecrypting"
              class="inline-flex items-center px-6 py-3 bg-[#91D300] text-white rounded-lg font-medium hover:bg-[#82BD00] transition-all duration-200 disabled:opacity-50"
            >
              <svg v-if="mediaDecrypting" class="w-5 h-5 mr-2 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
              </svg>
              <svg v-else class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14"/>
              </svg>
              {{ mediaDecrypting ? '解密中...' : (mediaDecryptResult ? '重新解密' : '开始解密图片') }}
            </button>
            <button
              @click="skipToChat"
              :disabled="mediaDecrypting"
              class="inline-flex items-center px-6 py-3 bg-[#07C160] text-white rounded-lg font-medium hover:bg-[#06AD56] transition-all duration-200 disabled:opacity-50"
            >
              查看聊天记录
              <svg class="w-5 h-5 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
              </svg>
            </button>
          </div>
        </div>
      </div>
    
      <!-- 错误提示 -->
      <transition name="fade">
        <div v-if="error" class="bg-red-50 border border-red-200 rounded-lg p-4 mt-6 animate-shake flex items-start">
          <svg class="h-5 w-5 mr-2 flex-shrink-0 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
          </svg>
          <div>
            <p class="font-semibold text-red-700">操作失败</p>
            <p class="text-sm mt-1 text-red-600">{{ error }}</p>
          </div>
        </div>
      </transition>
    </div>
  </div>
</template>

<style scoped>
/* 动画效果 */
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from, .fade-leave-to {
  opacity: 0;
}

@keyframes shake {
  0%, 100% { transform: translateX(0); }
  10%, 30%, 50%, 70%, 90% { transform: translateX(-5px); }
  20%, 40%, 60%, 80% { transform: translateX(5px); }
}

.animate-shake {
  animation: shake 0.5s ease-in-out;
}
</style>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useApi } from '~/composables/useApi'

const { decryptDatabase, getMediaKeys, decryptAllMedia } = useApi()

const loading = ref(false)
const error = ref('')
const currentStep = ref(0)

// 步骤定义
const steps = [
  { title: '数据库解密' },
  { title: '图片密钥' },
  { title: '图片解密' }
]

// 表单数据
const formData = reactive({
  key: '',
  db_storage_path: ''
})

// 表单错误
const formErrors = reactive({
  key: '',
  db_storage_path: ''
})

// 图片密钥相关
const mediaKeys = reactive({
  xor_key: '',
  aes_key: '',
  message: ''
})
const mediaLoading = ref(false)
const copyMessage = ref('')
let copyMessageTimer = null

// 图片解密相关
const mediaDecryptResult = ref(null)
const mediaDecrypting = ref(false)

// 实时解密进度
const decryptProgress = reactive({
  current: 0,
  total: 0,
  success_count: 0,
  skip_count: 0,
  fail_count: 0,
  current_file: '',
  fileStatus: '',
  status: ''
})

// 进度百分比
const progressPercent = computed(() => {
  if (decryptProgress.total === 0) return 0
  return Math.round((decryptProgress.current / decryptProgress.total) * 100)
})

// 解密结果存储
const decryptResult = ref(null)

// 验证表单
const validateForm = () => {
  let isValid = true
  formErrors.key = ''
  formErrors.db_storage_path = ''
  
  // 验证密钥
  if (!formData.key) {
    formErrors.key = '请输入解密密钥'
    isValid = false
  } else if (formData.key.length !== 64) {
    formErrors.key = '密钥必须是64位十六进制字符串'
    isValid = false
  } else if (!/^[0-9a-fA-F]+$/.test(formData.key)) {
    formErrors.key = '密钥必须是有效的十六进制字符串'
    isValid = false
  }
  
  // 验证路径
  if (!formData.db_storage_path) {
    formErrors.db_storage_path = '请输入数据库存储路径'
    isValid = false
  }
  
  return isValid
}

// 处理解密
const handleDecrypt = async () => {
  if (!validateForm()) {
    return
  }
  
  loading.value = true
  error.value = ''
  
  try {
    const result = await decryptDatabase({
      key: formData.key,
      db_storage_path: formData.db_storage_path
    })
    
    if (result.status === 'completed') {
      // 解密成功，保存结果并进入下一步
      decryptResult.value = result
      if (process.client && typeof window !== 'undefined') {
        sessionStorage.setItem('decryptResult', JSON.stringify(result))
      }
      // 进入图片密钥获取步骤
      currentStep.value = 1
      // 自动尝试获取图片密钥
      fetchMediaKeys(false)
    } else if (result.status === 'failed') {
      if (result.failure_count > 0 && result.success_count === 0) {
        error.value = result.message || '所有文件解密失败'
      } else {
        error.value = '部分文件解密失败，请检查密钥是否正确'
      }
    } else {
      error.value = result.message || '解密失败，请检查输入信息'
    }
  } catch (err) {
    error.value = err.message || '解密过程中发生错误'
  } finally {
    loading.value = false
  }
}

// 获取图片密钥
const fetchMediaKeys = async (forceExtract = false) => {
  mediaLoading.value = true
  error.value = ''
  
  try {
    const result = await getMediaKeys({ force_extract: forceExtract })
    
    if (result.status === 'success') {
      mediaKeys.xor_key = result.xor_key || ''
      mediaKeys.aes_key = result.aes_key || ''
      mediaKeys.message = result.message || ''
    } else {
      error.value = result.message || '获取密钥失败'
    }
  } catch (err) {
    error.value = err.message || '获取密钥过程中发生错误'
  } finally {
    mediaLoading.value = false
  }
}

const _copyToClipboard = async (text) => {
  if (!process.client || typeof window === 'undefined') return false
  if (!text) return false

  try {
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch (e) {
    // Ignore and fallback below
  }

  try {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.setAttribute('readonly', '')
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    textarea.style.left = '-9999px'
    textarea.style.top = '0'
    document.body.appendChild(textarea)
    textarea.select()
    textarea.setSelectionRange(0, textarea.value.length)
    const ok = document.execCommand('copy')
    document.body.removeChild(textarea)
    return ok
  } catch (e) {
    return false
  }
}

const _setCopyMessage = (message) => {
  copyMessage.value = message
  if (copyMessageTimer) clearTimeout(copyMessageTimer)
  copyMessageTimer = setTimeout(() => {
    copyMessage.value = ''
    copyMessageTimer = null
  }, 2000)
}

const copyKey = async (label, value) => {
  if (!value) return
  const ok = await _copyToClipboard(value)
  _setCopyMessage(ok ? `${label}已复制` : `${label}复制失败，请手动复制`)
}

// 批量解密所有图片（使用SSE实时进度）
const decryptAllImages = async () => {
  mediaDecrypting.value = true
  mediaDecryptResult.value = null
  error.value = ''
  
  // 重置进度
  decryptProgress.current = 0
  decryptProgress.total = 0
  decryptProgress.success_count = 0
  decryptProgress.skip_count = 0
  decryptProgress.fail_count = 0
  decryptProgress.current_file = ''
  decryptProgress.fileStatus = ''
  decryptProgress.status = ''
  
  try {
    // 构建SSE URL
    const params = new URLSearchParams()
    if (mediaKeys.xor_key) params.set('xor_key', mediaKeys.xor_key)
    if (mediaKeys.aes_key) params.set('aes_key', mediaKeys.aes_key)
    const url = `http://localhost:8000/api/media/decrypt_all_stream?${params.toString()}`
    
    // 使用EventSource接收SSE
    const eventSource = new EventSource(url)
    
    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        
        if (data.type === 'scanning') {
          decryptProgress.current_file = '正在扫描文件...'
        } else if (data.type === 'start') {
          decryptProgress.total = data.total
        } else if (data.type === 'progress') {
          decryptProgress.current = data.current
          decryptProgress.total = data.total
          decryptProgress.success_count = data.success_count
          decryptProgress.skip_count = data.skip_count
          decryptProgress.fail_count = data.fail_count
          decryptProgress.current_file = data.current_file
          decryptProgress.fileStatus = data.status
        } else if (data.type === 'complete') {
          decryptProgress.status = 'complete'
          decryptProgress.current = data.total
          decryptProgress.total = data.total
          decryptProgress.success_count = data.success_count
          decryptProgress.skip_count = data.skip_count
          decryptProgress.fail_count = data.fail_count
          mediaDecryptResult.value = data
          eventSource.close()
          mediaDecrypting.value = false
        } else if (data.type === 'error') {
          error.value = data.message
          eventSource.close()
          mediaDecrypting.value = false
        }
      } catch (e) {
        console.error('解析SSE消息失败:', e)
      }
    }
    
    eventSource.onerror = (e) => {
      console.error('SSE连接错误:', e)
      eventSource.close()
      if (mediaDecrypting.value) {
        error.value = 'SSE连接中断，请重试'
        mediaDecrypting.value = false
      }
    }
  } catch (err) {
    error.value = err.message || '图片解密过程中发生错误'
    mediaDecrypting.value = false
  }
}

// 跳转到指定步骤
const goToStep = (step) => {
  currentStep.value = step
  error.value = ''
}

// 跳过图片解密，直接查看聊天记录
const skipToChat = () => {
  navigateTo('/chat')
}

// 页面加载时检查是否有选中的账户
onMounted(() => {
  if (process.client && typeof window !== 'undefined') {
    const selectedAccount = sessionStorage.getItem('selectedAccount')
    if (selectedAccount) {
      try {
        const account = JSON.parse(selectedAccount)
        // 填充数据路径
        if (account.data_dir) {
          formData.db_storage_path = account.data_dir + '\\db_storage'
        }
        // 清除sessionStorage
        sessionStorage.removeItem('selectedAccount')
      } catch (e) {
        console.error('解析账户信息失败:', e)
      }
    }
  }
})
</script>
