<template>
  <div class="decrypt-page min-h-screen flex items-center justify-center py-8">
    
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
                  {{ isGettingDbKey ? '获取中...' : (isMacos ? '查看 Mac 获取方式' : '一键获取数据库密钥') }}
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
                {{ isMacos
                  ? 'macOS 版不提取数据库密钥。请使用支持 Mac 的同类本地工具获取后，在上方手动填写 64 位密钥；填写后实时消息等功能仍可使用。'
                  : '点击按钮将优先使用 V4 内存扫描获取【数据库解密密钥】；失败时会询问您是否改用 Hook。您也可以手动输入已知的64位密钥。' }}
              </p>
              <p v-if="!isMacos" class="mt-2 text-xs text-[#7F7F7F] flex items-start">
                <svg class="w-4 h-4 mr-1 mt-0.5 text-[#10AEEF]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
                <span>
                  V4 内存扫描这部分参考了
                  <a
                    href="https://github.com/recarto404"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="text-[#576B95] underline decoration-[#576B95]/30 underline-offset-2 hover:text-[#07C160]"
                  >recarto404</a>
                  提供的扫内存技术方案。
                </span>
              </p>
              <p v-if="formData.wechat_install_path" class="mt-2 text-xs text-[#7F7F7F] flex items-start">
                <svg class="w-4 h-4 mr-1 mt-0.5 text-[#10AEEF]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
                <span>当前将使用第一步检测时保存的微信安装目录：<span class="font-mono break-all">{{ formData.wechat_install_path }}</span>。</span>
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
                :placeholder="isMacos ? '例如: /Users/你的用户名/.../wxid_xxx/db_storage' : '例如: D:\\wechatMSG\\xwechat_files\\wxid_xxx\\db_storage'"
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
              <div class="flex flex-wrap items-center justify-center gap-3">
                <button
                  type="button"
                  data-testid="decrypt-step-back"
                  @click="goBackFromCurrentStep"
                  class="inline-flex items-center px-6 py-3 bg-white text-[#000000e6] border border-[#EDEDED] rounded-lg text-base font-medium hover:bg-gray-50 transition-all duration-200"
                >
                  <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/>
                  </svg>
                  返回账号选择
                </button>
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

              <div class="flex flex-col gap-3 mb-3 pb-3 border-b border-gray-200 sm:flex-row sm:items-center sm:justify-between">
                <span class="text-sm font-medium text-gray-500">此步骤将为您解密微信聊天中的图片</span>
                <button
                  type="button"
                  @click="scanImageKeyMemory"
                  :disabled="isImageKeyAcquisitionPending"
                  :aria-busy="isScanningImageKeyMemory"
                  title="扫描微信内存获取图片密钥"
                  class="inline-flex h-9 shrink-0 items-center justify-center self-start rounded-lg border border-[#10AEEF] px-3 text-sm font-medium text-[#087FAE] transition-colors hover:bg-[#EAF8FE] disabled:cursor-not-allowed disabled:opacity-60 sm:self-auto"
                >
                  <svg v-if="isScanningImageKeyMemory" class="mr-2 h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"></path>
                  </svg>
                  <svg v-else class="mr-2 h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <rect x="5" y="5" width="14" height="14" rx="2" stroke-width="2"></rect>
                    <path stroke-linecap="round" stroke-width="2" d="M9 2v3m6-3v3M9 19v3m6-3v3M2 9h3m-3 6h3m14-6h3m-3 6h3"></path>
                  </svg>
                  {{ isScanningImageKeyMemory ? '正在扫描...' : '扫描微信内存' }}
                </button>
              </div>
              <div class="min-h-6" aria-live="polite">
                <p
                  v-if="imageMemoryScanMessage"
                  role="status"
                  class="mb-3 text-xs"
                  :class="imageMemoryScanState === 'success' ? 'text-[#078A45]' : imageMemoryScanState === 'error' ? 'text-[#C83C3C]' : 'text-[#087FAE]'"
                >
                  {{ imageMemoryScanMessage }}
                </p>
              </div>
              <p class="mt-3 mb-4 text-xs text-[#7F7F7F] flex items-center">
                <svg class="w-4 h-4 mr-1 text-[#10AEEF]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
                系统已为您尝试通过【本地算法】或【云端解析】自动获取图片密钥。如果输入框为空，请手动填写。
              </p>

              <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label class="block text-sm font-medium text-[#000000e6] mb-2">XOR（必填）</label>
                  <input
                      v-model="manualKeys.xor_key"
                      @input="markImageKeysManual"
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
                      @input="markImageKeysManual"
                      type="text"
                      placeholder="16 个字符（V4-V2 需要）"
                      class="w-full px-4 py-2 border border-[#EDEDED] rounded-lg focus:ring-2 focus:ring-[#10AEEF] focus:border-transparent font-mono"
                  />
                  <p v-if="manualKeyErrors.aes_key" class="text-xs text-red-500 mt-1">{{ manualKeyErrors.aes_key }}</p>
                </div>
              </div>
            </div>
          </div>

          <!-- 操作按钮 -->
          <div class="flex flex-wrap gap-3 justify-center pt-4 border-t border-[#EDEDED]">
            <button
              type="button"
              data-testid="decrypt-step-back"
              @click="goBackFromCurrentStep"
              class="inline-flex items-center px-6 py-3 bg-white text-[#000000e6] border border-[#EDEDED] rounded-lg font-medium hover:bg-gray-50 transition-all duration-200"
            >
              <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/>
              </svg>
              上一步
            </button>
            <button
              type="button"
              @click="goToMediaDecryptStep"
              :disabled="isImageKeyAcquisitionPending"
              class="inline-flex items-center px-6 py-3 bg-[#07C160] text-white rounded-lg font-medium hover:bg-[#06AD56] transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-60"
            >
              下一步
              <svg class="w-5 h-5 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
              </svg>
            </button>
          </div>

          <!-- 跳过按钮 -->
          <div class="text-center mt-4">
            <button
              @click="skipToChat"
              :disabled="isImageKeyAcquisitionPending"
              class="text-sm text-[#7F7F7F] hover:text-[#07C160] transition-colors disabled:cursor-not-allowed disabled:opacity-60"
            >
              跳过后续媒体准备，直接查看聊天记录 →
            </button>
          </div>
        </div>
      </div>

      <!-- 步骤3: 图片解密 -->
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
                <p class="text-sm text-[#7F7F7F]">仅解密加密图片文件(.dat)，完成后可继续进入表情下载步骤</p>
              </div>
            </div>
            <!-- 进度计数 -->
            <div v-if="mediaDecrypting && decryptProgress.total > 0" class="text-right">
              <div class="text-lg font-bold text-[#91D300]">{{ decryptProgress.current }} / {{ decryptProgress.total }}</div>
              <div class="text-xs text-[#7F7F7F]">已处理 / 总图片</div>
            </div>
          </div>

          <div class="mb-6 bg-lime-50 border border-lime-100 rounded-lg p-4">
            <label class="block text-sm font-medium text-[#000000e6] mb-2">解密并发线程数</label>
            <div class="flex flex-col sm:flex-row sm:items-center gap-3">
              <input
                v-model.number="mediaDecryptConcurrency"
                type="number"
                min="1"
                max="64"
                step="1"
                :disabled="mediaDecrypting"
                class="w-40 px-3 py-2 border border-[#EDEDED] rounded-lg focus:outline-none focus:ring-2 focus:ring-[#91D300] disabled:bg-gray-100"
              />
              <div class="text-xs text-[#7F7F7F]">
                默认 10；图片解密主要吃本地磁盘和 CPU，机器较快可适度调高。
              </div>
            </div>
          </div>

          <!-- 实时进度条 -->
          <div v-if="mediaDecrypting || decryptProgress.total > 0" class="mb-6">
            <!-- 进度条 -->
            <div class="mb-3">
              <div class="flex justify-between text-xs text-[#7F7F7F] mb-1">
                <span>{{ decryptProgress.message || '解密进度' }}</span>
                <span>{{ progressPercent }}%</span>
              </div>
              <div class="w-full bg-gray-200 rounded-full h-2.5 overflow-hidden">
                <div 
                  class="h-2.5 rounded-full transition-all duration-300 ease-out"
                  :class="decryptProgress.status === 'complete' ? 'bg-[#07C160]' : decryptProgress.status === 'cancelled' ? 'bg-[#FAAD14]' : 'bg-[#91D300]'"
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
            <div class="grid grid-cols-5 gap-3 text-center bg-gray-50 rounded-lg p-3">
              <div>
                <div class="text-xl font-bold text-[#10AEEF]">{{ decryptProgress.total }}</div>
                <div class="text-xs text-[#7F7F7F]">总图片</div>
              </div>
              <div>
                <div class="text-xl font-bold text-[#91D300]">{{ decryptProgress.concurrency || getMediaDecryptConcurrency() }}</div>
                <div class="text-xs text-[#7F7F7F]">并发线程</div>
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
              <div class="mt-2 grid grid-cols-2 md:grid-cols-4 gap-2 text-xs text-green-700">
                <div>并发线程: {{ mediaDecryptResult.concurrency || decryptProgress.concurrency }}</div>
                <div>平均解密: {{ mediaDecryptResult.decrypt_stats?.avg_decrypt_ms || 0 }} ms</div>
                <div>最大解密: {{ mediaDecryptResult.decrypt_stats?.max_decrypt_ms || 0 }} ms</div>
                <div>慢解密数: {{ mediaDecryptResult.decrypt_stats?.slow_decrypt_count || 0 }}</div>
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
          <div class="flex flex-wrap gap-3 justify-center pt-4 border-t border-[#EDEDED]">
            <button
              type="button"
              data-testid="decrypt-step-back"
              @click="goBackFromCurrentStep"
              class="inline-flex items-center px-6 py-3 bg-white text-[#000000e6] border border-[#EDEDED] rounded-lg font-medium hover:bg-gray-50 transition-all duration-200"
            >
              <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/>
              </svg>
              上一步
            </button>
            <button
              type="button"
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
              v-if="mediaDecrypting"
              @click="cancelMediaDecrypt"
              class="inline-flex items-center px-6 py-3 bg-[#FA5151] text-white rounded-lg font-medium hover:bg-[#E54D4D] transition-all duration-200"
            >
              停止解密
            </button>
            <button
              @click="goToEmojiDownloadStep"
              :disabled="mediaDecrypting"
              class="inline-flex items-center px-6 py-3 bg-[#FA8C16] text-white rounded-lg font-medium hover:bg-[#E67E11] transition-all duration-200 disabled:opacity-50"
            >
              下一步：下载表情
              <svg class="w-5 h-5 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
              </svg>
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

      <!-- 步骤4: 表情下载 -->
      <div v-if="currentStep === 3" class="bg-white rounded-2xl border border-[#EDEDED]">
        <div class="p-8">
          <div class="flex items-center justify-between mb-6">
            <div class="flex items-center">
              <div class="w-12 h-12 bg-[#FA8C16] rounded-lg flex items-center justify-center mr-4">
                <svg class="w-7 h-7 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.828 14.828a4 4 0 01-5.656 0M9 10h.01M15 10h.01M12 21a9 9 0 100-18 9 9 0 000 18z"/>
                </svg>
              </div>
              <div>
                <h2 class="text-xl font-bold text-[#000000e6]">批量下载表情包</h2>
                <p class="text-sm text-[#7F7F7F]">从 `emoticon.db` 和聊天消息 XML 收集可下载表情，下载过的会自动跳过</p>
              </div>
            </div>
            <div v-if="emojiDownloading && emojiDownloadProgress.total > 0" class="text-right">
              <div class="text-lg font-bold text-[#FA8C16]">{{ emojiDownloadProgress.current }} / {{ emojiDownloadProgress.total }}</div>
              <div class="text-xs text-[#7F7F7F]">已处理 / 总表情</div>
            </div>
          </div>

          <p class="mb-4 text-xs text-[#7F7F7F]">
            表情会缓存到本地 `resource` 目录，后续聊天导出时可直接复用，不必再临时查找或下载。
          </p>

          <div class="mb-4 bg-orange-50 border border-orange-100 rounded-lg p-4">
            <label class="block text-sm font-medium text-[#000000e6] mb-2">下载并发线程数</label>
            <div class="flex flex-col sm:flex-row sm:items-center gap-3">
              <input
                v-model.number="emojiDownloadConcurrency"
                type="number"
                min="1"
                max="100"
                step="1"
                :disabled="emojiDownloading"
                class="w-40 px-3 py-2 border border-[#EDEDED] rounded-lg focus:outline-none focus:ring-2 focus:ring-[#FA8C16] disabled:bg-gray-100"
              />
              <div class="text-xs text-[#7F7F7F]">
                默认 20；网络带宽足够可调高，超时/失败变多时建议调低。
              </div>
            </div>
          </div>

          <div v-if="emojiDownloading || emojiDownloadProgress.total > 0" class="mb-4">
            <div class="mb-3">
              <div class="flex justify-between text-xs text-[#7F7F7F] mb-1">
                <span>{{ emojiDownloadProgress.message || '下载进度' }}</span>
                <span>{{ emojiProgressPercent }}%</span>
              </div>
              <div class="w-full bg-gray-200 rounded-full h-2.5 overflow-hidden">
                <div
                  class="h-2.5 rounded-full transition-all duration-300 ease-out"
                  :class="emojiDownloadProgress.status === 'complete' ? 'bg-[#07C160]' : emojiDownloadProgress.status === 'cancelled' ? 'bg-[#FAAD14]' : 'bg-[#FA8C16]'"
                  :style="{ width: emojiProgressPercent + '%' }"
                ></div>
              </div>
            </div>

            <div v-if="emojiDownloadProgress.current_file" class="flex items-center text-sm text-[#7F7F7F] mb-3">
              <svg class="w-4 h-4 mr-2 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.828 14.828a4 4 0 01-5.656 0M9 10h.01M15 10h.01M12 21a9 9 0 100-18 9 9 0 000 18z"/>
              </svg>
              <span class="truncate font-mono text-xs">{{ emojiDownloadProgress.current_file }}</span>
              <span
                class="ml-2 px-2 py-0.5 rounded text-xs"
                :class="{
                  'bg-green-100 text-green-700': emojiDownloadProgress.fileStatus === 'success',
                  'bg-gray-100 text-gray-600': emojiDownloadProgress.fileStatus === 'skip',
                  'bg-red-100 text-red-700': emojiDownloadProgress.fileStatus === 'fail'
                }"
              >
                {{ emojiDownloadProgress.fileStatus === 'success' ? '下载成功' : emojiDownloadProgress.fileStatus === 'skip' ? '已存在' : emojiDownloadProgress.fileStatus === 'fail' ? '失败' : '' }}
              </span>
            </div>

            <div class="grid grid-cols-5 gap-3 text-center bg-gray-50 rounded-lg p-3">
              <div>
                <div class="text-xl font-bold text-[#10AEEF]">{{ emojiDownloadProgress.total }}</div>
                <div class="text-xs text-[#7F7F7F]">总表情</div>
              </div>
              <div>
                <div class="text-xl font-bold text-[#FA8C16]">{{ emojiDownloadProgress.concurrency || getEmojiDownloadConcurrency() }}</div>
                <div class="text-xs text-[#7F7F7F]">并发线程</div>
              </div>
              <div>
                <div class="text-xl font-bold text-[#07C160]">{{ emojiDownloadProgress.success_count }}</div>
                <div class="text-xs text-[#7F7F7F]">成功</div>
              </div>
              <div>
                <div class="text-xl font-bold text-[#7F7F7F]">{{ emojiDownloadProgress.skip_count }}</div>
                <div class="text-xs text-[#7F7F7F]">跳过(已下载)</div>
              </div>
              <div>
                <div class="text-xl font-bold text-[#FA5151]">{{ emojiDownloadProgress.fail_count }}</div>
                <div class="text-xs text-[#7F7F7F]">失败</div>
              </div>
            </div>
          </div>

          <div v-if="emojiDownloadResult && !emojiDownloading" class="mb-4">
            <div class="bg-green-50 border border-green-200 rounded-lg p-4">
              <div class="flex items-center mb-2">
                <svg class="w-5 h-5 text-green-600 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
                </svg>
                <span class="font-medium text-green-700">表情下载完成</span>
              </div>
              <div class="text-sm text-green-600">
                输出目录: <code class="bg-white px-2 py-1 rounded text-xs">{{ emojiDownloadResult.output_dir }}</code>
              </div>
              <div class="mt-2 grid grid-cols-2 md:grid-cols-4 gap-2 text-xs text-green-700">
                <div>并发线程: {{ emojiDownloadResult.concurrency || emojiDownloadProgress.concurrency }}</div>
                <div>平均下载: {{ emojiDownloadResult.download_stats?.avg_fetch_ms || 0 }} ms</div>
                <div>最大下载: {{ emojiDownloadResult.download_stats?.max_fetch_ms || 0 }} ms</div>
                <div>慢下载数: {{ emojiDownloadResult.download_stats?.slow_fetch_count || 0 }}</div>
              </div>
            </div>
          </div>

          <div v-if="emojiDownloadProgress.fail_count > 0" class="mb-4">
            <details class="text-sm">
              <summary class="cursor-pointer text-[#7F7F7F] hover:text-[#000000e6]">
                <span class="ml-1">查看表情下载失败说明</span>
              </summary>
              <div class="mt-2 bg-gray-50 rounded-lg p-3 text-xs text-[#7F7F7F]">
                <ul class="list-disc list-inside space-y-1">
                  <li><strong>未找到可下载地址</strong>：该表情在数据库里没有可用的 CDN 链接</li>
                  <li><strong>下载失败</strong>：网络超时、远端资源失效或微信 CDN 已回收文件</li>
                  <li><strong>写入失败</strong>：本地目录无权限或目标文件被占用</li>
                </ul>
              </div>
            </details>
          </div>

          <div class="flex flex-wrap gap-3 justify-center pt-4 border-t border-[#EDEDED]">
            <button
              type="button"
              data-testid="decrypt-step-back"
              @click="goBackFromCurrentStep"
              class="inline-flex items-center px-6 py-3 bg-white text-[#000000e6] border border-[#EDEDED] rounded-lg font-medium hover:bg-gray-50 transition-all duration-200"
            >
              <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/>
              </svg>
              上一步
            </button>
            <button
              @click="downloadAllEmojis"
              :disabled="emojiDownloading"
              class="inline-flex items-center px-6 py-3 bg-[#FA8C16] text-white rounded-lg font-medium hover:bg-[#E67E11] transition-all duration-200 disabled:opacity-50"
            >
              <svg v-if="emojiDownloading" class="w-5 h-5 mr-2 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
              </svg>
              <svg v-else class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.828 14.828a4 4 0 01-5.656 0M9 10h.01M15 10h.01M12 21a9 9 0 100-18 9 9 0 000 18z"/>
              </svg>
              {{ emojiDownloading ? '下载中...' : (emojiDownloadResult ? '重新检查表情' : '开始下载表情') }}
            </button>
            <button
              v-if="emojiDownloading"
              @click="cancelEmojiDownload"
              class="inline-flex items-center px-6 py-3 bg-[#FA5151] text-white rounded-lg font-medium hover:bg-[#E54D4D] transition-all duration-200"
            >
              停止下载
            </button>
            <button
              @click="skipToChat"
              :disabled="emojiDownloading"
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
        <ErrorNotice v-if="warning && warningIsError" :message="warning" class="mt-6" />
        <div v-else-if="warning" class="bg-amber-50 border border-amber-200 rounded-lg p-4 mt-6 flex items-start">
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
        <ErrorNotice v-if="error" :message="error" class="mt-6 animate-shake" />
      </transition>
    </div>

    <GuideDialog
      :open="guideDialog.open"
      :eyebrow="guideDialog.eyebrow"
      :title="guideDialog.title"
      :description="guideDialog.description"
      :details="guideDialog.details"
      :note="guideDialog.note"
      :error-message="guideDialog.errorMessage"
      :primary-label="guideDialog.primaryLabel"
      :secondary-label="guideDialog.secondaryLabel"
      :tone="guideDialog.tone"
      @primary="settleGuideDialog(true)"
      @secondary="settleGuideDialog(false)"
      @close="settleGuideDialog(false)"
    />
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
import { normalizeWechatInstallPath, readStoredWechatInstallPath } from '~/lib/wechat-install-path'

