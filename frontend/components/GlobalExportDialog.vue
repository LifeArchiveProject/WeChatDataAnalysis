<template>
  <div v-if="open" class="fixed inset-0 z-[135] flex items-center justify-center px-4 py-6">
    <div class="absolute inset-0 bg-black/40 backdrop-blur-[2px]" @click="requestClose"></div>

    <div class="relative flex max-h-[88vh] w-full max-w-[1180px] flex-col overflow-hidden rounded-[16px] border border-[#e6e6e6] bg-white shadow-2xl">
      <div class="flex items-center gap-3 border-b border-[#efefef] px-5 py-4">
        <div>
          <div class="text-[16px] font-semibold text-[#222]">批量导出</div>
          <div class="mt-1 text-[12px] text-[#7a7a7a]">
            统一导出聊天记录、朋友圈和联系人，可按模块多选并分别设置导出粒度。
          </div>
        </div>
        <button
          type="button"
          class="ml-auto flex h-8 w-8 items-center justify-center rounded-md text-[#888] transition hover:bg-[#f4f4f4] hover:text-[#222] disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="running"
          title="关闭"
          @click="requestClose"
        >
          <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
      </div>

      <div class="flex-1 overflow-y-auto px-5 py-5">
        <div class="space-y-5">
          <div v-if="!selectedAccount" class="rounded-[12px] border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] text-amber-900">
            当前未选择账号，请先导入或切换到一个已解密账号后再导出。
          </div>

          <div v-if="globalError" class="rounded-[12px] border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-700 whitespace-pre-wrap">
            {{ globalError }}
          </div>

          <div v-if="globalMessage" class="rounded-[12px] border border-emerald-200 bg-emerald-50 px-4 py-3 text-[13px] text-emerald-700 whitespace-pre-wrap">
            {{ globalMessage }}
          </div>

          <div v-if="privacyMode" class="rounded-[12px] border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] text-amber-900">
            已开启隐私模式：聊天记录导出会隐藏会话/用户名/内容，且不会打包头像与多媒体文件。
          </div>

          <div class="rounded-[14px] border border-[#ececec] bg-[#fafafa] p-4">
            <div class="flex flex-wrap items-start gap-4">
              <div class="min-w-[180px] flex-1">
                <div class="text-[13px] font-medium text-[#222]">导出目录</div>
                <div class="mt-1 text-[12px] text-[#7a7a7a]">
                  桌面端会直接写入目标目录；浏览器端会在任务完成后自动保存到选中的浏览器目录。
                </div>
                <div class="mt-3 min-h-[44px] rounded-[10px] border border-[#e4e4e4] bg-white px-3 py-2 text-[12px] leading-5 text-[#555] break-all">
                  {{ exportFolder || '未选择' }}
                </div>
              </div>

              <div class="flex shrink-0 flex-wrap gap-2">
                <button
                  type="button"
                  class="rounded-[10px] border border-[#dcdcdc] bg-white px-3 py-2 text-[13px] text-[#333] transition hover:bg-[#f4f4f4] disabled:cursor-not-allowed disabled:opacity-50"
                  :disabled="running"
                  @click="chooseExportFolder"
                >
                  选择文件夹
                </button>
                <button
                  v-if="exportFolder"
                  type="button"
                  class="rounded-[10px] border border-[#dcdcdc] bg-white px-3 py-2 text-[13px] text-[#333] transition hover:bg-[#f4f4f4] disabled:cursor-not-allowed disabled:opacity-50"
                  :disabled="running"
                  @click="clearExportFolderSelection"
                >
                  清空
                </button>
              </div>
            </div>
          </div>

          <div v-if="sourceError" class="rounded-[12px] border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-700 whitespace-pre-wrap">
            {{ sourceError }}
          </div>

          <div v-if="loadingSources" class="rounded-[12px] border border-[#ececec] bg-[#fafafa] px-4 py-3 text-[13px] text-[#666]">
            正在加载导出数据源...
          </div>

          <section class="rounded-[14px] border border-[#ececec] bg-white p-4">
            <div class="flex items-start gap-3">
              <input v-model="moduleSelection.chat" type="checkbox" class="mt-1 h-4 w-4 rounded border-[#d0d0d0] text-[#07C160] focus:ring-[#07C160]" />
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-2">
                  <div class="text-[15px] font-semibold text-[#222]">聊天记录</div>
                  <div class="rounded-full bg-[#07C160]/10 px-2 py-0.5 text-[11px] text-[#07C160]">
                    支持 JSON / TXT / HTML
                  </div>
                </div>
                <div class="mt-1 text-[12px] text-[#7a7a7a]">
                  可按全部、群聊、单聊或自定义会话导出，并支持多选消息类型。
                </div>

                <div class="mt-4 space-y-4" :class="moduleSelection.chat ? '' : 'pointer-events-none select-none opacity-50'">
                  <div class="flex flex-wrap gap-4">
                    <div>
                      <div class="mb-2 text-[13px] font-medium text-[#333]">导出范围</div>
                      <div class="flex flex-wrap gap-2">
                        <button
                          type="button"
                          class="rounded-[999px] border px-3 py-1.5 text-[12px] transition"
                          :class="chatScope === 'all' ? 'border-[#07C160] bg-[#07C160] text-white' : 'border-[#e1e1e1] bg-white text-[#444] hover:bg-[#f7f7f7]'"
                          @click="setChatScope('all')"
                        >
                          全部 {{ chatSessionCounts.total }}
                        </button>
                        <button
                          type="button"
                          class="rounded-[999px] border px-3 py-1.5 text-[12px] transition"
                          :class="chatScope === 'groups' ? 'border-[#07C160] bg-[#07C160] text-white' : 'border-[#e1e1e1] bg-white text-[#444] hover:bg-[#f7f7f7]'"
                          @click="setChatScope('groups')"
                        >
                          群聊 {{ chatSessionCounts.groups }}
                        </button>
                        <button
                          type="button"
                          class="rounded-[999px] border px-3 py-1.5 text-[12px] transition"
                          :class="chatScope === 'singles' ? 'border-[#07C160] bg-[#07C160] text-white' : 'border-[#e1e1e1] bg-white text-[#444] hover:bg-[#f7f7f7]'"
                          @click="setChatScope('singles')"
                        >
                          单聊 {{ chatSessionCounts.singles }}
                        </button>
                        <button
                          type="button"
                          class="rounded-[999px] border px-3 py-1.5 text-[12px] transition"
                          :class="chatScope === 'custom' ? 'border-[#07C160] bg-[#07C160] text-white' : 'border-[#e1e1e1] bg-white text-[#444] hover:bg-[#f7f7f7]'"
                          @click="setChatScope('custom')"
                        >
                          自定义多选
                        </button>
                      </div>
                    </div>

                    <div>
                      <div class="mb-2 text-[13px] font-medium text-[#333]">导出格式</div>
                      <div class="flex flex-wrap gap-2">
                        <label
                          v-for="format in chatFormats"
                          :key="format.value"
                          class="cursor-pointer rounded-[999px] border px-3 py-1.5 text-[12px] transition"
                          :class="chatFormat === format.value ? 'border-[#07C160] bg-[#07C160] text-white' : 'border-[#e1e1e1] bg-white text-[#444] hover:bg-[#f7f7f7]'"
                        >
                          <input v-model="chatFormat" type="radio" class="hidden" :value="format.value" />
                          <span>{{ format.label }}</span>
                        </label>
                      </div>
                    </div>
                  </div>

                  <div class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
                    <div class="space-y-3">
                      <div class="text-[13px] font-medium text-[#333]">时间范围（可选）</div>
                      <div class="flex flex-wrap items-center gap-2">
                        <input
                          v-model="chatStartLocal"
                          type="datetime-local"
                          class="min-w-[220px] rounded-[10px] border border-[#e1e1e1] px-3 py-2 text-[13px] text-[#333] outline-none focus:border-[#07C160] focus:ring-2 focus:ring-[#07C160]/15"
                        />
                        <span class="text-[#999]">至</span>
                        <input
                          v-model="chatEndLocal"
                          type="datetime-local"
                          class="min-w-[220px] rounded-[10px] border border-[#e1e1e1] px-3 py-2 text-[13px] text-[#333] outline-none focus:border-[#07C160] focus:ring-2 focus:ring-[#07C160]/15"
                        />
                      </div>
                    </div>

                    <div class="space-y-2 rounded-[12px] border border-[#ededed] bg-[#fafafa] p-3">
                      <label class="flex items-center gap-2 text-[13px] text-[#333]">
                        <input v-model="chatIncludeOfficial" type="checkbox" class="h-4 w-4 rounded border-[#d0d0d0] text-[#07C160] focus:ring-[#07C160]" />
                        <span>包含公众号/官方账号会话</span>
                      </label>
                      <label class="flex items-center gap-2 text-[13px] text-[#333]">
                        <input v-model="chatIncludeHidden" type="checkbox" class="h-4 w-4 rounded border-[#d0d0d0] text-[#07C160] focus:ring-[#07C160]" />
                        <span>包含隐藏会话</span>
                      </label>
                    </div>
                  </div>

                  <div v-if="chatScope === 'custom'" class="rounded-[12px] border border-[#ececec] bg-[#fafafa] p-3">
                    <div class="flex flex-wrap items-center gap-2">
                      <input
                        v-model="chatSearchQuery"
                        type="text"
                        placeholder="搜索会话（名称 / username）"
                        class="min-w-[220px] flex-1 rounded-[10px] border border-[#e1e1e1] px-3 py-2 text-[13px] text-[#333] outline-none focus:border-[#07C160] focus:ring-2 focus:ring-[#07C160]/15"
                      />
                      <button
                        type="button"
                        class="rounded-[10px] border border-[#dcdcdc] bg-white px-3 py-2 text-[12px] text-[#333] transition hover:bg-[#f4f4f4]"
                        @click="selectAllChatFiltered"
                      >
                        全选筛选结果
                      </button>
                      <button
                        type="button"
                        class="rounded-[10px] border border-[#dcdcdc] bg-white px-3 py-2 text-[12px] text-[#333] transition hover:bg-[#f4f4f4]"
                        @click="clearChatSelection"
                      >
                        清空
                      </button>
                    </div>

                    <div class="mt-3 max-h-[240px] overflow-y-auto rounded-[10px] border border-[#e7e7e7] bg-white">
                      <label
                        v-for="item in chatFilteredSessions"
                        :key="item.username"
                        class="flex cursor-pointer items-center gap-3 border-b border-[#f1f1f1] px-3 py-2 transition hover:bg-[#f8f8f8]"
                        :class="isChatSelected(item.username) ? 'bg-[#07C160]/5' : ''"
                      >
                        <input v-model="chatSelectedUsernames" type="checkbox" :value="item.username" class="h-4 w-4 rounded border-[#d0d0d0] text-[#07C160] focus:ring-[#07C160]" />
                        <div class="h-9 w-9 overflow-hidden rounded-[10px] bg-[#e9e9e9]">
                          <img v-if="item.avatar" :src="item.avatar" :alt="item.name" class="h-full w-full object-cover" referrerpolicy="no-referrer" />
                          <div v-else class="flex h-full w-full items-center justify-center text-[12px] font-semibold text-[#666]">
                            {{ (item.name || item.username || '?').charAt(0) }}
                          </div>
                        </div>
                        <div class="min-w-0 flex-1">
                          <div class="truncate text-[13px] text-[#222]">
                            {{ item.name }}
                            <span v-if="item.isGroup" class="text-[11px] text-[#999]">（群）</span>
                          </div>
                          <div class="truncate text-[12px] text-[#8a8a8a]">{{ item.username }}</div>
                        </div>
                      </label>
                      <div v-if="chatFilteredSessions.length === 0" class="px-3 py-4 text-[12px] text-[#888]">没有匹配的会话</div>
                    </div>

                    <div class="mt-2 text-[12px] text-[#7a7a7a]">已选 {{ chatSelectedUsernames.length }} 个会话</div>
                  </div>

                  <div>
                    <div class="mb-2 text-[13px] font-medium text-[#333]">消息类型（可多选）</div>
                    <div class="grid gap-2 rounded-[12px] border border-[#ececec] bg-[#fafafa] p-3 sm:grid-cols-2 xl:grid-cols-4">
                      <label
                        v-for="item in chatMessageTypeOptions"
                        :key="item.value"
                        class="flex items-center gap-2 text-[13px] text-[#444]"
                      >
                        <input v-model="chatMessageTypes" type="checkbox" :value="item.value" class="h-4 w-4 rounded border-[#d0d0d0] text-[#07C160] focus:ring-[#07C160]" />
                        <span>{{ item.label }}</span>
                      </label>
                    </div>
                  </div>

                  <div v-if="chatFormat === 'html'" class="rounded-[12px] border border-[#ececec] bg-[#fafafa] p-3">
                    <div class="text-[13px] font-medium text-[#333]">HTML 选项</div>
                    <div class="mt-3 space-y-3">
                      <label class="flex items-start gap-2 text-[13px] text-[#444]">
                        <input
                          v-model="chatDownloadRemoteMedia"
                          type="checkbox"
                          class="mt-0.5 h-4 w-4 rounded border-[#d0d0d0] text-[#07C160] focus:ring-[#07C160]"
                          :disabled="privacyMode"
                        />
                        <span>允许联网下载链接 / 引用缩略图（隐私模式下自动忽略）</span>
                      </label>

                      <div class="flex flex-wrap items-center gap-2">
                        <span class="text-[13px] text-[#444]">每页消息数</span>
                        <input
                          v-model.number="chatHtmlPageSize"
                          type="number"
                          min="0"
                          step="100"
                          class="w-[140px] rounded-[10px] border border-[#e1e1e1] px-3 py-2 text-[13px] text-[#333] outline-none focus:border-[#07C160] focus:ring-2 focus:ring-[#07C160]/15"
                        />
                        <span class="text-[12px] text-[#888]">推荐 1000，0 表示单文件</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section class="rounded-[14px] border border-[#ececec] bg-white p-4">
            <div class="flex items-start gap-3">
              <input v-model="moduleSelection.sns" type="checkbox" class="mt-1 h-4 w-4 rounded border-[#d0d0d0] text-[#07C160] focus:ring-[#07C160]" />
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-2">
                  <div class="text-[15px] font-semibold text-[#222]">朋友圈</div>
                  <div class="rounded-full bg-[#576b95]/10 px-2 py-0.5 text-[11px] text-[#576b95]">
                    支持 HTML / JSON / TXT
                  </div>
                </div>
                <div class="mt-1 text-[12px] text-[#7a7a7a]">
                  可导出全部联系人朋友圈，或按联系人自定义多选。
                </div>

                <div class="mt-4 space-y-4" :class="moduleSelection.sns ? '' : 'pointer-events-none select-none opacity-50'">
                  <div class="flex flex-wrap gap-4">
                    <div>
                      <div class="mb-2 text-[13px] font-medium text-[#333]">导出范围</div>
                      <div class="flex flex-wrap gap-2">
                        <button
                          type="button"
                          class="rounded-[999px] border px-3 py-1.5 text-[12px] transition"
                          :class="snsScope === 'all' ? 'border-[#07C160] bg-[#07C160] text-white' : 'border-[#e1e1e1] bg-white text-[#444] hover:bg-[#f7f7f7]'"
                          @click="setSnsScope('all')"
                        >
                          全部 {{ snsUsers.length }}
                        </button>
                        <button
                          type="button"
                          class="rounded-[999px] border px-3 py-1.5 text-[12px] transition"
                          :class="snsScope === 'custom' ? 'border-[#07C160] bg-[#07C160] text-white' : 'border-[#e1e1e1] bg-white text-[#444] hover:bg-[#f7f7f7]'"
                          @click="setSnsScope('custom')"
                        >
                          自定义多选
                        </button>
                      </div>
                    </div>

                    <div>
                      <div class="mb-2 text-[13px] font-medium text-[#333]">导出格式</div>
                      <div class="flex flex-wrap gap-2">
                        <label
                          v-for="format in snsFormats"
                          :key="format.value"
                          class="cursor-pointer rounded-[999px] border px-3 py-1.5 text-[12px] transition"
                          :class="snsFormat === format.value ? 'border-[#07C160] bg-[#07C160] text-white' : 'border-[#e1e1e1] bg-white text-[#444] hover:bg-[#f7f7f7]'"
                        >
                          <input v-model="snsFormat" type="radio" class="hidden" :value="format.value" />
                          <span>{{ format.label }}</span>
                        </label>
                      </div>
                    </div>

                    <label class="flex items-center gap-2 rounded-[12px] border border-[#ececec] bg-[#fafafa] px-3 py-2 text-[13px] text-[#444]">
                      <input v-model="snsUseCache" type="checkbox" class="h-4 w-4 rounded border-[#d0d0d0] text-[#07C160] focus:ring-[#07C160]" />
                      <span>复用缓存</span>
                    </label>
                  </div>

                  <div v-if="snsScope === 'custom'" class="rounded-[12px] border border-[#ececec] bg-[#fafafa] p-3">
                    <div class="flex flex-wrap items-center gap-2">
                      <input
                        v-model="snsSearchQuery"
                        type="text"
                        placeholder="搜索朋友圈联系人"
                        class="min-w-[220px] flex-1 rounded-[10px] border border-[#e1e1e1] px-3 py-2 text-[13px] text-[#333] outline-none focus:border-[#07C160] focus:ring-2 focus:ring-[#07C160]/15"
                      />
                      <button
                        type="button"
                        class="rounded-[10px] border border-[#dcdcdc] bg-white px-3 py-2 text-[12px] text-[#333] transition hover:bg-[#f4f4f4]"
                        @click="selectAllSnsFiltered"
                      >
                        全选筛选结果
                      </button>
                      <button
                        type="button"
                        class="rounded-[10px] border border-[#dcdcdc] bg-white px-3 py-2 text-[12px] text-[#333] transition hover:bg-[#f4f4f4]"
                        @click="clearSnsSelection"
                      >
                        清空
                      </button>
                    </div>

                    <div class="mt-3 max-h-[240px] overflow-y-auto rounded-[10px] border border-[#e7e7e7] bg-white">
                      <label
                        v-for="item in snsFilteredUsers"
                        :key="item.username"
                        class="flex cursor-pointer items-center gap-3 border-b border-[#f1f1f1] px-3 py-2 transition hover:bg-[#f8f8f8]"
                        :class="isSnsSelected(item.username) ? 'bg-[#07C160]/5' : ''"
                      >
                        <input v-model="snsSelectedUsernames" type="checkbox" :value="item.username" class="h-4 w-4 rounded border-[#d0d0d0] text-[#07C160] focus:ring-[#07C160]" />
                        <div class="h-9 w-9 overflow-hidden rounded-[10px] bg-[#e9e9e9]">
                          <img v-if="item.avatar" :src="item.avatar" :alt="item.displayName" class="h-full w-full object-cover" referrerpolicy="no-referrer" />
                          <div v-else class="flex h-full w-full items-center justify-center text-[12px] font-semibold text-[#666]">
                            {{ (item.displayName || item.username || '?').charAt(0) }}
                          </div>
                        </div>
                        <div class="min-w-0 flex-1">
                          <div class="truncate text-[13px] text-[#222]">{{ item.displayName || item.username }}</div>
                          <div class="truncate text-[12px] text-[#8a8a8a]">{{ item.username }} · {{ item.postCount || 0 }} 条</div>
                        </div>
                      </label>
                      <div v-if="snsFilteredUsers.length === 0" class="px-3 py-4 text-[12px] text-[#888]">没有匹配的联系人</div>
                    </div>

                    <div class="mt-2 text-[12px] text-[#7a7a7a]">已选 {{ snsSelectedUsernames.length }} 个联系人</div>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section class="rounded-[14px] border border-[#ececec] bg-white p-4">
            <div class="flex items-start gap-3">
              <input v-model="moduleSelection.contacts" type="checkbox" class="mt-1 h-4 w-4 rounded border-[#d0d0d0] text-[#07C160] focus:ring-[#07C160]" />
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-2">
                  <div class="text-[15px] font-semibold text-[#222]">联系人</div>
                  <div class="rounded-full bg-[#0ea5e9]/10 px-2 py-0.5 text-[11px] text-[#0ea5e9]">
                    支持 JSON / CSV
                  </div>
                </div>
                <div class="mt-1 text-[12px] text-[#7a7a7a]">
                  可按联系人类型多选导出，也支持关键词过滤。
                </div>

                <div class="mt-4 space-y-4" :class="moduleSelection.contacts ? '' : 'pointer-events-none select-none opacity-50'">
                  <div class="flex flex-wrap gap-4">
                    <div>
                      <div class="mb-2 text-[13px] font-medium text-[#333]">导出格式</div>
                      <div class="flex flex-wrap gap-2">
                        <label
                          v-for="format in contactFormats"
                          :key="format.value"
                          class="cursor-pointer rounded-[999px] border px-3 py-1.5 text-[12px] transition"
                          :class="contactsFormat === format.value ? 'border-[#07C160] bg-[#07C160] text-white' : 'border-[#e1e1e1] bg-white text-[#444] hover:bg-[#f7f7f7]'"
                        >
                          <input v-model="contactsFormat" type="radio" class="hidden" :value="format.value" />
                          <span>{{ format.label }}</span>
                        </label>
                      </div>
                    </div>

                    <label class="flex items-center gap-2 rounded-[12px] border border-[#ececec] bg-[#fafafa] px-3 py-2 text-[13px] text-[#444]">
                      <input v-model="contactsIncludeAvatarLink" type="checkbox" class="h-4 w-4 rounded border-[#d0d0d0] text-[#07C160] focus:ring-[#07C160]" />
                      <span>包含头像链接</span>
                    </label>
                  </div>

                  <div class="grid gap-4 md:grid-cols-[minmax(0,1fr)_320px]">
                    <div>
                      <div class="mb-2 text-[13px] font-medium text-[#333]">关键词过滤（可选）</div>
                      <input
                        v-model="contactsKeyword"
                        type="text"
                        placeholder="例如：备注名、昵称、username"
                        class="w-full rounded-[10px] border border-[#e1e1e1] px-3 py-2 text-[13px] text-[#333] outline-none focus:border-[#07C160] focus:ring-2 focus:ring-[#07C160]/15"
                      />
                    </div>

                    <div class="rounded-[12px] border border-[#ececec] bg-[#fafafa] p-3">
                      <div class="mb-2 text-[13px] font-medium text-[#333]">联系人类型（可多选）</div>
                      <div class="space-y-2">
                        <label class="flex items-center gap-2 text-[13px] text-[#444]">
                          <input v-model="contactTypes.friends" type="checkbox" class="h-4 w-4 rounded border-[#d0d0d0] text-[#07C160] focus:ring-[#07C160]" />
                          <span>好友</span>
                        </label>
                        <label class="flex items-center gap-2 text-[13px] text-[#444]">
                          <input v-model="contactTypes.groups" type="checkbox" class="h-4 w-4 rounded border-[#d0d0d0] text-[#07C160] focus:ring-[#07C160]" />
                          <span>群聊</span>
                        </label>
                        <label class="flex items-center gap-2 text-[13px] text-[#444]">
                          <input v-model="contactTypes.officials" type="checkbox" class="h-4 w-4 rounded border-[#d0d0d0] text-[#07C160] focus:ring-[#07C160]" />
                          <span>公众号</span>
                        </label>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section v-if="taskRuns.length > 0" class="rounded-[14px] border border-[#ececec] bg-white p-4">
            <div class="text-[15px] font-semibold text-[#222]">导出进度</div>
            <div class="mt-3 space-y-3">
              <div v-for="task in taskRuns" :key="task.key" class="rounded-[12px] border border-[#ececec] bg-[#fafafa] p-3">
                <div class="flex flex-wrap items-center gap-2">
                  <div class="text-[14px] font-medium text-[#222]">{{ task.label }}</div>
                  <span class="rounded-full px-2 py-0.5 text-[11px]" :class="taskStatusClass(task.status)">
                    {{ taskStatusLabel(task.status) }}
                  </span>
                </div>

                <div v-if="task.percent != null" class="mt-3">
                  <div class="flex items-center justify-between text-[12px] text-[#666]">
                    <span>{{ task.detail || task.message || '处理中...' }}</span>
                    <span>{{ task.percent }}%</span>
                  </div>
                  <div class="mt-1 h-2 overflow-hidden rounded-full bg-white">
                    <div class="h-full rounded-full bg-[#07C160] transition-all duration-300" :style="{ width: `${task.percent}%` }"></div>
                  </div>
                </div>

                <div v-else-if="task.detail || task.message" class="mt-2 text-[12px] text-[#666] whitespace-pre-wrap">
                  {{ task.detail || task.message }}
                </div>

                <div v-if="task.backendPath" class="mt-2 text-[12px] text-[#666] break-all">
                  <span class="font-medium text-[#333]">后端产物：</span>{{ task.backendPath }}
                </div>
                <div v-if="task.outputPath" class="mt-1 text-[12px] text-[#666] break-all">
                  <span class="font-medium text-[#333]">最终位置：</span>{{ task.outputPath }}
                </div>
                <div v-if="task.error" class="mt-2 text-[12px] text-red-600 whitespace-pre-wrap">
                  {{ task.error }}
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>

      <div class="flex items-center justify-end gap-2 border-t border-[#efefef] px-5 py-4">
        <button
          type="button"
          class="rounded-[10px] border border-[#dcdcdc] bg-white px-4 py-2 text-[13px] text-[#333] transition hover:bg-[#f4f4f4] disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="running"
          @click="requestClose"
        >
          关闭
        </button>
        <button
          type="button"
          class="rounded-[10px] bg-[#07C160] px-4 py-2 text-[13px] font-medium text-white transition hover:bg-[#06ad56] disabled:cursor-not-allowed disabled:opacity-60"
          :disabled="!canStartExport"
          @click="startBatchExport"
        >
          {{ running ? '导出中...' : '开始批量导出' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useChatAccountsStore } from '~/stores/chatAccounts'
import { usePrivacyStore } from '~/stores/privacy'
import { toUnixSeconds } from '~/lib/chat/formatters'

const props = defineProps({
  open: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['close'])

const api = useApi()
const apiBase = useApiBase()

const chatAccounts = useChatAccountsStore()
const { selectedAccount } = storeToRefs(chatAccounts)

const privacyStore = usePrivacyStore()
const { privacyMode } = storeToRefs(privacyStore)

const loadingSources = ref(false)
const sourceError = ref('')
const globalError = ref('')
const globalMessage = ref('')
const running = ref(false)

const exportFolder = ref('')
const exportFolderHandle = ref(null)

const moduleSelection = reactive({
  chat: true,
  sns: true,
  contacts: true
})

const chatFormats = [
  { value: 'json', label: 'JSON' },
  { value: 'txt', label: 'TXT' },
  { value: 'html', label: 'HTML' }
]

const snsFormats = [
  { value: 'html', label: 'HTML' },
  { value: 'json', label: 'JSON' },
  { value: 'txt', label: 'TXT' }
]

const contactFormats = [
  { value: 'json', label: 'JSON' },
  { value: 'csv', label: 'CSV' }
]

const chatMessageTypeOptions = [
  { value: 'text', label: '文本' },
  { value: 'image', label: '图片' },
  { value: 'emoji', label: '表情' },
  { value: 'video', label: '视频' },
  { value: 'voice', label: '语音' },
  { value: 'chatHistory', label: '聊天记录' },
  { value: 'transfer', label: '转账' },
  { value: 'redPacket', label: '红包' },
  { value: 'file', label: '文件' },
  { value: 'link', label: '链接' },
  { value: 'quote', label: '引用' },
  { value: 'system', label: '系统' },
  { value: 'voip', label: '通话' }
]

const chatScope = ref('all')
const chatFormat = ref('json')
const chatIncludeOfficial = ref(true)
const chatIncludeHidden = ref(false)
const chatDownloadRemoteMedia = ref(true)
const chatHtmlPageSize = ref(1000)
const chatStartLocal = ref('')
const chatEndLocal = ref('')
const chatSearchQuery = ref('')
const chatSelectedUsernames = ref([])
const chatMessageTypes = ref(chatMessageTypeOptions.map((item) => item.value))
const chatSessions = ref([])

const snsFormat = ref('html')
const snsScope = ref('all')
const snsUseCache = ref(true)
const snsSearchQuery = ref('')
const snsSelectedUsernames = ref([])
const snsUsers = ref([])

const contactsFormat = ref('json')
const contactsIncludeAvatarLink = ref(true)
const contactsKeyword = ref('')
const contactTypes = reactive({
  friends: true,
  groups: true,
  officials: true
})

const taskRuns = ref([])

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

const asNumber = (value) => {
  const next = Number(value)
  return Number.isFinite(next) ? next : 0
}

const clamp01 = (value) => Math.min(1, Math.max(0, value))

const formatBytes = (value) => {
  const bytes = Number(value)
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = bytes
  let index = 0
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index += 1
  }
  const digits = size >= 100 || index === 0 ? 0 : size >= 10 ? 1 : 2
  return `${size.toFixed(digits)} ${units[index]}`
}

const buildExportTimestamp = () => {
  const now = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
}

const sanitizeFileNamePart = (value, fallback = 'export') => {
  const cleaned = String(value || '')
    .trim()
    .replace(/[^0-9A-Za-z._-]+/g, '_')
    .replace(/^[._-]+|[._-]+$/g, '')
  return cleaned || fallback
}

const normalizeUniqueUsernames = (list) => {
  const seen = new Set()
  return (Array.isArray(list) ? list : []).reduce((acc, item) => {
    const username = String(item || '').trim()
    if (!username || seen.has(username)) return acc
    seen.add(username)
    acc.push(username)
    return acc
  }, [])
}

const isDesktopExportRuntime = () => {
  return !!(process.client && typeof window !== 'undefined' && window?.wechatDesktop?.chooseDirectory)
}

const isWebDirectoryPickerSupported = () => {
  return !!(process.client && typeof window !== 'undefined' && typeof window.showDirectoryPicker === 'function')
}

const hasExportTarget = computed(() => {
  return isDesktopExportRuntime()
    ? !!String(exportFolder.value || '').trim()
    : !!exportFolderHandle.value
})

const activeModuleCount = computed(() => {
  return ['chat', 'sns', 'contacts'].filter((key) => !!moduleSelection[key]).length
})

const canStartExport = computed(() => {
  if (running.value) return false
  if (!selectedAccount.value) return false
  if (!hasExportTarget.value) return false
  return activeModuleCount.value > 0
})

const normalizeChatSession = (session) => {
  return {
    id: session?.id || session?.username || '',
    username: String(session?.username || '').trim(),
    name: String(session?.name || session?.username || '').trim(),
    avatar: String(session?.avatar || '').trim(),
    isGroup: !!session?.isGroup
  }
}

const chatFilteredSessions = computed(() => {
  const query = String(chatSearchQuery.value || '').trim().toLowerCase()
  if (!query) return chatSessions.value
  return chatSessions.value.filter((item) => {
    const name = String(item?.name || '').toLowerCase()
    const username = String(item?.username || '').toLowerCase()
    return name.includes(query) || username.includes(query)
  })
})

const chatSessionCounts = computed(() => {
  const total = chatSessions.value.length
  const groups = chatSessions.value.filter((item) => !!item?.isGroup).length
  return {
    total,
    groups,
    singles: total - groups
  }
})

const snsFilteredUsers = computed(() => {
  const query = String(snsSearchQuery.value || '').trim().toLowerCase()
  if (!query) return snsUsers.value
  return snsUsers.value.filter((item) => {
    const name = String(item?.displayName || '').toLowerCase()
    const username = String(item?.username || '').toLowerCase()
    return name.includes(query) || username.includes(query)
  })
})

const ensureAccountReady = async () => {
  privacyStore.init()
  await chatAccounts.ensureLoaded()
}

const loadChatSessions = async () => {
  const account = String(selectedAccount.value || '').trim()
  if (!account) {
    chatSessions.value = []
    return
  }
  const response = await api.listChatSessions({
    account,
    limit: 5000,
    include_hidden: true,
    include_official: true
  })
  const sessions = Array.isArray(response?.sessions) ? response.sessions : []
  chatSessions.value = sessions
    .map(normalizeChatSession)
    .filter((item) => !!item.username)
}

const loadSnsUsers = async () => {
  const account = String(selectedAccount.value || '').trim()
  if (!account) {
    snsUsers.value = []
    return
  }
  const response = await api.listSnsUsers({ account, limit: 5000 })
  const items = Array.isArray(response?.items) ? response.items : []
  snsUsers.value = items
    .map((item) => ({
      username: String(item?.username || '').trim(),
      displayName: String(item?.displayName || item?.username || '').trim(),
      avatar: String(item?.avatar || '').trim(),
      postCount: asNumber(item?.postCount)
    }))
    .filter((item) => !!item.username)
}

const ensureSourcesLoaded = async () => {
  if (!selectedAccount.value) {
    chatSessions.value = []
    snsUsers.value = []
    return
  }
  loadingSources.value = true
  sourceError.value = ''
  try {
    await Promise.all([loadChatSessions(), loadSnsUsers()])
  } catch (error) {
    sourceError.value = error?.message || '加载导出数据源失败'
  } finally {
    loadingSources.value = false
  }
}

const setChatScope = (scope) => {
  chatScope.value = String(scope || 'all')
  if (chatScope.value === 'custom' && chatSelectedUsernames.value.length === 0) {
    chatSelectedUsernames.value = chatFilteredSessions.value.map((item) => item.username)
  }
}

const setSnsScope = (scope) => {
  snsScope.value = String(scope || 'all')
  if (snsScope.value === 'custom' && snsSelectedUsernames.value.length === 0) {
    snsSelectedUsernames.value = snsFilteredUsers.value.map((item) => item.username)
  }
}

const isChatSelected = (username) => {
  return normalizeUniqueUsernames(chatSelectedUsernames.value).includes(String(username || '').trim())
}

const isSnsSelected = (username) => {
  return normalizeUniqueUsernames(snsSelectedUsernames.value).includes(String(username || '').trim())
}

const selectAllChatFiltered = () => {
  const merged = [
    ...normalizeUniqueUsernames(chatSelectedUsernames.value),
    ...chatFilteredSessions.value.map((item) => item.username)
  ]
  chatSelectedUsernames.value = normalizeUniqueUsernames(merged)
}

const clearChatSelection = () => {
  chatSelectedUsernames.value = []
}

const selectAllSnsFiltered = () => {
  const merged = [
    ...normalizeUniqueUsernames(snsSelectedUsernames.value),
    ...snsFilteredUsers.value.map((item) => item.username)
  ]
  snsSelectedUsernames.value = normalizeUniqueUsernames(merged)
}

const clearSnsSelection = () => {
  snsSelectedUsernames.value = []
}

const chooseExportFolder = async () => {
  globalError.value = ''
  globalMessage.value = ''
  try {
    if (!process.client) {
      globalError.value = '当前环境不支持选择导出目录'
      return
    }

    if (isDesktopExportRuntime()) {
      const result = await window.wechatDesktop.chooseDirectory({ title: '选择导出目录' })
      if (result && !result.canceled && Array.isArray(result.filePaths) && result.filePaths.length > 0) {
        exportFolder.value = String(result.filePaths[0] || '').trim()
        exportFolderHandle.value = null
      }
      return
    }

    if (isWebDirectoryPickerSupported()) {
      const handle = await window.showDirectoryPicker()
      if (handle) {
        exportFolderHandle.value = handle
        exportFolder.value = `浏览器目录：${String(handle.name || '已选择')}`
      }
      return
    }

    globalError.value = '当前浏览器不支持目录选择，请使用桌面端或 Chromium 新版浏览器'
  } catch (error) {
    const message = String(error?.message || '').trim()
    if (error?.name === 'AbortError' || message.includes('The user aborted a request')) {
      return
    }
    globalError.value = error?.message || '选择导出目录失败'
  }
}

const clearExportFolderSelection = () => {
  exportFolder.value = ''
  exportFolderHandle.value = null
}

const taskStatusLabel = (status) => {
  if (status === 'running') return '进行中'
  if (status === 'done') return '已完成'
  if (status === 'error') return '失败'
  return '等待中'
}

const taskStatusClass = (status) => {
  if (status === 'running') return 'bg-sky-100 text-sky-700'
  if (status === 'done') return 'bg-emerald-100 text-emerald-700'
  if (status === 'error') return 'bg-red-100 text-red-700'
  return 'bg-gray-100 text-gray-600'
}

const createTask = (key, label) => ({
  key,
  label,
  status: 'pending',
  message: '',
  detail: '',
  percent: null,
  error: '',
  backendPath: '',
  outputPath: ''
})

const guessZipFileName = (job, fallback) => {
  const raw = String(job?.zipPath || '').trim()
  if (raw) {
    const name = raw.replace(/\\/g, '/').split('/').pop()
    if (name) return name
  }
  return fallback
}

const buildBrowserOutputLabel = (fileName) => {
  const folderLabel = String(exportFolder.value || '浏览器目录').trim()
  return `${folderLabel}/${fileName}`
}

const saveResponseToBrowserFolder = async ({ response, fileName, task }) => {
  if (!exportFolderHandle.value || typeof exportFolderHandle.value.getFileHandle !== 'function') {
    throw new Error('请先选择浏览器导出目录')
  }

  const safeName = sanitizeFileNamePart(fileName, 'export')
  const fileHandle = await exportFolderHandle.value.getFileHandle(safeName, { create: true })
  const writable = await fileHandle.createWritable()

  const totalBytes = asNumber(response.headers.get('Content-Length'))
  let writtenBytes = 0

  if (response.body && typeof response.body.getReader === 'function') {
    const reader = response.body.getReader()
    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        if (!value || !value.byteLength) continue
        await writable.write(value)
        writtenBytes += value.byteLength
        task.detail = totalBytes > 0
          ? `正在保存到浏览器目录：${formatBytes(writtenBytes)} / ${formatBytes(totalBytes)}`
          : `正在保存到浏览器目录：${formatBytes(writtenBytes)}`
      }
      await writable.close()
    } catch (error) {
      try {
        await reader.cancel()
      } catch {}
      try {
        await writable.abort()
      } catch {}
      throw error
    }
  } else {
    const blob = await response.blob()
    writtenBytes = asNumber(blob.size)
    task.detail = `正在保存到浏览器目录：${formatBytes(writtenBytes)}`
    await writable.write(blob)
    await writable.close()
  }

  return buildBrowserOutputLabel(safeName)
}

