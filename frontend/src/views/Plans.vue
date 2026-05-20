<template>
  <div class="content-card">
    <div class="search-bar">
      <el-button type="primary" @click="openCreate">创建考核方案</el-button>
    </div>

    <el-table :data="plans" border stripe>
      <template #empty><el-empty description="暂无考核方案" :image-size="80" /></template>
      <el-table-column prop="name" label="方案名称" />
      <el-table-column prop="year" label="考核年度" width="100" />
      <el-table-column prop="start_date" label="开始日期" width="110" />
      <el-table-column prop="end_date" label="结束日期" width="110" />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status==='draft'?'info':row.status==='issued'?'success':'danger'">
            {{ row.status==='draft'?'草稿':row.status==='issued'?'已下发':'已关闭' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="320">
        <template #default="{ row }">
          <el-button size="small" link @click="openEdit(row)">编辑</el-button>
          <el-button size="small" link type="success" @click="openDetail(row)">详情</el-button>
          <el-button v-if="row.status==='draft'" size="small" link type="primary" @click="handleIssue(row)">下发</el-button>
          <el-button size="small" link type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination-wrap" v-if="total > 0">
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="loadPlans"
      />
    </div>

    <!-- 新建/编辑方案基本信息 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑方案' : '新建方案'" width="550px">
      <el-form ref="formRef" :model="form" :rules="formRules">
        <el-form-item label="方案名称" prop="name">
          <el-input v-model="form.name" placeholder="如：2026年度考核方案" />
        </el-form-item>
        <el-form-item label="考核年度" prop="year">
          <el-input-number v-model="form.year" :min="2020" :max="2099" style="width:200px" />
        </el-form-item>
        <el-form-item label="开始日期" prop="start_date">
          <el-date-picker v-model="form.start_date" type="date" placeholder="选择开始日期" value-format="YYYY-MM-DD" />
        </el-form-item>
        <el-form-item label="结束日期" prop="end_date">
          <el-date-picker v-model="form.end_date" type="date" placeholder="选择结束日期" value-format="YYYY-MM-DD" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>

    <!-- 详情/配置对话框 -->
    <el-dialog v-model="detailVisible" title="方案详情" width="900px" top="30px">
      <template v-if="detail">
        <el-descriptions :column="2" border style="margin-bottom:20px">
          <el-descriptions-item label="方案名称">{{ detail.name }}</el-descriptions-item>
          <el-descriptions-item label="考核年度">{{ detail.year }}</el-descriptions-item>
          <el-descriptions-item label="开始日期">{{ detail.start_date }}</el-descriptions-item>
          <el-descriptions-item label="结束日期">{{ detail.end_date }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="detail.status==='draft'?'info':'success'">{{ detail.status==='draft'?'草稿':'已下发' }}</el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <!-- 评价维度 -->
        <h4 style="margin-bottom:8px">评价维度（分值合计=100）<span style="font-weight:400;font-size:12px;color:#909399;margin-left:8px">剩余可分配：{{ remainingScore }} 分</span></h4>
        <el-table :data="detail.evaluation_dimensions || []" border size="small">
          <el-table-column prop="name" label="维度名称" />
          <el-table-column prop="score" label="分值" width="80">
            <template #default="{ row }">
              <el-input-number v-if="!row.is_actual_assessment" v-model="row.score" :min="1" :max="remainingScore + row.score" size="small" controls-position="right" @change="saveDim($event, row)" />
              <span v-else>{{ row.score }} <el-tooltip content="单位实际考核分值 = 100 - 其他维度分，自动计算"><span style="color:#909399;font-size:12px;cursor:help">ⓘ</span></el-tooltip></span>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="140">
            <template #default="{ row }">
              <el-tag v-if="row.is_actual_assessment" size="small" type="primary">单位实际考核</el-tag>
              <el-tag v-else size="small">其他评价维度</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="180">
            <template #default="{ row }">
              <template v-if="row.is_actual_assessment">
                <el-button size="small" @click="openAddAssessmentDim(row)">添加考核维度</el-button>
              </template>
              <template v-else>
                <el-button size="small" link @click="openEditDim(row)">编辑</el-button>
                <el-button size="small" link type="danger" @click="handleDeleteDim(row)">删除</el-button>
              </template>
            </template>
          </el-table-column>
          <!-- 考核维度子表 -->
          <el-table-column type="expand">
            <template #default="{ row }">
              <div v-if="row.is_actual_assessment && row.assessment_dimensions?.length" style="padding:8px 20px">
                <div v-for="ad in row.assessment_dimensions" :key="ad.id" style="display:flex;justify-content:space-between;align-items:center;padding:4px 0">
                  <span>{{ ad.name }}</span>
                  <span>
                    <el-button size="small" link @click="openEditAssessmentDim(ad)">编辑</el-button>
                    <el-button size="small" link type="danger" @click="handleDeleteAssessmentDim(ad)">删除</el-button>
                  </span>
                </div>
              </div>
            </template>
          </el-table-column>
        </el-table>
        <el-button size="small" type="primary" style="margin-top:8px" @click="openAddDim">+ 添加评价维度</el-button>

        <el-divider />

        <!-- 主考单位 -->
        <h4 style="margin-bottom:8px">主考单位</h4>
        <div style="margin-bottom:8px">
          <el-tree ref="assessorTree" :data="unitsTree" show-checkbox node-key="id" :props="{ label: 'name', children: 'children' }" :check-strictly="false" default-expand-all style="max-height:200px;overflow:auto" @check="onAssessorCheck" />
          <el-button size="small" type="primary" style="margin-top:4px" @click="saveAssessorUnits">保存主考单位</el-button>
        </div>

        <el-divider />

        <!-- 被考核分组 -->
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
          <h4>被考核分组</h4>
          <el-button size="small" type="primary" @click="openAddGroup">+ 新增分组</el-button>
        </div>
        <div v-for="g in detail.assessed_groups" :key="g.id" style="border:1px solid #e6e6e6;border-radius:4px;padding:12px;margin-bottom:8px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
            <strong>{{ g.name }}</strong>
            <span>
              <el-button size="small" link @click="openEditGroup(g)">编辑</el-button>
              <el-button size="small" link type="danger" @click="handleDeleteGroup(g)">删除</el-button>
            </span>
          </div>
          <div style="font-size:13px;color:#606266">被考核单位：<el-tag v-for="u in g.units" :key="u.id" size="small" style="margin:1px">{{ u.name }}</el-tag><span v-if="!g.units?.length">无</span></div>
          <div style="font-size:13px;color:#606266;margin-top:4px">考核维度权重：
            <el-tag v-for="w in g.dimension_weights" :key="w.assessment_dimension_id" size="small" type="warning" style="margin:1px">{{ w.dimension_name }} {{ w.weight }}%</el-tag>
          </div>
        </div>
      </template>
    </el-dialog>

    <!-- 添加评价维度 -->
    <el-dialog v-model="dimVisible" :title="dimForm.editId ? '编辑评价维度' : '添加评价维度'" width="400px">
      <el-form>
        <el-form-item label="维度名称"><el-input v-model="dimForm.name" placeholder="如：民主测评" /></el-form-item>
        <el-form-item label="分值"><el-input-number v-model="dimForm.score" :min="1" :max="dimForm.editId ? remainingScore + (dimForm.oldScore || 0) : remainingScore" /> <span style="color:#909399;font-size:12px;margin-left:4px">剩余 {{ remainingScore }} 分</span></el-form-item>
      </el-form>
      <template #footer><el-button @click="dimVisible=false">取消</el-button><el-button type="primary" @click="handleAddDim">确认</el-button></template>
    </el-dialog>

    <!-- 添加考核维度 -->
    <el-dialog v-model="adVisible" title="添加考核维度" width="400px">
      <el-form><el-form-item label="维度名称"><el-input v-model="adForm.name" placeholder="如：党建工作" /></el-form-item></el-form>
      <template #footer><el-button @click="adVisible=false">取消</el-button><el-button type="primary" @click="handleAddAssessmentDim">确认</el-button></template>
    </el-dialog>

    <!-- 被考核分组 -->
    <el-dialog v-model="groupVisible" :title="groupEditId ? '编辑分组' : '新增分组'" width="650px">
      <el-form>
        <el-form-item label="分组名称"><el-input v-model="groupForm.name" placeholder="如：第一组" /></el-form-item>
        <el-form-item label="被考核单位">
          <el-tree ref="groupUnitTree" :data="unitsTree" show-checkbox node-key="id" :props="{ label: 'name', children: 'children', disabled: isOrg }" default-expand-all style="max-height:200px;overflow:auto" />
        </el-form-item>
        <el-form-item label="考核维度权重（合计=100%）">
          <div v-for="ad in actualAssessmentDims" :key="ad.id" style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
            <span style="width:120px">{{ ad.name }}</span>
            <el-input-number v-model="groupWeights[ad.id]" :min="0" :max="100" size="small" controls-position="right" /> %
          </div>
          <span v-if="!actualAssessmentDims.length" style="color:#909399">请先在"单位实际考核"下添加考核维度</span>
        </el-form-item>
      </el-form>
      <template #footer><el-button @click="groupVisible=false">取消</el-button><el-button type="primary" @click="handleSaveGroup">确认</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, nextTick, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as api from '../api/plan'

const plans = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(10)
const unitsTree = ref([])
const assessorTree = ref()
const groupUnitTree = ref()

function isOrg(data) { return data.type === 'org' }

async function loadPlans() {
  try {
    const r = await api.getPlans({ page: currentPage.value, page_size: pageSize.value })
    if (r.data?.items) { plans.value = r.data.items; total.value = r.data.total }
    else { plans.value = r.data || []; total.value = plans.value.length }
  } catch {}
}
async function loadUnitsTree() { try { const r = await api.getUnitsTree(); unitsTree.value = r.data || [] } catch {} }

// 方案 CRUD
const dialogVisible = ref(false); const isEdit = ref(false); const editId = ref(null)
const formRef = ref(); const form = reactive({ name: '', year: 2026, start_date: '', end_date: '' })
const formRules = {
  name: [{ required: true, message: '请输入方案名称', trigger: 'blur' }],
  year: [{ required: true, message: '请输入考核年度', trigger: 'blur' }],
  start_date: [{ required: true, message: '请选择开始日期', trigger: 'change' }],
  end_date: [{ required: true, message: '请选择结束日期', trigger: 'change' }],
}

function openCreate() { isEdit.value = false; editId.value = null; form.name = ''; form.year = 2026; form.start_date = ''; form.end_date = ''; dialogVisible.value = true }
function openEdit(row) { isEdit.value = true; editId.value = row.id; form.name = row.name; form.year = row.year; form.start_date = row.start_date; form.end_date = row.end_date; dialogVisible.value = true }

async function handleSave() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  try {
    const data = { name: form.name, year: form.year, start_date: form.start_date, end_date: form.end_date }
    if (isEdit.value) { await api.updatePlan(editId.value, data); ElMessage.success('编辑成功') }
    else { await api.createPlan(data); ElMessage.success('创建成功，已自动创建"单位实际考核"维度') }
    dialogVisible.value = false; await loadPlans()
  } catch {}
}

async function handleDelete(row) {
  await ElMessageBox.confirm(`确定删除方案「${row.name}」？所有关联的考核任务、分组、权重将被同步清除，此操作不可恢复。`, '确认删除', { type: 'warning' })
  try { await api.deletePlan(row.id); ElMessage.success('删除成功'); await loadPlans() } catch {}
}

async function handleIssue(row) {
  await ElMessageBox.confirm('确定下发该方案？', '确认下发', { type: 'warning' })
  try { await api.issuePlan(row.id); ElMessage.success('下发成功'); await loadPlans(); if (detailVisible.value) detailVisible.value = false } catch {}
}

// 详情
const detailVisible = ref(false); const detail = ref(null)
const remainingScore = computed(() => {
  if (!detail.value?.evaluation_dimensions) return 100
  const otherTotal = detail.value.evaluation_dimensions
    .filter(d => !d.is_actual_assessment)
    .reduce((sum, d) => sum + d.score, 0)
  return Math.max(0, 100 - otherTotal)
})
async function openDetail(row) {
  try { const r = await api.getPlan(row.id); detail.value = r.data; detailVisible.value = true } catch {}
}
async function refreshDetail() { if (detail.value) { const r = await api.getPlan(detail.value.id); detail.value = r.data } }

// 评价维度
const dimVisible = ref(false); const dimForm = reactive({ name: '', score: 20 })
function openAddDim() { dimForm.name = ''; dimForm.score = 1; delete dimForm.editId; dimVisible.value = true }
function openEditDim(row) { dimForm.name = row.name; dimForm.score = row.score; dimForm.editId = row.id; dimForm.oldScore = row.score; dimVisible.value = true }
async function handleAddDim() {
  if (!dimForm.name) return
  try {
    if (dimForm.editId) {
      await api.updateDimension(dimForm.editId, { name: dimForm.name, score: dimForm.score })
      delete dimForm.editId
    } else {
      await api.addDimension(detail.value.id, { name: dimForm.name, score: dimForm.score })
    }
    dimVisible.value = false; await refreshDetail()
  } catch {}
}
async function saveDim(score, row) { try { await api.updateDimension(row.id, { score }); ElMessage.success('分值已更新') } catch {} }
async function handleDeleteDim(row) {
  await ElMessageBox.confirm('确定删除该评价维度？', '确认', { type: 'warning' })
  try { await api.deleteDimension(row.id); ElMessage.success('删除成功'); await refreshDetail() } catch {}
}

// 考核维度
const adVisible = ref(false); const adForm = reactive({ name: '', dimId: null })
const actualAssessmentDims = ref([])
function openAddAssessmentDim(row) { adForm.name = ''; adForm.dimId = row.id; actualAssessmentDims.value = row.assessment_dimensions || []; adVisible.value = true }
function openEditAssessmentDim(ad) { adForm.name = ad.name; adForm.editId = ad.id; adVisible.value = true }
async function handleAddAssessmentDim() {
  if (!adForm.name) return
  try {
    if (adForm.editId) { await api.updateAssessmentDim(adForm.editId, { name: adForm.name }); delete adForm.editId }
    else { await api.addAssessmentDim(adForm.dimId, { name: adForm.name }) }
    adVisible.value = false; await refreshDetail()
  } catch {}
}
async function handleDeleteAssessmentDim(ad) {
  await ElMessageBox.confirm('确定删除该考核维度？', '确认', { type: 'warning' })
  try { await api.deleteAssessmentDim(ad.id); await refreshDetail() } catch {}
}

// 主考单位
function onAssessorCheck() { /* handle in save */ }
async function saveAssessorUnits() {
  const checked = assessorTree.value.getCheckedNodes(false, true)
  const ids = checked.filter(n => n.type === 'unit').map(n => n.id)
  const halfChecked = assessorTree.value.getHalfCheckedNodes()
  const halfIds = halfChecked.filter(n => n.type === 'unit').map(n => n.id)
  const allIds = [...new Set([...ids, ...halfIds])]
  try { await api.setAssessorUnits(detail.value.id, allIds); ElMessage.success('已保存'); await refreshDetail() } catch {}
}

// 被考核分组
const groupVisible = ref(false); const groupEditId = ref(null); const groupForm = reactive({ name: '' }); const groupWeights = reactive({})
function openAddGroup() {
  groupEditId.value = null; groupForm.name = ''; groupWeightsObj()
  const dims = detail.value.evaluation_dimensions?.find(d => d.is_actual_assessment)?.assessment_dimensions || []
  actualAssessmentDims.value = dims
  for (const ad of dims) { groupWeights[ad.id] = 0 }
  groupVisible.value = true
}
function openEditGroup(g) {
  groupEditId.value = g.id; groupForm.name = g.name; groupWeightsObj()
  const dims = detail.value.evaluation_dimensions?.find(d => d.is_actual_assessment)?.assessment_dimensions || []
  actualAssessmentDims.value = dims
  for (const ad of dims) { groupWeights[ad.id] = 0 }
  for (const w of g.dimension_weights) { groupWeights[w.assessment_dimension_id] = w.weight }
  groupVisible.value = true
  nextTick(() => {
    if (groupUnitTree.value) {
      groupUnitTree.value.setCheckedKeys(g.units.map(u => u.id))
    }
  })
}
function groupWeightsObj() { for (const k in groupWeights) delete groupWeights[k] }
async function handleSaveGroup() {
  const unitIds = groupUnitTree.value?.getCheckedNodes(false, true).filter(n => n.type === 'unit').map(n => n.id) || []
  const halfIds = groupUnitTree.value?.getHalfCheckedNodes().filter(n => n.type === 'unit').map(n => n.id) || []
  const allUnitIds = [...new Set([...unitIds, ...halfIds])]
  const weights = []
  for (const adId in groupWeights) {
    weights.push({ assessment_dimension_id: parseInt(adId), weight: groupWeights[adId] })
  }
  try {
    if (groupEditId.value) {
      await api.updateGroup(groupEditId.value, { name: groupForm.name, unit_ids: allUnitIds, dimension_weights: weights })
    } else {
      await api.createGroup(detail.value.id, { name: groupForm.name, unit_ids: allUnitIds, dimension_weights: weights })
    }
    ElMessage.success('保存成功'); groupVisible.value = false; await refreshDetail()
  } catch {}
}
async function handleDeleteGroup(g) {
  await ElMessageBox.confirm(`确定删除分组「${g.name}」？`, '确认', { type: 'warning' })
  try { await api.deleteGroup(g.id); await refreshDetail() } catch {}
}

onMounted(() => { loadPlans(); loadUnitsTree() })
</script>
