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
      <el-button v-if="allIssues.length" @click="loadIssues">刷新</el-button>
      <el-button @click="$router.push('/quality-check/manage')">问题管理 →</el-button>
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
    <el-table :data="filteredIssues" border stripe v-loading="checking" @row-click="openEdit" style="cursor:pointer"
      empty-description="请选择方案后点击「开始检测」">
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag size="small" :type="row.status === 'pending' ? 'danger' : row.status === 'confirmed' ? 'warning' : row.status === 'resolved' ? 'success' : 'info'">
            {{ row.status === 'pending' ? '待处理' : row.status === 'confirmed' ? '确认无误' : row.status === 'resolved' ? '已修复' : '已移除' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="140">
        <template #default="{ row }">
          <el-tag size="small" :type="tagType(row.issue_type)">{{ row.issue_type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="unit_name" label="单位" width="130" />
      <el-table-column label="字段" width="90">
        <template #default="{ row }">{{ row.column || row.column_name }}</template>
      </el-table-column>
      <el-table-column label="问题内容" min-width="160">
        <template #default="{ row }"><span class="cell-wrap">{{ row.text }}</span></template>
      </el-table-column>
      <el-table-column prop="suggestion" label="修改建议" min-width="180" show-overflow-tooltip />
      <el-table-column label="操作" width="240" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click.stop="openEdit(row)">查看</el-button>
          <el-button v-if="row.status === 'pending'" size="small" link @click.stop="updateStatus(row, 'confirmed')">确认无误</el-button>
          <el-button v-if="row.status === 'pending'" size="small" type="success" link @click.stop="updateStatus(row, 'resolved')">已修复</el-button>
          <el-button size="small" type="danger" link @click.stop="updateStatus(row, 'ignored')">移除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 任务编辑弹窗 -->
    <el-dialog v-model="editVisible" title="编辑任务" width="650px" @close="editTaskId = null">
      <el-form v-if="editTask" :model="editForm" label-width="90px">
        <el-form-item label="考核维度">
          <el-select v-model="editForm.assessment_dimension_id" style="width:100%">
            <el-option v-for="d in availableDims" :key="d.id" :label="d.name" :value="d.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="被考核单位">
          <el-select v-model="editForm.unit_id" filterable style="width:100%">
            <el-option v-for="u in allUnits" :key="u.id" :label="u.name" :value="u.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="评价部门">
          <el-select v-model="editForm.assessor_unit_id" style="width:100%">
            <el-option v-for="u in assessorUnits" :key="u.id" :label="u.name" :value="u.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="重点工作">
          <el-input v-model="editForm.key_work" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="主要任务">
          <el-input v-model="editForm.main_task" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="评分说明">
          <el-input v-model="editForm.scoring_note" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="晾晒周期">
          <el-select v-model="editForm.review_period" style="width:100%">
            <el-option v-for="p in periods" :key="p.value" :label="p.label" :value="p.value" />
          </el-select>
        </el-form-item>
        <el-alert v-if="siblingCount > 1" type="info" :closable="false" show-icon
          title="批量更正提示" :description="`同一评价部门下，此项涉及 ${siblingCount} 条任务（${editSiblingUnits}），保存后将全部更正。`" />
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" @click="saveEdit">保存并更正全部</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getPlans, getPlan } from '../api/plan'
import { getUnits } from '../api/unit'
import { getTasks } from '../api/task'
import http from '../api/index'

const filterPlanId = ref(null)
const filterType = ref('')
const checking = ref(false)
const plans = ref([])
const summary = ref(null)
const allIssues = ref([])
const allUnits = ref([])
const assessorUnits = ref([])
const availableDims = ref([])
const periods = [
  { label: '月度', value: 'monthly' }, { label: '季度', value: 'quarterly' },
  { label: '半年度', value: 'semiannual' }, { label: '年度', value: 'annual' },
]

const issueTypes = computed(() => [...new Set(allIssues.value.map(i => i.issue_type))].sort())
const filteredIssues = computed(() => {
  let arr = allIssues.value.filter(i => i.status === 'pending')
  if (filterType.value) arr = arr.filter(i => i.issue_type === filterType.value)
  return arr
})

// Edit dialog
const editVisible = ref(false)
const editTaskId = ref(null)
const editTask = ref(null)
const siblingCount = ref(0)
const editSiblingUnits = ref('')
const editForm = reactive({
  assessment_dimension_id: null, unit_id: null, assessor_unit_id: null,
  key_work: '', main_task: '', scoring_note: '', review_period: 'monthly'
})

function tagType(type) {
  if (!type) return 'info'
  if (type.includes('错别字')) return 'danger'
  if (type.includes('重复')) return 'warning'
  if (type.includes('标点')) return 'primary'
  return 'info'
}

async function loadPlans() { try { const r = await getPlans(); plans.value = r.data?.items || [] } catch (_) { } }
async function loadUnits() { try { const r = await getUnits({ page_size: 9999 }); allUnits.value = r.data?.items || [] } catch (_) { } }

function onPlanChange() { summary.value = null; allIssues.value = []; loadIssues() }

watch(filterPlanId, async (pid) => {
  if (pid) {
    try {
      const r = await getPlan(pid)
      assessorUnits.value = r.data?.assessor_units || []
      const dim = r.data?.evaluation_dimensions?.find(d => d.is_actual_assessment)
      availableDims.value = dim?.assessment_dimensions || []
    } catch { assessorUnits.value = []; availableDims.value = [] }
  }
})

async function loadIssues() {
  if (!filterPlanId.value) return
  try {
    const r = await http.get('/quality-check/issues', { params: { plan_id: filterPlanId.value, page_size: 500 } })
    allIssues.value = (r.data?.data?.items || r.data?.items || []).map(i => ({
      ...i, unit_name: '', column: i.column_name, status: i.status || 'pending',
    }))
    // Enrich with task data
    for (const iss of allIssues.value) {
      if (iss.task_id) {
        try {
          const tr = await getTasks({ plan_id: filterPlanId.value, page_size: 1 })
          // We'll get task info on click instead
        } catch (_) { }
      }
    }
  } catch (_) { }
}

async function runCheck() {
  if (!filterPlanId.value) return
  checking.value = true; summary.value = null; allIssues.value = []
  try {
    const r = await http.post('/quality-check/run', { plan_id: filterPlanId.value })
    const data = r.data?.data || r.data
    summary.value = { total_tasks: data.total_tasks, summary: data.summary, total_issues: data.total_issues }
    await loadIssues()
    ElMessage.success(r.data?.msg || r.msg || '检测完成')
  } catch (_) { } finally { checking.value = false }
}

async function updateStatus(row, status) {
  try {
    await http.put(`/quality-check/issues/${row.id}`, { status })
    row.status = status
    ElMessage.success(status === 'confirmed' ? '已标记为确认无误' : status === 'resolved' ? '已标记为已修复' : '已移除')
  } catch (_) { }
}

async function openEdit(row) {
  // Fetch task detail
  try {
    const r = await getTasks({ plan_id: filterPlanId.value, page_size: 500 })
    const tasks = r.data?.items || r.data || []
    const task = tasks.find(t => t.id === row.task_id)
    if (!task) { ElMessage.warning('未找到关联任务'); return }

    editTask.value = task
    editTaskId.value = task.id
    editForm.assessment_dimension_id = task.assessment_dimension_id
    editForm.unit_id = task.unit_id
    editForm.assessor_unit_id = task.assessor_unit_id
    editForm.key_work = task.key_work
    editForm.main_task = task.main_task
    editForm.scoring_note = task.scoring_note
    editForm.review_period = task.review_period

    // Find siblings (same plan + same assessor + same key_work)
    const siblings = tasks.filter(t =>
      t.assessor_unit_id === task.assessor_unit_id && t.key_work === task.key_work
    )
    siblingCount.value = siblings.length
    const unitNames = [...new Set(siblings.map(s => s.unit_name).filter(Boolean))]
    editSiblingUnits.value = unitNames.join('、')

    editVisible.value = true
  } catch (_) { ElMessage.error('加载任务失败') }
}

async function saveEdit() {
  if (!editTaskId.value) return
  try {
    const fields = ['key_work', 'main_task', 'scoring_note']
    for (const f of fields) {
      const oldVal = (editTask.value || {})[f] || ''
      const newVal = editForm[f] || ''
      if (oldVal !== newVal) {
        await http.post('/quality-check/batch-correct', {
          task_id: editTaskId.value, field: f, new_value: newVal,
        })
      }
    }
    // Also update the task itself (non-batch fields)
    await http.put(`/tasks/${editTaskId.value}`, {
      assessment_dimension_id: editForm.assessment_dimension_id,
      unit_id: editForm.unit_id,
      assessor_unit_id: editForm.assessor_unit_id,
      review_period: editForm.review_period,
    })
    ElMessage.success('保存成功')
    editVisible.value = false; editTaskId.value = null
    loadIssues()
  } catch (_) { ElMessage.error('保存失败') }
}

onMounted(() => { loadPlans(); loadUnits() })
</script>

<style scoped>
.summary-row { display: flex; gap: 14px; margin-bottom: 18px; flex-wrap: wrap; }
.sum-card { flex: 1; min-width: 100px; background: #fff; border-radius: 8px; padding: 14px 16px; text-align: center; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
.sum-card.total { background: #fef0f0; }
.sum-num { font-size: 28px; font-weight: 700; color: #303133; }
.sum-label { font-size: 13px; color: #909399; margin-top: 4px; }
.cell-wrap { white-space: pre-wrap; word-break: break-all; }
</style>
