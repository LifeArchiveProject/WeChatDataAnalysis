<template>
  <section class="local-search-settings" aria-label="本地语义检索">
    <div :inert="dialog ? true : undefined">
      <header class="lss-heading">
        <div><h4>记不清原话，也能找到聊天</h4><p>{{ accountWide ? '启用本地模型后，后台逐步整理当前账号全部聊天；整理期间即可提问。无需配置 API 密钥。' : '选好模型和聊天，整理一次，就能按意思搜索。无需配置 API 密钥。' }}</p></div>
        <span class="lss-badge" :class="{ 'is-on': form.enabled }">{{ form.enabled ? '已开启' : '尚未开启' }}</span>
      </header>

      <div v-if="!account" class="lss-feedback">请先在聊天页面选择账号。现在也可以下载模型，之后再开始整理。</div>
      <div v-if="job && (form.enabled || job.status==='error')" ref="statusRef" class="lss-status" tabindex="-1" :class="{ 'is-error': job.status==='error', 'is-paused': job.status==='paused' }">
        <div class="lss-status-heading">
          <div class="lss-status-title" role="status"><LoaderCircle v-if="running" class="agent-icon-spin" :size="16" :stroke-width="1.8" aria-hidden="true" /><CircleAlert v-else-if="job.status==='error'" :size="16" :stroke-width="1.8" aria-hidden="true" /><CircleCheck v-else-if="job.status==='done' && hasSearchData" :size="16" :stroke-width="1.8" aria-hidden="true" /><Info v-else-if="job.status==='done'" :size="16" :stroke-width="1.8" aria-hidden="true" /><CirclePause v-else :size="16" :stroke-width="1.8" aria-hidden="true" /><strong>{{ job.status==='done' ? completedTitle : stage(job) }}</strong></div>
          <div class="lss-status-meta"><span class="lss-device-badge"><Microchip :size="16" :stroke-width="1.8" aria-hidden="true" />{{ actualDevice }}</span><span class="lss-note">用时 {{ elapsed(job) }}</span></div>
        </div>
        <div class="lss-progress-heading">
          <span>{{ progress.total ? (progress.unit==='消息' ? '已保存消息进度' : `${progress.unit}进度`) : job.status==='done' ? '本轮整理进度' : job.stage==='counting' ? '统计完成后显示总量' : '正在确认整理范围' }}<span v-if="progress.total" class="lss-progress-count">{{ number(progress.completed) }} / {{ number(progress.total) }} 已完成</span></span>
          <strong>{{ progress.percent === null ? '—' : `${progress.percent}%` }}</strong>
        </div>
        <progress class="lss-index-progress" :value="progress.percent ?? undefined" max="100" :aria-label="`${progress.unit}整理进度`" />
        <dl class="lss-metrics">
          <div class="lss-metric" data-metric="read"><dt>{{ job.status==='done' ? '本次检查消息' : '已读取消息' }}<template v-if="messageTotal.value !== null"> / 本轮总量</template></dt><dd><strong class="lss-read-total">{{ number(job.read_count ?? job.processed ?? 0) }}<span v-if="messageTotal.value !== null" class="lss-total-denominator">/ {{ number(messageTotal.value) }}</span></strong><span>{{ messageTotal.value !== null ? '条消息' : messageTotal.hint }}</span></dd></div>
          <div class="lss-metric lss-metric-saved" data-metric="saved"><dt>已保存进度</dt><dd><strong>{{ number(job.processed ?? 0) }}</strong><span>条消息</span></dd></div>
          <div class="lss-metric" data-metric="generated"><dt>{{ running ? '本次生成片段' : '本次已保存片段' }}</dt><dd><strong>{{ number(running ? (job.embedded_count ?? job.embedded ?? 0) : (job.embedded ?? 0)) }}</strong><span>个片段</span></dd></div>
          <div class="lss-metric lss-metric-index" data-metric="indexed"><dt>当前索引片段</dt><dd><strong>{{ indexStats ? number(indexStats.chunks) : '—' }}</strong><span>{{ indexStats ? `覆盖 ${number(indexStats.messages)} 条消息` : '等待索引统计' }}</span></dd></div>
        </dl>
        <p v-if="job.warning" class="lss-status-warning" role="status"><Info :size="16" :stroke-width="1.8" aria-hidden="true" />{{ job.warning }}</p>
        <p v-if="job.error" :class="job.status==='paused' ? 'lss-note' : 'lss-error'" :role="job.status==='paused' ? 'status' : 'alert'">{{ job.error }}</p>
        <div class="lss-status-footer">
          <p class="lss-note">{{ statusHint }}</p>
          <button v-if="running" type="button" :disabled="busy" @click="act(()=>request('/index/pause',{method:'POST'},true))"><Pause :size="16" :stroke-width="1.8" aria-hidden="true" />暂停整理</button>
        </div>
        <details class="lss-status-details">
          <summary>处理详情<ChevronDown :size="16" :stroke-width="1.8" aria-hidden="true" /></summary>
          <div>
            <p v-if="job.mode" class="lss-note">{{ indexMode(job.mode) }}</p>
            <p v-if="job.unchanged" class="lss-note">已复用 {{ number(job.unchanged) }} 条未变化消息，无需重复生成片段。</p>
            <p v-if="job.status==='done' && !job.embedded && hasSearchData" class="lss-note">内容没有变化，已复用现有搜索数据，无需重复生成片段。</p>
            <p class="lss-note">已读取 {{ number(job.read_count ?? job.processed ?? 0) }} 条消息，已保存 {{ number(job.processed ?? 0) }} 条消息的进度。生成中的片段以保存后结果为准。</p>
            <p class="lss-note">开始整理前先统计完整消息总量，本轮总量固定不变；新增消息留到下一轮。暂停或重启后继续使用同一总量。</p>
            <p v-if="running && job.read_batch_size_effective" class="lss-note">当前每批最多 {{ number(job.read_batch_size_effective) }} 条 · 根据可用内存调整</p>
            <p class="lss-note">进度按已保存的{{ progress.unit }}计算，不代表剩余用时。</p>
          </div>
        </details>
      </div>

      <div class="lss-setup">
        <section class="lss-step" aria-labelledby="lss-model-title">
          <div class="lss-step-heading"><span class="lss-step-number" :class="{ complete: modelReady }"><Check v-if="modelReady" :size="16" :stroke-width="1.8" aria-hidden="true" /><template v-else>1</template></span><div><h5 id="lss-model-title">选择检索模型</h5><p>模型只需下载一次，所有账号都可使用。</p></div><button type="button" class="lss-link" :disabled="busy || running" @click="dialog='models'">更换模型</button></div>
          <div v-if="displayModel" class="lss-model-summary">
            <div class="lss-model-icon"><Box :size="16" :stroke-width="1.8" aria-hidden="true" /></div>
            <div class="lss-grow"><strong>{{ displayModel.name }}</strong><span v-if="displayModel.recommended" class="lss-tag">推荐</span><p>{{ displayModel.description }} · {{ bytes(displayModel.size) }}</p><span class="lss-note">{{ modelReady ? '已就绪' : displayModel.downloaded ? '已下载，点击右侧使用' : '首次使用需要下载 · Hugging Face 免登录' }}</span></div>
            <button v-if="displayModel.downloaded && !modelReady" type="button" :disabled="busy || running || !account" @click="selectModel(displayModel)">使用此模型</button>
            <span v-else-if="modelReady" class="lss-ready"><CircleCheck :size="16" :stroke-width="1.8" aria-hidden="true" /> 已选择</span>
            <button v-else-if="['running','queued'].includes(displayModel.job?.status)" type="button" :disabled="busy" @click="act(()=>request(`/models/${displayModel.id}/pause`,{method:'POST'}))">暂停下载</button>
            <button v-else type="button" :disabled="busy" @click="act(()=>request(`/models/${displayModel.id}/download`,{method:'POST'}))">{{ displayModel.job ? '继续下载' : '下载模型' }}</button>
          </div>
          <p v-if="modelChanged" class="lss-note">更换模型后，{{ accountWide ? '全部聊天历史' : '所选聊天和时间范围内的全部内容' }}都需要重新生成向量。新索引完成前仍可使用原有索引。</p>
          <div v-if="displayModel?.job && !displayModel.downloaded" class="lss-download-state">
            <progress v-if="displayModel.job.status!=='error'" :value="displayModel.job.total ? displayModel.job.bytes : undefined" :max="displayModel.job.total || undefined" aria-label="模型下载进度" />
            <p class="lss-note">{{ stage(displayModel.job) }} · {{ bytes(displayModel.job.bytes) }}<template v-if="displayModel.job.total"> / {{ bytes(displayModel.job.total) }}</template><template v-if="displayModel.job.speed"> · {{ bytes(displayModel.job.speed) }}/s</template><template v-if="displayModel.job.stage==='retry_wait'"> · {{ Math.max(0,Math.ceil(displayModel.job.next_retry-now)) }} 秒后重试</template></p>
            <p v-if="displayModel.job.error" class="lss-error">{{ displayModel.job.error }}</p>
          </div>
        </section>

        <section v-if="accountWide" class="lss-step" aria-labelledby="lss-global-title">
          <div class="lss-step-heading"><span class="lss-step-number">2</span><div><h5 id="lss-global-title">当前账号全部群聊和私聊</h5><p>先整理近期，再补齐更早历史；新增消息持续更新。提问中的人物、群聊和时间条件只筛选本次查询。</p></div></div>
          <p>基础搜索始终可用，已保存的语义索引立即参与查询。暂停或重启会保留进度，聊天原始数据保持只读。</p>
          <p class="lss-note" role="status">{{ globalCoverage }}</p>
        </section>
        <section v-else class="lss-step" aria-labelledby="lss-scope-title">
          <div class="lss-step-heading"><span class="lss-step-number" :class="{ complete: form.usernames.length }"><Check v-if="form.usernames.length" :size="16" :stroke-width="1.8" aria-hidden="true" /><template v-else>2</template></span><div><h5 id="lss-scope-title">选择要搜索的聊天</h5><p>只整理选中的聊天，不会自动扩大范围。</p></div></div>
          <div class="lss-scope-row"><div class="lss-grow"><strong>{{ form.usernames.length ? '已选择 '+form.usernames.length+' 个聊天' : '还没有选择聊天' }}</strong><p>{{ selectedChatNames || '选择你经常需要查找的好友或群聊' }}</p></div><button type="button" :disabled="!account || busy || running" @click="openScope">{{ form.usernames.length ? '调整聊天' : '选择聊天' }}</button></div>
          <div class="lss-time-row"><span>聊天时间</span><UiSelect v-model="period" label="聊天时间" :disabled="running || busy" :options="periods" @change="changePeriod" /><span class="lss-note">时间范围越大，首次整理越久</span></div>
          <div v-if="period==='custom'" class="lss-grid"><label>开始日期<input v-model="startDate" type="date" :disabled="running || busy" /></label><label>结束日期<input v-model="endDate" type="date" :disabled="running || busy" /></label></div>
        </section>

        <footer class="lss-start">
          <div><strong>{{ running ? (accountWide ? '正在整理全部聊天' : '正在整理所选聊天') : canResume ? '上次整理尚未完成' : modelChanged ? '新模型需要从头整理' : form.enabled && state.config?.active ? '按当前设置更新聊天' : '准备好后，一次开启' }}</strong><p id="lss-start-hint">{{ blockingReason || (accountWide ? '保存模型并开始整理全部历史；前台提问优先使用计算资源。' : running ? '整理会在后台继续，可以随时暂停。' : canResume ? '继续会保留已完成的进度；从头整理会重新处理所选范围的全部内容。' : modelChanged ? '保存当前选择，用新模型重新生成全部向量，完成后切换索引。' : state.config?.active ? '默认增量更新；从头整理会重新生成所选范围的全部向量。' : '点击后保存选择并开始整理，无需另开功能开关。') }}</p></div>
          <div class="lss-start-actions">
            <button type="button" class="lss-primary" aria-describedby="lss-start-hint" :disabled="busy || !!blockingReason || running" @click="primaryAction"><LoaderCircle v-if="busy || running" class="agent-icon-spin" :size="16" :stroke-width="1.8" aria-hidden="true" /><Play v-else :size="16" :stroke-width="1.8" aria-hidden="true" />{{ busy ? '正在提交…' : running ? '正在整理' : canResume ? '继续整理' : modelChanged ? '使用新模型从头整理' : form.enabled ? '保存并开始整理' : '开启并开始整理' }}</button>
            <button v-if="(job || state.config?.active) && (!modelChanged || canResume || running)" type="button" :disabled="busy || !!blockingReason || running" aria-describedby="lss-start-hint" @click="rebuildIndex">从头整理</button>
          </div>
        </footer>
        <p v-if="error" class="lss-feedback lss-error" role="alert">{{ error }}</p><p v-if="notice" class="lss-feedback lss-notice" role="status">{{ notice }}</p>
      </div>

      <details class="lss-advanced" @toggle="advancedOpen=$event.target.open">
        <summary>
          <span class="lss-advanced-icon"><SlidersHorizontal :size="16" :stroke-width="1.8" aria-hidden="true" /></span>
          <span class="lss-advanced-copy"><strong>高级设置</strong><span>{{ isMac ? '运行设备 · 读取批量 · 自动更新' : '运行设备与 GPU 加速 · 读取批量 · 自动更新' }}</span></span>
          <span class="lss-advanced-action">{{ advancedOpen ? '收起设置' : '展开设置' }}<ChevronDown :size="16" :stroke-width="1.8" aria-hidden="true" /></span>
        </summary>
        <div class="lss-advanced-body">
          <p class="lss-note">{{ isMac ? 'macOS 使用 CPU 在本机运行检索模型，无需下载加速组件。' : 'CPU 即可使用，NVIDIA 加速为可选项，无需先下载加速组件。' }}</p>
              <article class="lss-device-panel">
      <div class="lss-row"><div><h5>运行设备</h5><p>{{ isMac ? '自动模式使用 CPU，支持 Apple Silicon 与 Intel Mac。' : '优先使用可用的 NVIDIA GPU，出现故障时自动使用 CPU 继续。' }}</p></div>
        <div class="lss-segments" role="group" aria-label="推理设备"><button v-for="d in devices" :key="d.value" type="button" :aria-pressed="form.device === d.value" :disabled="!account || busy || running" @click="form.device=d.value; save()">{{ d.label }}</button></div>
      </div>
      <div class="lss-row lss-device-state"><span>已选：{{ devices.find(d=>d.value===form.device)?.label || 'NVIDIA GPU（当前系统使用 CPU）' }} · 实际：{{ actualDevice }}</span><button type="button" :disabled="busy || !account" @click="act(()=>request('/device/recheck',{method:'POST'},true),'设备检测完成')">重新检测</button></div>
      <UiSelect v-if="gpuDevices.length > 1" :model-value="String(form.device_id)" @update:model-value="form.device_id=Number($event)" label="选择 NVIDIA 显卡" :options="gpuDevices.map(d=>({value:String(d.id),label:d.name}))" @change="save" />
      <p v-if="state.device?.reason" class="lss-note">{{ state.device.reason }}</p>
      <div v-if="!isMac" class="lss-row"><span>{{ state.gpu?.installed ? 'NVIDIA 加速组件已安装' : 'NVIDIA 加速组件 · ' + bytes(state.gpu?.size) }}</span>
        <div class="lss-actions">
          <button v-if="!state.gpu?.installed" type="button" :disabled="busy || gpuActive || !state.gpu?.supported" :aria-busy="gpuActive || gpuOperation==='download'" @click="downloadGpu">{{ gpuDownloadLabel }}</button>
          <button v-if="gpuActive" type="button" :disabled="busy" @click="pauseGpu">{{ gpuOperation==='pause' ? '正在暂停…' : '暂停' }}</button>
          <button type="button" :disabled="busy || gpuActive || !state.gpu?.supported" @click="openImport('gpu')">离线导入</button>
        </div>
      </div>
      <p v-if="!isMac && state.gpu?.job && state.gpu.job.status !== 'done'" class="lss-note">{{ stage(state.gpu.job) }} · {{ bytes(state.gpu.job.bytes) }} / {{ bytes(state.gpu.job.total) }} {{ state.gpu.job.error }}</p>
    </article>


          <div class="lss-row lss-maintenance"><div><h5>每批读取消息数</h5><p>自动按本机可用内存调整。手动选择较大批量时，内存不足也会减小；读取数量持续更新。</p></div><UiSelect :model-value="String(form.read_batch_size)" @update:model-value="form.read_batch_size=Number($event)" label="每批读取消息数" :disabled="!account || busy || running" :options="readBatchOptions" /></div>
          <div v-if="!accountWide" class="lss-row lss-maintenance"><div><h5>自动整理新消息</h5><p>每分钟检查所选聊天的新内容。</p></div><label class="lss-check"><input v-model="form.auto_update" type="checkbox" :disabled="!account || busy || running" />自动更新</label></div>
          <p v-else class="lss-note">已启用时自动检查全部聊天的新消息和新增会话；暂停后保留已完成部分。</p>
          <div class="lss-actions"><button type="button" :disabled="busy || !account || running" @click="save">保存高级设置</button></div>
          <div class="lss-row lss-maintenance"><div><h5>功能与数据管理</h5><p>{{ account ? '当前账号：'+account : '请先选择账号' }} · 本地索引 {{ bytes(state.index_bytes) }}</p><p v-if="state.config?.active" class="lss-note">最近更新 {{ date(state.config.active.updated) }}</p></div><div class="lss-actions"><button v-if="form.enabled" type="button" :disabled="busy" @click="disableSearch">关闭本地检索</button><button type="button" :disabled="busy || !account || running" @click="clearIndex">清理索引</button></div></div>
          <p class="lss-note">关闭功能会保留模型和索引；清理索引不会删除聊天记录。未解析的图片和扫描件不在本地搜索范围内。</p>
          <details v-if="state.audit?.length" class="lss-section"><summary>本地处理记录</summary><p v-for="a in state.audit" :key="a.id" class="lss-note">{{ a.kind==='search' ? '检索' : '整理聊天' }} · {{ a.model }} · {{ a.actual_device==='cuda' ? 'NVIDIA GPU' : 'CPU' }} · {{ Number(a.seconds).toFixed(1) }} 秒</p></details>
        </div>
      </details>
      <div class="lss-bottom-note"><Laptop :size="16" :stroke-width="1.8" aria-hidden="true" /><span>本地搜索不上传聊天。AI 助手回答时，引用的内容仍会发送至你配置的模型服务。</span></div>
    </div>

    <Teleport to="body"><div v-if="dialog" class="lss-overlay" @click.self="closeDialog" @keydown.esc.stop="closeDialog" @keydown.tab="trapFocus">
      <section ref="dialogRef" class="lss-dialog local-search-settings" :class="{ 'lss-model-dialog':dialog==='models', 'lss-scope-dialog':dialog==='scope' }" role="dialog" aria-modal="true" :aria-label="dialogTitle" tabindex="-1">
        <header class="lss-dialog-heading"><div><h4>{{ dialogTitle }}</h4><p>{{ dialog==='models' ? '按语言和电脑配置选择，下载完成后点击「使用此模型」。' : dialog==='scope' ? '按分类选择要检索的聊天' : '导入后会校验版本和文件完整性。' }}</p></div><button type="button" aria-label="关闭" :disabled="busy" @click="closeDialog"><X :size="16" :stroke-width="1.8" aria-hidden="true" /></button></header>
        <p v-if="dialogError" class="lss-feedback lss-error" role="alert">{{ dialogError }}</p>
        <template v-if="dialog==='models'">    <div class="lss-models" role="list" aria-label="可用检索模型">
      <article v-for="m in state.models || []" :key="m.id" class="lss-card lss-model" :class="{selected: form.model===m.id}" role="listitem">
        <div class="lss-row"><h5>{{ m.name }} <small v-if="m.recommended">推荐</small></h5><span class="lss-note">{{ m.downloaded ? '已下载' : stage(m.job) }}</span></div>
        <p>{{ m.description }}</p><p class="lss-note">{{ bytes(m.size) }} · 本地运行 · {{ m.license }}</p>
        <details class="lss-source"><summary>模型来源</summary><a :href="`https://huggingface.co/${m.repo}`" target="_blank" rel="noopener noreferrer">{{ m.repo }}</a><p>{{ m.id.startsWith('bge') ? '原作者 BAAI · ONNX 转换 Xenova' : '原作者 intfloat' }}</p><p>固定版本 {{ m.revision.slice(0, 12) }}</p></details>
        <template v-if="m.job && !['done','error'].includes(m.job.status)"><progress :value="m.job.total ? m.job.bytes : undefined" :max="m.job.total || undefined" :aria-label="`${m.name} 下载进度`" /><p class="lss-note">{{ stage(m.job) }} · {{ bytes(m.job.bytes) }} / {{ bytes(m.job.total) }}<span v-if="m.job.speed"> · {{ bytes(m.job.speed) }}/s</span><span v-if="m.job.stage==='retry_wait'"> · {{ Math.max(0,Math.ceil(m.job.next_retry-now)) }} 秒后重试</span></p></template>
        <p v-if="m.job?.error" class="lss-error">{{ m.job.error }}</p>
        <div class="lss-actions lss-model-actions">
          <button v-if="m.downloaded" type="button" :disabled="busy || running || !account || form.model===m.id" @click="selectModel(m)">{{ form.model===m.id ? '当前使用' : '使用此模型' }}</button>
          <button v-else-if="!['running','queued'].includes(m.job?.status)" type="button" class="lss-primary" :disabled="busy" @click="act(()=>request(`/models/${m.id}/download`,{method:'POST'}))">{{ m.job ? '继续 / 重试' : '下载' }}</button>
          <button v-else type="button" :disabled="busy" @click="act(()=>request(`/models/${m.id}/pause`,{method:'POST'}))">暂停</button>
          <button v-if="!m.downloaded" type="button" :disabled="busy || modelActive(m.id)" @click="openImport(m.id)">离线导入</button>
          <button v-if="m.downloaded || m.job" type="button" :disabled="busy || form.model===m.id" @click="removeModel(m)">{{ m.downloaded ? '删除' : '取消并清理' }}</button>
        </div>
      </article>
    </div>

