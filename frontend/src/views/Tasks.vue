<template>
  <div class="content-card">
    <div class="search-bar">
      <el-select v-model="filterPlanId" placeholder="筛选方案" clearable @change="onFilterChange" style="width:200px">
        <el-option v-for="p in plans" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <el-select v-model="chipCategory" placeholder="选择筛选维度" clearable @change="onChipCategoryChange" @clear="clearChipFilter" style="width:150px">
        <el-option label="考核维度" value="dimension" />
        <el-option label="重点工作" value="key_work" />
        <el-option label="评价部门" value="assessor" />
        <el-option label="被考核单位" value="unit" />
        <el-option label="晾晒周期" value="period" />
      </el-select>
      <el-select v-model="filterStatus" placeholder="筛选状态" clearable @change="onFilterChange" style="width:140px">
        <el-option label="待填报" value="pending" />
        <el-option label="已提交" value="submitted" />
        <el-option label="已审核" value="reviewed" />
      </el-select>
      <el-input v-model="searchKey" placeholder="搜索..." clearable @clear="onSearch" @keyup.enter="onSearch" style="width:160px" />
      <el-button type="primary" @click="onSearch">搜索</el-button>
      <el-button v-if="chipCategory && chipSelected.length" @click="clearChipFilter">清除</el-button>
    </div>

    <!-- 方片筛选区 -->
    <div v-if="chipCategory && chipOptions.length" class="chip-filter-area">
      <div class="chip-summary" v-if="chipSummary">{{ chipSummary }}</div>
      <div class="chip-grid">
        <div
          v-for="item in chipOptions" :key="item.id || item"
          :class="['chip-item', { active: isChipSelected(item), disabled: item.active === false }]"
          @click="item.active !== false && toggleChip(item)"
        >
          {{ item.name || item }}
        </div>
      </div>
    </div>

    <div class="search-bar">
      <template v-if="auth.currentIdentity==='assessor'">
        <el-button type="primary" @click="openCreate">新建任务</el-button>
        <el-button @click="downloadTpl">下载导入模板</el-button>
        <el-button v-if="selectedRows.length" type="danger" @click="handleBatchDelete">删除选中({{ selectedRows.length }})</el-button>
        <el-button v-if="filterPlanId" type="danger" plain @click="handleBatchDeleteAll">删除全部任务</el-button>
        <el-upload :show-file-list="false" :before-upload="handleImport" accept=".xlsx,.xls" :multiple="true" style="display:inline-block">
          <el-button :disabled="!filterPlanId">批量导入xlsx</el-button>
        </el-upload>
      </template>
      <el-dropdown @command="handleExportMenu" style="margin-left:4px">
        <el-button type="primary">
          导出 <el-icon><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="search">📥 导出当前搜索结果</el-dropdown-item>
            <el-dropdown-item command="single">📄 全量单表导出</el-dropdown-item>
            <el-dropdown-item command="by-unit">📦 按被考核单位分包ZIP</el-dropdown-item>
            <el-dropdown-item command="by-assessor">📦 按主考单位分包ZIP</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <el-table :data="tasks" border stripe @selection-change="onSelectionChange" empty-description="暂无任务数据">
      <template #empty>
        <el-empty description="暂无任务数据" :image-size="80" />
      </template>
      <el-table-column type="selection" width="45" />
      <el-table-column prop="dimension_name" label="考核维度" width="120" />
      <el-table-column prop="assessor_unit_name" label="评价部门" width="120" />
      <el-table-column prop="key_work" label="重点工作" min-width="150">
        <template #default="{ row }"><span class="cell-wrap" v-html="highlight(row.key_work)"></span></template>
      </el-table-column>
      <el-table-column prop="main_task" label="主要任务" min-width="180">
        <template #default="{ row }"><span class="cell-wrap" v-html="highlight(row.main_task)"></span></template>
      </el-table-column>
      <el-table-column prop="scoring_note" label="评分说明" min-width="150">
        <template #default="{ row }"><span class="cell-wrap" v-html="highlight(row.scoring_note)"></span></template>
      </el-table-column>
      <el-table-column prop="review_period" label="晾晒周期" width="90" />
      <el-table-column v-if="auth.currentIdentity==='assessor'" prop="unit_name" label="被考核单位" width="120" />
      <el-table-column prop="status" label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.status==='pending'?'info':row.status==='submitted'?'warning':'success'" size="small">
            {{ row.status==='pending'?'待填报':row.status==='submitted'?'已提交':'已审核' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" :width="auth.currentIdentity==='assessor'?280:200">
        <template #default="{ row }">
          <template v-if="auth.currentIdentity==='assessor'">
            <el-button size="small" link @click="openEdit(row)">编辑</el-button>
            <el-button v-if="row.status==='pending'" size="small" link type="primary" @click="handleReview(row,'reviewed')">审核</el-button>
            <el-button v-if="row.status==='submitted'" size="small" link type="success" @click="openScore(row)">打分</el-button>
            <el-button size="small" link type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
          <template v-if="auth.currentIdentity==='assessed'">
            <el-button v-if="row.status==='pending'" size="small" link type="primary" @click="openSubmit(row)">填报</el-button>
            <el-button size="small" link @click="openView(row)">查看</el-button>
          </template>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination-wrap" v-if="total > 0">
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next, sizes"
        :page-sizes="[10, 20, 50, 100]"
        @current-change="loadTasks"
        @size-change="onPageSizeChange"
      />
    </div>

    <!-- 新建/编辑任务 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑任务' : '新建任务'" width="650px">
      <el-form ref="formRef" :model="form" :rules="formRules">
        <el-form-item label="考核方案" prop="plan_id">
          <el-select v-model="form.plan_id" placeholder="选择方案" style="width:100%" :disabled="isEdit">
            <el-option v-for="p in plans" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="考核维度" prop="assessment_dimension_id">
          <el-select v-model="form.assessment_dimension_id" placeholder="选择考核维度" style="width:100%">
            <el-option v-for="d in availableDims" :key="d.id" :label="d.name" :value="d.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="被考核单位" prop="unit_id">
          <el-select v-model="form.unit_id" placeholder="选择被考核单位" style="width:100%" filterable>
            <el-option v-for="u in allUnits" :key="u.id" :label="u.name" :value="u.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="评价部门" prop="assessor_unit_id">
          <el-select v-model="form.assessor_unit_id" placeholder="选择评价部门（主考单位）" style="width:100%" filterable>
            <el-option v-for="u in assessorUnits" :key="u.id" :label="u.name" :value="u.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="重点工作" prop="key_work">
          <el-input v-model="form.key_work" placeholder="如：经济指标完成情况" />
        </el-form-item>
        <el-form-item label="主要任务" prop="main_task">
          <el-input v-model="form.main_task" type="textarea" :rows="2" placeholder="如：GDP增速达到6%以上" />
        </el-form-item>
        <el-form-item label="评分说明">
          <el-input v-model="form.scoring_note" type="textarea" :rows="2" placeholder="评分标准说明" />
        </el-form-item>
        <el-form-item label="晾晒周期" prop="review_period">
          <el-select v-model="form.review_period" style="width:100%">
            <el-option label="月度" value="月度" />
            <el-option label="季度" value="季度" />
            <el-option label="半年度" value="半年度" />
            <el-option label="年度" value="年度" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>

    <!-- 填报 -->
    <el-dialog v-model="submitVisible" title="填报完成情况" width="500px">
      <el-form>
        <el-form-item label="填报内容">
          <el-input v-model="submitContent" type="textarea" :rows="5" placeholder="请填写完成情况..." />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="submitVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit">提交</el-button>
      </template>
    </el-dialog>

    <!-- 打分 -->
    <el-dialog v-model="scoreVisible" title="打分" width="400px">
      <el-form>
        <el-form-item label="分数">
          <el-input-number v-model="scoreVal" :min="0" :max="100" style="width:200px" />
        </el-form-item>
        <el-form-item label="评语">
          <el-input v-model="scoreComment" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="scoreVisible = false">取消</el-button>
        <el-button type="primary" @click="handleScore">提交</el-button>
      </template>
    </el-dialog>

    <!-- 查看详情 -->
    <el-dialog v-model="viewVisible" title="任务详情" width="500px">
      <el-descriptions v-if="viewTask" :column="1" border>
        <el-descriptions-item label="考核维度">{{ viewTask.dimension_name }}</el-descriptions-item>
        <el-descriptions-item label="重点工作">{{ viewTask.key_work }}</el-descriptions-item>
        <el-descriptions-item label="主要任务">{{ viewTask.main_task }}</el-descriptions-item>
        <el-descriptions-item label="评分说明">{{ viewTask.scoring_note || '-' }}</el-descriptions-item>
        <el-descriptions-item label="晾晒周期">{{ viewTask.review_period }}</el-descriptions-item>
        <el-descriptions-item label="填报内容">{{ viewTask.submissions?.[0]?.content || '未填报' }}</el-descriptions-item>
        <el-descriptions-item label="得分">{{ viewTask.scores?.[0]?.score ?? '未打分' }}</el-descriptions-item>
        <el-descriptions-item label="评语">{{ viewTask.scores?.[0]?.comment || '-' }}</el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '../store/auth'
import * as api from '../api/task'
import { getPlans, getPlan } from '../api/plan'
import { getUnits } from '../api/unit'

const auth = useAuthStore()
const plans = ref([])
const tasks = ref([])
const allUnits = ref([])
const assessorUnits = ref([])
const availableDims = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)

const searchKey = ref('')
const filterPlanId = ref(null)
const filterStatus = ref('')
const selectedRows = ref([])

// 方片筛选
const chipCategory = ref('')
const chipOptions = ref([])
const chipSelected = ref([])
const chipSummary = ref('')  // 如 "1/11"
const filterOpts = ref({ dimensions: [], key_works: [], assessor_units: [], assessed_units: [], review_periods: [] })

function onSelectionChange(rows) { selectedRows.value = rows }
function onSearch() { currentPage.value = 1; loadTasks() }
function onFilterChange() { currentPage.value = 1; chipCategory.value = ''; chipOptions.value = []; chipSelected.value = []; chipSummary.value = ''; loadFilterOpts(); loadTasks() }

function onChipCategoryChange() {
  chipSelected.value = []; chipSummary.value = ''
  const opts = filterOpts.value
  if (chipCategory.value === 'dimension' || chipCategory.value === 'assessor') {
    // 合并预设 + 已有任务数据
    const isDim = chipCategory.value === 'dimension'
    const preset = isDim ? (availableDims.value || []) : (assessorUnits.value || [])
    const active = isDim ? (opts.dimensions || []) : (opts.assessor_units || [])
    const activeIds = new Set(active.map(a => a.id))
    chipOptions.value = preset.map(p => ({
      ...p,
      active: activeIds.has(p.id),
    }))
    chipSummary.value = `${active.length}/${preset.length}`
  } else if (chipCategory.value === 'key_work') {
    chipOptions.value = (opts.key_works || []).map(k => ({ id: k, name: k, active: true }))
    chipSummary.value = `${opts.key_works?.length || 0} 项`
  } else if (chipCategory.value === 'unit') {
    chipOptions.value = (opts.assessed_units || []).map(u => ({ ...u, active: true }))
    chipSummary.value = `${opts.assessed_units?.length || 0} 个`
  } else if (chipCategory.value === 'period') {
    chipOptions.value = (opts.review_periods || []).map(p => ({ ...p, active: true }))
    chipSummary.value = `${opts.review_periods?.length || 0} 种`
  } else {
    chipOptions.value = []
  }
}

function isChipSelected(item) {
  const id = item.id || item
  return chipSelected.value.some(s => (s.id || s) === id)
}

function toggleChip(item) {
  const id = item.id || item
  const idx = chipSelected.value.findIndex(s => (s.id || s) === id)
  if (idx >= 0) chipSelected.value.splice(idx, 1)
  else chipSelected.value.push(item)
}

function clearChipFilter() { chipSelected.value = []; currentPage.value = 1; loadTasks() }

function escapeHtml(text) {
  const div = document.createElement('div')
  div.textContent = text
  return div.innerHTML
}

function highlight(text) {
  if (!searchKey.value || !text) return escapeHtml(String(text))
  const esc = escapeHtml(String(text))
  const kw = searchKey.value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return esc.replace(new RegExp(kw, 'gi'), m => `<mark style="background:#fef08a;padding:0 2px">${m}</mark>`)
}

function onPageSizeChange(size) {
  pageSize.value = size
  currentPage.value = 1
  loadTasks()
}

async function loadPlansData() {
  try {
    const r = await getPlans()
    plans.value = r.data?.items || r.data || []
    if (plans.value.length && !filterPlanId.value) {
      const sorted = [...plans.value].sort((a, b) => (b.year || 0) - (a.year || 0))
      filterPlanId.value = sorted[0].id
    }
  } catch {}
}
async function loadAllUnits() { try { const r = await getUnits(); allUnits.value = r.data?.items || r.data || [] } catch {} }

async function loadTasks() {
  const params = { page: currentPage.value, page_size: pageSize.value }
  if (searchKey.value) { params.search = searchKey.value; params.search_type = 'all' }
  if (filterPlanId.value) params.plan_id = filterPlanId.value
  if (filterStatus.value) params.status = filterStatus.value
  if (chipSelected.value.length) {
    if (chipCategory.value === 'dimension') params.dimension_ids = chipSelected.value.map(c => c.id).join(',')
    else if (chipCategory.value === 'key_work') params.key_works = chipSelected.value.map(c => c.name || c).join(',')
    else if (chipCategory.value === 'assessor') params.assessor_unit_id = chipSelected.value.map(c => c.id).join(',')
    else if (chipCategory.value === 'unit') params.unit_id = chipSelected.value.map(c => c.id).join(',')
    else if (chipCategory.value === 'period') params.period = chipSelected.value.map(c => c.id).join(',')
  }
  try {
    const r = await api.getTasks(params)
    if (r.data?.items) {
      tasks.value = r.data.items
      total.value = r.data.total
    } else {
      tasks.value = r.data || []
      total.value = tasks.value.length
    }
  } catch {}
}

async function loadFilterOpts() {
  if (!filterPlanId.value) { filterOpts.value = { dimensions: [], key_works: [], assessor_units: [], assessed_units: [] }; return }
  try {
    const r = await api.getTaskFilterOptions(filterPlanId.value)
    filterOpts.value = r.data?.data || r.data || filterOpts.value
  } catch { filterOpts.value = { dimensions: [], key_works: [], assessor_units: [], assessed_units: [] } }
}

watch(filterPlanId, async (pid) => {
  if (pid) {
    try {
      const r = await getPlan(pid)
      const plan = r.data
      assessorUnits.value = plan.assessor_units || []
      const dim = plan.evaluation_dimensions?.find(d => d.is_actual_assessment)
      availableDims.value = dim?.assessment_dimensions || []
    } catch {
      assessorUnits.value = []
      availableDims.value = []
    }
    loadFilterOpts()
  }
})

// 任务 CRUD
const dialogVisible = ref(false); const isEdit = ref(false); const editId = ref(null)
const formRef = ref(); const form = reactive({
  plan_id: null, assessment_dimension_id: null, unit_id: null, assessor_unit_id: null,
  key_work: '', main_task: '', scoring_note: '', review_period: '月度',
})
const formRules = {
  plan_id: [{ required: true, message: '请选择方案', trigger: 'change' }],
  assessment_dimension_id: [{ required: true, message: '请选择考核维度', trigger: 'change' }],
  unit_id: [{ required: true, message: '请选择被考核单位', trigger: 'change' }],
  assessor_unit_id: [{ required: true, message: '请选择评价部门', trigger: 'change' }],
  key_work: [{ required: true, message: '请输入重点工作', trigger: 'blur' }],
  main_task: [{ required: true, message: '请输入主要任务', trigger: 'blur' }],
  review_period: [{ required: true, message: '请选择晾晒周期', trigger: 'change' }],
}

function resetForm() {
  form.plan_id = null; form.assessment_dimension_id = null; form.unit_id = null
  form.assessor_unit_id = null; form.key_work = ''; form.main_task = ''
  form.scoring_note = ''; form.review_period = '月度'
}

function openCreate() {
  isEdit.value = false; editId.value = null; resetForm(); dialogVisible.value = true
}
function openEdit(row) {
  isEdit.value = true; editId.value = row.id
  form.plan_id = row.plan_id; form.assessment_dimension_id = row.assessment_dimension_id
  form.unit_id = row.unit_id; form.assessor_unit_id = row.assessor_unit_id
  form.key_work = row.key_work; form.main_task = row.main_task
  form.scoring_note = row.scoring_note; form.review_period = row.review_period
  dialogVisible.value = true
}

async function handleSave() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  const data = { ...form }
  try {
    if (isEdit.value) { await api.updateTask(editId.value, data); ElMessage.success('编辑成功') }
    else { await api.createTask(data); ElMessage.success('创建成功') }
    dialogVisible.value = false; await loadTasks()
  } catch {}
}

