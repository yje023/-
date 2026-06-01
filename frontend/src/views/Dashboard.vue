<template>
  <div class="cockpit">
    <!-- 顶部导航栏 -->
    <header class="cockpit-header">
      <div class="header-left">
        <el-button size="small" class="back-btn" @click="$router.push('/orgs')" title="进入系统后台">
          <el-icon><Menu /></el-icon>
        </el-button>
        <el-select v-model="filterYear" placeholder="考核年度" style="width:120px" @change="loadAll">
          <el-option v-for="y in years" :key="y" :label="String(y)" :value="y" />
        </el-select>
        <el-select v-model="filterPlanId" placeholder="考核方案" style="width:180px;margin-left:8px" clearable @change="loadAll">
          <el-option v-for="p in plans" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
      </div>
      <div class="header-title">绩效分析评估系统驾驶舱</div>
      <div class="header-right">
        <el-button size="small" ghost>镇街评价</el-button>
        <el-input v-model="globalSearch" placeholder="综合搜索..." size="small" style="width:160px;margin-left:8px" clearable />
      </div>
    </header>

    <!-- 三栏主体 -->
    <main class="cockpit-body">
      <!-- ========== 左侧 ========== -->
      <section class="panel-col">
        <!-- 任务解构 -->
        <div class="panel-card">
          <div class="card-title">任务解构管理</div>
          <div ref="sunburstChart" class="chart-box" style="height:200px"></div>
          <div class="card-stats-row">
            <div class="stat-item"><span class="stat-num">{{ decompStats.precise }}</span><span class="stat-label">精准解构数</span></div>
            <div class="stat-item"><span class="stat-num">{{ decompStats.declared }}</span><span class="stat-label">主动申报数</span></div>
          </div>
        </div>

        <!-- 2025考核结果 -->
        <div class="panel-card">
          <div class="card-title">
            {{ filterYear }}年 考核结果管理
            <div class="title-tabs">
              <span :class="{ active: resultTab === '正职' }" @click.stop="resultTab = '正职'">正职</span>
              <span :class="{ active: resultTab === '副职' }" @click.stop="resultTab = '副职'">副职</span>
            </div>
          </div>
          <div class="result-table-wrap">
            <table class="result-table">
              <thead><tr><th>排名</th><th>单位</th><th>姓名</th><th>得分</th><th>违纪</th><th>评优</th></tr></thead>
              <tbody>
                <tr v-for="r in filteredResults" :key="r.rank">
                  <td><span class="rank-badge">{{ r.rank }}</span></td>
                  <td>{{ r.unit_name }}</td><td>{{ r.cadre_name }}</td><td>{{ r.total_score }}</td>
                  <td><span :class="r.has_violation ? 'tag-bad' : 'tag-ok'">{{ r.has_violation ? '是' : '否' }}</span></td>
                  <td><span :class="r.is_excellent ? 'tag-good' : ''">{{ r.is_excellent ? '优' : '' }}</span></td>
                </tr>
                <tr v-if="!filteredResults.length"><td colspan="6" style="color:#64748b">暂无数据</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <!-- ========== 中间 ========== -->
      <section class="panel-col panel-center-col">
        <!-- 干部结构概览 -->
        <div class="panel-card">
          <div class="card-title">干部结构概览</div>
          <div class="cadre-overview">
            <div class="overview-left">
              <div ref="totalRingChart" class="chart-box" style="width:130px;height:130px"></div>
              <div class="total-num">{{ cadreStats.total }}</div>
              <div class="total-label">总人数</div>
            </div>
            <div class="overview-right">
              <div class="info-row"><span>男</span><span class="val">{{ cadreStats.gender?.male || 0 }}人</span></div>
              <div class="info-row"><span>女</span><span class="val">{{ cadreStats.gender?.female || 0 }}人</span></div>
              <div v-for="e in (cadreStats.education || []).slice(0,3)" :key="e.name" class="info-row">
                <span>{{ e.name }}</span><span class="val">{{ e.value }}人</span>
              </div>
              <div ref="ageBarChart" class="chart-box" style="height:90px;margin-top:6px"></div>
            </div>
          </div>
        </div>

        <!-- 政治与专业属性 -->
        <div class="panel-card">
          <div class="card-title">政治与专业属性</div>
          <div ref="politicalChart" class="chart-box" style="height:140px"></div>
          <div class="prop-grid-2col">
            <div ref="ethnicityChart" class="chart-box" style="height:130px"></div>
            <div ref="specialtyCloud" class="chart-box" style="height:130px"></div>
          </div>
          <div class="card-subtitle">擅长领域</div>
          <div ref="expertiseTree" class="chart-box" style="height:140px"></div>
        </div>
      </section>

      <!-- ========== 右侧 ========== -->
      <section class="panel-col">
        <!-- 重点任务管理 -->
        <div class="panel-card">
          <div class="card-title">重点任务管理</div>
          <div class="gauge-row">
            <div ref="progressGauge" class="chart-box" style="width:130px;height:130px"></div>
            <div class="gauge-info">
              <div class="gauge-num">{{ taskProgress.total }}</div>
              <div class="gauge-label">任务流转总数</div>
            </div>
          </div>
          <div class="status-cards">
            <div class="scard" v-for="sc in taskProgress.status_cards" :key="sc.label"
              :style="{borderLeftColor: sc.color==='green'?'var(--g-cyan)':sc.color==='cyan'?'var(--g-green)':sc.color==='orange'?'var(--g-orange)':'#ef4444'}">
              <div class="scard-num">{{ sc.value }} <small>({{ sc.rate }}%)</small></div>
              <div class="scard-label">{{ sc.label }}</div>
            </div>
          </div>
          <div class="dim-stats-mini">
            <span v-for="d in taskProgress.dim_stats" :key="d.name" class="dim-chip">{{ d.name }} {{ d.count }}</span>
          </div>
          <div class="card-subtitle">任务明细</div>
          <div class="mini-table-wrap">
            <table class="mini-table">
              <thead><tr><th>#</th><th>单位</th><th>任务</th><th>状态</th></tr></thead>
              <tbody>
                <tr v-for="(r, idx) in recentTasks.slice(0,8)" :key="idx">
                  <td>{{ idx + 1 }}</td><td>{{ r.unit_name }}</td>
                  <td class="ellipsis">{{ r.key_work }}</td>
                  <td><el-tag size="small" :type="r.action === '已打分' ? 'success' : 'warning'">{{ r.action }}</el-tag></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- 考核系统进度监控 -->
        <div class="panel-card">
          <div class="card-title">考核系统进度监控</div>
          <div ref="sankeyChart" class="chart-box" style="height:240px"></div>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { getDashboardOverview } from '../api/dashboard'
