import assert from 'node:assert/strict'
import test from 'node:test'

// 应用内「高级功能」弹窗直接吃官网 pro-demos 引擎的清单：这里守住三处共用的数据契约
import {
  PRO_BY_KEY,
  PRO_GROUPS,
  PRO_HERO_MODULES,
  PRO_ITEMS,
  PRO_TOTAL
} from '../../website/assets/js/pro-demos/catalog.js'

test('高级版清单：共 54 项，key 唯一，每项带 name / caption / index / group', () => {
  assert.equal(PRO_TOTAL, 54)
  assert.equal(PRO_ITEMS.length, 54)

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

test('分组顺序固定为 edit / add / action / moments / group / contact / alert，且每项 group 与所在分组一致', () => {
  assert.deepEqual(
    PRO_GROUPS.map((g) => g.key),
    ['edit', 'add', 'action', 'moments', 'group', 'contact', 'alert']
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

test('官网首屏五模块视图：项数合计为 54，群聊 / 联系人 / 提醒 合并为末尾一栏', () => {
  assert.equal(PRO_HERO_MODULES.reduce((n, m) => n + m.items.length, 0), 54)
  assert.equal(PRO_HERO_MODULES.length, 5)
  const last = PRO_HERO_MODULES[PRO_HERO_MODULES.length - 1]
  assert.equal(last.name, '群聊、联系人与提醒')
  assert.deepEqual(
    [...new Set(last.items.map((it) => it.group))],
    ['group', 'contact', 'alert']
  )
})
