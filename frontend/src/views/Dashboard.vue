<template>
  <div class="dashboard">
    <!-- 顶部标题栏 -->
    <div class="dash-hero">
      <div class="hero-left">
        <h2 class="hero-title">黔江区多维度精准考核评价系统</h2>
        <p class="hero-sub">全区综合考核数据驾驶舱</p>
      </div>
      <div class="hero-right">
        <el-select v-model="selectedPlanId" placeholder="选择考核方案" clearable @change="loadAll" size="large" style="width:320px" class="plan-select">
          <el-option v-for="p in plans" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stat-grid">
      <div class="stat-card card-blue">
        <div class="card-inner">
          <div class="card-icon-wrap"><el-icon :size="28"><Document /></el-icon></div>
          <div class="card-body">
            <div class="card-value">{{ overview.stats?.total_plans || 0 }}</div>
            <div class="card-label">考核方案总数</div>
          </div>
        </div>
      </div>
      <div class="stat-card card-amber">
        <div class="card-inner">
          <div class="card-icon-wrap"><el-icon :size="28"><OfficeBuilding /></el-icon></div>
          <div class="card-body">
            <div class="card-value">{{ overview.stats?.total_units || 0 }}</div>
            <div class="card-label">被考核单位数</div>
          </div>
        </div>
      </div>
      <div class="stat-card card-green">
        <div class="card-inner">
          <div class="card-icon-wrap"><el-icon :size="28"><List /></el-icon></div>
          <div class="card-body">
            <div class="card-value">{{ overview.stats?.total_tasks || 0 }}</div>
            <div class="card-label">考核任务总数</div>
          </div>
        </div>
      </div>
      <div class="stat-card card-red">
        <div class="card-inner">
          <div class="card-icon-wrap"><el-icon :size="28"><DataAnalysis /></el-icon></div>
          <div class="card-body">
            <div class="card-value">{{ overview.stats?.completion_rate || 0 }}<span class="card-unit">%</span></div>
            <div class="card-label">任务完成率</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 图表行1 -->
    <div class="chart-grid cols-2">
      <div class="panel">
        <div class="panel-hd">
          <h3>各维度任务统计</h3>
        </div>
        <div class="panel-bd">
          <div ref="dimChartRef" class="chart-box"></div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-hd">
          <h3>各单位完成率排名 TOP15</h3>
        </div>
        <div class="panel-bd">
          <div ref="unitChartRef" class="chart-box"></div>
        </div>
      </div>
    </div>

    <!-- 图表行2 -->
    <div class="chart-grid cols-2">
      <div class="panel">
        <div class="panel-hd">
          <h3>任务状态分布</h3>
        </div>
        <div class="panel-bd">
          <div ref="statusChartRef" class="chart-box chart-box-sm"></div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-hd">
          <h3>晾晒周期分布</h3>
        </div>
        <div class="panel-bd">
          <div ref="periodChartRef" class="chart-box chart-box-sm"></div>
        </div>
      </div>
    </div>

    <!-- 最近动态 -->
    <div class="panel">
      <div class="panel-hd">
        <h3>最近考核动态</h3>
      </div>
      <div class="panel-bd" style="padding:0">
        <el-table :data="overview.recent_activity || []" stripe size="small" style="width:100%">
          <template #empty><el-empty description="暂无动态" :image-size="60" /></template>
          <el-table-column prop="time" label="时间" width="170" />
          <el-table-column prop="unit_name" label="单位" width="160" show-overflow-tooltip />
          <el-table-column prop="dim_name" label="考核维度" width="120" show-overflow-tooltip />
          <el-table-column prop="key_work" label="重点工作" min-width="160" show-overflow-tooltip />
          <el-table-column prop="action" label="动作" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="row.action === '已打分' ? 'success' : 'warning'" size="small" effect="plain">
                {{ row.action }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="score" label="得分" width="80" align="center">
            <template #default="{ row }">{{ row.score != null ? row.score : '-' }}</template>
          </el-table-column>
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, nextTick, watch } from 'vue'
import { getDashboardOverview } from '../api/dashboard'
import { getPlans } from '../api/plan'

const selectedPlanId = ref(null)
const plans = ref([])
const overview = reactive({
  stats: {}, dim_stats: [], unit_completion: [],
  status_dist: {}, period_dist: {}, recent_activity: [],
})