const downloadJobToBrowserFolder = async ({ url, fileName, task }) => {
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`下载导出文件失败（${response.status}）`)
  }
  return await saveResponseToBrowserFolder({ response, fileName, task })
}

const computeChatPercent = (job) => {
  const progress = job?.progress || {}
  const total = asNumber(progress.conversationsTotal)
  const done = asNumber(progress.conversationsDone)
  if (total <= 0) return null
  const currentTotal = asNumber(progress.currentConversationMessagesTotal)
  const currentDone = asNumber(progress.currentConversationMessagesExported)
  const currentFraction = currentTotal > 0 ? clamp01(currentDone / currentTotal) : 0
  const percent = clamp01((done + (String(job?.status || '') === 'running' ? currentFraction : 0)) / total)
  return Math.round(percent * 100)
}

const updateChatTaskFromJob = (task, job) => {
  const progress = job?.progress || {}
  task.percent = computeChatPercent(job)
  const convDone = asNumber(progress.conversationsDone)
  const convTotal = asNumber(progress.conversationsTotal)
  const msgDone = asNumber(progress.messagesExported)
  const mediaCopied = asNumber(progress.mediaCopied)
  const mediaMissing = asNumber(progress.mediaMissing)
  const currentName = String(progress.currentConversationName || progress.currentConversationUsername || '').trim()
  const currentDone = asNumber(progress.currentConversationMessagesExported)
  const currentTotal = asNumber(progress.currentConversationMessagesTotal)
  task.detail = `会话 ${convDone}/${convTotal} · 消息 ${msgDone} · 媒体 ${mediaCopied} · 缺失 ${mediaMissing}`
  if (currentName && String(job?.status || '') === 'running') {
    task.message = `当前：${currentName}（${currentDone}/${currentTotal}）`
  }
  task.backendPath = String(job?.zipPath || '').trim()
}

