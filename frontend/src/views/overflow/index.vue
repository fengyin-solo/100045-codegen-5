<template>
  <section class="page" data-module="overflow">
    <header class="page-head">
      <div>
        <h2>雨天溢流与调蓄池监控</h2>
        <p class="page-desc">同一张看板汇总雨天溢流事件的登记与处置进度、各调蓄池液位越限分级；液位无数据、采集失败、重复上报均有兜底提示。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="showForm = !showForm">
          {{ showForm ? '收起登记表单' : '登记溢流事件' }}
        </button>
        <button class="btn" type="button" @click="reload">刷新看板</button>
      </div>
    </header>

    <!-- 事件登记：提交后整体重拉看板，进度与列表始终同源 -->
    <form v-if="showForm" class="create-panel" @submit.prevent="submitCreate">
      <div class="create-grid">
        <label>
          <span>站点 *</span>
          <select v-model="form.站点编号">
            <option value="" disabled>请选择调蓄池站点</option>
            <option v-for="site in sites" :key="site.站点编号" :value="site.站点编号">
              {{ site.站点编号 }} {{ site.站点名称 }}
            </option>
          </select>
        </label>
        <label>
          <span>溢流点位 *</span>
          <input v-model="form.溢流点位" placeholder="如：2#溢流口" />
        </label>
        <label>
          <span>发生时间 *</span>
          <input v-model="form.发生时间" type="datetime-local" />
        </label>
        <label>
          <span>溢流量</span>
          <input v-model="form.溢流量" placeholder="如：约120m³" />
        </label>
        <label>
          <span>上报人 *</span>
          <input v-model="form.上报人" placeholder="值班人员姓名" />
        </label>
        <label class="full">
          <span>事件描述</span>
          <textarea v-model="form.事件描述" rows="2" placeholder="溢流情形、现场处置与雨况说明"></textarea>
        </label>
      </div>
      <div class="page-actions" style="margin-top: 10px">
        <button class="btn primary" type="submit" :disabled="submitting">
          {{ submitting ? '提交中…' : '提交登记' }}
        </button>
        <button class="btn ghost" type="button" @click="resetForm">清空</button>
        <span v-if="formMessage" class="form-message" :class="{ ok: formOk }">{{ formMessage }}</span>
      </div>
    </form>

    <!-- 统计卡片：数字全部来自同一次看板聚合 -->
    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value" :style="item.tone ? `color:${item.tone}` : ''">{{ item.value }}</strong>
      </article>
    </div>

    <div class="board-controls">
      <label class="filter-item">
        <span>站点</span>
        <select v-model="siteFilter" @change="reload">
          <option value="">全部站点</option>
          <option v-for="site in sites" :key="site.站点编号" :value="site.站点编号">
            {{ site.站点编号 }} {{ site.站点名称 }}
          </option>
        </select>
      </label>
      <label class="filter-item">
        <span>排列方式</span>
        <select v-model="sortMode" @change="reload">
          <option value="site">按站点排列</option>
          <option value="severity">按越限严重程度排列</option>
        </select>
      </label>
      <label class="filter-item">
        <span>事件状态</span>
        <select v-model="eventStatusFilter">
          <option value="">全部进度</option>
          <option v-for="name in eventStatuses" :key="name" :value="name">{{ name }}</option>
        </select>
      </label>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </div>

    <h3 class="board-section-title">调蓄池液位（{{ stations.length }} 座）</h3>
    <div class="site-grid">
      <article
        v-for="card in stations"
        :key="card.站点编号"
        class="site-card"
        :class="cardClass(card)"
      >
        <div>
          <span class="site-name">{{ card.站点名称 }}</span>
          <span class="site-code">{{ card.站点编号 }}</span>
          <span class="level-badge" :class="badgeClass(card)">{{ levelLabel(card) }}</span>
        </div>
        <template v-if="card.液位 !== null && card.液位 !== undefined">
          <div class="level-bar">
            <span :class="barClass(card)" :style="`width:${levelPercent(card)}%`"></span>
          </div>
          <div class="site-meta">
            当前液位 <strong>{{ Number(card.液位).toFixed(2) }}m</strong>
            <span v-if="card.data_state === 'failed'" class="error-text">（回退值）</span>
            · 上报 {{ card.上报时间 }}
          </div>
          <div class="site-meta">预警 ≥ {{ card.预警液位 }}m · 报警 ≥ {{ card.报警液位 }}m</div>
        </template>
        <template v-else>
          <div class="level-bar"><span class="unknown" style="width:0%"></span></div>
          <div class="site-meta">当前液位 --m · 上报 --</div>
          <div class="site-meta">预警 ≥ {{ card.预警液位 }}m · 报警 ≥ {{ card.报警液位 }}m</div>
        </template>
        <div v-for="tip in card.提示" :key="tip" class="site-tip">⚠ {{ tip }}</div>
      </article>
      <div v-if="!stations.length" class="empty-state" style="grid-column: 1 / -1">
        没有符合站点筛选条件的调蓄池
      </div>
    </div>

    <h3 class="board-section-title">雨天溢流事件（{{ filteredEvents.length }} 件）</h3>
    <table class="data-table">
      <thead>
        <tr>
          <th>事件编号</th>
          <th>站点</th>
          <th>溢流点位</th>
          <th>发生时间</th>
          <th>溢流量</th>
          <th>上报人</th>
          <th>处置状态</th>
          <th>处置进度</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in filteredEvents" :key="String(row.id)">
          <td>{{ row.事件编号 }}</td>
          <td>{{ row.站点编号 }}</td>
          <td>{{ row.溢流点位 }}</td>
          <td>{{ row.发生时间 }}</td>
          <td>{{ row.溢流量 || '—' }}</td>
          <td>{{ row.上报人 }}</td>
          <td><span class="status-pill">{{ row.status }}</span></td>
          <td class="progress-cell">
            <div class="progress-track"><span :style="`width:${row.progress}%`"></span></div>
            <span class="site-meta">{{ row.progress }}%</span>
          </td>
          <td class="row-actions">
            <button
              v-for="action in availableActions(row.status)"
              :key="action"
              class="link"
              type="button"
              :disabled="actionLoading === row.id"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <span v-if="!availableActions(row.status).length" class="site-meta">无</span>
          </td>
        </tr>
        <tr v-if="!filteredEvents.length">
          <td colspan="9" class="empty-state">
            {{ events.length ? '当前进度筛选下没有事件' : '暂无雨天溢流事件，可点击右上角登记' }}
          </td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>看板数据每次刷新整体重拉，处置进度与事件列表口径一致</span>
      <span v-if="lastUpdated" class="site-meta">最近刷新：{{ lastUpdated }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

const ENDPOINT = '/api/overflow'

type StationCard = {
  站点编号: string
  站点名称: string
  设计容积: string
  预警液位: number
  报警液位: number
  液位: number | null
  上报时间: string | null
  data_state: 'ok' | 'failed' | 'no_data'
  level_state: 'normal' | 'warning' | 'alarm' | null
  severity: string
  重复上报: number
  最近有效液位: number | null
  最近有效时间: string | null
  提示: string[]
}

type Site = { 站点编号: string; 站点名称: string }

type OverflowEvent = {
  id: number
  事件编号: string
  站点编号: string
  溢流点位: string
  发生时间: string
  溢流量: string
  上报人: string
  事件描述: string
  status: string
  progress: number
}

type Summary = {
  event_total: number
  todo: number
  doing: number
  done: number
  closed: number
  site_total: number
  alarm: number
  warning: number
  normal: number
  failed: number
  no_data: number
  duplicate: number
}

const eventStatuses = ['待处置', '处置中', '已处置', '已关闭']
const nextAction: Record<string, string[]> = {
  待处置: ['开始处置'],
  处置中: ['完成处置'],
  已处置: ['关闭归档'],
  已关闭: [],
}

const stations = ref<StationCard[]>([])
const events = ref<OverflowEvent[]>([])
const sites = ref<Site[]>([])
const summary = ref<Summary | null>(null)
const errorMessage = ref('')
const lastUpdated = ref('')
const siteFilter = ref('')
const sortMode = ref('site')
const eventStatusFilter = ref('')
const showForm = ref(false)
const submitting = ref(false)
const actionLoading = ref<number | null>(null)
const formMessage = ref('')
const formOk = ref(false)

const emptyForm = () => ({
  站点编号: '',
  溢流点位: '',
  发生时间: '',
  溢流量: '',
  上报人: '',
  事件描述: '',
})
const form = reactive(emptyForm())

function resetForm() {
  Object.assign(form, emptyForm())
  formMessage.value = ''
}

const statCards = computed(() => {
  const s = summary.value
  if (!s) return []
  return [
    { label: '溢流事件总数', value: s.event_total },
    { label: '待处置', value: s.todo, tone: s.todo ? '#b42318' : '' },
    { label: '处置中', value: s.doing, tone: s.doing ? '#d97706' : '' },
    { label: '已处置/关闭', value: s.done + s.closed },
    { label: '液位报警', value: s.alarm, tone: s.alarm ? '#dc2626' : '' },
    { label: '液位预警', value: s.warning, tone: s.warning ? '#d97706' : '' },
    { label: '采集失败/无数据', value: s.failed + s.no_data, tone: s.failed + s.no_data ? '#b45309' : '' },
    { label: '重复上报条数', value: s.duplicate, tone: s.duplicate ? '#b45309' : '' },
  ]
})

const filteredEvents = computed(() => {
  if (!eventStatusFilter.value) return events.value
  return events.value.filter((item) => item.status === eventStatusFilter.value)
})

function availableActions(status: string): string[] {
  return nextAction[status] ?? []
}

function cardClass(card: StationCard): string {
  if (card.data_state === 'failed') return 'data-failed'
  if (card.data_state === 'no_data') return 'data-nodata'
  return `level-${card.level_state ?? 'nodata'}`
}

function badgeClass(card: StationCard): string {
  if (card.data_state === 'failed') return 'failed'
  if (card.data_state === 'no_data') return 'nodata'
  return card.level_state ?? 'nodata'
}

function levelLabel(card: StationCard): string {
  if (card.data_state === 'failed') return '采集失败'
  if (card.data_state === 'no_data') return '暂无数据'
  return { normal: '液位正常', warning: '液位预警', alarm: '液位报警' }[card.level_state ?? 'normal'] ?? '未知'
}

function barClass(card: StationCard): string {
  if (card.data_state !== 'ok') return 'unknown'
  return card.level_state ?? 'unknown'
}

function levelPercent(card: StationCard): number {
  if (card.液位 === null || card.液位 === undefined) return 0
  // 以报警液位的 1.2 倍作为满刻度，直观区分预警/报警；上限封顶 100
  const full = Number(card.报警液位) * 1.2 || 1
  return Math.min(100, Math.round((Number(card.液位) / full) * 100))
}

async function loadSites() {
  try {
    const response = await request(`${ENDPOINT}/sites`)
    if (response.ok) {
      const payload = await response.json()
      sites.value = payload.items ?? []
    }
  } catch {
    // 站点清单拉不到时登记下拉为空，不阻断看板主体
    sites.value = []
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (siteFilter.value) query.set('site', siteFilter.value)
  query.set('sort', sortMode.value)
  try {
    const response = await request(`${ENDPOINT}/board?${query.toString()}`)
    if (!response.ok) {
      throw new Error(`看板接口返回 ${response.status}`)
    }
    const payload = await response.json()
    summary.value = payload.summary ?? null
    stations.value = payload.stations ?? []
    events.value = payload.events ?? []
    lastUpdated.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  } catch (error) {
    // 兜底：看板整体拉取失败时保留旧数据并显式提示，而不是白屏
    errorMessage.value = error instanceof Error ? error.message : '看板数据加载失败，请稍后重试'
  }
}

async function submitCreate() {
  formMessage.value = ''
  formOk.value = false
  submitting.value = true
  try {
    const response = await request(`${ENDPOINT}/events`, {
      method: 'POST',
      body: JSON.stringify({ values: { ...form } }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload) {
      throw new Error('溢流事件登记未生效，请稍后重试')
    }
    formMessage.value = payload.message ?? (payload.ok ? '登记成功' : '登记失败')
    formOk.value = Boolean(payload.ok)
    if (payload.ok) {
      resetForm()
      await reload()
    }
  } catch (error) {
    formMessage.value = error instanceof Error ? error.message : '溢流事件登记失败'
  } finally {
    submitting.value = false
  }
}

async function runAction(action: string, row: OverflowEvent) {
  errorMessage.value = ''
  actionLoading.value = row.id
  try {
    const response = await request(`${ENDPOINT}/events/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload || !payload.ok) {
      throw new Error(payload?.message ?? '处置动作未生效，请稍后重试')
    }
    // 动作生效后整体重拉：看板进度条、统计卡片、事件列表一次刷新到位
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '溢流事件处置失败'
  } finally {
    actionLoading.value = null
  }
}

onMounted(() => {
  void loadSites()
  void reload()
})
</script>
