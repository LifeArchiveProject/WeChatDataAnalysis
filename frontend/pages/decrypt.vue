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
                解密密钥 <span class="text-red-500">*</span>
              </label>

              <div class="flex gap-3">
                <div class="relative flex-1">
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

                <button
                    type="button"
                    @click="handleGetDbKey"
                    :disabled="isGettingDbKey"
                    class="flex-none inline-flex items-center px-4 py-3 bg-[#07C160] text-white rounded-lg text-sm font-medium hover:bg-[#06AD56] transition-all duration-200 disabled:opacity-50 disabled:cursor-wait whitespace-nowrap"
                >
                  <svg v-if="isGettingDbKey" class="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
                  </svg>
                  <svg v-else class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  {{ isGettingDbKey ? '获取中...' : '自动获取' }}
                </button>
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
                尝试自动获取，或者使用 <a href="https://github.com/ycccccccy/wx_key" target="_blank" class="text-[#07C160] hover:text-[#06AD56]">wx_key</a> 等工具获取的64位十六进制字符串
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

            <!-- 解密进度 -->
            <div v-if="loading || dbDecryptProgress.total > 0" class="mt-6">
              <div class="flex items-center justify-between mb-2">
                <div class="text-sm text-[#7F7F7F]">
                  {{ dbDecryptProgress.message || (loading ? '解密中...' : '') }}
                </div>
                <div v-if="dbDecryptProgress.total > 0" class="text-sm font-mono text-[#000000e6]">
                  {{ dbDecryptProgress.current }} / {{ dbDecryptProgress.total }}
                </div>
              </div>

              <div class="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
                <div
                  class="h-full bg-[#07C160] transition-all duration-300"
                  :style="{ width: dbProgressPercent + '%' }"
                ></div>
              </div>

              <div v-if="dbDecryptProgress.current_file" class="mt-2 text-xs text-[#7F7F7F] truncate font-mono">
                {{ dbDecryptProgress.current_file }}
              </div>

              <div v-if="dbDecryptProgress.total > 0" class="mt-3 grid grid-cols-2 gap-4 text-center">
                <div class="bg-gray-50 rounded-lg p-3">
                  <div class="text-lg font-bold text-[#07C160]">{{ dbDecryptProgress.success_count }}</div>
                  <div class="text-xs text-[#7F7F7F]">成功</div>
                </div>
                <div class="bg-gray-50 rounded-lg p-3">
                  <div class="text-lg font-bold text-[#FA5151]">{{ dbDecryptProgress.fail_count }}</div>
                  <div class="text-xs text-[#7F7F7F]">失败</div>
                </div>
              </div>
            </div>
          </form>
        </div>
      </div>

      <!-- 步骤2: 填写图片密钥 -->
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
              <p class="text-sm text-[#7F7F7F]">填写后会自动保存并下次回填</p>
            </div>
          </div>

          <!-- 填写密钥 -->
          <div class="mb-6">
            <div class="bg-gray-50 rounded-lg p-4">

              <div class="flex justify-between items-center mb-4 pb-3 border-b border-gray-200">
                <span class="text-sm font-medium text-gray-500">手动输入或通过微信获取</span>
                <button
                    type="button"
                    @click="handleGetImageKey"
                    :disabled="isGettingImageKey"
                    class="flex-none inline-flex items-center px-4 py-3 bg-[#07C160] text-white rounded-lg text-sm font-medium hover:bg-[#06AD56] transition-all duration-200 disabled:opacity-50 disabled:cursor-wait whitespace-nowrap"
                >
                  <svg v-if="isGettingImageKey" class="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
                  </svg>
                  <svg v-else class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  {{ isGettingImageKey ? '正在获取...' : '自动获取' }}
                </button>
              </div>

              <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label class="block text-sm font-medium text-[#000000e6] mb-2">XOR（必填）</label>
                  <input
                    v-model="manualKeys.xor_key"
                    type="text"
                    placeholder="例如：0xA5"
                    class="w-full px-4 py-2 border border-[#EDEDED] rounded-lg focus:ring-2 focus:ring-[#10AEEF] focus:border-transparent font-mono"
                  />
                  <p v-if="manualKeyErrors.xor_key" class="text-xs text-red-500 mt-1">{{ manualKeyErrors.xor_key }}</p>
                </div>
                <div>
                  <label class="block text-sm font-medium text-[#000000e6] mb-2">AES（可选）</label>
                  <input
                    v-model="manualKeys.aes_key"
                    type="text"
                    placeholder="16 个字符（V4-V2 需要）"
                    class="w-full px-4 py-2 border border-[#EDEDED] rounded-lg focus:ring-2 focus:ring-[#10AEEF] focus:border-transparent font-mono"
                  />
                  <p v-if="manualKeyErrors.aes_key" class="text-xs text-red-500 mt-1">{{ manualKeyErrors.aes_key }}</p>
                </div>
              </div>

              <p class="mt-3 text-xs text-[#7F7F7F] flex items-center">
                <svg class="w-4 h-4 mr-1 text-[#10AEEF]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
                尝试自动获取，或使用 <a href="https://github.com/ycccccccy/wx_key" target="_blank" class="text-[#07C160] hover:text-[#06AD56]">wx_key</a> 获取图片密钥；AES 可选（V4-V2 需要）
              </p>
            </div>
          </div>

          <!-- 操作按钮 -->
          <div class="flex gap-3 justify-center pt-4 border-t border-[#EDEDED]">
            <button
              @click="goToMediaDecryptStep"
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
                  <li><strong>V4-V2版本需要AES密钥</strong>：请使用 wx_key 获取 AES 密钥后再重试解密</li>
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

      <!-- 警告渲染 -->
      <transition name="fade">
        <div v-if="warning" class="bg-amber-50 border border-amber-200 rounded-lg p-4 mt-6 flex items-start">
          <svg class="h-5 w-5 mr-2 flex-shrink-0 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
          </svg>
          <div>
            <p class="font-semibold text-amber-800">温馨提示</p>
            <p class="text-sm mt-1 text-amber-700">{{ warning }}</p>
          </div>
        </div>
      </transition>
    
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
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { useApi } from '~/composables/useApi'

