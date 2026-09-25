<template>
  <section class="page overflow-page" data-module="overflow">
    <header class="page-head">
      <div>
        <h2>雨天溢流与调蓄池监控</h2>
        <p class="page-desc">
          雨天溢流事件登记与处置进度、各站点调蓄池液位分级同屏呈现；看板与事件列表共用同一数据源，刷新后进度保持一致。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记溢流事件</button>
        <button class="btn" type="button" :disabled="loading" @click="reload">刷新看板</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card" :class="statClass(item.label)">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>站点</span>
        <select v-model="siteFilter">
          <option value="">全部站点</option>
          <option v-for="site in sites" :key="site" :value="site">{{ site }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>排列方式</span>
        <select v-model="sortMode">
          <option value="site">按站点排列</option>
          <option value="level">按液位越限排列</option>
        </select>
      </label>
      <label class="filter-item">
        <span>事件状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="s in statusOptions" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <label class="filter-item grow">
        <span>事件检索</span>
        <input v-model="keyword" placeholder="按事件编号 / 溢流口 / 站点检索" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <div v-if="errorMessage" class="board-banner error">
      <span>{{ errorMessage }}</span>
      <button class="link" type="button" @click="reload">重新加载</button>
    </div>

    <!-- 调蓄池液位看板：默认按站点分组；按液位排列时平铺，越限的排前面 -->
    <section class="board-section">
      <h3 class="section-title">
        调蓄池液位
        <small class="section-sub">
          阈值分级：达到「警戒液位」预警，达到「超限液位」立即应急；无数据 / 采集失败 / 重复上报单独标注
        </small>
      </h3>

      <div v-if="sortMode === 'site'">
        <div v-for="group in groups" :key="group['站点']" class="site-group">
          <div class="site-head">
            <strong>{{ group['站点'] }}</strong>
            <span class="site-meta">
              <span class="chip chip-danger">超限 {{ group['液位分级']['超限'] }}</span>
              <span class="chip chip-warn">警戒 {{ group['液位分级']['警戒'] }}</span>
              <span class="chip chip-failed">采集失败 {{ group['液位分级']['采集失败'] }}</span>
              <span class="chip chip-empty">无数据 {{ group['液位分级']['无数据'] }}</span>
              <span class="chip chip-normal">正常 {{ group['液位分级']['正常'] }}</span>
            </span>
            <span class="site-progress">
              事件进度：待处置 {{ group['事件待处置'] }} · 处置中 {{ group['事件处置中'] }} · 已处置 {{ group['事件已处置'] }}
            </span>
          </div>
          <div class="tank-grid">
            <article
              v-for="tank in group.tanks"
              :key="String(tank.id)"
              class="tank-card"
              :class="gradeClass(tank['液位等级'])"
            >
              <tank-card-body :tank="tank" @recollect="recollect" @report="reportLevel" />
            </article>
          </div>
        </div>
        <div v-if="!groups.length" class="board-empty">所选站点暂无调蓄池与溢流事件数据</div>
      </div>

      <div v-else class="tank-grid">
        <article
          v-for="tank in flatTanks"
          :key="String(tank.id)"
          class="tank-card"
          :class="gradeClass(tank['液位等级'])"
        >
          <div class="tank-site-tag">{{ tank['站点'] }}</div>
          <tank-card-body :tank="tank" @recollect="recollect" @report="reportLevel" />
        </article>
        <div v-if="!flatTanks.length" class="board-empty">所选站点暂无调蓄池数据</div>
      </div>
    </section>

    <!-- 雨天溢流事件列表：与看板共用 /api/overflow 数据，刷新后进度必然一致 -->
    <section class="board-section">
      <h3 class="section-title">
        雨天溢流事件
        <small class="section-sub">看板站点块上的处置进度直接取自本表，任何状态变更两处同步刷新</small>
      </h3>
      <table class="data-table">
        <thead>
          <tr>
            <th>事件编号</th>
            <th>站点</th>
            <th>溢流口</th>
            <th>发生时间</th>
            <th>处置人</th>
            <th>处置措施</th>
            <th>最新进度</th>
            <th>处置状态</th>
            <th>更新时间</th>
            <th>可执行动作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in events" :key="String(row.id)">
            <td>{{ row['事件编号'] }}</td>
            <td>{{ row['站点'] }}</td>
            <td>{{ row['溢流口'] }}</td>
            <td>{{ row['发生时间'] }}</td>
            <td>{{ row['处置人'] || '—' }}</td>
            <td>{{ row['处置措施'] || '—' }}</td>
            <td class="progress-note">{{ row['进度备注'] || '—' }}</td>
            <td>
              <span class="status-tag" :class="statusClass(row.status)">{{ row.status }}</span>
            </td>
            <td>{{ row['更新时间'] }}</td>
            <td class="row-actions">
              <button v-if="row.status === '待处置'" class="link" type="button" @click="startAction(row)">
                开始处置
              </button>
              <button v-if="row.status !== '已处置'" class="link" type="button" @click="progressAction(row)">
                更新进度
              </button>
              <button v-if="row.status !== '已处置'" class="link" type="button" @click="finishAction(row)">
                完成处置
              </button>
              <span v-else class="action-done">已闭环</span>
            </td>
          </tr>
          <tr v-if="!events.length">
            <td colspan="10" class="empty-state">当前条件下暂无溢流事件，雨天发现溢流请先「登记溢流事件」</td>
          </tr>
        </tbody>
      </table>
      <footer class="page-foot">
        <span>共 {{ eventTotal }} 条溢流事件{{ siteFilter ? `（${siteFilter}）` : '' }}</span>
        <span v-if="noticeMessage" :class="noticeOk ? 'ok-text' : 'error-text'">{{ noticeMessage }}</span>
      </footer>
    </section>

    <!-- 登记溢流事件 -->
    <div v-if="createOpen" class="modal-mask" @click.self="closeCreate">
      <div class="modal">
        <h3>登记雨天溢流事件</h3>
        <div v-if="createError" class="modal-error">{{ createError }}</div>
        <label class="modal-field">
          <span>站点 *</span>
          <input v-model="createForm['站点']" list="overflow-site-list" placeholder="如：1号雨水泵站" />
          <datalist id="overflow-site-list">
            <option v-for="site in sites" :key="site" :value="site" />
          </datalist>
        </label>
        <label class="modal-field">
          <span>溢流口 *</span>
          <input v-model="createForm['溢流口']" placeholder="如：1号溢流口" />
        </label>
        <label class="modal-field">
          <span>发生时间 *</span>
          <input v-model="createForm['发生时间']" placeholder="YYYY-MM-DD HH:mm" />
        </label>
        <label class="modal-field">
          <span>溢流原因</span>
          <input v-model="createForm['溢流原因']" placeholder="如：暴雨超过管网输送能力" />
        </label>
        <label class="modal-field">
          <span>上报人</span>
          <input v-model="createForm['上报人']" placeholder="默认记为值班员" />
        </label>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="closeCreate">取消</button>
          <button class="btn primary" type="button" :disabled="submitting" @click="submitCreate">
            {{ submitting ? '提交中…' : '确认登记' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 更新进度 / 开始处置 / 完成处置 共用的处置弹窗 -->
    <div v-if="actionOpen" class="modal-mask" @click.self="closeAction">
      <div class="modal">
        <h3>{{ actionForm.action }} · {{ actionTarget?.['事件编号'] }}</h3>
        <p class="modal-tip">{{ actionTip }}</p>
        <div v-if="actionError" class="modal-error">{{ actionError }}</div>
        <label class="modal-field">
          <span>处置人</span>
          <input v-model="actionForm['处置人']" :placeholder="actionTarget?.['处置人'] ? `当前：${actionTarget['处置人']}` : '请填写到场处置人'" />
        </label>
        <label v-if="actionForm.action !== '完成处置'" class="modal-field">
          <span>进度备注 *</span>
          <textarea v-model="actionForm['进度备注']" rows="3" placeholder="说明当前处置进展，刷新后看板同步显示" />
        </label>
        <template v-else>
          <label class="modal-field">
            <span>处置措施 *</span>
            <textarea v-model="actionForm['处置措施']" rows="3" placeholder="说明已采取的关闸、抽排、消杀等措施" />
          </label>
          <label class="modal-field">
            <span>闭环备注</span>
            <input v-model="actionForm['进度备注']" placeholder="默认：处置完成，现场恢复正常" />
          </label>
        </template>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="closeAction">取消</button>
          <button class="btn primary" type="button" :disabled="submitting" @click="submitAction">
            {{ submitting ? '提交中…' : '确认' }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Grade = '超限' | '警戒' | '正常' | '采集失败' | '无数据'
type Tank = Record<string, string | number | null> & {
  id: number
  '调蓄池编号': string
  '调蓄池名称': string
  '站点': string
  '液位': number | null
  '警戒液位': number
  '超限液位': number
  '采集时间': string | null
  '采集状态': string
  '上次液位': number | null
  '上次采集时间': string | null
  '重复上报': boolean
  '液位等级': Grade
  '等级提示': string
  '液位百分比': number | null
  '越限': boolean
}
type OverflowEvent = Record<string, string | number | null> & {
  id: number
  '事件编号': string
  '站点': string
  '溢流口': string
  '发生时间': string
  '处置人': string
  '处置措施': string
  '进度备注': string
  status: string
  '更新时间': string
}
type BoardGroup = {
  '站点': string
  '调蓄池数': number
  '液位分级': Record<Grade, number>
  '事件待处置': number
  '事件处置中': number
  '事件已处置': number
  tanks: Tank[]
}
type Board = {
  stats: { label: string; value: number }[]
  sites: string[]
  groups: BoardGroup[]
  tanks: Tank[]
}

const ENDPOINT = '/api/overflow'
const statusOptions = ['待处置', '处置中', '已处置']

const stats = ref<{ label: string; value: number }[]>([
  { label: '溢流事件', value: 0 },
  { label: '待处置', value: 0 },
  { label: '处置中', value: 0 },
  { label: '调蓄池', value: 0 },
  { label: '液位超限', value: 0 },
  { label: '液位警戒', value: 0 },
  { label: '采集异常', value: 0 },
])
const sites = ref<string[]>([])
const groups = ref<BoardGroup[]>([])
const flatTanks = ref<Tank[]>([])
const events = ref<OverflowEvent[]>([])
const eventTotal = ref(0)

const siteFilter = ref('')
const sortMode = ref<'site' | 'level'>('site')
const statusFilter = ref('')
const keyword = ref('')
const loading = ref(false)
const errorMessage = ref('')
const noticeMessage = ref('')
const noticeOk = ref(true)
let noticeTimer: ReturnType<typeof setTimeout> | undefined

// 调蓄池卡片单独抽成内联组件，两种排列方式共用同一套展示与兜底操作
const TankCardBody = defineComponent({
  name: 'TankCardBody',
  props: { tank: { type: Object as () => Tank, required: true } },
  emits: ['recollect', 'report'],
  setup(props, { emit }) {
    const reportOpen = ref(false)
    const reportLevel = ref('')
    const reportTime = ref('')
    const reportError = ref('')

    function submit() {
      emit('report', props.tank, reportLevel.value, reportTime.value, reportOpen, reportError)
    }
    return () =>
      h('div', { class: 'tank-body' }, [
        h('div', { class: 'tank-name' }, props.tank['调蓄池名称']),
        h('div', { class: 'tank-no' }, props.tank['调蓄池编号']),
        h(
          'div',
          { class: 'tank-level' },
          props.tank['液位'] === null || props.tank['液位'] === undefined
            ? [h('span', { class: 'level-na' }, '—')]
            : [
                h('strong', null, String(props.tank['液位'])),
                h('span', { class: 'level-unit' }, 'm'),
              ],
        ),
        h('div', { class: 'tank-thresholds' }, `警戒 ${props.tank['警戒液位']}m / 超限 ${props.tank['超限液位']}m`),
        // 阈值分级条：用超限液位归一化，越限部分红色加深
        h('div', { class: 'level-track' }, [
          h('div', {
            class: ['level-fill', `fill-${gradeKey(props.tank['液位等级'])}`],
            style: props.tank['液位百分比'] === null ? {} : { width: `${Math.min(props.tank['液位百分比'], 100)}%` },
          }),
        ]),
        h('div', { class: ['grade-tag', `grade-${gradeKey(props.tank['液位等级'])}`] }, props.tank['液位等级']),
        h('div', { class: 'tank-hint' }, props.tank['等级提示']),
        h(
          'div',
          { class: 'tank-time' },
          props.tank['采集时间'] ? `采集时间：${props.tank['采集时间']}` : '采集时间：—',
        ),
        props.tank['上次液位'] !== null
          ? h('div', { class: 'tank-last' }, `上次成功：${props.tank['上次液位']}m（${props.tank['上次采集时间'] || '时间未知'}）`)
          : null,
        props.tank['液位等级'] === '采集失败'
          ? h('button', { class: 'btn mini warning', type: 'button', onClick: () => emit('recollect', props.tank) }, '重新采集')
          : null,
        h(
          'button',
          {
            class: 'link mini-link',
            type: 'button',
            onClick: () => {
              reportOpen.value = !reportOpen.value
              reportError.value = ''
            },
          },
          reportOpen.value ? '收起补录' : props.tank['液位等级'] === '无数据' ? '手动补录液位' : '补录液位',
        ),
        reportOpen.value
          ? h('div', { class: 'report-form' }, [
              h('input', {
                value: reportLevel.value,
                placeholder: '液位数值（m）',
                onInput: (e: Event) => (reportLevel.value = (e.target as HTMLInputElement).value),
              }),
              h('input', {
                value: reportTime.value,
                placeholder: '采集时间 YYYY-MM-DD HH:mm（可留空）',
                onInput: (e: Event) => (reportTime.value = (e.target as HTMLInputElement).value),
              }),
              reportError.value ? h('div', { class: 'form-error' }, reportError.value) : null,
              h('button', { class: 'btn mini primary', type: 'button', onClick: submit }, '提交补录'),
            ])
          : null,
      ])
  },
})

function gradeKey(grade: Grade): string {
  return { 超限: 'danger', 警戒: 'warn', 正常: 'normal', 采集失败: 'failed', 无数据: 'empty' }[grade]
}
function gradeClass(grade: Grade): string {
  return `grade-${gradeKey(grade)}`
}
function statusClass(status: string): string {
  if (status === '待处置') return 'status-pending'
  if (status === '处置中') return 'status-doing'
  return 'status-done'
}
function statClass(label: string): string {
  const hit = stats.value.find((item) => item.label === label && item.value > 0)
  if (!hit) return ''
  if (label === '液位超限') return 'stat-danger'
  if (label === '待处置' || label === '液位警戒' || label === '采集异常') return 'stat-warn'
  if (label === '处置中') return 'stat-doing'
  return ''
}

function resetFilters() {
  siteFilter.value = ''
  sortMode.value = 'site'
  statusFilter.value = ''
  keyword.value = ''
  void reload()
}

function showNotice(message: string, ok = true) {
  noticeMessage.value = message
  noticeOk.value = ok
  clearTimeout(noticeTimer)
  noticeTimer = setTimeout(() => (noticeMessage.value = ''), 5000)
}

// 看板（统计 + 调蓄池分级）与事件列表并行取数，共用同一后端数据源；
// 任意处置动作之后整页重载，刷新浏览器后两处状态也仍然一致。
async function reload() {
  loading.value = true
  errorMessage.value = ''
  try {
    const boardQuery = new URLSearchParams()
    if (siteFilter.value) boardQuery.set('site', siteFilter.value)
    boardQuery.set('sort', sortMode.value)
    const eventQuery = new URLSearchParams()
    if (siteFilter.value) eventQuery.set('site', siteFilter.value)
    if (statusFilter.value) eventQuery.set('status', statusFilter.value)
    if (keyword.value.trim()) eventQuery.set('keyword', keyword.value.trim())
    eventQuery.set('size', '100')

    const [boardRes, eventRes] = await Promise.all([
      request(`${ENDPOINT}/board?${boardQuery.toString()}`),
      request(`${ENDPOINT}/events?${eventQuery.toString()}`),
    ])
    if (!boardRes.ok || !eventRes.ok) {
      throw new Error('看板数据读取失败，请检查后端服务后刷新重试')
    }
    const board = (await boardRes.json()) as Board
    const page = await eventRes.json()
    stats.value = board.stats
    sites.value = board.sites
    groups.value = board.groups
    flatTanks.value = board.tanks
    events.value = (page.items ?? []) as OverflowEvent[]
    eventTotal.value = page.total ?? events.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '看板数据读取失败'
    stats.value.forEach((item) => (item.value = 0))
    groups.value = []
    flatTanks.value = []
    events.value = []
    eventTotal.value = 0
  } finally {
    loading.value = false
  }
}

// ------------------------------------------------------------- 登记溢流事件
const createOpen = ref(false)
const submitting = ref(false)
const createError = ref('')
const createForm = ref<Record<string, string>>({ 站点: '', 溢流口: '', 发生时间: '', 溢流原因: '', 上报人: '' })

function openCreate() {
  createForm.value = { 站点: siteFilter.value, 溢流口: '', 发生时间: '', 溢流原因: '', 上报人: '' }
  createError.value = ''
  createOpen.value = true
}
function closeCreate() {
  createOpen.value = false
}
async function submitCreate() {
  createError.value = ''
  submitting.value = true
  try {
    const res = await request(`${ENDPOINT}/events`, {
      method: 'POST',
      body: JSON.stringify({ values: createForm.value }),
    })
    const payload = await res.json()
    if (!payload.ok) {
      // 缺字段、重复上报的兜底说明直接展示后端口径
      createError.value = payload.message
      return
    }
    createOpen.value = false
    showNotice(payload.message, true)
    await reload()
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '溢流事件登记失败'
  } finally {
    submitting.value = false
  }
}

// ------------------------------------------------------------- 处置进度流转
const actionOpen = ref(false)
const actionTarget = ref<OverflowEvent | null>(null)
const actionForm = ref<Record<string, string>>({})
const actionError = ref('')

const actionTip = computed(() => {
  switch (actionForm.value.action) {
    case '开始处置':
      return '填写到场处置人后开始应急处置，事件进入「处置中」。'
    case '更新进度':
      return '补充最新处置进展，看板站点块上的进度说明会同步更新。'
    default:
      return '填写实际处置措施并闭环事件，闭环后不可再更新进度。'
  }
})

function startAction(row: OverflowEvent) {
  openAction(row, { action: '开始处置', 处置人: row['处置人'] || '', 进度备注: '' })
}
function progressAction(row: OverflowEvent) {
  openAction(row, { action: '更新进度', 处置人: row['处置人'] || '', 进度备注: '' })
}
function finishAction(row: OverflowEvent) {
  openAction(row, { action: '完成处置', 处置人: row['处置人'] || '', 处置措施: row['处置措施'] || '', 进度备注: '' })
}
function openAction(row: OverflowEvent, form: Record<string, string>) {
  actionTarget.value = row
  actionForm.value = form
  actionError.value = ''
  actionOpen.value = true
}
function closeAction() {
  actionOpen.value = false
  actionTarget.value = null
}
async function submitAction() {
  if (!actionTarget.value) return
  actionError.value = ''
  submitting.value = true
  try {
    const res = await request(`${ENDPOINT}/events/${actionTarget.value.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: actionForm.value }),
    })
    const payload = await res.json()
    if (!payload.ok) {
      actionError.value = payload.message
      return
    }
    actionOpen.value = false
    showNotice(payload.message, true)
    await reload()
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '处置动作提交失败'
  } finally {
    submitting.value = false
  }
}

// ------------------------------------------------------------- 调蓄池兜底操作
async function recollect(tank: Tank) {
  try {
    const res = await request(`${ENDPOINT}/tanks/${tank.id}/recollect`, { method: 'POST', body: JSON.stringify({}) })
    const payload = await res.json()
    showNotice(payload.message, Boolean(payload.ok))
    await reload()
  } catch (error) {
    showNotice(error instanceof Error ? error.message : '重新采集失败', false)
  }
}

async function reportLevel(
  tank: Tank,
  level: string,
  collectedAt: string,
  openRef: { value: boolean },
  errorRef: { value: string },
) {
  errorRef.value = ''
  const values: Record<string, string> = { 液位: level }
  if (collectedAt.trim()) values['采集时间'] = collectedAt.trim()
  try {
    const res = await request(`${ENDPOINT}/tanks/${tank.id}/report`, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = await res.json()
    if (!payload.ok) {
      // 重复上报、非数字等兜底说明回显到卡片上，不关闭补录框
      errorRef.value = payload.message
      showNotice(payload.message, false)
      return
    }
    openRef.value = false
    showNotice(payload.message, true)
    await reload()
  } catch (error) {
    errorRef.value = error instanceof Error ? error.message : '液位补录失败'
  }
}

onMounted(reload)
</script>