const { decryptDatabase, saveMediaKeys, getSavedKeys, getKeys, getImageKey, getImageKeyMemory, getWxStatus, getPlatformCapabilities } = useApi()

const loading = ref(false)
const error = ref('')
const warning = ref('') // 警告，用于密钥提示
const warningIsError = computed(() => /失败|错误|异常|中断/.test(String(warning.value || '')))
const currentStep = ref(0)
const mediaAccount = ref('')
const activeKeyAccount = ref('')
const isGettingDbKey = ref(false)
let dbKeyRequestRevision = 0
let dbKeyRequestController = null
const platformCapabilities = ref({ platform: '' })
const isMacos = computed(() => platformCapabilities.value?.platform === 'macos')
const guideDialog = reactive({
  open: false,
  eyebrow: '操作提示',
  title: '',
  description: '',
  details: [],
  note: '',
  errorMessage: '',
  primaryLabel: '我知道了，继续',
  secondaryLabel: '',
  tone: 'guide'
})
let guideDialogResolve = null

const requestGuideDialog = (options) => new Promise((resolve) => {
  if (guideDialogResolve) guideDialogResolve(false)
  Object.assign(guideDialog, {
    open: true,
    eyebrow: '操作提示',
    title: '',
    description: '',
    details: [],
    note: '',
    errorMessage: '',
    primaryLabel: '我知道了，继续',
    secondaryLabel: '',
    tone: 'guide',
    ...options
  })
  guideDialogResolve = resolve
})