const computeSnsPercent = (job) => {
  const progress = job?.progress || {}
  const totalUsers = asNumber(progress.usersTotal)
  const doneUsers = asNumber(progress.usersDone)
  if (totalUsers <= 0) return null
  const currentTotal = asNumber(progress.currentUserPostsTotal)
  const currentDone = asNumber(progress.currentUserPostsDone)
  const currentFraction = currentTotal > 0 ? clamp01(currentDone / currentTotal) : 0
  const percent = clamp01((doneUsers + (String(job?.status || '') === 'running' ? currentFraction : 0)) / totalUsers)
  return Math.round(percent * 100)
}

const updateSnsTaskFromJob = (task, job) => {
  const progress = job?.progress || {}
  task.percent = computeSnsPercent(job)
  const usersDone = asNumber(progress.usersDone)
  const usersTotal = asNumber(progress.usersTotal)
  const postsDone = asNumber(progress.postsExported)
  const postsTotal = asNumber(progress.postsTotal)
  const mediaCopied = asNumber(progress.mediaCopied)
  const mediaMissing = asNumber(progress.mediaMissing)
  const currentName = String(progress.currentUserDisplayName || progress.currentUserUsername || '').trim()
  const currentDone = asNumber(progress.currentUserPostsDone)
  const currentTotal = asNumber(progress.currentUserPostsTotal)
  task.detail = `联系人 ${usersDone}/${usersTotal} · 朋友圈 ${postsDone}/${postsTotal} · 媒体 ${mediaCopied} · 缺失 ${mediaMissing}`
  if (currentName && String(job?.status || '') === 'running') {
    task.message = `当前：${currentName}（${currentDone}/${currentTotal}）`
  }
  task.backendPath = String(job?.zipPath || '').trim()
}