</template>
        <template v-else-if="dialog==='scope'">
          <div class="lss-scope-search"><Search :size="16" :stroke-width="1.8" aria-hidden="true" /><input v-model="scopeSearch" type="search" placeholder="搜索群聊或个人聊天" aria-label="搜索群聊或个人聊天" /></div>
          <div class="lss-scope-columns">
            <section v-for="category in scopeCategories" :key="category.key" class="lss-scope-category" :aria-labelledby="`lss-category-${category.key}`" :data-category="category.key">
              <header class="lss-category-heading">
                <h5 :id="`lss-category-${category.key}`">{{ category.label }} <span>{{ scopeQuery ? category.visible.length+' / '+category.total : category.total }}</span></h5>
                <div class="lss-category-actions">
                  <button type="button" class="lss-category-select" :aria-label="`${scopeQuery ? '全选搜索结果中的' : '全选'}${category.label}`" :disabled="!category.visible.length || category.allSelected" @click="selectCategory(category)">{{ scopeQuery ? '全选结果' : '全选' }}</button>
                  <button type="button" class="lss-category-clear" :aria-label="`${scopeQuery ? '清除搜索结果中的' : '清除'}${category.label}选择`" :disabled="!category.visibleSelected" @click="clearCategory(category)">清除</button>
                </div>
              </header>
              <div class="lss-chat-list" tabindex="0" :aria-label="`${category.label}列表`">
                <label v-for="c in category.visible" :key="c.username" class="lss-check" :class="{ 'is-selected': scopeSelected.has(c.username) }"><input v-model="scopeDraft" type="checkbox" :value="c.username" /><span :title="c.name">{{ c.name }}</span></label>
                <p v-if="!category.visible.length" class="lss-empty">{{ scopeQuery ? '没有匹配的'+category.label : '暂无'+category.label }}</p>
              </div>
            </section>
          </div>
          <footer class="lss-scope-footer"><div aria-live="polite"><strong>已选择 {{ scopeDraft.length }} 个聊天</strong><p>群聊 {{ scopeCategories[0].selected }} · 个人聊天 {{ scopeCategories[1].selected }}<template v-if="scopeUnavailable"> · 暂不可用 {{ scopeUnavailable }}</template></p></div><div class="lss-scope-footer-actions"><button type="button" @click="closeDialog">取消</button><button type="button" class="lss-primary" @click="form.usernames=[...scopeDraft]; dialog=''">确认选择</button></div></footer>
        </template>
        <template v-else><p>填写完整的{{ importId==='gpu' ? '加速组件 wheel 文件' : '内置模型' }}所在目录。</p><input v-model="importPath" placeholder="本机目录完整路径" aria-label="离线文件目录" /><p v-if="importActive" class="lss-note">正在下载或处理文件，请先暂停，再离线导入。</p><button type="button" class="lss-primary" :disabled="busy || !importPath || (importActive)" @click="importFiles">校验并导入</button></template>
      </section>
    </div></Teleport>
  </section>
