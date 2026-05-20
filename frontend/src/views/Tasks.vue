<template>
  <div class="content-card">
    <div class="search-bar">
      <el-input v-model="searchKey" placeholder="搜索任务..." clearable @clear="onSearch" @keyup.enter="onSearch" style="width:200px" />
      <el-select v-model="filterPlanId" placeholder="筛选方案" clearable @change="onFilterChange" style="width:200px">
        <el-option v-for="p in plans" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <el-select v-model="filterStatus" placeholder="筛选状态" clearable @change="onFilterChange" style="width:140px">
        <el-option label="待填报" value="pending" />
        <el-option label="已提交" value="submitted" />
        <el-option label="已审核" value="reviewed" />
      </el-select>
      <template v-if="auth.currentIdentity==='assessor'">
        <el-button type="primary" @click="openCreate">新建任务</el-button>
        <el-button @click="downloadTpl">下载导入模板</el-button>
        <el-button v-if="selectedRows.length" type="danger" @click="handleBatchDelete">删除选中({{ selectedRows.length }})</el-button>
        <el-upload :show-file-list="false" :before-upload="handleImport" accept=".xlsx,.xls" :multiple="true" style="display:inline-block">
          <el-button :disabled="!filterPlanId">批量导入xlsx</el-button>
        </el-upload>
      </template>
      <el-button @click="handleExport">导出xlsx</el-button>
      <el-button type="primary" @click="handleExportAll">全量导出ZIP</el-button>
    </div>

    <el-table :data="tasks" border stripe @selection-change="onSelectionChange" empty-description="暂无任务数据">
      <template #empty>
        <el-empty description="暂无任务数据" :image-size="80" />
      </template>
      <el-table-column type="selection" width="45" />
      <el-table-column prop="dimension_name" label="考核维度" width="120" />
      <el-table-column prop="key_work" label="重点工作" min-width="150" show-overflow-tooltip />
      <el-table-column prop="main_task" label="主要任务" min-width="180" show-overflow-tooltip />
      <el-table-column prop="review_period" label="晾晒周期" width="90" />
      <el-table-column v-if="auth.currentIdentity==='assessor'" prop="unit_name" label="被考核单位" width="120" />
      <el-table-column v-if="auth.currentIdentity==='assessed'" prop="assessor_unit_name" label="评价部门" width="120" />
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
function onSelectionChange(rows) { selectedRows.value = rows }

function onSearch() { currentPage.value = 1; loadTasks() }
function onFilterChange() { currentPage.value = 1; loadTasks() }

function onPageSizeChange(size) {
  pageSize.value = size
  currentPage.value = 1
  loadTasks()
}

async function loadPlansData() { try { const r = await getPlans(); plans.value = r.data?.items || r.data || [] } catch {} }
async function loadAllUnits() { try { const r = await getUnits(); allUnits.value = r.data?.items || r.data || [] } catch {} }

async function loadTasks() {
  const params = { page: currentPage.value, page_size: pageSize.value }
  if (searchKey.value) params.search = searchKey.value
  if (filterPlanId.value) params.plan_id = filterPlanId.value
  if (filterStatus.value) params.status = filterStatus.value
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
    for (const row of selectedRows.value) {
      await api.deleteTask(row.id)
    }
    ElMessage.success('批量删除成功')
    selectedRows.value = []
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
    ElMessage.success(r.msg || '导入成功')
    if (r.errors) ElMessage.warning('部分失败：' + r.errors.join('; '))
    await loadTasks()
  } catch {}
  return false
}
async function downloadTpl() {
  const r = await api.downloadTaskTemplate()
  const url = URL.createObjectURL(r.data)
  const a = document.createElement('a'); a.href = url; a.download = '考核任务导入模板.xlsx'; a.click(); URL.revokeObjectURL(url)
}
async function handleExport() {
  const params = {}
  if (filterPlanId.value) params.plan_id = filterPlanId.value
  try {
    const r = await api.exportTasks(params)
    const url = URL.createObjectURL(r.data)
    const a = document.createElement('a'); a.href = url; a.download = '考核任务书.xlsx'; a.click(); URL.revokeObjectURL(url)
  } catch {}
}
async function handleExportAll() {
  const params = {}
  if (filterPlanId.value) params.plan_id = filterPlanId.value
  try {
    const r = await api.exportAllTasks(params)
    const url = URL.createObjectURL(r.data)
    const a = document.createElement('a'); a.href = url; a.download = '考核任务书_全量导出.zip'; a.click(); URL.revokeObjectURL(url)
  } catch {}
}

onMounted(() => { loadPlansData(); loadAllUnits(); loadTasks() })
</script>