async function handleDelete(row) {
  await ElMessageBox.confirm('确定删除该任务？', '确认', { type: 'warning' })
  try { await api.deleteTask(row.id); ElMessage.success('删除成功'); await loadTasks() } catch {}
}
async function handleBatchDelete() {
  await ElMessageBox.confirm(`确定删除选中的 ${selectedRows.value.length} 个任务？`, '批量删除', { type: 'warning' })
  try {
    const ids = selectedRows.value.map(r => r.id)
    await api.batchDeleteTasks(ids)
    ElMessage.success('批量删除成功')
    selectedRows.value = []
    await loadTasks()
  } catch {}
}
async function handleBatchDeleteAll() {
  const plan = plans.value.find(p => p.id === filterPlanId.value)
  const planName = plan?.name || '当前方案'
  await ElMessageBox.confirm(
    `确定删除「${planName}」的全部任务？此操作不可恢复！`,
    '删除全部任务',
    { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' }
  )
  try {
    const r = await api.batchDeleteAllTasks(filterPlanId.value)
    ElMessage.success(r.msg || '删除成功')
    await loadTasks()
  } catch {}
}

async function handleReview(row, status) {
  try { await api.reviewTask(row.id, status); ElMessage.success('审核完成'); await loadTasks() } catch {}
}

// 填报
const submitVisible = ref(false); const submitContent = ref(''); const submitTaskId = ref(null)
function openSubmit(row) { submitTaskId.value = row.id; submitContent.value = ''; submitVisible.value = true }
async function handleSubmit() {
  if (!submitContent.value) { ElMessage.warning('请填写内容'); return }
  try { await api.submitTask(submitTaskId.value, submitContent.value); ElMessage.success('提交成功'); submitVisible.value = false; await loadTasks() } catch {}
}

// 打分
const scoreVisible = ref(false); const scoreVal = ref(0); const scoreComment = ref(''); const scoreTaskId = ref(null)
function openScore(row) { scoreTaskId.value = row.id; scoreVal.value = row.scores?.[0]?.score || 0; scoreComment.value = row.scores?.[0]?.comment || ''; scoreVisible.value = true }
async function handleScore() {
  try { await api.scoreTask(scoreTaskId.value, scoreVal.value, scoreComment.value); ElMessage.success('打分成功'); scoreVisible.value = false; await loadTasks() } catch {}
}

// 查看
const viewVisible = ref(false); const viewTask = ref(null)
function openView(row) { viewTask.value = row; viewVisible.value = true }

// 导入导出
async function handleImport(file) {
  if (!filterPlanId.value) { ElMessage.warning('请先筛选考核方案'); return false }
  try {
    const r = await api.importTasks(filterPlanId.value, file)
    const contentType = r.headers['content-type'] || ''
    if (contentType.includes('application/json')) {
      // 全部成功
      const text = await r.data.text()
      const data = JSON.parse(text)
      ElMessage.success(data.msg || '导入成功')
      await loadTasks()
    } else {
      // 有错误，返回的是 Excel 错误报告
      const blob = r.data
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `考核任务导入错误报告.xlsx`
      a.click()
      URL.revokeObjectURL(url)
      ElMessage.error('导入数据存在问题，已下载错误报告，请修正后重新导入')
    }
  } catch {}
  return false
}
async function downloadTpl() {
  const r = await api.downloadTaskTemplate()
  const url = URL.createObjectURL(r.data)
  const a = document.createElement('a'); a.href = url; a.download = '考核任务导入模板.xlsx'; a.click(); URL.revokeObjectURL(url)
}
function buildExportParams() {
  const params = {}
  if (filterPlanId.value) params.plan_id = filterPlanId.value
  if (searchKey.value) { params.search = searchKey.value; params.search_type = 'all' }
  if (filterStatus.value) params.status = filterStatus.value
  if (chipSelected.value.length) {
    if (chipCategory.value === 'dimension') params.dimension_ids = chipSelected.value.map(c => c.id).join(',')
    else if (chipCategory.value === 'key_work') params.key_works = chipSelected.value.map(c => c.name || c).join(',')
    else if (chipCategory.value === 'assessor') params.assessor_unit_id = chipSelected.value.map(c => c.id).join(',')
    else if (chipCategory.value === 'unit') params.unit_id = chipSelected.value.map(c => c.id).join(',')
    else if (chipCategory.value === 'period') params.period = chipSelected.value.map(c => c.id).join(',')
  }
  return params
}

function downloadBlob(r, filename) {
  const url = URL.createObjectURL(r.data)
  const a = document.createElement('a'); a.href = url; a.download = filename; a.click(); URL.revokeObjectURL(url)
}

async function handleExportMenu(cmd) {
  const params = buildExportParams()
  const map = {
    'search': ['exportTasks', '考核任务书_搜索结果.xlsx'],
    'single': ['exportAllSingle', '考核任务书_全量单表.xlsx'],
    'by-unit': ['exportAllByUnit', '考核任务书_按被考核单位.zip'],
    'by-assessor': ['exportByAssessor', '考核任务书_按主考单位.zip'],
  }
  const [fn, filename] = map[cmd] || []
  if (!fn) return
  try { const r = await api[fn](params); downloadBlob(r, filename) } catch {}
}

onMounted(async () => { await loadPlansData(); await loadFilterOpts(); loadAllUnits(); loadTasks() })
</script>

<style scoped>
.chip-filter-area { margin-bottom: 14px; padding: 12px; background: #f5f7fa; border-radius: 8px; border: 1px solid #e4e7ed; }
.chip-grid { display: flex; flex-wrap: wrap; gap: 8px; max-height: 200px; overflow-y: auto; }
.chip-item { display: inline-block; padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; background: #fff; border: 1px solid #dcdfe6; color: #606266; transition: all 0.2s; user-select: none; white-space: nowrap; }
.chip-item:hover { border-color: #409eff; color: #409eff; }
.chip-item.active { background: #409eff; color: #fff; border-color: #409eff; }
.chip-item.disabled { color: #f56c6c; border-color: #fbc4c4; background: #fef0f0; cursor: not-allowed; }
.chip-item.disabled:hover { border-color: #fbc4c4; color: #f56c6c; }
.chip-summary { font-size: 12px; color: #909399; margin-bottom: 8px; }
.cell-wrap { white-space: pre-wrap; word-break: break-all; }
</style>