const waitForJobDone = async ({ exportId, task, getter, updater, kind }) => {
  let continuousFailures = 0
  while (true) {
    try {
      const response = await getter(exportId)
      const job = response?.job || null
      if (!job) throw new Error('导出任务不存在')
      continuousFailures = 0
      updater(task, job)
      const status = String(job?.status || '').trim()
      if (status === 'done') return job
      if (status === 'cancelled') throw new Error('导出任务已取消')
      if (status === 'error') throw new Error(job?.error || `${kind}导出失败`)
    } catch (error) {
      continuousFailures += 1
      if (continuousFailures >= 5) {
        throw error
      }
      task.detail = `轮询状态失败，正在重试（${continuousFailures}/5）`
    }
    await sleep(1200)
  }
}

const buildChatMediaKinds = (messageTypes) => {
  const selectedTypeSet = new Set(messageTypes.map((item) => String(item || '').trim()))
  const mediaKindSet = new Set()
  if (selectedTypeSet.has('chatHistory')) {
    mediaKindSet.add('image')
    mediaKindSet.add('emoji')
    mediaKindSet.add('video')
    mediaKindSet.add('video_thumb')
    mediaKindSet.add('voice')
    mediaKindSet.add('file')
  }
  if (selectedTypeSet.has('image')) mediaKindSet.add('image')
  if (selectedTypeSet.has('emoji')) mediaKindSet.add('emoji')
  if (selectedTypeSet.has('video')) {
    mediaKindSet.add('video')
    mediaKindSet.add('video_thumb')
  }
  if (selectedTypeSet.has('voice')) mediaKindSet.add('voice')
  if (selectedTypeSet.has('file')) mediaKindSet.add('file')
  return Array.from(mediaKindSet)
}

