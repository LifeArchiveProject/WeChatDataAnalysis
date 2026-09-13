import assert from 'node:assert/strict'
import test from 'node:test'

// 应用内「高级功能」弹窗直接吃官网 pro-demos 引擎的清单：这里守住三处共用的数据契约
import {
  PRO_BY_KEY,
  PRO_GROUPS,
  PRO_ITEMS,
  PRO_LOCAL_ITEMS,
  PRO_TOTAL
} from '../../website/assets/js/pro-demos/catalog.js'

test('高级版清单：共 61 项，key 唯一，每项带 name / caption / index / group', () => {
  assert.equal(PRO_TOTAL, 61)
  assert.equal(PRO_ITEMS.length, 61)

  const keys = PRO_ITEMS.map((it) => it.key)
  assert.equal(new Set(keys).size, keys.length, 'key 有重复')
  assert.equal(Object.keys(PRO_BY_KEY).length, keys.length)

  PRO_ITEMS.forEach((it, i) => {
    assert.ok(typeof it.key === 'string' && it.key, `第 ${i + 1} 项缺 key`)
    assert.ok(typeof it.name === 'string' && it.name, `${it.key} 缺 name`)
    assert.ok(typeof it.caption === 'string' && it.caption, `${it.key} 缺 caption`)
    assert.equal(it.index, i + 1, `${it.key} 的全局序号不连续`)
    assert.ok(typeof it.group === 'string' && it.group, `${it.key} 缺 group`)
    assert.equal(PRO_BY_KEY[it.key], it)
  })
})

test('分组顺序固定为 edit / add / action / moments / group / contact / automation，且每项 group 与所在分组一致', () => {
  assert.deepEqual(
    PRO_GROUPS.map((g) => g.key),
    ['edit', 'add', 'action', 'moments', 'group', 'contact', 'automation']
  )
  for (const g of PRO_GROUPS) {
    assert.ok(g.label && g.tag, `${g.key} 缺 label / tag`)
    assert.ok(g.items.length > 0, `${g.key} 分组为空`)
    for (const it of g.items) {
      assert.equal(it.group, g.key)
      assert.equal(it.groupLabel, g.label)
      assert.equal(it.groupTag, g.tag)
    }
  }
  assert.equal(PRO_GROUPS.reduce((n, g) => n + g.items.length, 0), PRO_TOTAL)
})

test('每项能力都带场景与需求（use / need），否则动画只演操作、看不出用途', () => {
  const missing = PRO_ITEMS.filter((it) => !it.use || !it.need)
  assert.deepEqual(missing.map((it) => it.key), [], '缺少 use/need 的能力')
  for (const it of PRO_ITEMS) {
    assert.ok(it.use.length <= 8, `${it.key} 的场景标签过长：${it.use}`)
    assert.ok(it.need.length >= 8 && it.need.length <= 34, `${it.key} 的需求句长度不合适：${it.need}`)
  }
})

test('每项都带 story（场景编写依据，首屏不显示）、flow（首屏场景解说的三步）与可选 edge', () => {
  for (const it of PRO_ITEMS) {
    assert.ok(typeof it.story === 'string' && it.story.length >= 12 && it.story.length <= 60, `${it.key} 的场景陈述长度不合适：${it.story}`)
    assert.ok(Array.isArray(it.flow) && it.flow.length === 3, `${it.key} 的工作流不是三步`)
    for (const step of it.flow) {
      assert.ok(typeof step === 'string' && step.length > 0 && step.length <= 12, `${it.key} 的工作流步骤过长：${step}`)
    }
    if (it.edge !== undefined) assert.ok(typeof it.edge === 'string' && it.edge.length <= 34, `${it.key} 的边界句过长`)
  }
})

test('回写类与真实动作的边界：直接回写微信本地库、可还原的恰好 27 项', () => {
  assert.equal(PRO_LOCAL_ITEMS.length, 27)
  const localKeys = PRO_LOCAL_ITEMS.map((it) => it.key)
  // 消息修改 8 + 消息补录 17 + 这两项会话状态
  assert.ok(localKeys.includes('chat-mark-read'))
  assert.ok(localKeys.includes('chat-set-mute'))
  for (const it of PRO_ITEMS) {
    const expected = it.group === 'edit' || it.group === 'add' || it.key === 'chat-mark-read' || it.key === 'chat-set-mute'
    assert.equal(it.local, expected, `${it.key} 的本地/真实归类不对`)
  }
})

test('联系人变化记录不得写成「谁删了你」：整份清单里不出现单删检测口径', () => {
  const banned = ['谁删了你', '单删', '清粉', '删了我', '检测对方']
  for (const it of PRO_ITEMS) {
    const text = [it.name, it.caption, it.use, it.need, it.story, it.edge, ...(it.flow || [])].filter(Boolean).join(' ')
    for (const word of banned) {
      assert.ok(!text.includes(word), `${it.key} 的文案里出现了越界表述：${word}`)
    }
  }
})

test('每项能力都有对应的演示场景，且没有对不上清单的孤儿场景', async () => {
  const mod = await import('../../website/assets/js/pro-demos/index.js')
  assert.deepEqual(mod.missingScenes(), [], '这些能力还没有场景')
  const orphans = Object.keys(mod.SCENES).filter((key) => !PRO_BY_KEY[key])
  assert.deepEqual(orphans, [], '这些场景在清单里找不到对应能力')
})