</template>

<script setup>
import { Box, Check, ChevronDown, CircleAlert, CircleCheck, CirclePause, Info, Laptop, LoaderCircle, Microchip, Pause, Play, Search, SlidersHorizontal, X } from '@lucide/vue'
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import { useChatAccountsStore } from '~/stores/chatAccounts'
import UiSelect from './UiSelect.vue'
const props=defineProps({accountWide:{type:Boolean,default:false}})
const { selectedAccount: account }=storeToRefs(useChatAccountsStore())
const api=useAiApi(), route=useRoute()
const state=ref({}), form=reactive({enabled:false,model:null,usernames:[],days:90,start:null,end:null,device:'auto',device_id:0,auto_update:true,read_batch_size:0})
const statusRef=ref(null)
const advancedOpen=ref(false),busy=ref(false),dialogError=ref(''),error=ref(''),notice=ref(''),now=ref(Date.now()/1000),gpuDevices=ref([])
const dialog=ref(''),dialogRef=ref(null),scopeSearch=ref(''),scopeDraft=ref([]),chats=ref([]),importId=ref(''),importPath=ref('')
const period=ref('90'),startDate=ref(''),endDate=ref('')
const periods=[{value:'90',label:'最近 90 天'},{value:'30',label:'最近 30 天'},{value:'0',label:'全部历史'},{value:'custom',label:'自定义时间'}]
const isMac=computed(()=>state.value.gpu?.platform==='darwin')
const devices=computed(()=>[{value:'auto',label:'自动'},{value:'cpu',label:'CPU'},...(!isMac.value ? [{value:'cuda',label:'NVIDIA GPU'}] : [])])
const readBatchOptions=[{value:'0',label:'自动 · 推荐'},{value:'100',label:'100 条 · 低占用'},{value:'500',label:'500 条'},{value:'1000',label:'1,000 条'},{value:'2000',label:'2,000 条 · 大批量'}]
const job=computed(()=>state.value.jobs?.[0])
const indexStats=computed(()=>state.value.index_stats ?? job.value?.index_stats)
const hasSearchData=computed(()=>Number(indexStats.value?.chunks)>0)
const completedTitle=computed(()=>props.accountWide ? '本轮整理已完成' : !indexStats.value ? '本次检查完成' : !hasSearchData.value ? '所选范围内暂无可搜索内容' : !job.value?.embedded ? '搜索数据已是最新' : '聊天已准备好，可以智能搜索了')
const globalCoverage=computed(()=>{
  const active=state.value.config?.active
  if(!active)return '尚未建立语义索引，当前使用基础搜索。'
  const ranges=Object.values(active.coverage || {}), complete=ranges.filter(r=>r.complete).length
  if(!ranges.length)return '覆盖范围未知：旧索引未记录会话时间段；继续整理后更新覆盖状态。'
  return `${active.partial ? '部分覆盖' : '本轮覆盖已保存'} · ${new Set(ranges.map(r=>r.username)).size} 个聊天 · ${complete} 个时间段已读完。新增或尚未读取的记录继续使用基础搜索。`
})
const modelActive=id=>['queued','running'].includes(state.value.models?.find(m=>m.id===id)?.job?.status)
const importActive=computed(()=>importId.value==='gpu' ? gpuActive.value : modelActive(importId.value))
const gpuOperation=ref('')
const gpuActive=computed(()=>['queued','running'].includes(state.value.gpu?.job?.status))
const gpuDownloadLabel=computed(()=>{
  if(gpuOperation.value==='download')return '正在提交…'
  const current=state.value.gpu?.job
  if(current?.status==='queued')return '等待下载…'
  if(gpuActive.value)return ({connecting:'正在连接…',retry_wait:'等待重试…',verifying:'正在校验…',installing:'正在安装…'}[current.stage] || '正在下载…')
  return current?.status==='paused' ? '继续下载组件' : current?.status==='error' ? '重试下载组件' : '下载加速组件'
})
const scopeQuery=computed(()=>scopeSearch.value.trim().toLowerCase())
const scopeSelected=computed(()=>new Set(scopeDraft.value))
const scopeCategories=computed(()=>[
  {key:'groups',label:'群聊',isGroup:true},
  {key:'people',label:'个人聊天',isGroup:false},
].map(category=>{
  // 优先采用后端标识，兼容尚未返回标识的旧服务；不根据聊天名称猜测类型。
  const items=chats.value.filter(c=>(c.isGroup ?? c.username.endsWith('@chatroom'))===category.isGroup)
  const visible=items.filter(c=>c.name.toLowerCase().includes(scopeQuery.value))
  const visibleSelected=visible.filter(c=>scopeSelected.value.has(c.username)).length
  return {...category,total:items.length,visible,visibleSelected,allSelected:visible.length>0 && visibleSelected===visible.length,selected:items.filter(c=>scopeSelected.value.has(c.username)).length}
}))
const scopeUnavailable=computed(()=>scopeDraft.value.length-scopeCategories.value.reduce((total,c)=>total+c.selected,0))
function selectCategory(category){
  // 批量操作只影响本类当前搜索结果，保留其他分类和被搜索隐藏的选择。
  scopeDraft.value=[...new Set([...scopeDraft.value,...category.visible.map(c=>c.username)])]
}
function clearCategory(category){
  const visible=new Set(category.visible.map(c=>c.username))
  scopeDraft.value=scopeDraft.value.filter(username=>!visible.has(username))
}
// 首次开通只有一个提交入口；模型下载和会话草稿都不隐式开启索引。
const selectedModel=computed(()=>state.value.models?.find(m=>m.id===form.model))
const displayModel=computed(()=>selectedModel.value || state.value.models?.find(m=>m.recommended) || state.value.models?.[0])
const modelReady=computed(()=>!!selectedModel.value?.downloaded)
const running=computed(()=>['running','queued'].includes(job.value?.status))
const number=value=>Number(value ?? 0).toLocaleString('zh-CN')
const messageTotal=computed(()=>{
  const current=job.value, total=state.value.message_total
  // 固定总量从统计快照读取，完成、暂停和实时读取事件都不能改写分母。
  if(total?.job_id===current?.id && total?.status==='ready' && total.fixed===true && typeof total.value==='number' && Number.isFinite(total.value) && total.value>=0){
    return {value:total.value}
  }
  if(current?.status==='done')return {value:current.processed ?? 0}
  const status=total?.job_id===current?.id ? total?.status : null
  return {value:null,hint:status==='unavailable' ? '总量统计未完成' : !running.value ? '总量未统计完' : '总量统计中…'}
})
const progress=computed(()=>{
  const current=job.value, total=messageTotal.value.value
  if(total!==null){
    const completed=Math.min(total,Math.max(0,Number(current?.processed) || 0))
    return {total,completed,unit:'消息',percent:total ? Math.floor(completed/total*100) : current?.status==='done' ? 100 : 0}
  }
  if(current?.stage==='counting')return {total:0,completed:0,unit:'消息',percent:null}
  // 旧任务尚未迁移固定消息清单时，继续展示原来已有的会话进度。
  const segments=current?.segments?.length ?? current?.config?.usernames?.length ?? 0
  const completed=Math.min(segments,Math.max(0,Number(current?.chat_index) || 0))
  return {total:segments,completed,unit:current?.segments ? '会话时间段' : '聊天',percent:segments ? Math.floor(completed/segments*100) : null}
})
const statusHint=computed(()=>{
  if(running.value && job.value?.stage==='counting')return '正在统计本轮消息总量，统计完成后开始整理。'
  if(running.value)return '本轮范围已固定，新增消息留到下一轮；可以离开此页面。'
  if(job.value?.status==='paused')return '进度已保存，可继续整理。'
  if(job.value?.status==='error')return '已保存的进度会保留，可在下方重试整理。'
  if(job.value?.status==='done' && hasSearchData.value)return '本轮整理已完成。在聊天搜索中切换到「智能搜索」，或直接向 AI 助手提问。'
  if(job.value?.status==='done' && indexStats.value)return '请调整聊天或时间范围；只有图片等尚未提取文字的内容无法生成搜索片段。'
  return '本轮整理已结束。'
})
const selectedChatNames=computed(()=>form.usernames.map(id=>chats.value.find(c=>c.username===id)?.name).filter(Boolean).slice(0,3).join('、')+(form.usernames.length>3?' 等':''))
const dialogTitle=computed(()=>({models:'选择检索模型',scope:'选择聊天',import:'离线导入'}[dialog.value] || ''))
const invalidDates=computed(()=>period.value==='custom' && (!startDate.value || !endDate.value || startDate.value>endDate.value))
const blockingReason=computed(()=>!account.value ? '请先在聊天页面选择账号。' : !modelReady.value ? '请先下载并使用一个检索模型。' : !props.accountWide && !form.usernames.length ? '请选择至少一个聊天。' : !props.accountWide && invalidDates.value ? '请选择有效的开始和结束日期。' : '')
const hasChanges=computed(()=>Object.keys(defaults).some(key=>JSON.stringify(form[key])!==JSON.stringify(state.value.config?.[key] ?? defaults[key])) || (period.value==='custom' && (startDate.value!==localDate(state.value.config?.start) || endDate.value!==localDate(state.value.config?.end))))
const canResume=computed(()=>form.enabled && (!props.accountWide || state.value.config?.agent_global) && ['paused','error'].includes(job.value?.status) && !hasChanges.value && job.value.config?.revision===state.value.config?.revision)
const modelChanged=computed(()=>!!state.value.config?.active && !!form.model && form.model!==state.value.config.active.model)
const indexMode=mode=>({incremental:'增量整理：读取新增消息与最近十分钟的补写；新增聊天或扩展历史会补齐对应范围。',reconcile:'正在进行每日历史校对，检查补写或修改的消息；未变化内容复用已有索引。',enrichment:'已有转写或附件文字发生变化，正在核对所选范围；未变化内容复用已有索引。',rebuild:'正在重新建立索引，原索引保留至完成。',initial:'首次整理当前模型和范围，进度会自动保存。',manual_check:'正在核对所选范围，未变化内容复用已有索引。'}[mode] || '')
const localDate=value=>value ? new Date(value*1000).toLocaleDateString('en-CA') : ''
const actualDevice=computed(()=>state.value.device?.actual_device==='cuda' ? (state.value.device?.device_name || 'NVIDIA GPU') : ({cpu:'CPU',switching:'正在切换 CPU'}[state.value.device?.actual_device] || '等待模型加载'))
const bytes=n=>!n ? '0 B' : n<1024**2 ? `${(n/1024).toFixed(0)} KB` : n<1024**3 ? `${(n/1024**2).toFixed(1)} MB` : `${(n/1024**3).toFixed(2)} GB`
const date=n=>n ? new Date(n*1000).toLocaleString() : '—'
const elapsed=j=>`${Math.max(0,Math.floor((j.finished || (['paused','done','error'].includes(j.status) ? j.updated : now.value) || now.value)-j.started))} 秒`
const stage=j=>!j ? '未下载' : ({counting:'正在统计消息总量',importing:'导入中',pausing:'正在暂停',queued:'等待整理',connecting:'连接中',downloading:'下载中',retry_wait:'等待重试',paused:'已暂停',verifying:'校验中',verified:'校验完成',loading:'测试模型',done:'已完成',error:'处理失败',reading:'读取聊天记录',organizing:'整理消息片段',embedding:'正在理解聊天内容',saving:'正在保存搜索数据',installing:'安装加速组件'}[j.status==='error' || j.status==='paused' ? j.status : j.stage] || '处理中')
const request=(path,options={},scoped=false)=>api.request(`/local-search${path}${scoped && account.value ? `${path.includes('?')?'&':'?'}account=${encodeURIComponent(account.value)}`:''}`,options)
let refreshDone=Promise.resolve()
let timer, loading=false, version=0, gpuVersion=0, needsReset=false, previousFocus, stopEvents
const defaults={...form,usernames:[]}
async function refresh(reset=false,wait=false){
  needsReset ||= reset
  if(loading){if(wait){await refreshDone;return refresh(reset,true)}return}
  let finishRefresh;refreshDone=new Promise(resolve=>{finishRefresh=resolve})
  loading=true; const current=account.value, stamp=version, gpuStamp=gpuVersion
  try { const result=await request('/status',{},true); if(current!==account.value || stamp!==version)return;
    // 慢轮询响应不能覆盖刚收到的实时进度。
    result.jobs=result.jobs?.map(incoming=>{const live=state.value.jobs?.find(j=>j.id===incoming.id);if(live?.updated>incoming.updated){api.diagnostic?.('response.stale',{task_id:incoming.id,component:'search'});return live}return incoming})
    state.value=gpuStamp===gpuVersion ? result : {...result,gpu:state.value.gpu}
    if(needsReset){Object.assign(form,defaults);if(result.config)for(const key of Object.keys(form)) if(key in result.config)form[key]=result.config[key];period.value=form.start!==null?'custom':String(form.days);startDate.value=form.start?new Date(form.start*1000).toLocaleDateString('en-CA'):'';endDate.value=form.end?new Date(form.end*1000).toLocaleDateString('en-CA'):'';needsReset=false}
  } catch(e){error.value=e.message} finally{loading=false;finishRefresh()}
}
async function act(fn,message=''){
  if(busy.value)return
  const stamp=version
  busy.value=true;error.value='';dialogError.value='';notice.value=''
  try{await fn();if(stamp===version){notice.value=message;await refresh(false,true)}}
  catch(e){if(stamp===version){error.value=e.message;if(dialog.value)dialogError.value=e.message}}
  finally{busy.value=false}
}
function changePeriod(){form.days=period.value==='custom'?0:Number(period.value);form.start=null;form.end=null}
async function persist(){
  if(props.accountWide){
    const current=account.value
    const result=await request('/settings',{method:'PUT',body:{...form,agent_global:true,usernames:[],days:0,start:0,end:null,auto_update:true}},true)
    // 服务端解析全账号目录；同步已保存配置，暂停后才可直接沿用断点。
    if(current===account.value){for(const key of Object.keys(defaults))if(key in result)form[key]=result[key];period.value='0';startDate.value='';endDate.value=''}
    return result
  }
  if(period.value==='custom'){form.start=startDate.value?Math.floor(new Date(`${startDate.value}T00:00:00`).getTime()/1000):null;form.end=endDate.value?Math.floor(new Date(`${endDate.value}T23:59:59`).getTime()/1000):null}
  return request('/settings',{method:'PUT',body:{...form}},true)
}
// 高级设置只保存设备、批量和更新偏好，不顺带提交尚未确认的模型与聊天草稿。
function savedValues(){
  const saved=Object.fromEntries(Object.keys(defaults).map(key=>[key,state.value.config?.[key] ?? defaults[key]]))
  // 全账号目录由服务端解析，保存高级设置或关闭功能时也不回传整份目录。
  return state.value.config?.agent_global ? {...saved,agent_global:true,usernames:[]} : saved
}
const save=()=>act(async()=>{
  const prior=savedValues(), current=account.value
  try{await request('/settings',{method:'PUT',body:{...prior,device:form.device,device_id:form.device_id,auto_update:form.auto_update,read_batch_size:form.read_batch_size}},true)}
  catch(e){if(current===account.value)for(const key of ['device','device_id','auto_update','read_batch_size'])form[key]=prior[key];throw e}
},'高级设置已保存')