const dimChartRef = ref(null)
const unitChartRef = ref(null)
const statusChartRef = ref(null)
const periodChartRef = ref(null)

let echartsMod = null
let charts = { dim: null, unit: null, status: null, period: null }

async function ensureECharts() {
  if (echartsMod) return echartsMod
  echartsMod = await import('echarts')
  return echartsMod
}

function disposeAll() {
  Object.values(charts).forEach(c => { try { c?.dispose() } catch {} })
  charts = { dim: null, unit: null, status: null, period: null }
}

async function renderCharts() {
  await nextTick()
  if (!dimChartRef.value) return

  const ec = await ensureECharts()
  disposeAll()

  const commonGrid = { left: 10, right: 20, top: 20, bottom: 35 }

  // 维度统计堆叠柱状图
  charts.dim = ec.init(dimChartRef.value)
  const dims = overview.dim_stats || []
  charts.dim.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['待填报', '已提交', '已审核'], bottom: 0, textStyle: { fontSize: 11 } },
    grid: { ...commonGrid, top: 10, bottom: 35 },
    xAxis: {
      type: 'category', data: dims.map(d => d.name),
      axisLabel: { rotate: dims.length > 6 ? 35 : 0, fontSize: 10, color: '#606266' },
      axisTick: { alignWithLabel: true },
    },
    yAxis: { type: 'value', name: '任务数', nameTextStyle: { fontSize: 11, color: '#909399' } },
    series: [
      { name: '待填报', type: 'bar', stack: 'total', data: dims.map(d => d.pending || 0), itemStyle: { color: '#c0c4cc' }, barWidth: 28 },
      { name: '已提交', type: 'bar', stack: 'total', data: dims.map(d => d.submitted || 0), itemStyle: { color: '#f4a941' }, barWidth: 28 },
      { name: '已审核', type: 'bar', stack: 'total', data: dims.map(d => d.reviewed || 0), itemStyle: { color: '#5cb87a' }, barWidth: 28 },
    ],
  })

  // 单位完成率横向柱状图
  charts.unit = ec.init(unitChartRef.value)
  const units = (overview.unit_completion || []).slice(0, 15)
  charts.unit.setOption({
    tooltip: { trigger: 'axis', formatter: '{b}: {c}%' },
    grid: { left: 110, right: 50, top: 5, bottom: 5 },
    xAxis: { type: 'value', name: '%', max: 100, nameTextStyle: { fontSize: 11 } },
    yAxis: {
      type: 'category', data: units.map(u => u.unit_name).reverse(),
      axisLabel: { fontSize: 10, color: '#606266' }, inverse: true,
      axisTick: { show: false },
    },
    series: [{
      type: 'bar', data: units.map(u => u.rate).reverse(),
      itemStyle: {
        color: { type: 'linear', x: 0, y: 0, x2: 1, y2: 0,
          colorStops: [{ offset: 0, color: '#4a90d9' }, { offset: 1, color: '#67b8f8' }] },
        borderRadius: [0, 4, 4, 0],
      },
      barMaxWidth: 20,
      label: { show: true, position: 'right', formatter: '{c}%', fontSize: 10, color: '#606266' },
    }],
  })

  // 状态分布饼图
  charts.status = ec.init(statusChartRef.value)
  const sd = overview.status_dist || {}
  charts.status.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0, textStyle: { fontSize: 11 } },
    series: [{
      type: 'pie', radius: ['45%', '72%'], center: ['50%', '43%'],
      avoidLabelOverlap: false,
      itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
      data: [
        { value: sd.pending || 0, name: '待填报', itemStyle: { color: '#c0c4cc' } },
        { value: sd.submitted || 0, name: '已提交', itemStyle: { color: '#f4a941' } },
        { value: sd.reviewed || 0, name: '已审核', itemStyle: { color: '#5cb87a' } },
      ],
      label: { formatter: '{b}\n{c} 条', fontSize: 11 },
    }],
  })

  // 晾晒周期饼图
  charts.period = ec.init(periodChartRef.value)
  const pd = overview.period_dist || {}
  const periodColors = { '月度': '#4a90d9', '季度': '#36cfc9', '半年度': '#b37feb', '年度': '#ffb755' }
  charts.period.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0, textStyle: { fontSize: 11 } },
    series: [{
      type: 'pie', radius: ['45%', '72%'], center: ['50%', '43%'],
      avoidLabelOverlap: false,
      itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
      data: Object.entries(pd).map(([k, v]) => ({ name: k, value: v, itemStyle: { color: periodColors[k] || '#909399' } })),
      label: { formatter: '{b}\n{c} 条', fontSize: 11 },
    }],
  })

  // 监听窗口resize
  window.addEventListener('resize', handleResize)
}