const settleGuideDialog = (confirmed) => {
  const resolve = guideDialogResolve
  guideDialogResolve = null
  guideDialog.open = false
  resolve?.(!!confirmed)
}

// 步骤定义
const steps = [
  { title: '数据库解密' },
  { title: '填写图片密钥' },
  { title: '图片解密' },
  { title: '表情下载' }
]

// 表单数据
const formData = reactive({
  key: '',
  db_storage_path: '',
  wechat_install_path: ''
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
const imageKeysVerified = ref(false)
const imageKeyInputOrigin = ref('empty')
const imageMemoryScanState = ref('idle')
const imageMemoryScanMessage = ref('')
const imageKeyPendingCount = ref(0)
const imageMemoryScanPending = ref(false)
const isImageKeyAcquisitionPending = computed(() => imageKeyPendingCount.value > 0)
const isScanningImageKeyMemory = computed(() => imageMemoryScanPending.value)
let imageKeyRequestRevision = 0
let ensureKeysRevision = 0
const manualKeyErrors = reactive({
  xor_key: '',
  aes_key: ''
})

const normalizeAccountId = (value) => String(value || '').trim()
const normalizeImageKeyPath = (value) => String(value || '')
  .trim()
  .replace(/\//g, '\\')
  .replace(/[\\]+$/, '')
  .toLowerCase()
const imageKeyAccountDirName = (value) => {
  const normalized = String(value || '').trim().replace(/[\\/]+$/, '')
  return normalized ? String(normalized.split(/[\\/]/).pop() || '').trim() : ''
}
const imageKeyAccountVariants = (value) => {
  const normalized = normalizeAccountId(value).toLowerCase()
  if (!normalized) return new Set()
  const variants = new Set([normalized])
  const suffixMatch = /^(wxid_[^_\s]+)_[0-9a-f]{4}$/i.exec(normalized)
  if (suffixMatch) variants.add(suffixMatch[1].toLowerCase())
  return variants
}
const imageKeyAccountsMatch = (left, right) => {
  const leftVariants = imageKeyAccountVariants(left)
  const rightVariants = imageKeyAccountVariants(right)
  return [...leftVariants].some((value) => rightVariants.has(value))
}
const currentImageKeyAccount = () => normalizeAccountId(mediaAccount.value || activeKeyAccount.value)
const beginImageKeyRequest = (account, dbStoragePath) => {
  const context = {
    id: ++imageKeyRequestRevision,
    account: normalizeAccountId(account),
    dbStoragePath: String(dbStoragePath || '').trim()
  }
  imageKeyPendingCount.value += 1
  return context
}
const finishImageKeyRequest = () => {
  imageKeyPendingCount.value = Math.max(0, imageKeyPendingCount.value - 1)
}
const invalidateImageKeyRequests = () => {
  imageKeyRequestRevision += 1
}
const imageKeyContextStillSelected = (context) => (
  currentImageKeyAccount() === context.account
  && normalizeImageKeyPath(formData.db_storage_path) === normalizeImageKeyPath(context.dbStoragePath)
)
const isCurrentImageKeyRequest = (context) => (
  context.id === imageKeyRequestRevision && imageKeyContextStillSelected(context)
)
const imageKeyResponseMatchesContext = (responseAccount, context) => {
  const canonical = normalizeAccountId(responseAccount)
  if (!canonical) return false
  const requestedDir = imageKeyAccountDirName(wxidDirFromDbStoragePath(context.dbStoragePath))
  return imageKeyAccountsMatch(canonical, context.account) || imageKeyAccountsMatch(canonical, requestedDir)
}
const summarizeKeyStateForLog = (xorKey, aesKey) => {
  const normalizedXor = String(xorKey || '').trim()
  const normalizedAes = String(aesKey || '').trim()
  return {
    has_xor: !!normalizedXor,
    has_aes: !!normalizedAes,
    xor_length: normalizedXor.length,
    aes_length: normalizedAes.length
  }
}
const formatLogError = (error) => {
  if (!error) return ''
  if (error instanceof Error) {
    return {
      name: String(error.name || 'Error'),
      message: String(error.message || ''),
      stack: String(error.stack || '')
    }
  }
  if (typeof error === 'object') {
    try {
      return JSON.parse(JSON.stringify(error))
    } catch {}
  }
  return String(error)
}
const logDecryptDebug = (phase, details = {}) => {
  if (process.client && typeof window !== 'undefined') {
    try {
      window.wechatDesktop?.logDebug?.('decrypt-page', phase, details)
    } catch {}
  }
  try {
    console.info(`[decrypt-page] ${phase}`, details)
  } catch {}
}

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

const normalizeCompleteImageKeys = (xorKey, aesKey) => {
  const xor = normalizeXorKey(xorKey)
  const aes = normalizeAesKey(aesKey)
  return {
    ok: xor.ok && aes.ok && !!aes.value,
    xor,
    aes
  }
}

const markImageKeysManual = () => {
  invalidateImageKeyRequests()
  imageKeyInputOrigin.value = 'manual'
  imageKeysVerified.value = false
  imageMemoryScanState.value = 'idle'
  imageMemoryScanMessage.value = ''
}

const wxidDirFromDbStoragePath = (value) => {
  const normalized = String(value || '').trim().replace(/[\\/]+$/, '')
  if (!normalized) return ''
  return /[\\/]db_storage$/i.test(normalized)
    ? normalized.replace(/[\\/]db_storage$/i, '')
    : ''
}

const scanImageKeyMemory = async () => {
  if (isImageKeyAcquisitionPending.value) return

  const account = currentImageKeyAccount()
  const dbStoragePath = String(formData.db_storage_path || '').trim()
  const wxidDir = wxidDirFromDbStoragePath(dbStoragePath)
  if (!account && !dbStoragePath && !wxidDir) {
    imageMemoryScanState.value = 'error'
    imageMemoryScanMessage.value = '无法定位当前账号目录，请先完成数据库解密。'
    return
  }

  const context = beginImageKeyRequest(account, dbStoragePath)
  imageMemoryScanPending.value = true
  imageMemoryScanState.value = 'loading'
  imageMemoryScanMessage.value = '正在扫描微信进程内存，请保持微信运行并打开几张聊天图片。'
  logDecryptDebug('image-memory-scan:start', {
    account,
    db_storage_path: dbStoragePath,
    wxid_dir: wxidDir
  })

  try {
    const response = await getImageKeyMemory({
      account: account || null,
      db_storage_path: dbStoragePath,
      wxid_dir: wxidDir
    })
    if (!isCurrentImageKeyRequest(context)) {
      logDecryptDebug('image-memory-scan:stale-response', {
        request_account: account,
        response_account: String(response?.data?.account || '').trim(),
        request_id: context.id
      })
      return
    }
    const scannedKeys = normalizeCompleteImageKeys(
      response?.data?.xor_key,
      response?.data?.aes_key
    )
    const verified = response?.status === 0 && response?.data?.verified === true && scannedKeys.ok
    const accountMatches = imageKeyResponseMatchesContext(response?.data?.account, context)

    if (!verified || !accountMatches) {
      imageMemoryScanState.value = 'error'
      imageMemoryScanMessage.value = !accountMatches && verified
        ? '内存扫描结果不属于当前账号，已拒绝采用。'
        : String(response?.errmsg || '内存扫描未找到可验证的图片密钥，请打开图片后重试。')
      logDecryptDebug('image-memory-scan:invalid-response', {
        account,
        status: response?.status,
        verified: response?.data?.verified === true,
        account_matches: accountMatches,
        source: String(response?.data?.source || ''),
        errmsg: String(response?.errmsg || '')
      })
      return
    }

    manualKeys.xor_key = scannedKeys.xor.value
    manualKeys.aes_key = scannedKeys.aes.value
    imageKeysVerified.value = true
    imageKeyInputOrigin.value = 'memory'
    imageMemoryScanState.value = 'success'
    imageMemoryScanMessage.value = '内存扫描完成，图片密钥已通过本地图片校验。'
    logDecryptDebug('image-memory-scan:success', {
      account,
      source: String(response?.data?.source || ''),
      pid: response?.data?.pid,
      encoding: String(response?.data?.encoding || ''),
      keys: summarizeKeyStateForLog(scannedKeys.xor.value, scannedKeys.aes.value)
    })
  } catch (e) {
    if (isCurrentImageKeyRequest(context)) {
      imageMemoryScanState.value = 'error'
      imageMemoryScanMessage.value = String(e?.message || '内存扫描失败，请确认微信正在运行后重试。')
      logDecryptDebug('image-memory-scan:error', { account, error: formatLogError(e) })
    }
  } finally {
    imageMemoryScanPending.value = false
    finishImageKeyRequest()
  }
}

const prefillKeysForAccount = async (account) => {
  const acc = normalizeAccountId(account)
  if (!acc) return
  const dbStoragePath = String(formData.db_storage_path || '').trim()
  const context = beginImageKeyRequest(acc, dbStoragePath)
  logDecryptDebug('prefill:start', { account: acc })
  try {
    const resp = await getSavedKeys({
      account: acc,
      db_storage_path: dbStoragePath
    })
    if (!resp || resp.status !== 'success') return
    const keys = resp.keys || {}

    const dbKey = String(keys.db_key || '').trim()
    if (imageKeyContextStillSelected(context) && dbKey && !String(formData.key || '').trim()) {
      formData.key = dbKey
    }

    if (!isCurrentImageKeyRequest(context) || imageKeyInputOrigin.value === 'manual') {
      logDecryptDebug('prefill:stale-image-response', {
        account: acc,
        request_id: context.id,
        input_origin: imageKeyInputOrigin.value
      })
      return
    }

    const xorKey = String(keys.image_xor_key || '').trim()
    const aesKey = String(keys.image_aes_key || '').trim()
    const cachedXor = normalizeXorKey(xorKey)
    const cachedAes = normalizeAesKey(aesKey)
    const cachedPair = normalizeCompleteImageKeys(xorKey, aesKey)
    if (cachedPair.ok) {
      manualKeys.xor_key = cachedPair.xor.value
      manualKeys.aes_key = cachedPair.aes.value
      imageKeysVerified.value = keys.image_key_verified === true
      imageKeyInputOrigin.value = 'prefill'
    } else if (xorKey || aesKey) {
      manualKeys.xor_key = cachedXor.ok ? cachedXor.value : ''
      manualKeys.aes_key = cachedAes.ok ? cachedAes.value : ''
      imageKeysVerified.value = false
      imageKeyInputOrigin.value = 'prefill'
    } else {
      imageKeysVerified.value = false
      imageKeyInputOrigin.value = 'empty'
    }
    logDecryptDebug('prefill:done', {
      request_account: acc,
      response_account: String(resp.account || '').trim(),
      db_key_present: !!dbKey,
      db_key_store_account: String(keys.db_key_store_account || '').trim(),
      db_key_source_wxid_dir: String(keys.db_key_source_wxid_dir || '').trim(),
      db_key_blocked_reason: String(keys.db_key_blocked_reason || '').trim(),
      ...summarizeKeyStateForLog(
        String(keys.image_xor_key || '').trim(),
        String(keys.image_aes_key || '').trim()
      ),
      applied: summarizeKeyStateForLog(manualKeys.xor_key, manualKeys.aes_key)
    })
  } catch (e) {
    logDecryptDebug('prefill:error', { account: acc, error: formatLogError(e) })
  } finally {
    finishImageKeyRequest()
  }
}

const tryAutoFetchImageKeys = async (account) => {
  const acc = normalizeAccountId(account)
  if (!acc) return
  if (imageKeyInputOrigin.value === 'manual') {
    logDecryptDebug('auto-fetch:skip-manual-input', { account: acc })
    return
  }
  const existingKeys = normalizeCompleteImageKeys(manualKeys.xor_key, manualKeys.aes_key)
  if (existingKeys.ok && imageKeysVerified.value) {
    logDecryptDebug('auto-fetch:skip-existing', {
      account: acc,
      keys: summarizeKeyStateForLog(manualKeys.xor_key, manualKeys.aes_key)
    })
    return
  }

  const dbStoragePath = String(formData.db_storage_path || '').trim()
  const context = beginImageKeyRequest(acc, dbStoragePath)
  warning.value = '正在自动解析并校验图片密钥，请稍候...'
  logDecryptDebug('auto-fetch:start', { account: acc })
  try {
    const imgRes = await getImageKey({
      account: acc,
      db_storage_path: dbStoragePath
    })
    logDecryptDebug('auto-fetch:response', {
      account: acc,
      status: imgRes?.status,
      errmsg: String(imgRes?.errmsg || ''),
      data_account: String(imgRes?.data?.account || '').trim(),
      keys: summarizeKeyStateForLog(imgRes?.data?.xor_key, imgRes?.data?.aes_key)
    })

    if (!isCurrentImageKeyRequest(context)) {
      logDecryptDebug('auto-fetch:stale-response', { account: acc, request_id: context.id })
      return
    }

    const fetchedKeys = normalizeCompleteImageKeys(
      imgRes?.data?.xor_key,
      imgRes?.data?.aes_key
    )
    const verified = imgRes && imgRes.status === 0 && imgRes?.data?.verified === true && fetchedKeys.ok
    if (verified && imageKeyResponseMatchesContext(imgRes?.data?.account, context)) {
      manualKeys.xor_key = fetchedKeys.xor.value
      manualKeys.aes_key = fetchedKeys.aes.value
      imageKeysVerified.value = true
      imageKeyInputOrigin.value = 'auto'
      const successMessage = String(imgRes?.data?.source || '').startsWith('remote_')
        ? '远端候选已通过本地图片校验！'
        : '已通过本地解析成功获取图片密钥！'
      warning.value = successMessage
      setTimeout(() => { if (warning.value === successMessage) warning.value = '' }, 3000)
    } else {
      warning.value = '本地解析图片密钥失败，您可以尝试手动填写。'
      logDecryptDebug('auto-fetch:invalid-response', {
        account: acc,
        status: imgRes?.status,
        verified: imgRes?.data?.verified === true,
        source: String(imgRes?.data?.source || ''),
        errmsg: String(imgRes?.errmsg || ''),
        xor_error: fetchedKeys.xor.message,
        aes_error: fetchedKeys.aes.message || (fetchedKeys.aes.value ? '' : '缺少 AES 密钥')
      })
    }
  } catch (e) {
    if (isCurrentImageKeyRequest(context)) {
      warning.value = '本地解析图片密钥失败，请手动填写图片密钥。'
      logDecryptDebug('auto-fetch:error', { account: acc, error: formatLogError(e) })
    }
  } finally {
    finishImageKeyRequest()
  }
}

const ensureKeysForAccount = async (account) => {
  const acc = normalizeAccountId(account)
  if (!acc) return
  const ensureRevision = ++ensureKeysRevision

  logDecryptDebug('ensure-keys:start', {
    account: acc,
    ensure_revision: ensureRevision,
    previous_account: activeKeyAccount.value,
    current_manual: summarizeKeyStateForLog(manualKeys.xor_key, manualKeys.aes_key)
  })
  if (activeKeyAccount.value && activeKeyAccount.value !== acc) {
    logDecryptDebug('ensure-keys:switch-account', {
      from: activeKeyAccount.value,
      to: acc,
      cleared_keys: summarizeKeyStateForLog(manualKeys.xor_key, manualKeys.aes_key)
    })
    clearManualKeys()
  }

  activeKeyAccount.value = acc
  const ensureContext = { account: acc, dbStoragePath: String(formData.db_storage_path || '').trim() }
  await prefillKeysForAccount(acc)
  if (ensureRevision !== ensureKeysRevision || activeKeyAccount.value !== acc || !imageKeyContextStillSelected(ensureContext)) {
    logDecryptDebug('ensure-keys:stale-after-prefill', {
      account: acc,
      ensure_revision: ensureRevision,
      current_ensure_revision: ensureKeysRevision,
      active_account: activeKeyAccount.value,
      db_storage_path: ensureContext.dbStoragePath
    })
    return
  }
  if (imageKeyInputOrigin.value !== 'manual') {
    await tryAutoFetchImageKeys(acc)
  }
  logDecryptDebug('ensure-keys:done', {
    account: acc,
    manual: summarizeKeyStateForLog(manualKeys.xor_key, manualKeys.aes_key)
  })
}

const isDbKeyRequestActive = (revision, controller) => (
  revision === dbKeyRequestRevision
  && controller === dbKeyRequestController
  && !controller.signal.aborted
)

const waitForDbKeyDelay = (milliseconds, signal) => new Promise((resolve, reject) => {
  if (signal.aborted) {
    const error = new Error('数据库密钥获取已停止')
    error.name = 'AbortError'
    reject(error)
    return
  }

  const onAbort = () => {
    clearTimeout(timer)
    const error = new Error('数据库密钥获取已停止')
    error.name = 'AbortError'
    reject(error)
  }
  const timer = setTimeout(() => {
    signal.removeEventListener('abort', onAbort)
    resolve()
  }, milliseconds)
  signal.addEventListener('abort', onAbort, { once: true })
})

const cancelDbKeyAcquisition = () => {
  if (!dbKeyRequestController && !isGettingDbKey.value) return

  dbKeyRequestRevision += 1
  const controller = dbKeyRequestController
  dbKeyRequestController = null
  controller?.abort()
  isGettingDbKey.value = false
}

const handleGetDbKey = async () => {
  if (isGettingDbKey.value) return

  if (isMacos.value) {
    const openTool = await requestGuideDialog({
      eyebrow: 'macOS 数据库密钥',
      title: '请使用支持 Mac 的同类工具获取密钥',
      description: platformCapabilities.value?.database_key_guidance || 'macOS 版不提供数据库密钥提取，请获取后回到这里手动填写。',
      details: [
        '仅处理您本人账号的数据，并妥善保存密钥',
        '获取 64 位数据库密钥后粘贴到当前输入框',
        '本应用仍会负责解密、实时消息、图片密钥和后续分析'
      ],
      note: '本应用不会调用或依赖外部工具；链接仅用于帮助您获取密钥。',
      primaryLabel: '打开 WeFlow 项目页',
      secondaryLabel: '返回手动填写',
      tone: 'guide'
    })
    if (openTool && process.client && typeof window !== 'undefined') {
      const url = 'https://github.com/hicccc77/WeFlow'
      if (window.wechatDesktop?.openExternalUrl) await window.wechatDesktop.openExternalUrl(url)
      else window.open(url, '_blank', 'noopener,noreferrer')
    }
    return
  }

  const shouldContinue = await requestGuideDialog({
    eyebrow: '密钥获取提示',
    title: '获取前请确认微信已登录',
    description: '系统会先尝试从当前运行的微信中扫描数据库密钥。这里只做操作提醒，不会强制检查登录状态。',
    details: [
      '保持电脑版微信运行，并登录需要解密的账号',
      '确认下方数据库路径属于同一个微信账号',
      '获取期间不要退出微信或切换到其他账号'
    ],
    note: '如果内存扫描失败，系统会再次询问是否切换到 Hook 获取。',
    primaryLabel: '准备好了，开始获取',
    secondaryLabel: '暂不获取',
    tone: 'guide'
  })
  if (!shouldContinue) return

  const requestRevision = ++dbKeyRequestRevision
  const requestController = new AbortController()
  dbKeyRequestController = requestController
  isGettingDbKey.value = true

  error.value = ''
  warning.value = ''
  formErrors.key = ''

  try {
    const wechatInstallPath = normalizeWechatInstallPath(formData.wechat_install_path || readStoredWechatInstallPath())
    const dbStoragePath = String(formData.db_storage_path || '').trim()
    formData.wechat_install_path = wechatInstallPath
    const statusRes = await getWxStatus({ signal: requestController.signal })
    if (!isDbKeyRequestActive(requestRevision, requestController)) return
    const wxStatus = statusRes?.wx_status

    const applySuccessResult = (res) => {
      if (!isDbKeyRequestActive(requestRevision, requestController)) return
      if (res.data?.db_key) {
        formData.key = res.data.db_key
      }
      let successMessage = ''
      if (res.data?.method === 'key_v4') {
        successMessage = '数据库解密密钥已通过 V4 内存扫描获取成功！'
      } else {
        successMessage = '数据库解密密钥已通过 Hook 获取成功！'
      }
      warning.value = successMessage
      setTimeout(() => {
        if (requestRevision === dbKeyRequestRevision && warning.value === successMessage) warning.value = ''
      }, 3000)
    }

    const fetchByHook = async () => {
      if (wxStatus?.is_running) {
        warning.value = '即将改用 Hook 获取数据库密钥：5秒后会关闭并重启微信，请确保微信未开启“自动登录”，并在弹窗中正常登录。'
        await waitForDbKeyDelay(5000, requestController.signal)
      } else {
        warning.value = '正在使用 Hook 获取数据库密钥，请确保微信未开启“自动登录”，并在弹窗中正常登录。'
      }

      if (!isDbKeyRequestActive(requestRevision, requestController)) return null
      return await getKeys({
        wechat_install_path: wechatInstallPath,
        db_storage_path: dbStoragePath,
        key_mode: 'hook',
        signal: requestController.signal
      })
    }

    let res = null
    if (dbStoragePath) {
      warning.value = '正在优先尝试 V4 内存扫描获取数据库密钥。'
      res = await getKeys({
        wechat_install_path: wechatInstallPath,
        db_storage_path: dbStoragePath,
        key_mode: 'key_v4',
        signal: requestController.signal
      })
      if (!isDbKeyRequestActive(requestRevision, requestController)) return
    } else {
      const useHook = await requestGuideDialog({
        eyebrow: '获取方式切换',
        title: '是否改用 Hook 获取密钥？',
        description: 'V4 内存扫描需要数据库存储路径来校验候选密钥。当前路径为空，可以返回填写，也可以直接切换到 Hook。',
        details: [
          'Hook 可能会关闭并重新启动微信',
          '请关闭微信自动登录，并在弹出的微信窗口中手动登录',
          '登录时请选择当前准备解密的同一个账号'
        ],
        note: '选择“返回填写路径”不会执行 Hook，也不会关闭微信。',
        primaryLabel: '继续使用 Hook',
        secondaryLabel: '返回填写路径',
        tone: 'warning'
      })
      if (!isDbKeyRequestActive(requestRevision, requestController)) return
      if (!useHook) {
        warning.value = ''
        formErrors.db_storage_path = '请填写数据库存储路径后再使用 V4 内存扫描'
        return
      }
      res = await fetchByHook()
      if (!isDbKeyRequestActive(requestRevision, requestController)) return
    }

    if (res && res.status === 0) {
      applySuccessResult(res)
    } else if (res?.data?.can_fallback_to_hook) {
      const detail = res?.data?.key_v4_error || res?.errmsg || '未知错误'
      warning.value = ''
      const useHook = await requestGuideDialog({
        eyebrow: '获取方式切换',
        title: '内存扫描失败，是否改用 Hook？',
        description: '可以继续改用 Hook 获取密钥。',
        errorMessage: `V4 内存扫描未能获取密钥：${detail}`,
        details: [
          'Hook 可能会关闭并重新启动微信',
          '请关闭微信自动登录，并在弹出的微信窗口中手动登录',
          '登录时请选择当前准备解密的同一个账号'
        ],
        note: '选择“暂不切换”会停止本次获取，不影响现有微信数据。',
        primaryLabel: '继续使用 Hook',
        secondaryLabel: '暂不切换',
        tone: 'warning'
      })
      if (!isDbKeyRequestActive(requestRevision, requestController)) return
      if (!useHook) {
        error.value = 'V4 内存扫描失败，已取消 Hook 获取。'
        return
      }

      res = await fetchByHook()
      if (!isDbKeyRequestActive(requestRevision, requestController)) return
      if (res && res.status === 0) {
        applySuccessResult(res)
      } else {
        error.value = 'Hook 获取失败: ' + (res?.errmsg || '未知错误')
        warning.value = ''
      }
    } else {
      error.value = '获取失败: ' + (res?.errmsg || '未知错误')
      warning.value = ''
    }
  } catch (e) {
    if (!isDbKeyRequestActive(requestRevision, requestController) || e?.name === 'AbortError') return
    console.error(e)
    error.value = '系统错误: ' + e.message
    warning.value = ''
  } finally {
    if (isDbKeyRequestActive(requestRevision, requestController)) {
      dbKeyRequestController = null
      isGettingDbKey.value = false
    }
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
  invalidateImageKeyRequests()
  logDecryptDebug('keys:clear', {
    active_account: activeKeyAccount.value,
    manual: summarizeKeyStateForLog(manualKeys.xor_key, manualKeys.aes_key),
    applied: summarizeKeyStateForLog(mediaKeys.xor_key, mediaKeys.aes_key)
  })
  manualKeys.xor_key = ''
  manualKeys.aes_key = ''
  imageKeysVerified.value = false
  imageKeyInputOrigin.value = 'empty'
  imageMemoryScanState.value = 'idle'
  imageMemoryScanMessage.value = ''
  manualKeyErrors.xor_key = ''
  manualKeyErrors.aes_key = ''
  mediaKeys.xor_key = ''
  mediaKeys.aes_key = ''
  activeKeyAccount.value = ''
}

// 图片解密相关
const mediaDecryptResult = ref(null)
const mediaDecrypting = ref(false)
const mediaDecryptConcurrency = ref(10)
const emojiDownloadResult = ref(null)
const emojiDownloading = ref(false)
const emojiDownloadConcurrency = ref(20)

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
  concurrency: 0,
  success_count: 0,
  skip_count: 0,
  fail_count: 0,
  current_file: '',
  fileStatus: '',
  status: '',
  message: ''
})

// 进度百分比
const progressPercent = computed(() => {
  if (decryptProgress.total === 0) return 0
  return Math.round((decryptProgress.current / decryptProgress.total) * 100)
})

const emojiDownloadProgress = reactive({
  current: 0,
  total: 0,
  concurrency: 0,
  success_count: 0,
  skip_count: 0,
  fail_count: 0,
  current_file: '',
  fileStatus: '',
  status: '',
  message: ''
})

const emojiProgressPercent = computed(() => {
  if (emojiDownloadProgress.total === 0) return 0
  return Math.round((emojiDownloadProgress.current / emojiDownloadProgress.total) * 100)
})

const getEmojiDownloadConcurrency = () => {
  const raw = Number.parseInt(String(emojiDownloadConcurrency.value || 20), 10)
  if (!Number.isFinite(raw)) return 20
  return Math.max(1, Math.min(100, raw))
}

const getMediaDecryptConcurrency = () => {
  const raw = Number.parseInt(String(mediaDecryptConcurrency.value || 10), 10)
  if (!Number.isFinite(raw)) return 10
  return Math.max(1, Math.min(64, raw))
}

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
let mediaDecryptEventSource = null
let emojiDownloadEventSource = null

const closeDbDecryptEventSource = () => {
  try {
    if (dbDecryptEventSource) dbDecryptEventSource.close()
  } catch (e) {
    // ignore
  } finally {
    dbDecryptEventSource = null
  }
}

const closeMediaDecryptEventSource = () => {
  try {
    if (mediaDecryptEventSource) mediaDecryptEventSource.close()
  } catch (e) {
    // ignore
  } finally {
    mediaDecryptEventSource = null
  }
}

const closeEmojiDownloadEventSource = () => {
  try {
    if (emojiDownloadEventSource) emojiDownloadEventSource.close()
  } catch (e) {
    // ignore
  } finally {
    emojiDownloadEventSource = null
  }
}

onBeforeUnmount(() => {
  settleGuideDialog(false)
  cancelDbKeyAcquisition()
  ensureKeysRevision += 1
  invalidateImageKeyRequests()
  closeDbDecryptEventSource()
  closeMediaDecryptEventSource()
  closeEmojiDownloadEventSource()
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

const resetMediaDecryptProgress = () => {
  decryptProgress.current = 0
  decryptProgress.total = 0
  decryptProgress.concurrency = 0
  decryptProgress.success_count = 0
  decryptProgress.skip_count = 0
  decryptProgress.fail_count = 0
  decryptProgress.current_file = ''
  decryptProgress.fileStatus = ''
  decryptProgress.status = ''
  decryptProgress.message = ''
}

const resetEmojiDownloadProgress = () => {
  emojiDownloadProgress.current = 0
  emojiDownloadProgress.total = 0
  emojiDownloadProgress.concurrency = 0
  emojiDownloadProgress.success_count = 0
  emojiDownloadProgress.skip_count = 0
  emojiDownloadProgress.fail_count = 0
  emojiDownloadProgress.current_file = ''
  emojiDownloadProgress.fileStatus = ''
  emojiDownloadProgress.status = ''
  emojiDownloadProgress.message = ''
}

// 处理解密
const handleDecrypt = async () => {
  if (!validateForm()) {
    return
  }

  logDecryptDebug('decrypt:start', {
    db_storage_path: String(formData.db_storage_path || '').trim(),
    db_key_length: String(formData.key || '').trim().length
  })
  loading.value = true
  error.value = ''
  warning.value = ''

  resetDbDecryptProgress()
  resetMediaDecryptProgress()
  resetEmojiDownloadProgress()
  mediaDecryptResult.value = null
  emojiDownloadResult.value = null
  mediaDecrypting.value = false
  emojiDownloading.value = false
  closeMediaDecryptEventSource()
  closeEmojiDownloadEventSource()

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
          if (accounts.length > 0) {
            mediaAccount.value = accounts[0]
          } else {
            const match = formData.db_storage_path.match(/(wxid_[a-zA-Z0-9]+)/)
            if (match) mediaAccount.value = match[1]
          }
        } catch (e) {}
        logDecryptDebug('decrypt:completed-fallback', {
          media_account: mediaAccount.value,
          accounts: Object.keys(result.account_results || {})
        })

        currentStep.value = 1
        await ensureKeysForAccount(mediaAccount.value)

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
    const apiBase = useApiBase()
    const url = `${apiBase}/decrypt_stream?${params.toString()}`

    dbDecryptProgress.message = '连接中...'
    const eventSource = new EventSource(url)
    dbDecryptEventSource = eventSource

    eventSource.onmessage = async (event) => {
      if (dbDecryptEventSource !== eventSource) return

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
            if (accounts.length > 0) {
              mediaAccount.value = accounts[0]
            } else {
              const match = formData.db_storage_path.match(/(wxid_[a-zA-Z0-9]+)/)
              if (match) mediaAccount.value = match[1]
            }
          } catch (e) {}
          logDecryptDebug('decrypt:completed-sse', {
            media_account: mediaAccount.value,
            accounts: Object.keys(data.account_results || {})
          })

          try {
            eventSource.close()
          } catch (e) {}
          dbDecryptEventSource = null
          loading.value = false

          if (data.status === 'completed') {
            currentStep.value = 1
            await ensureKeysForAccount(mediaAccount.value)
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
      if (dbDecryptEventSource !== eventSource) return

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
  closeMediaDecryptEventSource()
  mediaDecrypting.value = true
  mediaDecryptResult.value = null
  error.value = ''
  warning.value = ''
  const configuredConcurrency = getMediaDecryptConcurrency()
  mediaDecryptConcurrency.value = configuredConcurrency
  logDecryptDebug('media-decrypt:start', {
    account: mediaAccount.value,
    concurrency: configuredConcurrency,
    keys: summarizeKeyStateForLog(mediaKeys.xor_key, mediaKeys.aes_key)
  })
  
  // 重置进度
  resetMediaDecryptProgress()
  
  try {
    // 构建SSE URL
    const params = new URLSearchParams()
    if (mediaAccount.value) params.set('account', mediaAccount.value)
    if (mediaKeys.xor_key) params.set('xor_key', mediaKeys.xor_key)
    if (mediaKeys.aes_key) params.set('aes_key', mediaKeys.aes_key)
    params.set('concurrency', String(configuredConcurrency))
    const apiBase = useApiBase()
    const url = `${apiBase}/media/decrypt_all_stream?${params.toString()}`
    
    // 使用EventSource接收SSE
    const eventSource = new EventSource(url)
    mediaDecryptEventSource = eventSource
    
    eventSource.onmessage = (event) => {
      if (mediaDecryptEventSource !== eventSource) return

      try {
        const data = JSON.parse(event.data)
        
        if (data.type === 'scanning') {
          decryptProgress.current_file = '正在扫描文件...'
          decryptProgress.message = data.message || '正在扫描图片文件...'
        } else if (data.type === 'start') {
          decryptProgress.total = data.total || 0
          decryptProgress.concurrency = data.concurrency || configuredConcurrency
          decryptProgress.message = data.message || ''
        } else if (data.type === 'progress') {
          decryptProgress.current = data.current || 0
          decryptProgress.total = data.total || 0
          decryptProgress.concurrency = data.concurrency || configuredConcurrency
          decryptProgress.success_count = data.success_count || 0
          decryptProgress.skip_count = data.skip_count || 0
          decryptProgress.fail_count = data.fail_count || 0
          decryptProgress.current_file = data.current_file || ''
          decryptProgress.fileStatus = data.status || ''
          decryptProgress.message = data.message || ''
        } else if (data.type === 'complete') {
          decryptProgress.status = 'complete'
          decryptProgress.current = data.total || 0
          decryptProgress.total = data.total || 0
          decryptProgress.concurrency = data.concurrency || configuredConcurrency
          decryptProgress.success_count = data.success_count || 0
          decryptProgress.skip_count = data.skip_count || 0
          decryptProgress.fail_count = data.fail_count || 0
          decryptProgress.message = data.message || '解密完成'
          mediaDecryptResult.value = data
          mediaDecrypting.value = false
          logDecryptDebug('media-decrypt:complete', {
            account: mediaAccount.value,
            total: data.total,
            concurrency: data.concurrency,
            decrypt_stats: data.decrypt_stats,
            success_count: data.success_count,
            skip_count: data.skip_count,
            fail_count: data.fail_count
          })
          closeMediaDecryptEventSource()
        } else if (data.type === 'error') {
          error.value = data.message
          logDecryptDebug('media-decrypt:error-event', {
            account: mediaAccount.value,
            message: data.message
          })
          mediaDecrypting.value = false
          closeMediaDecryptEventSource()
        }
      } catch (e) {
        console.error('解析SSE消息失败:', e)
      }
    }
    
    eventSource.onerror = (e) => {
      if (mediaDecryptEventSource !== eventSource) return

      console.error('SSE连接错误:', e)
      closeMediaDecryptEventSource()
      if (mediaDecrypting.value) {
        error.value = 'SSE连接中断，请重试'
        mediaDecrypting.value = false
      }
    }
  } catch (err) {
    error.value = err.message || '图片解密过程中发生错误'
    mediaDecrypting.value = false
    closeMediaDecryptEventSource()
  }
}

const cancelMediaDecrypt = () => {
  if (!mediaDecrypting.value) return

  decryptProgress.status = 'cancelled'
  decryptProgress.message = '已停止图片解密'
  mediaDecrypting.value = false
  warning.value = '已停止图片解密，已完成的图片会保留。'
  logDecryptDebug('media-decrypt:cancelled', {
    account: mediaAccount.value,
    current: decryptProgress.current,
    total: decryptProgress.total,
    concurrency: decryptProgress.concurrency || getMediaDecryptConcurrency()
  })
  closeMediaDecryptEventSource()
}

const downloadAllEmojis = async () => {
  closeEmojiDownloadEventSource()
  emojiDownloading.value = true
  emojiDownloadResult.value = null
  error.value = ''
  warning.value = ''
  const configuredConcurrency = getEmojiDownloadConcurrency()
  emojiDownloadConcurrency.value = configuredConcurrency
  logDecryptDebug('emoji-download:start', {
    account: mediaAccount.value,
    concurrency: configuredConcurrency
  })

  resetEmojiDownloadProgress()

  try {
    const params = new URLSearchParams()
    if (mediaAccount.value) params.set('account', mediaAccount.value)
    params.set('concurrency', String(configuredConcurrency))
    const apiBase = useApiBase()
    const url = `${apiBase}/media/emoji/download_all_stream?${params.toString()}`

    const eventSource = new EventSource(url)
    emojiDownloadEventSource = eventSource

    eventSource.onmessage = (event) => {
      if (emojiDownloadEventSource !== eventSource) return

      try {
        const data = JSON.parse(event.data)

        if (data.type === 'scanning') {
          emojiDownloadProgress.current_file = '正在扫描表情资源...'
          emojiDownloadProgress.message = data.message || '正在扫描表情资源...'
        } else if (data.type === 'start') {
          emojiDownloadProgress.total = data.total || 0
          emojiDownloadProgress.concurrency = data.concurrency || configuredConcurrency
          emojiDownloadProgress.message = data.message || ''
        } else if (data.type === 'progress') {
          emojiDownloadProgress.current = data.current || 0
          emojiDownloadProgress.total = data.total || 0
          emojiDownloadProgress.concurrency = data.concurrency || configuredConcurrency
          emojiDownloadProgress.success_count = data.success_count || 0
          emojiDownloadProgress.skip_count = data.skip_count || 0
          emojiDownloadProgress.fail_count = data.fail_count || 0
          emojiDownloadProgress.current_file = data.current_file || ''
          emojiDownloadProgress.fileStatus = data.status || ''
          emojiDownloadProgress.message = data.message || ''
        } else if (data.type === 'complete') {
          emojiDownloadProgress.status = 'complete'
          emojiDownloadProgress.current = data.total || 0
          emojiDownloadProgress.total = data.total || 0
          emojiDownloadProgress.concurrency = data.concurrency || configuredConcurrency
          emojiDownloadProgress.success_count = data.success_count || 0
          emojiDownloadProgress.skip_count = data.skip_count || 0
          emojiDownloadProgress.fail_count = data.fail_count || 0
          emojiDownloadProgress.message = data.message || '表情下载完成'
          emojiDownloadResult.value = data
          emojiDownloading.value = false
          logDecryptDebug('emoji-download:complete', {
            account: mediaAccount.value,
            total: data.total,
            concurrency: data.concurrency,
            download_stats: data.download_stats,
            success_count: data.success_count,
            skip_count: data.skip_count,
            fail_count: data.fail_count
          })
          closeEmojiDownloadEventSource()
        } else if (data.type === 'error') {
          error.value = data.message || '表情下载失败'
          logDecryptDebug('emoji-download:error-event', {
            account: mediaAccount.value,
            message: data.message
          })
          emojiDownloading.value = false
          closeEmojiDownloadEventSource()
        }
      } catch (e) {
        console.error('解析表情下载SSE消息失败:', e)
      }
    }

    eventSource.onerror = (e) => {
      if (emojiDownloadEventSource !== eventSource) return

      console.error('表情下载SSE连接错误:', e)
      closeEmojiDownloadEventSource()
      if (emojiDownloading.value) {
        error.value = '表情下载连接中断，请重试'
        emojiDownloading.value = false
      }
    }
  } catch (err) {
    error.value = err.message || '表情下载过程中发生错误'
    emojiDownloading.value = false
    closeEmojiDownloadEventSource()
  }
}

const cancelEmojiDownload = () => {
  if (!emojiDownloading.value) return

  emojiDownloadProgress.status = 'cancelled'
  emojiDownloading.value = false
  warning.value = '已停止表情下载，已完成的表情会保留。'
  logDecryptDebug('emoji-download:cancelled', {
    account: mediaAccount.value,
    current: emojiDownloadProgress.current,
    total: emojiDownloadProgress.total
  })
  closeEmojiDownloadEventSource()
}

const cancelDatabaseDecrypt = () => {
  if (!loading.value) return

  closeDbDecryptEventSource()
  loading.value = false
  dbDecryptProgress.status = 'cancelled'
  dbDecryptProgress.message = '已停止数据库解密'
  logDecryptDebug('decrypt:cancelled-by-back', {
    current: dbDecryptProgress.current,
    total: dbDecryptProgress.total
  })
}

const confirmBackFromRunningStep = () => {
  const runningStep = currentStep.value === 0 && loading.value
    ? { title: '数据库仍在解密', description: '返回账号选择会停止接收当前解密进度，已经生成的文件会保留。' }
    : currentStep.value === 0 && isGettingDbKey.value
      ? {
          title: '数据库密钥仍在获取',
          description: '返回账号选择会停止当前页面等待结果；如果 Hook 已经开始，微信重启或登录流程仍可能继续完成。',
          details: ['页面将不再接收本次密钥结果', '已经启动的 Hook 操作无法保证立即停止']
        }
    : currentStep.value === 2 && mediaDecrypting.value
      ? { title: '图片仍在解密', description: '返回填写图片密钥会停止当前图片解密，已经完成的图片会保留。' }
      : currentStep.value === 3 && emojiDownloading.value
        ? { title: '表情仍在下载', description: '返回图片解密会停止当前下载，已经完成的表情会保留。' }
        : null

  if (!runningStep) return Promise.resolve(true)
  return requestGuideDialog({
    eyebrow: '确认回退',
    title: runningStep.title,
    description: runningStep.description,
    details: runningStep.details || ['当前任务不会在后台继续显示进度', '稍后可以回到此步骤重新开始'],
    note: '取消后会留在当前步骤，任务继续运行。',
    primaryLabel: '停止并返回',
    secondaryLabel: '继续当前任务',
    tone: 'warning'
  })
}

const goBackFromCurrentStep = async () => {
  const fromStep = currentStep.value
  if (!(await confirmBackFromRunningStep())) return

  if (fromStep === 0) {
    cancelDatabaseDecrypt()
    cancelDbKeyAcquisition()
    error.value = ''
    warning.value = ''
    await navigateTo('/detection-result')
    return
  }

  if (fromStep === 1) {
    ensureKeysRevision += 1
    invalidateImageKeyRequests()
  }
  if (fromStep === 2) cancelMediaDecrypt()
  if (fromStep === 3) cancelEmojiDownload()
  error.value = ''
  warning.value = ''
  currentStep.value = Math.max(0, fromStep - 1)
}

const goToEmojiDownloadStep = () => {
  if (mediaDecrypting.value) return

  error.value = ''
  warning.value = ''
  currentStep.value = 3
}

// 从密钥步骤进入图片解密步骤
const goToMediaDecryptStep = async () => {
  if (isImageKeyAcquisitionPending.value) return
  error.value = ''
  warning.value = ''
  // 校验并应用（未填写则允许直接进入，后端会使用已保存密钥或报错提示）
  const ok = applyManualKeys()
  logDecryptDebug('media-step:apply-manual', {
    account: mediaAccount.value,
    ok,
    manual: summarizeKeyStateForLog(manualKeys.xor_key, manualKeys.aes_key),
    applied: summarizeKeyStateForLog(mediaKeys.xor_key, mediaKeys.aes_key),
    errors: { ...manualKeyErrors }
  })
  if (!ok || manualKeyErrors.xor_key || manualKeyErrors.aes_key) return

  if (!mediaKeys.xor_key) {
    const shouldContinue = await requestGuideDialog({
      eyebrow: '图片密钥提示',
      title: '尚未填写图片 XOR 密钥',
      description: '您可以继续进入图片解密步骤，但加密图片、视频缩略图等媒体大概率无法正常显示。',
      details: [
        '纯文本聊天记录不受图片密钥影响',
        '图片解密可能出现大量失败或空白预览',
        '之后仍可返回此流程补充密钥并重新解密'
      ],
      note: '这里只提示可能的影响，不会强制要求填写图片密钥。',
      primaryLabel: '仍然进入图片解密',
      secondaryLabel: '返回填写密钥',
      tone: 'warning'
    })
    if (!shouldContinue) return
  }

  // 用户已输入 XOR 时，自动保存一次，避免下次重复输入（失败不影响继续）
  if (mediaKeys.xor_key && !imageKeysVerified.value) {
    try {
      const aesVal = String(mediaKeys.aes_key || '').trim()
      logDecryptDebug('media-step:save-keys', {
        account: mediaAccount.value,
        keys: summarizeKeyStateForLog(mediaKeys.xor_key, aesVal)
      })
      await saveMediaKeys({
        account: mediaAccount.value || null,
        xor_key: mediaKeys.xor_key,
        aes_key: aesVal ? aesVal : null
      })
    } catch (e) {
      logDecryptDebug('media-step:save-keys-error', { account: mediaAccount.value, error: formatLogError(e) })
    }
  } else if (mediaKeys.xor_key) {
    logDecryptDebug('media-step:skip-save-verified', { account: mediaAccount.value })
  }
  currentStep.value = 2
}

// 跳过图片解密，直接查看聊天记录
const skipToChat = async () => {
  if (isImageKeyAcquisitionPending.value) return
  if (!mediaDecryptResult.value) {
    const shouldContinue = await requestGuideDialog({
      eyebrow: '跳过媒体准备',
      title: '确定暂时跳过图片解密？',
      description: '跳过后可以直接查看聊天记录，但尚未解密的图片和其他媒体可能显示为空或加载失败。',
      details: [
        '已解密的文字消息可以正常查看和搜索',
        '未处理的图片、缩略图和部分媒体暂时不可用',
        '之后可以重新进入解密流程继续处理媒体文件'
      ],
      note: '跳过不会删除已完成的数据，也不会修改微信客户端中的内容。',
      primaryLabel: '仍然查看聊天记录',
      secondaryLabel: '继续准备媒体',
      tone: 'warning'
    })
    if (!shouldContinue) return
  }

  try {
    const ok = applyManualKeys()
    if (ok && mediaKeys.xor_key && !imageKeysVerified.value) {
      const aesVal = String(mediaKeys.aes_key || '').trim()
      logDecryptDebug('skip-chat:save-keys', {
        account: mediaAccount.value,
        keys: summarizeKeyStateForLog(mediaKeys.xor_key, aesVal)
      })
      await saveMediaKeys({
        account: mediaAccount.value || null,
        xor_key: mediaKeys.xor_key,
        aes_key: aesVal ? aesVal : null
      })
    } else if (ok && mediaKeys.xor_key) {
      logDecryptDebug('skip-chat:skip-save-verified', { account: mediaAccount.value })
    }
  } catch (e) {
    logDecryptDebug('skip-chat:save-keys-error', { account: mediaAccount.value, error: formatLogError(e) })
  }
  navigateTo('/chat')
}

// 页面加载时检查是否有选中的账户
onMounted(async () => {
  if (process.client && typeof window !== 'undefined') {
    try {
      platformCapabilities.value = await getPlatformCapabilities()
    } catch {
      platformCapabilities.value = {
        platform: /Macintosh|Mac OS X/i.test(String(navigator.userAgent || '')) ? 'macos' : 'windows'
      }
    }
    formData.wechat_install_path = readStoredWechatInstallPath()
    const selectedAccount = sessionStorage.getItem('selectedAccount')
    logDecryptDebug('mounted:selected-account-raw', { raw: selectedAccount || '' })
    if (selectedAccount) {
      try {
        const account = JSON.parse(selectedAccount)
        // 填充数据路径
        if (account.data_dir) {
          const separator = isMacos.value ? '/' : '\\'
          formData.db_storage_path = String(account.data_dir).replace(/[\\/]+$/, '') + separator + 'db_storage'
        }
        if (account.account_name) {
          mediaAccount.value = account.account_name
        }
        // 清除sessionStorage
        sessionStorage.removeItem('selectedAccount')
        logDecryptDebug('mounted:selected-account-parsed', {
          account_name: String(account.account_name || '').trim(),
          data_dir: String(account.data_dir || '').trim()
        })
        await ensureKeysForAccount(mediaAccount.value)
      } catch (e) {
        console.error('解析账户信息失败:', e)
        logDecryptDebug('mounted:selected-account-error', { error: formatLogError(e) })
      }
    }
  }
})
</script>