const { decryptDatabase, saveMediaKeys, getSavedKeys, getDbKey, getImageKey, getWxStatus } = useApi()

const loading = ref(false)
const error = ref('')
const warning = ref('') // 警告，用于密钥提示
const currentStep = ref(0)
const mediaAccount = ref('')
const isGettingDbKey = ref(false)
const isGettingImageKey = ref(false)

// 步骤定义
const steps = [
  { title: '数据库解密' },
  { title: '填写图片密钥' },
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
  aes_key: ''
})

// 手动输入密钥（从 wx_key 获取）
const manualKeys = reactive({
  xor_key: '',
  aes_key: ''
})
const manualKeyErrors = reactive({
  xor_key: '',
  aes_key: ''
})

const normalizeXorKey = (value) => {
  const raw = String(value || '').trim()
  if (!raw) return { ok: false, value: '', message: '请输入 XOR 密钥' }
  const hex = raw.toLowerCase().replace(/^0x/, '')
  if (!/^[0-9a-f]{1,2}$/.test(hex)) return { ok: false, value: '', message: 'XOR 密钥格式无效（如 0xA5 或 A5）' }
  const n = parseInt(hex, 16)
  if (!Number.isFinite(n) || n < 0 || n > 255) return { ok: false, value: '', message: 'XOR 密钥必须在 0x00-0xFF 范围' }
  return { ok: true, value: `0x${n.toString(16).toUpperCase().padStart(2, '0')}`, message: '' }
}

const normalizeAesKey = (value) => {
  const raw = String(value || '').trim()
  if (!raw) return { ok: true, value: '', message: '' }
  if (raw.length < 16) return { ok: false, value: '', message: 'AES 密钥长度不足（至少 16 个字符）' }
  return { ok: true, value: raw.slice(0, 16), message: '' }
}