const startIndex=async(rebuild=false)=>{const currentAccount=account.value;await act(async()=>{
  if(blockingReason.value)throw new Error(blockingReason.value)
  const previous=form.enabled, current=account.value
  form.enabled=true
  try{await persist()}catch(e){form.enabled=previous;throw e}
  // 账号已切换时不能把旧操作继续提交到新账号。
  if(current!==account.value)return
  await request(rebuild ? '/index/rebuild' : '/index/build',{method:'POST'},true)
})
  if(currentAccount===account.value && !error.value){await nextTick();statusRef.value?.scrollIntoView?.({block:'nearest',behavior:'smooth'})}
}
const primaryAction=()=>canResume.value ? act(()=>request(`/index/resume?job_id=${job.value.id}`,{method:'POST'},true),'已继续整理') : startIndex()
const disableSearch=()=>act(async()=>{
  const current=account.value
  await request('/settings',{method:'PUT',body:{...savedValues(),enabled:false}},true)
  if(current===account.value)form.enabled=false
},'已关闭本地检索，模型和搜索数据已保留')
const rebuildIndex=()=>{if(window.confirm(`使用当前选择的模型，从头整理${props.accountWide ? '当前账号全部聊天历史' : ` ${form.usernames.length} 个聊天及所选时间范围`}？全部向量会重新生成，已有索引保留至完成。`))return startIndex(true)}
function closeDialog(){if(busy.value)return;dialog.value='';dialogError.value=''}
async function selectModel(m){
  // 选择只修改草稿，主按钮统一保存，避免选模型时取消已有后台任务。
  form.model=m.id;dialog.value='';error.value='';notice.value=''
}
async function removeModel(m){if(!window.confirm(`确定${m.downloaded?'删除模型':'取消下载并清理临时文件'} ${m.name}？`))return;await act(()=>request(`/models/${m.id}/delete`,{method:'POST'}))}
const clearIndex=()=>{if(window.confirm('清理当前账号的语义索引？聊天记录和模型文件会保留；功能已关闭时，同时取消模型选择。'))act(async()=>{await request('/index/clear',{method:'POST'},true);needsReset=true})}
async function openScope(){await act(async()=>{chats.value=await request('/conversations',{},true);scopeSearch.value='';scopeDraft.value=[...form.usernames];if(!scopeDraft.value.length && route.params.username && chats.value.some(c=>c.username===route.params.username))scopeDraft.value=[route.params.username];dialog.value='scope'})}
// 直接采用操作返回的状态，避免轮询尚未更新时按钮再次开放。
async function gpuRequest(action,body){
  gpuOperation.value=action;gpuVersion++
  try{state.value.gpu=await request(`/gpu/${action}`,{method:'POST',...(body ? {body} : {})})}
  finally{gpuVersion++;gpuOperation.value=''}
}
function downloadGpu(){if(busy.value || gpuActive.value || state.value.gpu?.installed || !state.value.gpu?.supported)return;return act(()=>gpuRequest('download'))}
function pauseGpu(){if(!gpuActive.value)return;return act(()=>gpuRequest('pause'))}
function openImport(id){if(busy.value || (id==='gpu' ? gpuActive.value : modelActive(id)))return;importId.value=id;importPath.value='';dialog.value='import'}
const importFiles=()=>{
  if(importActive.value)return
  return act(async()=>{if(importId.value==='gpu')await gpuRequest('import',{path:importPath.value});else await request(`/models/${importId.value}/import`,{method:'POST',body:{path:importPath.value}});dialog.value=''},'离线文件已提交校验')
}
function trapFocus(event){const items=[...dialogRef.value.querySelectorAll('button:not(:disabled),input:not(:disabled),[href],select,[tabindex="0"]')];const first=items[0],last=items.at(-1);if(!first){event.preventDefault();return}if(event.shiftKey && (document.activeElement===first || document.activeElement===dialogRef.value)){event.preventDefault();last.focus()}else if(!event.shiftKey && (document.activeElement===last || document.activeElement===dialogRef.value)){event.preventDefault();first.focus()}}
watch(dialog,async(value,oldValue)=>{dialogError.value='';if(value){if(!oldValue)previousFocus=document.activeElement;await nextTick();dialogRef.value?.focus()}else{previousFocus?.focus?.()}})
function subscribe(){
  stopEvents?.()
  const current=account.value
  stopEvents=api.localSearchEvents?.(current,event=>{
    if(current!==account.value)return
    if(event?.kind==='local_search_index' && event.account===current){
      const incoming=event.body, existing=state.value.jobs?.find(j=>j.id===incoming?.id)
      if(existing && incoming.updated>=existing.updated){
        // 进度事件只带高频字段；合并保留首次加载时拿到的 config/segments 等快照。
        state.value.jobs=state.value.jobs.map(j=>j.id===incoming.id ? {...j, ...incoming} : j)
        now.value=Date.now()/1000
        if(incoming.status==='done')refresh()
      }else if(!existing){refresh()}else{api.diagnostic?.('response.stale',{task_id:incoming.id,component:'search'})}
    }else{refresh()}
  },state.value.event_cursor || 0)
}
watch(account,async()=>{
  const current=account.value
  version++;stopEvents?.();dialog.value='';error.value='';notice.value='';chats.value=[];state.value={};Object.assign(form,defaults)
  await refresh(true,true)
  if(current===account.value)subscribe()
})
onMounted(async()=>{await refresh(true);subscribe();if(account.value)chats.value=await request('/conversations',{},true).catch(()=>[]);gpuDevices.value=await request('/device/list').catch(()=>[]);timer=setInterval(()=>{now.value=Date.now()/1000;refresh()},1500)})
onBeforeUnmount(()=>{clearInterval(timer);stopEvents?.()})
</script>


