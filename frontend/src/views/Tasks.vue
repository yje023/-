<template>
  <div class="content-card">
    <div class="search-bar">
      <el-select v-model="filterPlanId" placeholder="筛选方案" clearable @change="onFilterChange" style="width:200px">
        <el-option v-for="p in plans" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <el-select v-model="filterStatus" placeholder="筛选状态" clearable @change="onFilterChange" style="width:140px">
        <el-option label="待填报" value="pending" />
        <el-option label="已提交" value="submitted" />
        <el-option label="已审核" value="reviewed" />
      </el-select>
      <el-input v-model="searchKey" placeholder="搜索..." clearable @clear="onSearch" @keyup.enter="onSearch" style="width:160px" />
      <el-button type="primary" @click="onSearch">搜索</el-button>
      <el-button v-if="activeFilterCount" @click="clearChipFilter">清除筛选({{ activeFilterCount }})</el-button>
    </div>

    <!-- 多维度方片筛选区 -->
    <div class="chip-filter-area">
      <div v-if="!filterPlanId" style="text-align:center;color:#909399;padding:8px">请先选择一个考核方案查看维度筛选</div>
      <template v-else>
      <div v-for="dim in chipDimensions" :key="dim.key" class="chip-dim-row">
        <span class="chip-dim-label">{{ dim.label }}</span>
        <div :ref="el => setChipGridRef(dim.key, el)" :class="['chip-grid', { collapsed: dim.collapsed }]">
          <span class="chip-toggle" @click="dim.collapsed = !dim.collapsed">{{ dim.collapsed ? '▼' : '▲' }}</span>
          <span v-if="!dim.options.length" class="chip-empty">暂无数据</span>
          <template v-for="(item, ci) in dim.options" :key="item.id || item">
            <div
              :class="['chip-item', { active: isChipSelected(dim.key, item), disabled: item.active === false && !isChipSelected(dim.key, item) }]"
              draggable="true"
              @dragstart="onChipDragStart($event, dim.key, ci)"
              @dragover.prevent="onChipDragOver($event, dim.key, ci)"
              @dragenter.prevent="onChipDragEnter($event, dim.key, ci)"
              @dragleave="onChipDragLeave($event)"
              @drop="onChipDrop($event, dim.key, ci)"
              @dragend="onChipDragEnd($event)"
              @click="item.active !== false && toggleChip(dim.key, item)"
            >{{ item.name || item }}</div>
          </template>
        </div>
      </div>
      </template>
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
import { ref, reactive, computed, onMounted, watch, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '../store/auth'
import * as api from '../api/task'
import { getPlans, getPlan } from '../api/plan'
import { getUnits } from '../api/unit'
import { getChipSortOrder, saveChipSortOrder } from '../api/user'

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

// 多维度方片筛选
const filterOpts = ref({ dimensions: [], key_works: [], assessor_units: [], assessed_units: [], review_periods: [] })
const chipDimensions = reactive([
  { key: 'dimension', label: '考核维度', options: [], selected: [], collapsed: true },
  { key: 'key_work', label: '重点工作', options: [], selected: [], collapsed: true },
  { key: 'assessor', label: '主考单位', options: [], selected: [], collapsed: true },
  { key: 'unit', label: '被考核单位', options: [], selected: [], collapsed: true },
  { key: 'period', label: '晾晒周期', options: [], selected: [], collapsed: true },
])
const activeFilterCount = computed(() => chipDimensions.reduce((s, d) => s + d.selected.length, 0))

const chipGridRefs = {}
function setChipGridRef(key, el) { if (el) chipGridRefs[key] = el }
function checkChipOverflow() {
  for (const dim of chipDimensions) {
    if (dim.options.length > 6) dim.collapsed = true; else dim.collapsed = false
  }
}

// ===== 芯片拖拽排序 =====
const dragState = reactive({ sourceDimKey: null, sourceIndex: -1 })
const chipPageId = 'tasks'

function onChipDragStart(e, dimKey, index) {
  dragState.sourceDimKey = dimKey
  dragState.sourceIndex = index
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData('text/plain', `${dimKey}:${index}`)
  setTimeout(() => e.target.classList.add('dragging'), 0)
}
function onChipDragOver(e, dimKey, index) { e.dataTransfer.dropEffect = 'move' }
function onChipDragEnter(e, dimKey, index) {
  if (dimKey !== dragState.sourceDimKey) return
  e.target.classList.add('drag-over')
}
function onChipDragLeave(e) { e.target.classList.remove('drag-over') }
function onChipDrop(e, dimKey, index) {
  e.target.classList.remove('drag-over')
  if (dimKey !== dragState.sourceDimKey) return
  if (dragState.sourceIndex === index) return
  const dim = chipDimensions.find(d => d.key === dimKey)
  if (!dim) return
  const [removed] = dim.options.splice(dragState.sourceIndex, 1)
  dim.options.splice(index, 0, removed)
  const sortOrder = dim.options.map(o => String(o.id || o))
  saveChipSortOrder(chipPageId, dimKey, sortOrder).catch(() => {})
  dragState.sourceDimKey = null; dragState.sourceIndex = -1
}
function onChipDragEnd(e) {
  e.target.classList.remove('dragging')
  document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'))
}

// 排序持久化
let savedSortOrders = {}
async function loadChipSortOrders() {
  try {
    const res = await getChipSortOrder(chipPageId)
    savedSortOrders = res.data || res || {}
  } catch { savedSortOrders = {} }
}
function applySortOrders() {
  for (const dim of chipDimensions) {
    const order = savedSortOrders[dim.key]
    if (order && order.length) {
      const orderMap = new Map(order.map((id, i) => [String(id), i]))
      dim.options.sort((a, b) => {
        const aOrder = orderMap.get(String(a.id || a))
        const bOrder = orderMap.get(String(b.id || b))
        if (aOrder !== undefined && bOrder !== undefined) return aOrder - bOrder
        if (aOrder !== undefined) return -1
        if (bOrder !== undefined) return 1
        return 0
      })
    }
  }
}

function buildChipOptions() {
  const opts = filterOpts.value
  const presetDims = availableDims.value || []
  const presetAssessors = assessorUnits.value || []
  // 维度 + 主考单位：合并预设 + API 返回的 active 状态（API 返回全量选项）
  const activeDimMap = {}; for (const d of (opts.dimensions || [])) { activeDimMap[d.id] = d.active !== false }
  const activeAssessorMap = {}; for (const a of (opts.assessor_units || [])) { activeAssessorMap[a.id] = a.active !== false }
  chipDimensions[0].options = presetDims.map(p => ({ ...p, active: p.id in activeDimMap ? activeDimMap[p.id] : false }))
  chipDimensions[2].options = presetAssessors.map(p => ({ ...p, active: p.id in activeAssessorMap ? activeAssessorMap[p.id] : false }))
  // 重点工作、被考核单位、晾晒周期：直接使用 API 返回（已含全量选项+active）
  chipDimensions[1].options = (opts.key_works || []).map(k => typeof k === 'string' ? { id: k, name: k, active: true } : { id: k.id || k, name: k.name || k, active: k.active !== false })
  chipDimensions[3].options = (opts.assessed_units || []).map(u => ({ ...u, active: u.active !== false }))
  chipDimensions[4].options = (opts.review_periods || []).map(p => ({ ...p, active: p.active !== false }))
  checkChipOverflow()
  applySortOrders()
}

function isChipSelected(dimKey, item) {
  const dim = chipDimensions.find(d => d.key === dimKey)
  if (!dim) return false
  const id = item.id || item
  return dim.selected.some(s => (s.id || s) === id)
}

function toggleChip(dimKey, item) {
  const dim = chipDimensions.find(d => d.key === dimKey)
  if (!dim) return
  const id = item.id || item
  const idx = dim.selected.findIndex(s => (s.id || s) === id)
  if (idx >= 0) dim.selected.splice(idx, 1)
  else dim.selected.push(item)
  currentPage.value = 1; loadTasks(); loadFilterOpts()
}

function clearChipFilter() { chipDimensions.forEach(d => d.selected = []); currentPage.value = 1; loadFilterOpts(); loadTasks() }

function onSelectionChange(rows) { selectedRows.value = rows }
function onSearch() { currentPage.value = 1; loadTasks() }
function onFilterChange() { currentPage.value = 1; clearAllChips(); loadFilterOpts(); loadTasks() }
function clearAllChips() { chipDimensions.forEach(d => d.selected = []) }

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
  for (const dim of chipDimensions) {
    if (dim.selected.length) {
      if (dim.key === 'dimension') params.dimension_ids = dim.selected.map(c => c.id).join(',')
      else if (dim.key === 'key_work') params.key_works = dim.selected.map(c => c.name || c).join(',')
      else if (dim.key === 'assessor') params.assessor_unit_id = dim.selected.map(c => c.id).join(',')
      else if (dim.key === 'unit') params.unit_id = dim.selected.map(c => c.id).join(',')
      else if (dim.key === 'period') params.period = dim.selected.map(c => c.id).join(',')
    }
  }
  try {
    const r = await api.getTasks(params)
    if (r.data?.items) { tasks.value = r.data.items; total.value = r.data.total }
    else { tasks.value = r.data || []; total.value = tasks.value.length }
  } catch {}
}