function handleResize() {
  Object.values(charts).forEach(c => { try { c?.resize() } catch {} })
}

async function loadAll() {
  try {
    const pRes = await getPlans({ page_size: 100 })
    plans.value = pRes.data?.items || pRes.data || []

    const dRes = await getDashboardOverview(selectedPlanId.value || null)
    const data = dRes.data || {}
    overview.stats = data.stats || {}
    overview.dim_stats = data.dim_stats || []
    overview.unit_completion = data.unit_completion || []
    overview.status_dist = data.status_dist || {}
    overview.period_dist = data.period_dist || {}
    overview.recent_activity = data.recent_activity || []
    await renderCharts()
  } catch {}
}

onMounted(loadAll)
</script>

<style scoped>
.dashboard { padding: 0; }

/* 顶部 */
.dash-hero {
  display: flex; justify-content: space-between; align-items: center;
  background: linear-gradient(135deg, #1a3a5c 0%, #2563a6 50%, #3b82c4 100%);
  margin: -20px -20px 20px -20px;
  padding: 24px 32px;
  border-radius: 0 0 12px 12px;
}
.hero-title { margin: 0; font-size: 20px; color: #fff; font-weight: 600; letter-spacing: 1px; }
.hero-sub { margin: 4px 0 0 0; font-size: 13px; color: rgba(255,255,255,0.7); }
.plan-select :deep(.el-input__wrapper) { background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.25); box-shadow: none; }
.plan-select :deep(.el-input__inner) { color: #fff; }
.plan-select :deep(.el-input__inner::placeholder) { color: rgba(255,255,255,0.5); }

/* 统计卡片 */
.stat-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 16px; }
.stat-card { border-radius: 8px; overflow: hidden; }
.card-inner { display: flex; align-items: center; gap: 16px; padding: 20px 24px; }
.card-icon-wrap {
  width: 56px; height: 56px; border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.card-blue { background: #f0f5ff; border-left: 4px solid #4a90d9; }
.card-blue .card-icon-wrap { background: #dce8fa; color: #4a90d9; }
.card-amber { background: #fef7ed; border-left: 4px solid #f4a941; }
.card-amber .card-icon-wrap { background: #fdedcf; color: #f4a941; }
.card-green { background: #f1f9f2; border-left: 4px solid #5cb87a; }
.card-green .card-icon-wrap { background: #d9f0de; color: #5cb87a; }
.card-red { background: #fef2f2; border-left: 4px solid #e87474; }
.card-red .card-icon-wrap { background: #fde0e0; color: #e87474; }
.card-value { font-size: 28px; font-weight: 700; color: #1a1a2e; line-height: 1.1; }
.card-unit { font-size: 16px; font-weight: 500; color: #909399; margin-left: 2px; }
.card-label { font-size: 13px; color: #909399; margin-top: 2px; }

/* 图表面板 */
.chart-grid { display: grid; gap: 16px; margin-bottom: 16px; }
.chart-grid.cols-2 { grid-template-columns: 1fr 1fr; }
.panel {
  background: #fff; border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  overflow: hidden;
}
.panel-hd {
  padding: 14px 20px; border-bottom: 1px solid #f0f0f0;
  display: flex; justify-content: space-between; align-items: center;
}
.panel-hd h3 { margin: 0; font-size: 14px; font-weight: 600; color: #303133; }
.panel-bd { padding: 16px; }
.chart-box { width: 100%; height: 300px; }
.chart-box-sm { height: 260px; }

@media (max-width: 1200px) {
  .stat-grid { grid-template-columns: repeat(2, 1fr); }
  .chart-grid.cols-2 { grid-template-columns: 1fr; }
}
</style>