const runChatExport = async (task, stamp) => {
  task.status = 'running'
  task.message = '正在创建聊天导出任务...'
  task.detail = ''
  task.error = ''

  const messageTypes = normalizeUniqueUsernames(chatMessageTypes.value)
  const mediaKinds = buildChatMediaKinds(messageTypes)
  const includeMedia = !privacyMode.value && mediaKinds.length > 0
  const startTime = toUnixSeconds(chatStartLocal.value)
  const endTime = toUnixSeconds(chatEndLocal.value)

  let scope = String(chatScope.value || 'all')
  let usernames = []
  if (scope === 'custom') {
    scope = 'selected'
    usernames = normalizeUniqueUsernames(chatSelectedUsernames.value)
  }

  const response = await api.createChatExport({
    account: selectedAccount.value,
    scope,
    usernames,
    format: chatFormat.value,
    start_time: startTime,
    end_time: endTime,
    include_hidden: !!chatIncludeHidden.value,
    include_official: !!chatIncludeOfficial.value,
    message_types: messageTypes,
    include_media: includeMedia,
    media_kinds: mediaKinds,
    download_remote_media: chatFormat.value === 'html' && !privacyMode.value && !!chatDownloadRemoteMedia.value,
    html_page_size: Math.max(0, Math.floor(Number(chatHtmlPageSize.value || 1000))),
    output_dir: isDesktopExportRuntime() ? String(exportFolder.value || '').trim() : null,
    privacy_mode: !!privacyMode.value,
    file_name: isDesktopExportRuntime() ? null : `wechat_chat_export_${stamp}.zip`
  })

  const exportId = String(response?.job?.exportId || '').trim()
  if (!exportId) throw new Error('聊天导出任务创建失败')

  const job = await waitForJobDone({
    exportId,
    task,
    getter: api.getChatExport,
    updater: updateChatTaskFromJob,
    kind: '聊天记录'
  })

  task.percent = 100
  task.backendPath = String(job?.zipPath || '').trim()

  if (isDesktopExportRuntime()) {
    task.outputPath = task.backendPath
    task.detail = `导出完成，共 ${asNumber(job?.progress?.messagesExported)} 条消息`
    return
  }

  const fileName = guessZipFileName(job, `wechat_chat_export_${stamp}.zip`)
  task.message = '正在保存到浏览器目录...'
  task.outputPath = await downloadJobToBrowserFolder({
    url: `${apiBase}/chat/exports/${encodeURIComponent(exportId)}/download`,
    fileName,
    task
  })
  task.detail = `浏览器目录保存完成，共 ${asNumber(job?.progress?.messagesExported)} 条消息`
}