import { getPlans } from '../api/plan'
import http from '../api/index'

const filterYear = ref(2026); const filterPlanId = ref(null)
const globalSearch = ref(''); const resultTab = ref('正职')
const loading = ref(false)

let scrollTimer = null
function startResultScroll() {
  const wrap = document.querySelector('.result-table-wrap')
  if (!wrap) return
  let dir = 1
  scrollTimer = setInterval(function() {
    if (wrap.scrollTop + wrap.clientHeight >= wrap.scrollHeight) dir = -1
    if (wrap.scrollTop <= 0) dir = 1
    wrap.scrollTop += dir * 0.5
  }, 80)
}
const years = [2024, 2025, 2026, 2027]

const plans = ref([])
const overview = ref({ stats:{}, dim_stats:[], unit_completion:[], status_dist:{}, period_dist:{}, recent_activity:[] })
const decompStats = ref({ precise:0, declared:0, total:0 })
const cadreStats = ref({ total:0, gender:{}, education:[], political:[], ethnicity:[], specialty:[], expertise:[], age_groups:[] })
const taskProgress = ref({ total:0, status_cards:[], dim_stats:[], completion_rate:0 })
const results = ref([]); const flowData = ref({ nodes:[], links:[] }); const decompData = ref({ sunburst:[], dim_list:[] })

const recentTasks = computed(() => overview.value.recent_activity || [])
const filteredResults = computed(() =>
  results.value.length ? results.value.filter(r => r.position_type === resultTab.value) : []
)

const sunburstChart = ref(null); const totalRingChart = ref(null); const ageBarChart = ref(null)
const politicalChart = ref(null); const ethnicityChart = ref(null); const specialtyCloud = ref(null)
const expertiseTree = ref(null); const progressGauge = ref(null); const sankeyChart = ref(null)

let echarts = null; const chartInstances = []

async function initEC() {
  if (!echarts) { const m = await import('echarts'); echarts = m }
}
function disposeAll() { chartInstances.forEach(c => { try { c.dispose() } catch(_){} }); chartInstances.length = 0 }
function mk(refKey, opt) {
  if (!echarts || !refKey.value) return
  const i = echarts.init(refKey.value); i.setOption(opt); chartInstances.push(i); return i
}

const COLORS = ['#00d4ff','#a855f7','#f59e0b','#10b981','#ef4444','#3b82f6','#ec4899','#6366f1']