const prefillKeysForAccount = async (account) => {
  const acc = String(account || '').trim()
  if (!acc) return
  try {
    const resp = await getSavedKeys({ account: acc })
    if (!resp || resp.status !== 'success') return
    const keys = resp.keys || {}

    const dbKey = String(keys.db_key || '').trim()
    if (dbKey && !String(formData.key || '').trim()) {
      formData.key = dbKey
    }

    const xorKey = String(keys.image_xor_key || '').trim()
    if (xorKey && !String(manualKeys.xor_key || '').trim()) {
      manualKeys.xor_key = xorKey
    }

    const aesKey = String(keys.image_aes_key || '').trim()
    if (aesKey && !String(manualKeys.aes_key || '').trim()) {
      manualKeys.aes_key = aesKey
    }
  } catch (e) {
    // ignore
  }
}

const handleGetDbKey = async () => {
  if (isGettingDbKey.value) return
  isGettingDbKey.value = true

  error.value = ''
  warning.value = ''
  formErrors.key = ''

  try {
    const statusRes = await getWxStatus() // pid不是主进程，但是没关系
    const wxStatus = statusRes?.wx_status

    if (wxStatus?.is_running) {
      warning.value = '检测到微信正在运行，5秒后将终止进程并重启以获取密钥！！'
      await new Promise(resolve => setTimeout(resolve, 5000))
    } else {
      // 没有逻辑
    }

    warning.value = '正在启动微信以获取密钥，请确保微信未开启“自动登录”，并在启动后 1 分钟内完成登录操作。'

    const res = await getDbKey()

    if (res && res.status === 0) {
      if (res.data?.db_key) {
        formData.key = res.data.db_key
        warning.value = ''
      }

      if (res.errmsg && res.errmsg !== 'ok') {
        warning.value = res.errmsg
      }
    } else {
      error.value = '获取失败: ' + (res?.errmsg || '未知错误')
    }
  } catch (e) {
    console.error(e)
    error.value = '系统错误: ' + e.message
  } finally {
    isGettingDbKey.value = false
  }
}

const handleGetImageKey = async () => {
  if (isGettingImageKey.value) return
  isGettingImageKey.value = true
  manualKeyErrors.xor_key = ''
  manualKeyErrors.aes_key = ''

  error.value = ''
  warning.value = ''

  try {
    const res = await getImageKey()

    if (res && res.status === 0) {
      if (res.data?.aes_key) {
        manualKeys.aes_key = res.data.aes_key
      }
      if (res.data?.xor_key) {
        // 后端记得处理为16进制再返回！！！
        manualKeys.xor_key = res.data.xor_key
      }

      if (res.errmsg && res.errmsg !== 'ok') {
        error.value = res.errmsg
      }
    } else {
      error.value = '获取失败: ' + (res?.errmsg || '未知错误')
    }
  } catch (e) {
    console.error(e)
    error.value = '系统错误: ' + e.message
  } finally {
    isGettingImageKey.value = false
  }
}

const applyManualKeys = () => {
  manualKeyErrors.xor_key = ''
  manualKeyErrors.aes_key = ''
  error.value = ''
  warning.value = ''

  const aes = normalizeAesKey(manualKeys.aes_key)
  if (!aes.ok) {
    manualKeyErrors.aes_key = aes.message
    return false
  }

  mediaKeys.aes_key = aes.value

  const rawXor = String(manualKeys.xor_key || '').trim()
  if (!rawXor) {
    mediaKeys.xor_key = ''
    return true
  }

  const xor = normalizeXorKey(rawXor)
  if (!xor.ok) {
    manualKeyErrors.xor_key = xor.message
    return false
  }
  mediaKeys.xor_key = xor.value
  return true
}

const clearManualKeys = () => {
  manualKeys.xor_key = ''
  manualKeys.aes_key = ''
  manualKeyErrors.xor_key = ''
  manualKeyErrors.aes_key = ''
  mediaKeys.xor_key = ''
  mediaKeys.aes_key = ''
}

// 图片解密相关
const mediaDecryptResult = ref(null)
const mediaDecrypting = ref(false)