const runSnsExport = async (task, stamp) => {
  task.status = 'running'
  task.message = '正在创建朋友圈导出任务...'
  task.detail = ''
  task.error = ''

  let scope = String(snsScope.value || 'all')
  let usernames = []
  if (scope === 'custom') {
    scope = 'selected'
    usernames = normalizeUniqueUsernames(snsSelectedUsernames.value)
  }

  const response = await api.createSnsExport({
    account: selectedAccount.value,
    scope,
    usernames,
    format: snsFormat.value,
    use_cache: !!snsUseCache.value,
    output_dir: isDesktopExportRuntime() ? String(exportFolder.value || '').trim() : null,
    file_name: isDesktopExportRuntime() ? null : `wechat_sns_export_${stamp}.zip`
  })

  const exportId = String(response?.job?.exportId || '').trim()
  if (!exportId) throw new Error('朋友圈导出任务创建失败')

  const job = await waitForJobDone({
    exportId,
    task,
    getter: api.getSnsExport,
    updater: updateSnsTaskFromJob,
    kind: '朋友圈'
  })

  task.percent = 100
  task.backendPath = String(job?.zipPath || '').trim()

  if (isDesktopExportRuntime()) {
    task.outputPath = task.backendPath
    task.detail = `导出完成，共 ${asNumber(job?.progress?.postsExported)} 条朋友圈`
    return
  }

  const fileName = guessZipFileName(job, `wechat_sns_export_${stamp}.zip`)
  task.message = '正在保存到浏览器目录...'
  task.outputPath = await downloadJobToBrowserFolder({
    url: `${apiBase}/sns/exports/${encodeURIComponent(exportId)}/download`,
    fileName,
    task
  })
  task.detail = `浏览器目录保存完成，共 ${asNumber(job?.progress?.postsExported)} 条朋友圈`
}