function charts() {
  nextTick(() => {
    disposeAll()

    // -- 任务解构旭日图 --
    const sd = decompData.value.sunburst || []
    if (sd.length) {
      const sunData = sd.map(function(d, i) {
        var kids = (d.children || []).map(function(c) { return { name: c.name, value: c.value } })
        return { name: d.name, value: d.value, itemStyle: { color: COLORS[i % 8] }, children: kids }
      })
      mk(sunburstChart, {
        tooltip: { trigger: 'item' },
        animationDuration: 1200, animationEasing: 'cubicOut',
        series: [{ type: 'sunburst', radius: ['15%', '82%'], data: sunData,
          label: { color: '#e2e8f0', fontSize: 9 }, itemStyle: { borderColor: '#0a0e27', borderWidth: 1 } }]
      })
    }

    // -- 总人数环形图 --
    var total = cadreStats.value.total || 0
    var totalData = total > 0
      ? [{ value: total, name: '总人数', itemStyle: { color: '#00d4ff' } }]
      : [{ value: 1, name: '暂无', itemStyle: { color: '#334155' } }]
    mk(totalRingChart, { animationDuration: 1000, animationEasing: 'cubicOut',
      series: [{ type: 'pie', radius: ['60%', '85%'], data: totalData, label: { show: false }, emphasis: { scale: false } }] })

    // -- 年龄段 --
    var ages = cadreStats.value.age_groups || []
    if (ages.length) {
      var ageColors = ['#00d4ff', '#10b981', '#f59e0b', '#ef4444']
      var ageData = ages.map(function(d, i) { return { value: d.value, itemStyle: { color: ageColors[i] } } })
      mk(ageBarChart, {
        animationDuration: 1000, animationEasing: 'elasticOut', animationDelay: function(idx) { return idx * 150 },
        grid: { left: 5, right: 5, top: 5, bottom: 5 }, xAxis: { type: 'value', show: false },
        yAxis: { type: 'category', data: ages.map(function(d) { return d.name }), axisLabel: { color: '#94a3b8', fontSize: 9 }, axisLine: { show: false } },
        series: [{ type: 'bar', data: ageData, barWidth: 10, label: { show: true, position: 'right', color: '#94a3b8', fontSize: 9 } }]
      })
    }

    // -- 政治面貌 --
    var pol = cadreStats.value.political || []
    if (pol.length) {
      var polColors = ['#ef4444', '#00d4ff', '#10b981']
      mk(politicalChart, {
        animationDuration: 1000, animationEasing: 'elasticOut', animationDelay: function(idx) { return idx * 200 },
        grid: { left: 5, right: 20, top: 10, bottom: 5 },
        xAxis: { type: 'category', data: pol.map(function(d) { return d.name }), axisLabel: { color: '#94a3b8', fontSize: 9 } },
        yAxis: { type: 'value', show: false },
        series: [{ type: 'bar', data: pol.map(function(d, i) { return { value: d.value, itemStyle: { color: polColors[i] } } }),
          barWidth: 20, label: { show: true, position: 'top', color: '#94a3b8', fontSize: 9 } }]
      })
    }

    // -- 民族 --
    var eth = cadreStats.value.ethnicity || []
    if (eth.length) mk(ethnicityChart, {
      animationDuration: 800, animationEasing: 'cubicOut',
      tooltip: { trigger: 'item' },
      series: [{ type: 'pie', radius: ['40%', '70%'], animationType: 'scale',
        data: eth.map(function(d, i) { return { name: d.name, value: d.value, itemStyle: { color: COLORS[i % 8] } } }),
        label: { color: '#94a3b8', fontSize: 8 } }]
    })

    // -- 专业矩形树图 --
    var spec = cadreStats.value.specialty || []
    if (spec.length) mk(specialtyCloud, {
      animationDuration: 1000, animationEasing: 'cubicOut',
      tooltip: {}, series: [{ type: 'treemap', roam: false, nodeClick: false, breadcrumb: { show: false },
        data: spec.slice(0, 15).map(function(d) { return { name: d.name, value: d.value } }),
        label: { color: '#e2e8f0', fontSize: 8 }, itemStyle: { borderColor: '#0a0e27', gapWidth: 1 },
        levels: [{ colorMapping: 'value', color: ['#1e3a8a', '#00d4ff', '#a855f7'] }] }]
    })

    // -- 擅长领域矩形树图 --
    var exp = cadreStats.value.expertise || []
    if (exp.length) mk(expertiseTree, {
      animationDuration: 1000, animationEasing: 'cubicOut',
      tooltip: {}, series: [{ type: 'treemap', roam: false, nodeClick: false, breadcrumb: { show: false },
        data: exp.slice(0, 20).map(function(d) { return { name: d.name, value: d.value } }),
        label: { color: '#e2e8f0', fontSize: 8 }, itemStyle: { borderColor: '#0a0e27', gapWidth: 1 },
        levels: [{ colorMapping: 'value', color: ['#581c87', '#a855f7', '#c084fc'] }] }]
    })

    // -- 仪表盘 --
    var rate = taskProgress.value.completion_rate || 0
    mk(progressGauge, { series: [{ type: 'gauge', startAngle: 210, endAngle: -30, radius: '85%', animationDuration: 1500, animationEasing: 'cubicInOut',
      progress: { show: true, width: 12, itemStyle: { color: { type: 'linear', x: 0, y: 0, x2: 1, y2: 0, colorStops: [{ offset: 0, color: '#00d4ff' }, { offset: 1, color: '#a855f7' }] } } },
      axisLine: { lineStyle: { width: 12, color: [[1, '#1a2358']] } }, axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false },
      anchor: { show: false }, title: { show: false },
      detail: { valueAnimation: true, formatter: '{value}%', color: '#e2e8f0', fontSize: 16, offsetCenter: [0, '60%'] },
      data: [{ value: rate }] }] })

    // -- 桑基图 --
    var flow = flowData.value
    if (flow.nodes && flow.nodes.length) mk(sankeyChart, {
      animationDuration: 1200, animationEasing: 'cubicOut',
      tooltip: { trigger: 'item' }, series: [{ type: 'sankey', layout: 'none', emphasis: { focus: 'adjacency' }, nodeAlign: 'left',
        data: flow.nodes.map(function(n, i) { return { name: n.name, itemStyle: { color: COLORS[i % 8] } } }),
        links: flow.links.map(function(l) { return { source: l.source, target: l.target, value: l.value } }),
        label: { color: '#94a3b8', fontSize: 8 } }]
    })

    // 延迟启动结果表滚动
    setTimeout(startResultScroll, 500)
  })
}