// 数据库解密进度（SSE）
const dbDecryptProgress = reactive({
  current: 0,
  total: 0,
  success_count: 0,
  fail_count: 0,
  current_file: '',
  status: '',
  message: ''
})

const dbProgressPercent = computed(() => {
  if (dbDecryptProgress.total === 0) return 0
  return Math.round((dbDecryptProgress.current / dbDecryptProgress.total) * 100)
})

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

let dbDecryptEventSource = null
onBeforeUnmount(() => {
  try {
    if (dbDecryptEventSource) dbDecryptEventSource.close()
  } catch (e) {
    // ignore
  } finally {
    dbDecryptEventSource = null
  }
})

const resetDbDecryptProgress = () => {
  dbDecryptProgress.current = 0
  dbDecryptProgress.total = 0
  dbDecryptProgress.success_count = 0
  dbDecryptProgress.fail_count = 0
  dbDecryptProgress.current_file = ''
  dbDecryptProgress.status = ''
  dbDecryptProgress.message = ''
}

// 处理解密
const handleDecrypt = async () => {
  if (!validateForm()) {
    return
  }
  
  loading.value = true
  error.value = ''
  warning.value = ''

  resetDbDecryptProgress()
  
  try {
    const canSse = process.client && typeof window !== 'undefined' && typeof EventSource !== 'undefined'

    // Fallback: 如果环境不支持 SSE，则使用普通 POST（无进度）。
    if (!canSse) {
      const result = await decryptDatabase({
        key: formData.key,
        db_storage_path: formData.db_storage_path
      })

      if (result.status === 'completed') {
        decryptResult.value = result
        if (process.client && typeof window !== 'undefined') {
          sessionStorage.setItem('decryptResult', JSON.stringify(result))
        }
        try {
          const accounts = Object.keys(result.account_results || {})
          if (accounts.length > 0) mediaAccount.value = accounts[0]
        } catch (e) {}

        clearManualKeys()
        currentStep.value = 1
        await prefillKeysForAccount(mediaAccount.value)
      } else if (result.status === 'failed') {
        if (result.failure_count > 0 && result.success_count === 0) {
          error.value = result.message || '所有文件解密失败'
        } else {
          error.value = '部分文件解密失败，请检查密钥是否正确'
        }
      } else {
        error.value = result.message || '解密失败，请检查输入信息'
      }

      loading.value = false
      return
    }

    // SSE: 解密过程实时推送进度
    if (dbDecryptEventSource) {
      try {
        dbDecryptEventSource.close()
      } catch (e) {}
      dbDecryptEventSource = null
    }

    const params = new URLSearchParams()
    params.set('key', formData.key)
    params.set('db_storage_path', formData.db_storage_path)
    const url = `http://localhost:8000/api/decrypt_stream?${params.toString()}`

    dbDecryptProgress.message = '连接中...'
    const eventSource = new EventSource(url)
    dbDecryptEventSource = eventSource

    eventSource.onmessage = async (event) => {
      try {
        const data = JSON.parse(event.data)

        if (data.type === 'scanning') {
          dbDecryptProgress.message = data.message || '正在扫描数据库文件...'
        } else if (data.type === 'start') {
          dbDecryptProgress.total = data.total || 0
          dbDecryptProgress.message = data.message || '开始解密...'
        } else if (data.type === 'progress') {
          dbDecryptProgress.current = data.current || 0
          dbDecryptProgress.total = data.total || 0
          dbDecryptProgress.success_count = data.success_count || 0
          dbDecryptProgress.fail_count = data.fail_count || 0
          dbDecryptProgress.current_file = data.current_file || ''
          dbDecryptProgress.status = data.status || ''
          dbDecryptProgress.message = data.message || ''
        } else if (data.type === 'phase') {
          // e.g. building cache
          dbDecryptProgress.message = data.message || ''
        } else if (data.type === 'complete') {
          dbDecryptProgress.status = 'complete'
          dbDecryptProgress.current = data.total_databases || dbDecryptProgress.total
          dbDecryptProgress.total = data.total_databases || dbDecryptProgress.total
          dbDecryptProgress.success_count = data.success_count || 0
          dbDecryptProgress.fail_count = data.failure_count || 0
          dbDecryptProgress.message = data.message || '解密完成'

          decryptResult.value = data
          if (process.client && typeof window !== 'undefined') {
            sessionStorage.setItem('decryptResult', JSON.stringify(data))
          }

          try {
            const accounts = Object.keys(data.account_results || {})
            if (accounts.length > 0) mediaAccount.value = accounts[0]
          } catch (e) {}

          try {
            eventSource.close()
          } catch (e) {}
          dbDecryptEventSource = null
          loading.value = false

          if (data.status === 'completed') {
            clearManualKeys()
            currentStep.value = 1
            await prefillKeysForAccount(mediaAccount.value)
          } else if (data.status === 'failed') {
            error.value = data.message || '所有文件解密失败'
          } else {
            error.value = data.message || '解密失败，请检查输入信息'
          }
        } else if (data.type === 'error') {
          error.value = data.message || '解密失败，请检查输入信息'
          try {
            eventSource.close()
          } catch (e) {}
          dbDecryptEventSource = null
          loading.value = false
        }
      } catch (e) {
        console.error('解析SSE消息失败:', e)
      }
    }

    eventSource.onerror = (e) => {
      console.error('SSE连接错误:', e)
      try {
        eventSource.close()
      } catch (err) {}
      dbDecryptEventSource = null
      if (loading.value) {
        error.value = 'SSE连接中断，请重试'
        loading.value = false
      }
    }
  } catch (err) {
    error.value = err.message || '解密过程中发生错误'
    loading.value = false
  }
}

