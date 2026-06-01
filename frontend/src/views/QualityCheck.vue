<template>
  <div class="content-card">
    <div class="search-bar">
      <el-select v-model="filterPlanId" placeholder="选择考核方案" style="width:240px" @change="onPlanChange">
        <el-option v-for="p in plans" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <el-button type="primary" @click="runCheck" :loading="checking" :disabled="!filterPlanId">开始检测</el-button>
      <el-select v-model="filterType" placeholder="筛选问题类型" clearable style="width:180px;margin-left:8px">
        <el-option v-for="t in issueTypes" :key="t" :label="t" :value="t" />
      </el-select>
    </div>

    <!-- 统计卡片 -->
    <div v-if="summary" class="summary-row">
      <div class="sum-card">
        <div class="sum-num">{{ summary.total_tasks }}</div>
        <div class="sum-label">检测任务数</div>
      </div>
      <div class="sum-card" v-for="(count, type) in summary.summary" :key="type">
        <div class="sum-num" :style="{color: count > 0 ? '#f56c6c' : '#10b981'}">{{ count }}</div>
        <div class="sum-label">{{ type }}</div>
      </div>
      <div class="sum-card total">
        <div class="sum-num">{{ summary.total_issues }}</div>
        <div class="sum-label">问题总数</div>
      </div>
    </div>

    <!-- 问题列表 -->
    <el-table :data="filteredIssues" border stripe v-loading="checking" empty-description="请选择方案后点击「开始检测」">
      <el-table-column label="类型" width="150">
        <template #default="{ row }">
          <el-tag size="small" :type="tagType(row.issue_type)">{{ row.issue_type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="unit_name" label="单位" width="140" />
      <el-table-column prop="column" label="字段" width="100" />
      <el-table-column label="问题内容" min-width="160">
        <template #default="{ row }"><span class="cell-wrap">{{ row.text }}</span></template>
      </el-table-column>
      <el-table-column prop="suggestion" label="修改建议" min-width="180" show-overflow-tooltip />
      <el-table-column prop="context" label="上下文" min-width="150" show-overflow-tooltip />
      <el-table-column label="置信度" width="80">
        <template #default="{ row }">
          <el-tag size="small" :type="row.confidence === 'high' ? 'danger' : row.confidence === 'medium' ? 'warning' : 'info'">
            {{ row.confidence === 'high' ? '高' : row.confidence === 'medium' ? '中' : '低' }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getPlans } from '../api/plan'
import http from '../api/index'

const filterPlanId = ref(null)
const filterType = ref('')
const checking = ref(false)
const plans = ref([])
const summary = ref(null)
const allIssues = ref([])

const issueTypes = computed(() => [...new Set(allIssues.value.map(i => i.issue_type))].sort())
const filteredIssues = computed(() => {
  if (!filterType.value) return allIssues.value
  return allIssues.value.filter(i => i.issue_type === filterType.value)
})

function tagType(type) {
  if (!type) return 'info'
  if (type.includes('错别字')) return 'danger'
  if (type.includes('重复')) return 'warning'
  if (type.includes('标点')) return 'primary'
  return 'info'
}

async function loadPlans() {
  try { const r = await getPlans(); plans.value = r.data?.items || [] } catch (_) { }
}

function onPlanChange() { summary.value = null; allIssues.value = [] }

async function runCheck() {
  if (!filterPlanId.value) return
  checking.value = true; summary.value = null; allIssues.value = []
  try {
    const r = await http.post('/quality-check/run', { plan_id: filterPlanId.value })
    const data = r.data?.data || r.data
    summary.value = { total_tasks: data.total_tasks, summary: data.summary, total_issues: data.total_issues }
    allIssues.value = data.issues || []
    ElMessage.success(r.data?.msg || r.msg || '检测完成')
  } catch (_) { } finally { checking.value = false }
}

onMounted(loadPlans)
</script>

<style scoped>
.summary-row { display: flex; gap: 14px; margin-bottom: 18px; flex-wrap: wrap; }
.sum-card { flex: 1; min-width: 100px; background: #fff; border-radius: 8px; padding: 14px 16px; text-align: center; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
.sum-card.total { background: #fef0f0; }
.sum-num { font-size: 28px; font-weight: 700; color: #303133; }
.sum-label { font-size: 13px; color: #909399; margin-top: 4px; }
.cell-wrap { white-space: pre-wrap; word-break: break-all; }
</style>