async function loadPlans() {
  try { const r = await getPlans(); plans.value = r.data?.items || [] } catch(_){}
}

async function loadAll() {
  loading.value = true
  try {
    const [ov, cs, tp, fl, rs, td] = await Promise.all([
      getDashboardOverview(filterPlanId.value),
      http.get('/dashboard/cadre-stats'),
      http.get('/dashboard/task-progress', { params: { plan_id: filterPlanId.value } }),
      http.get('/dashboard/flow', { params: { plan_id: filterPlanId.value } }),
      http.get('/dashboard/results', { params: { plan_year: filterYear.value } }),
      http.get('/dashboard/task-decomp', { params: { plan_id: filterPlanId.value } }),
    ])
    overview.value = ov.data || overview.value
    cadreStats.value = cs.data?.data || cadreStats.value
    taskProgress.value = tp.data?.data || taskProgress.value
    flowData.value = fl.data?.data || flowData.value
    results.value = rs.data?.data || []
    decompData.value = td.data?.data || decompData.value
    decompStats.value = decompData.value.stats || decompStats.value
    charts()
  } catch(_){} finally { loading.value = false }
}

let rt; function onResize() { clearTimeout(rt); rt = setTimeout(() => chartInstances.forEach(c => { try { c.resize() } catch(_){} }), 200) }

onMounted(async () => { await initEC(); await loadPlans(); await loadAll(); window.addEventListener('resize', onResize) })
onUnmounted(() => { if (scrollTimer) clearInterval(scrollTimer); disposeAll(); window.removeEventListener('resize', onResize) })
</script>