<style scoped>
.local-search-settings svg.lucide{display:block;flex:none}
.local-search-settings{color:var(--app-text-primary,#20272f);font-size:12px;line-height:1.5}
.local-search-settings *{box-sizing:border-box}
.local-search-settings h4,.local-search-settings h5,.local-search-settings p{margin:0}
.local-search-settings h4{font-size:16px;font-weight:650;letter-spacing:-.3px}
.local-search-settings h5{font-size:13px;font-weight:600}
.local-search-settings p{color:var(--app-text-secondary,#687582);font-weight:400;line-height:1.65;margin-top:4px}
.lss-heading,.lss-row{display:flex;align-items:center;justify-content:space-between;gap:12px}
.lss-heading{margin-bottom:18px;align-items:flex-start}.lss-heading p{font-size:11px}
.lss-badge,.lss-tag{white-space:nowrap;font-size:10px;border-radius:5px;background:var(--app-surface-soft,#f6f7f8);padding:3px 7px;color:var(--app-text-secondary)}
.lss-badge.is-on,.lss-tag{color:#079b57;background:var(--app-accent-soft,#edf8f1)}.lss-tag{margin-left:7px;padding:1px 5px}
.lss-setup{border:1px solid var(--app-border,#e7e9ed);border-radius:10px;overflow:hidden;background:var(--app-surface-bg,#fff)}
.lss-step{padding:18px 20px}.lss-step+.lss-step{border-top:1px solid var(--app-border,#e7e9ed)}
.lss-step-heading{display:flex;align-items:center;gap:10px;margin-bottom:13px}
.lss-step-heading p{font-size:11px}.lss-step-heading>button{margin-left:auto}
.lss-step-number{display:grid;place-items:center;flex-shrink:0;width:25px;height:25px;border-radius:50%;font-size:11px;font-weight:600;background:var(--app-surface-soft,#f6f7f8);border:1px solid var(--app-border,#e7e9ed);color:var(--app-text-secondary)}
.lss-step-number.complete{color:#079b57;border-color:transparent;background:var(--app-accent-soft,#edf8f1)}
.lss-model-summary{display:flex;align-items:center;gap:12px;padding:13px;border-radius:7px;background:var(--app-surface-soft,#f7f8fa)}
.lss-model-icon{width:34px;height:34px;display:grid;place-items:center;background:var(--app-surface-bg,#fff);border:1px solid var(--app-border,#e7e9ed);border-radius:8px;color:#079b57}
.lss-grow{flex:1;min-width:0}.lss-grow p{font-size:11px;overflow-wrap:anywhere}
.lss-ready{color:#079b57;font-size:11px;white-space:nowrap}
.lss-note{color:var(--app-text-secondary,#687582);font-size:10px;font-weight:400}
.local-search-settings button{font:inherit;font-size:11px;min-height:32px;padding:6px 11px;display:inline-flex;align-items:center;justify-content:center;gap:6px;color:inherit;border:1px solid var(--app-border,#e7e9ed);border-radius:6px;background:var(--app-surface-bg,#fff);cursor:pointer;white-space:nowrap}
.local-search-settings button:hover{background:var(--app-surface-soft,#f7f8fa)}
.local-search-settings button:disabled{opacity:.5;cursor:not-allowed}
.local-search-settings .lss-primary{background:#079b57;color:white;border-color:#079b57;font-weight:550;min-height:36px;padding:8px 16px}
.local-search-settings .lss-primary:hover{background:#07834b}
.local-search-settings .lss-link{color:#079b57;border-color:transparent;background:transparent}
.local-search-settings :is(button,input,summary):focus-visible{outline:2px solid #079b57;outline-offset:3px}
.lss-scope-row{display:flex;align-items:center;gap:12px;border:1px solid var(--app-border,#e7e9ed);border-radius:7px;padding:12px}
.lss-time-row{display:flex;align-items:center;gap:12px;margin-top:12px}.lss-time-row>.ui-select{width:180px;flex-shrink:0}
.lss-start{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:16px 20px;background:var(--app-surface-soft,#f7f8fa);border-top:1px solid var(--app-border,#e7e9ed)}
.lss-start p{font-size:11px}.lss-start strong{font-size:12px}
.lss-start-actions{display:flex;gap:8px;flex-wrap:wrap;flex-shrink:0}
@container (max-width:600px){.lss-start-actions button{flex:1}}
.lss-status{--lss-green:#07834b;--lss-blue:#526d9e;border:1px solid color-mix(in srgb,var(--app-border,#e7e9ed),#079b57 20%);border-radius:12px;background:var(--app-surface-bg,#fff);padding:20px;margin-bottom:16px;container-type:inline-size;font-variant-numeric:tabular-nums}
.lss-status-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.lss-status-title{display:flex;align-items:center;gap:8px;font-size:14px;min-width:0}.lss-status-title>:is(i,svg){color:var(--lss-green);flex-shrink:0}
.lss-status-meta{display:flex;align-items:center;gap:12px;min-width:0;margin-left:auto}.lss-status-meta>.lss-note{white-space:nowrap}
.lss-device-badge{display:inline-flex;align-items:center;gap:6px;min-width:0;font-size:11px;padding:4px 9px;border-radius:6px;background:var(--app-accent-soft,#edf8f1);color:var(--lss-green);overflow-wrap:anywhere}
.lss-progress-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:20px 0 8px;color:var(--app-text-secondary,#687582);font-size:11px}
.lss-progress-heading strong{color:var(--lss-blue);font-size:16px;flex-shrink:0}.lss-progress-count{margin-left:10px}
.local-search-settings .lss-index-progress{display:block;width:100%;height:8px;appearance:none;border:0;border-radius:8px;overflow:hidden;background:var(--app-accent-soft,#e6f0eb);accent-color:#07bf63}
.lss-index-progress::-webkit-progress-bar{background:var(--app-accent-soft,#e6f0eb)}.lss-index-progress::-webkit-progress-value{background:#07bf63;border-radius:8px}.lss-index-progress::-moz-progress-bar{background:#07bf63;border-radius:8px}
.lss-index-progress:indeterminate{opacity:.6}.is-paused .lss-index-progress{accent-color:var(--app-text-secondary,#687582)}.is-paused .lss-index-progress::-webkit-progress-value{background:var(--app-text-secondary,#687582)}.is-paused .lss-index-progress::-moz-progress-bar{background:var(--app-text-secondary,#687582)}
.lss-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin:24px 0}
.lss-metric{display:flex;flex-direction:column;align-items:center;text-align:center;min-width:0}.lss-metric dt{order:2;margin-top:5px;font-size:11px;font-weight:400;color:var(--app-text-secondary,#687582)}
.lss-metric dd{display:contents;margin:0}.lss-metric dd>strong{font-size:clamp(18px,3.4cqw,24px);font-weight:600;overflow-wrap:anywhere;max-width:100%}.lss-metric{font-size:24px;font-weight:600;line-height:1.3}.lss-metric dd>span{order:3;margin-top:5px;font-size:10px;font-weight:400;color:var(--app-text-secondary,#687582)}
.lss-metric-saved{color:var(--lss-green)}.lss-metric-index{color:var(--lss-blue);border-left:1px solid var(--app-border,#e7e9ed)}
.lss-read-total{display:flex;align-items:baseline;justify-content:center;flex-wrap:wrap;gap:4px}.lss-total-denominator{font-size:14px;font-weight:400;white-space:nowrap;color:var(--app-text-secondary,#687582)}
.lss-status-footer{display:flex;align-items:center;justify-content:space-between;gap:16px}.lss-status-footer>.lss-note{margin:0;font-size:11px}.lss-status-footer button{flex-shrink:0}
.lss-status-details{border-top:1px solid var(--app-border,#e7e9ed);margin-top:16px;padding-top:12px}.lss-status-details summary{display:flex;align-items:center;gap:8px;width:fit-content;min-height:28px;font-size:11px;color:var(--app-text-secondary,#687582);list-style:none}.lss-status-details summary::-webkit-details-marker{display:none}.lss-status-details summary>:is(i,svg){font-size:9px}.lss-status-details[open] summary>:is(i,svg){transform:rotate(180deg)}.lss-status-details summary:hover{color:var(--lss-green)}.lss-status-details>div{padding-top:4px}
.lss-status :is(.lss-error,.lss-status-warning){overflow-wrap:anywhere;margin-bottom:12px}.lss-status-warning{display:flex;align-items:baseline;gap:7px}
.lss-status.is-error{border-color:var(--danger-color,#cb4b43)}
.lss-status.is-error .lss-status-title>:is(i,svg){color:var(--danger-color,#cb4b43)}
:global([data-theme=dark] .lss-status){--lss-green:#64d49c;--lss-blue:#9aafd7}
@container(max-width:520px){.lss-metrics{grid-template-columns:repeat(2,minmax(0,1fr));gap:20px 12px}.lss-metric-index{border-left:0}.lss-progress-count{display:block;margin:4px 0 0}.lss-status-footer{align-items:flex-start;flex-wrap:wrap}.lss-status-footer button{margin-left:auto}.lss-metric{font-size:22px}}
.lss-bottom-note{display:flex;align-items:flex-start;gap:7px;font-size:10px;color:var(--app-text-secondary,#687582);padding:12px 1px;line-height:1.7}
.lss-bottom-note>:is(i,svg){margin-top:3px}
.lss-advanced{border:1px solid var(--app-border,#e7e9ed);border-radius:9px;margin-top:14px;background:var(--app-surface-soft,#f7f7f7);overflow:hidden}
.lss-advanced>summary{display:flex;align-items:center;gap:12px;padding:16px;list-style:none}
.lss-advanced>summary::-webkit-details-marker{display:none}
.lss-advanced>summary:hover{background:var(--app-surface-muted,#f0f3f1)}
.lss-advanced>summary:focus-visible{outline-offset:-3px}
.lss-advanced-icon{display:grid;place-items:center;width:34px;height:34px;border-radius:8px;flex-shrink:0;color:var(--app-accent,#079b57);background:var(--app-surface-bg,#fff);border:1px solid var(--app-border,#e7e9ed)}
.lss-advanced-copy{display:flex;flex-direction:column;gap:4px;flex:1;min-width:0}
.lss-advanced-copy strong{font-size:13px;font-weight:600}
.lss-advanced-copy>span{color:var(--app-text-secondary,#687582);font-size:11px}
.lss-advanced-action{display:flex;align-items:center;gap:8px;flex-shrink:0;padding:7px 10px;border:1px solid var(--app-border,#e7e9ed);border-radius:6px;color:var(--app-accent,#079b57);background:var(--app-surface-bg,#fff);font-size:11px;font-weight:500}
.lss-advanced[open]>summary .lucide-chevron-down{transform:rotate(180deg)}
.lss-advanced-body{border-top:1px solid var(--app-border,#e7e9ed);padding:16px;background:var(--app-surface-bg,#fff)}
.lss-device-panel{margin-top:14px}.lss-device-state{margin:12px 0;color:var(--app-text-secondary)}
.lss-segments{display:flex;flex-shrink:0;gap:2px}
.lss-segments button[aria-pressed=true]{color:#079b57;background:var(--app-accent-soft,#edf8f1)}
.lss-maintenance{margin-top:16px;padding-top:16px;border-top:1px solid var(--app-border,#e7e9ed)}
.local-search-settings .lss-check{display:flex;flex-direction:row;align-items:center;justify-content:flex-start;gap:8px;font-size:12px;font-weight:400}
.local-search-settings input[type=checkbox]{width:14px;height:14px;flex-shrink:0;margin:0;accent-color:#079b57}
.local-search-settings input:not([type=checkbox]){width:100%;min-width:0;padding:8px 10px;border:1px solid var(--app-border,#e7e9ed);border-radius:6px;background:var(--app-surface-bg,#fff);color:inherit;font:inherit}
.lss-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px}.lss-grid label{display:flex;flex-direction:column;gap:6px}
.lss-actions{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}.lss-section{margin-top:16px}
.lss-feedback{padding:10px 16px;font-size:11px}.lss-error{color:var(--danger-color,#cb4b43)!important}.lss-notice{color:#079b57!important}
.local-search-settings .lss-feedback{margin:0}.lss-download-state{margin-top:10px}
.local-search-settings progress{width:100%;height:5px;accent-color:#079b57}
summary{cursor:pointer}
.lss-overlay{position:fixed;inset:0;z-index:22000;background:#0006;backdrop-filter:blur(4px);display:flex;align-items:center;justify-content:center;padding:24px}
.lss-dialog{width:520px;max-width:100%;max-height:80vh;overflow:auto;padding:22px;border-radius:12px;background:var(--app-surface-bg,#fff);box-shadow:0 16px 70px #0003}
.lss-model-dialog{width:760px}.lss-dialog-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:18px}.lss-dialog-heading p{font-size:11px}
.lss-dialog.lss-scope-dialog{width:820px;max-height:calc(100dvh - 48px);padding:28px 30px 0;border-radius:16px;display:flex;flex-direction:column;overflow:hidden;font-size:14px}
.lss-scope-dialog .lss-dialog-heading{flex-shrink:0;margin-bottom:22px}
.lss-scope-dialog .lss-dialog-heading h4{font-size:24px;line-height:1.4;font-weight:650}
.lss-scope-dialog .lss-dialog-heading p{font-size:14px;margin-top:7px}
.lss-scope-dialog .lss-dialog-heading>button{width:38px;height:38px;font-size:17px;color:var(--app-text-secondary,#687582)}
.lss-scope-search{position:relative;flex-shrink:0;margin-bottom:24px}
.lss-scope-search>:is(i,svg){position:absolute;left:15px;top:50%;transform:translateY(-50%);color:var(--app-text-secondary,#687582);pointer-events:none}
.lss-scope-search input[type=search]{height:46px;padding:10px 14px 10px 43px;border-radius:8px;background:var(--app-surface-soft,#f7f8fa);font-size:14px}
.lss-scope-columns{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:30px;min-height:0;overflow:hidden}
.lss-scope-category{display:flex;flex-direction:column;min-width:0;min-height:0}
.lss-category-heading{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:12px;min-height:32px;flex-shrink:0}
.lss-category-heading h5{font-size:18px;white-space:nowrap;font-weight:650}.lss-category-heading h5 span{font-size:14px;font-weight:400;color:var(--app-text-secondary,#687582);margin-left:5px}
.lss-category-actions{display:flex;align-items:center;gap:6px}.lss-category-actions button{min-height:30px;padding:3px 12px;font-size:13px}
.lss-category-actions .lss-category-select{color:#079b57;border-color:#079b57;background:transparent}
.lss-category-actions .lss-category-clear{color:var(--app-text-secondary,#687582);border-color:transparent;background:transparent;padding-right:0}
.lss-scope-dialog .lss-chat-list{height:344px;min-height:0;overflow:auto;scrollbar-gutter:stable;scrollbar-width:thin;scrollbar-color:var(--app-text-tertiary,#b9bec5) var(--app-surface-soft,#f7f8fa);padding-right:6px}
.lss-scope-dialog .lss-chat-list::-webkit-scrollbar{width:6px}.lss-scope-dialog .lss-chat-list::-webkit-scrollbar-thumb{background:var(--app-text-tertiary,#b9bec5);border-radius:6px}.lss-scope-dialog .lss-chat-list::-webkit-scrollbar-button{display:none}
.lss-scope-dialog .lss-chat-list .lss-check{min-height:54px;padding:12px 14px;gap:16px;border:0;border-radius:6px;margin-bottom:3px;font-size:16px;cursor:pointer}
.lss-scope-dialog .lss-chat-list .lss-check:hover{background:var(--app-surface-soft,#f7f8fa)}
.lss-scope-dialog .lss-chat-list .lss-check.is-selected{background:var(--app-accent-soft,#edf8f1)}
.lss-scope-dialog .lss-check input{width:18px;height:18px;cursor:pointer}
.lss-scope-dialog .lss-check span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.lss-scope-footer{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-shrink:0;margin:30px -30px 0;padding:24px 30px;border-top:1px solid var(--app-border,#e7e9ed)}
.lss-scope-footer strong{font-size:16px;font-weight:600}.lss-scope-footer p{font-size:13px;margin-top:5px}
.lss-scope-footer-actions{display:flex;gap:12px}.lss-scope-footer-actions button{min-width:100px;min-height:44px;padding:10px 18px;font-size:15px}.lss-scope-footer-actions .lss-primary{min-width:116px;min-height:44px;font-size:15px}
.lss-scope-dialog :is(button,input,.lss-chat-list):focus-visible{outline:2px solid #079b57;outline-offset:2px}
@media(max-width:700px){.lss-dialog.lss-scope-dialog{padding:22px 20px 0}.lss-scope-columns{gap:18px}.lss-category-heading{flex-wrap:wrap}.lss-category-heading h5{font-size:15px}.lss-category-actions{width:100%}.lss-scope-dialog .lss-chat-list .lss-check{padding:10px 8px;gap:10px;font-size:14px}.lss-scope-footer{margin:20px -20px 0;padding:16px 20px}.lss-scope-footer-actions{gap:8px}.lss-scope-footer-actions button{min-width:64px;padding:8px 12px}}
@media(max-width:480px){.lss-overlay:has(.lss-scope-dialog){padding:12px}.lss-dialog.lss-scope-dialog{padding:20px 16px 0;max-height:calc(100dvh - 24px)}.lss-scope-columns{grid-template-columns:1fr;overflow:auto;gap:20px}.lss-scope-category{min-height:230px}.lss-category-heading{flex-wrap:nowrap}.lss-category-actions{width:auto}.lss-scope-dialog .lss-chat-list{height:210px}.lss-scope-footer{margin:18px -16px 0;padding:16px;flex-wrap:wrap}.lss-scope-footer-actions{margin-left:auto}}
.lss-dialog>input{margin:12px 0}.lss-empty{padding:24px;text-align:center}
.lss-models{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.lss-model{border:1px solid var(--app-border,#e7e9ed);border-radius:8px;padding:15px;display:flex;flex-direction:column;min-width:0}
.lss-model.selected{border-color:#079b57;background:var(--app-surface-soft,#f7f8fa)}
.lss-model small{color:#079b57;font-size:10px;font-weight:400}.lss-model p{font-size:11px}
.lss-model .lss-row{align-items:flex-start}.lss-model-actions{margin-top:auto;padding-top:12px}
.lss-source{font-size:10px;color:var(--app-text-secondary);margin-top:10px;overflow-wrap:anywhere}.lss-source a{color:#079b57}
@container (max-width:600px){.lss-heading{flex-wrap:wrap}.lss-start{align-items:stretch;flex-direction:column}.lss-start>button{width:100%}.lss-time-row{flex-wrap:wrap}.lss-time-row>.lss-note{width:100%}.lss-model-summary{flex-wrap:wrap}.lss-model-summary>.lss-grow{min-width:180px}.lss-step{padding:15px}.lss-advanced>summary>.lss-note{font-size:9px}.lss-advanced .lss-row{flex-wrap:wrap}}
@media(max-width:600px){.lss-models,.lss-grid{grid-template-columns:1fr}.lss-row{flex-wrap:wrap}.lss-dialog{padding:16px}.lss-model-dialog{width:100%}}
@media(prefers-reduced-motion:reduce){.agent-icon-spin{animation:none}}
</style>