// 批量解密所有图片（使用SSE实时进度）
const decryptAllImages = async () => {
  mediaDecrypting.value = true
  mediaDecryptResult.value = null
  error.value = ''
  warning.value = ''
  
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
    if (mediaAccount.value) params.set('account', mediaAccount.value)
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

// 从密钥步骤进入图片解密步骤
const goToMediaDecryptStep = async () => {
  error.value = ''
  warning.value = ''
  // 校验并应用（未填写则允许直接进入，后端会使用已保存密钥或报错提示）
  const ok = applyManualKeys()
  if (!ok || manualKeyErrors.xor_key || manualKeyErrors.aes_key) return

  // 用户已输入 XOR 时，自动保存一次，避免下次重复输入（失败不影响继续）
  if (mediaKeys.xor_key) {
    try {
      const aesVal = String(mediaKeys.aes_key || '').trim()
      await saveMediaKeys({
        account: mediaAccount.value || null,
        xor_key: mediaKeys.xor_key,
        aes_key: aesVal ? aesVal : null
      })
    } catch (e) {
      // ignore
    }
  }
  currentStep.value = 2
}

// 跳过图片解密，直接查看聊天记录
const skipToChat = async () => {
  try {
    const ok = applyManualKeys()
    if (ok && mediaKeys.xor_key) {
      const aesVal = String(mediaKeys.aes_key || '').trim()
      await saveMediaKeys({
        account: mediaAccount.value || null,
        xor_key: mediaKeys.xor_key,
        aes_key: aesVal ? aesVal : null
      })
    }
  } catch (e) {
    // ignore
  }
  navigateTo('/chat')
}

// 页面加载时检查是否有选中的账户
onMounted(async () => {
  if (process.client && typeof window !== 'undefined') {
    const selectedAccount = sessionStorage.getItem('selectedAccount')
    if (selectedAccount) {
      try {
        const account = JSON.parse(selectedAccount)
        // 填充数据路径
        if (account.data_dir) {
          formData.db_storage_path = account.data_dir + '\\db_storage'
        }
        if (account.account_name) {
          mediaAccount.value = account.account_name
        }
        // 清除sessionStorage
        sessionStorage.removeItem('selectedAccount')
        await prefillKeysForAccount(mediaAccount.value)
      } catch (e) {
        console.error('解析账户信息失败:', e)
      }
    }
  }
})
</script>