<style scoped>
:root { --bg: #0a0e27; --panel: #0f1535; --border: #1a2358; --card: #111844; --g-cyan: #00d4ff; --g-purple: #a855f7; --g-orange: #f59e0b; --g-green: #10b981; --text: #e2e8f0; --dim: #94a3b8; }

.cockpit { background: #0a0e27; min-height: 100vh; color: #e2e8f0; overflow: hidden; }

.cockpit-header { display:flex; align-items:center; justify-content:space-between; padding:8px 20px; background:linear-gradient(180deg,#111844,#0f1535); border-bottom:1px solid #1a2358; position:sticky; top:0; z-index:100; }
.header-left, .header-right { display:flex; align-items:center; gap:4px; flex-shrink:0; }
.back-btn { background:rgba(0,212,255,0.1); border:1px solid rgba(0,212,255,0.3); color:#00d4ff; padding:4px 8px; }
.back-btn:hover { background:rgba(0,212,255,0.25); border-color:#00d4ff; }
.header-title { font-size:20px; font-weight:700; background:linear-gradient(90deg,#00d4ff,#a855f7); -webkit-background-clip:text; -webkit-text-fill-color:transparent; letter-spacing:4px; white-space:nowrap; }

.cockpit-body { display:grid; grid-template-columns:1fr 1.15fr 1fr; gap:12px; padding:12px; max-width:1920px; margin:0 auto; height:calc(100vh - 58px); overflow-y:auto; }
.panel-col { display:flex; flex-direction:column; gap:12px; }

.panel-card { background:#111844; border:1px solid #1a2358; border-radius:8px; padding:14px; box-shadow:0 0 20px rgba(0,212,255,0.08); }
.card-title { font-size:15px; font-weight:600; margin-bottom:10px; display:flex; align-items:center; justify-content:space-between; color:#00d4ff; border-bottom:1px solid #1a2358; padding-bottom:8px; }
.card-subtitle { font-size:12px; color:#a855f7; margin:6px 0 4px; font-weight:500; }
.card-stats-row { display:flex; justify-content:space-around; padding-top:6px; }
.stat-item { text-align:center; } .stat-num { display:block; font-size:22px; font-weight:700; color:#00d4ff; } .stat-label { font-size:11px; color:#94a3b8; }

.title-tabs { display:flex; gap:4px; } .title-tabs span { font-size:11px; padding:2px 10px; border-radius:10px; cursor:pointer; color:#94a3b8; background:rgba(255,255,255,0.05); } .title-tabs span.active { background:#00d4ff; color:#000; }

.chart-box { width:100%; overflow:hidden; }

.result-table-wrap { max-height:200px; overflow-y:auto; }
.result-table { width:100%; border-collapse:collapse; font-size:11px; }
.result-table th { color:#94a3b8; padding:6px 4px; text-align:left; border-bottom:1px solid #1a2358; position:sticky; top:0; background:#111844; }
.result-table td { padding:5px 4px; border-bottom:1px solid rgba(26,35,88,0.5); }
.rank-badge { display:inline-block; width:22px; height:22px; line-height:22px; text-align:center; border-radius:50%; background:linear-gradient(135deg,#00d4ff,#a855f7); font-size:10px; font-weight:700; color:#fff; }
.tag-bad { color:#ef4444; font-size:10px; } .tag-ok { color:#10b981; font-size:10px; } .tag-good { color:#f59e0b; font-size:10px; }

.cadre-overview { display:flex; align-items:center; gap:10px; }
.overview-left { text-align:center; flex-shrink:0; }
.total-label { font-size:11px; color:#94a3b8; margin-top:-12px; position:relative; }
.total-num { font-size:28px; font-weight:700; color:#00d4ff; }
.overview-right { flex:1; font-size:11px; }
.info-row { display:flex; justify-content:space-between; padding:2px 0; border-bottom:1px solid rgba(26,35,88,0.3); }
.info-row .val { color:#f59e0b; }

.prop-grid-2col { display:grid; grid-template-columns:1fr 1fr; gap:8px; }

.gauge-row { display:flex; align-items:center; justify-content:center; gap:8px; }
.gauge-info { text-align:center; } .gauge-num { font-size:28px; font-weight:700; color:#00d4ff; } .gauge-label { font-size:11px; color:#94a3b8; }

.status-cards { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:8px; }
.scard { background:rgba(255,255,255,0.03); border-left:3px solid; border-radius:4px; padding:8px 10px; }
.scard-num { font-size:16px; font-weight:700; } .scard-num small { font-size:10px; color:#94a3b8; font-weight:400; } .scard-label { font-size:10px; color:#94a3b8; margin-top:2px; }

.dim-stats-mini { display:flex; flex-wrap:wrap; gap:4px; margin-top:8px; }
.dim-chip { font-size:10px; background:rgba(0,212,255,0.1); color:#00d4ff; padding:2px 6px; border-radius:3px; }

.mini-table-wrap { max-height:160px; overflow-y:auto; }
.mini-table { width:100%; border-collapse:collapse; font-size:10px; }
.mini-table th { color:#94a3b8; padding:4px 3px; text-align:left; border-bottom:1px solid #1a2358; background:#111844; position:sticky; top:0; }
.mini-table td { padding:3px; border-bottom:1px solid rgba(26,35,88,0.3); }
.ellipsis { max-width:120px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }

::-webkit-scrollbar { width:4px; height:4px; } ::-webkit-scrollbar-thumb { background:rgba(0,212,255,0.3); border-radius:2px; }
</style>