let filterLoadId = 0
async function loadFilterOpts() {
  if (!filterPlanId.value) {
    filterOpts.value = { dimensions: [], key_works: [], assessor_units: [], assessed_units: [], review_periods: [] }
    chipDimensions.forEach(d => d.options = [])
    return
  }
  const thisId = ++filterLoadId
  try {
    const currentFilters = {}
    for (const dim of chipDimensions) {
      if (dim.selected.length) {
        currentFilters[dim.key] = dim.selected.map(c => c.id || c)
      }
    }
    const r = await api.getTaskFilterOptions(filterPlanId.value, currentFilters)
    if (thisId !== filterLoadId) return  // 竞态：后续调用已覆盖
    filterOpts.value = r.data?.data || r.data || filterOpts.value
  } catch {
    if (thisId !== filterLoadId) return  // 竞态：后续调用已覆盖
    filterOpts.value = { dimensions: [], key_works: [], assessor_units: [], assessed_units: [], review_periods: [] }
  }
}

// 当 filterOpts、availableDims、assessorUnits 就绪后构建芯片
watch([filterOpts, availableDims, assessorUnits], () => {
  if (filterPlanId.value) buildChipOptions()
})

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
  for (const dim of chipDimensions) {
    if (dim.selected.length) {
      if (dim.key === 'dimension') params.dimension_ids = dim.selected.map(c => c.id).join(',')
      else if (dim.key === 'key_work') params.key_works = dim.selected.map(c => c.name || c).join(',')
      else if (dim.key === 'assessor') params.assessor_unit_id = dim.selected.map(c => c.id).join(',')
      else if (dim.key === 'unit') params.unit_id = dim.selected.map(c => c.id).join(',')
      else if (dim.key === 'period') params.period = dim.selected.map(c => c.id).join(',')
    }
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

onMounted(async () => { await loadChipSortOrders(); await loadPlansData(); loadAllUnits(); loadTasks() })
</script>

<style scoped>
.chip-filter-area { margin-bottom: 14px; padding: 12px; background: #f5f7fa; border-radius: 8px; border: 1px solid #e4e7ed; }
.chip-grid { display: inline-flex; flex-wrap: wrap; gap: 8px; max-height: 120px; overflow-y: auto; max-width: calc(100% - 88px); transition: max-height 0.25s; }
.chip-grid.collapsed { max-height: 30px; overflow-y: hidden; }
.chip-toggle { display: inline-block; padding: 4px 8px; border-radius: 6px; font-size: 11px; cursor: pointer; color: #909399; background: #f0f2f5; border: 1px dashed #dcdfe6; user-select: none; white-space: nowrap; transition: all 0.2s; }
.chip-toggle:hover { color: #409eff; border-color: #409eff; background: #ecf5ff; }
.chip-dim-row { margin-bottom: 8px; }
.chip-dim-row:last-child { margin-bottom: 0; }
.chip-dim-label { display: inline-block; font-size: 12px; font-weight: 600; color: #606266; min-width: 80px; vertical-align: top; padding-top: 7px; }
.chip-item { display: inline-block; padding: 4px 12px; border-radius: 6px; font-size: 12px; cursor: pointer; background: #fff; border: 1px solid #dcdfe6; color: #606266; transition: all 0.2s; user-select: none; white-space: nowrap; }
.chip-item:hover { border-color: #409eff; color: #409eff; }
.chip-item.active { background: #409eff; color: #fff; border-color: #409eff; }
.chip-item.disabled { color: #f56c6c; border-color: #fbc4c4; background: #fef0f0; cursor: not-allowed; }
.chip-item.disabled:hover { border-color: #fbc4c4; color: #f56c6c; }
.chip-item.dragging { opacity: 0.4; }
.chip-item.drag-over { border-color: #409eff; background: #ecf5ff; transform: scale(1.05); }
.chip-empty { font-size: 12px; color: #c0c4cc; padding: 4px 0; }
.cell-wrap { white-space: pre-wrap; word-break: break-all; }
</style>