const escapeCsvCell = (value) => {
  const text = String(value == null ? '' : value)
  if (/[",\n\r]/.test(text)) return `"${text.replace(/"/g, '""')}"`
  return text
}

const buildContactsWebPayload = async () => {
  const response = await api.listChatContacts({
    account: selectedAccount.value,
    keyword: contactsKeyword.value || '',
    include_friends: contactTypes.friends,
    include_groups: contactTypes.groups,
    include_officials: contactTypes.officials
  })

  const contacts = Array.isArray(response?.contacts) ? response.contacts : []
  const rows = contacts.map((item) => {
    const row = {
      username: String(item?.username || ''),
      displayName: String(item?.displayName || ''),
      remark: String(item?.remark || ''),
      nickname: String(item?.nickname || ''),
      alias: String(item?.alias || ''),
      type: String(item?.type || ''),
      region: String(item?.region || ''),
      country: String(item?.country || ''),
      province: String(item?.province || ''),
      city: String(item?.city || ''),
      source: String(item?.source || ''),
      sourceScene: item?.sourceScene == null ? '' : String(item?.sourceScene)
    }
    if (contactsIncludeAvatarLink.value) {
      row.avatarLink = String(item?.avatarLink || '')
    }
    return row
  })

  return {
    account: String(selectedAccount.value || '').trim(),
    count: rows.length,
    contacts: rows
  }
}

const writeTextFileToBrowserFolder = async ({ fileName, content, task }) => {
  if (!exportFolderHandle.value || typeof exportFolderHandle.value.getFileHandle !== 'function') {
    throw new Error('请先选择浏览器导出目录')
  }
  const safeName = sanitizeFileNamePart(fileName, 'contacts')
  task.detail = '正在保存到浏览器目录...'
  const fileHandle = await exportFolderHandle.value.getFileHandle(safeName, { create: true })
  const writable = await fileHandle.createWritable()
  await writable.write(content)
  await writable.close()
  return buildBrowserOutputLabel(safeName)
}

const runContactsExport = async (task, stamp) => {
  task.status = 'running'
  task.message = '正在导出联系人...'
  task.detail = ''
  task.error = ''
  task.percent = null

  if (isDesktopExportRuntime()) {
    const response = await api.exportChatContacts({
      account: selectedAccount.value,
      output_dir: String(exportFolder.value || '').trim(),
      format: contactsFormat.value,
      include_avatar_link: contactsIncludeAvatarLink.value,
      keyword: contactsKeyword.value || '',
      contact_types: {
        friends: contactTypes.friends,
        groups: contactTypes.groups,
        officials: contactTypes.officials
      }
    })
    task.outputPath = String(response?.outputPath || '').trim()
    task.detail = `导出完成，共 ${asNumber(response?.count)} 个联系人`
    return
  }

  const payload = await buildContactsWebPayload()
  const extension = contactsFormat.value === 'csv' ? 'csv' : 'json'
  const fileName = `contacts_${sanitizeFileNamePart(payload.account, 'account')}_${stamp}.${extension}`

  if (contactsFormat.value === 'csv') {
    const columns = [
      ['username', '用户名'],
      ['displayName', '显示名称'],
      ['remark', '备注'],
      ['nickname', '昵称'],
      ['alias', '微信号'],
      ['type', '类型'],
      ['region', '地区'],
      ['country', '国家/地区码'],
      ['province', '省份'],
      ['city', '城市'],
      ['source', '来源'],
      ['sourceScene', '来源场景码']
    ]
    if (contactsIncludeAvatarLink.value) {
      columns.push(['avatarLink', '头像链接'])
    }
    const lines = [columns.map(([, label]) => escapeCsvCell(label)).join(',')]
    for (const row of payload.contacts) {
      lines.push(columns.map(([key]) => escapeCsvCell(row[key])).join(','))
    }
    task.outputPath = await writeTextFileToBrowserFolder({
      fileName,
      content: `\uFEFF${lines.join('\n')}`,
      task
    })
  } else {
    const jsonPayload = {
      exportedAt: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'),
      account: payload.account,
      count: payload.count,
      filters: {
        keyword: String(contactsKeyword.value || ''),
        contactTypes: {
          friends: !!contactTypes.friends,
          groups: !!contactTypes.groups,
          officials: !!contactTypes.officials
        },
        includeAvatarLink: !!contactsIncludeAvatarLink.value
      },
      contacts: payload.contacts
    }
    task.outputPath = await writeTextFileToBrowserFolder({
      fileName,
      content: JSON.stringify(jsonPayload, null, 2),
      task
    })
  }

  task.detail = `浏览器目录保存完成，共 ${payload.count} 个联系人`
}

const validateSelections = () => {
  const errors = []

  if (!selectedAccount.value) {
    errors.push('未选择账号')
  }
  if (!hasExportTarget.value) {
    errors.push('请先选择导出目录')
  }
  if (activeModuleCount.value <= 0) {
    errors.push('请至少勾选一个导出模块')
  }

  const startTime = toUnixSeconds(chatStartLocal.value)
  const endTime = toUnixSeconds(chatEndLocal.value)
  if (moduleSelection.chat && startTime && endTime && startTime > endTime) {
    errors.push('聊天记录时间范围不合法：开始时间不能晚于结束时间')
  }

  if (moduleSelection.chat && normalizeUniqueUsernames(chatMessageTypes.value).length <= 0) {
    errors.push('聊天记录至少勾选一个消息类型')
  }

  if (moduleSelection.chat && chatScope.value === 'custom' && normalizeUniqueUsernames(chatSelectedUsernames.value).length <= 0) {
    errors.push('聊天记录已选择自定义会话，请至少勾选一个会话')
  }

  if (moduleSelection.sns && snsScope.value === 'custom' && normalizeUniqueUsernames(snsSelectedUsernames.value).length <= 0) {
    errors.push('朋友圈已选择自定义联系人，请至少勾选一个联系人')
  }

  if (moduleSelection.contacts && !contactTypes.friends && !contactTypes.groups && !contactTypes.officials) {
    errors.push('联系人导出至少勾选一种联系人类型')
  }

  return errors
}

const startBatchExport = async () => {
  globalError.value = ''
  globalMessage.value = ''

  const errors = validateSelections()
  if (errors.length > 0) {
    globalError.value = errors.join('\n')
    return
  }

  const queue = []
  if (moduleSelection.chat) queue.push(createTask('chat', '聊天记录'))
  if (moduleSelection.sns) queue.push(createTask('sns', '朋友圈'))
  if (moduleSelection.contacts) queue.push(createTask('contacts', '联系人'))

  taskRuns.value = queue
  running.value = true

  const stamp = buildExportTimestamp()

  try {
    for (const task of taskRuns.value) {
      try {
        if (task.key === 'chat') {
          await runChatExport(task, stamp)
        } else if (task.key === 'sns') {
          await runSnsExport(task, stamp)
        } else if (task.key === 'contacts') {
          await runContactsExport(task, stamp)
        }
        task.status = 'done'
        task.error = ''
      } catch (error) {
        task.status = 'error'
        task.percent = null
        task.error = error?.message || '导出失败'
      }
    }

    const successCount = taskRuns.value.filter((item) => item.status === 'done').length
    const failedCount = taskRuns.value.filter((item) => item.status === 'error').length
    globalMessage.value = `批量导出已结束：成功 ${successCount} 项，失败 ${failedCount} 项。`
    if (failedCount > 0) {
      globalError.value = '部分导出任务失败，请查看下方任务详情。'
    }
  } finally {
    running.value = false
  }
}

const requestClose = () => {
  if (running.value) return
  emit('close')
}

const onWindowKeydown = (event) => {
  if (event?.key !== 'Escape') return
  if (!props.open || running.value) return
  event.preventDefault()
  requestClose()
}

watch(
  () => props.open,
  async (open) => {
    if (!open) return
    globalError.value = ''
    globalMessage.value = ''
    await ensureAccountReady()
    await ensureSourcesLoaded()
  }
)

watch(selectedAccount, async () => {
  chatSelectedUsernames.value = []
  snsSelectedUsernames.value = []
  if (props.open) {
    await ensureSourcesLoaded()
  }
})

onMounted(async () => {
  await ensureAccountReady()
  if (process.client && typeof window !== 'undefined') {
    window.addEventListener('keydown', onWindowKeydown)
  }
})

onBeforeUnmount(() => {
  if (!process.client || typeof window === 'undefined') return
  window.removeEventListener('keydown', onWindowKeydown)
})
</script>
