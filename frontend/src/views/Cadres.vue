<template>
  <div class="cadres-page">
    <div class="toolbar">
      <el-input v-model="search" placeholder="搜索姓名..." style="width: 200px" clearable @change="load" @keyup.enter="load" />
      <el-select v-model="filterUnitId" placeholder="按单位筛选" style="width: 240px; margin-left: 8px" clearable
        filterable @change="load">
        <el-option v-for="u in allUnits" :key="u.id" :label="u.name" :value="u.id" />
      </el-select>
      <el-button type="primary" @click="openCreate" style="margin-left: 8px">新增加干部</el-button>
      <el-button @click="downloadTpl">下载导入模板</el-button>
      <el-upload :show-file-list="false" :before-upload="handleImport" accept=".xlsx,.xls"
        style="display:inline-block;margin-left:8px">
        <el-button>导入xlsx</el-button>
      </el-upload>
      <el-button @click="handleExport">导出xlsx</el-button>
      <el-button type="danger" v-if="checkedIds.length > 0" @click="handleBatchDelete">批量删除 ({{
        checkedIds.length }})</el-button>
    </div>

    <el-table :data="cadres" style="width: 100%" @selection-change="onSelectionChange" v-loading="loading">
      <el-table-column type="selection" width="50" />
      <el-table-column prop="name" label="姓名" width="100" />
      <el-table-column prop="unit_name" label="所属单位" min-width="180" />
      <el-table-column prop="gender" label="性别" width="60" />
      <el-table-column prop="position_type" label="职务类型" width="80" />
      <el-table-column prop="political_status" label="政治面貌" width="100" />
      <el-table-column prop="education" label="最高学历" width="100" />
      <el-table-column prop="fulltime_education" label="全日制学历" width="120" />
      <el-table-column prop="ethnicity" label="民族" width="80" />
      <el-table-column prop="specialty" label="专业领域" min-width="150" />
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
      <template #empty><el-empty description="暂无干部数据" :image-size="80" /></template>
    </el-table>

    <div v-if="total > 0" class="pagination-wrap">
      <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="total"
        :page-sizes="[20, 50, 100, 200]" layout="total, sizes, prev, pager, next, jumper"
        @current-change="load" @size-change="load" />
    </div>

    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑干部' : '新增加干部'" width="600px" @close="resetForm">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="姓名" prop="name">
              <el-input v-model="form.name" placeholder="请输入姓名" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="性别">
              <el-select v-model="form.gender" style="width: 100%">
                <el-option label="男" value="男" />
                <el-option label="女" value="女" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="所属单位">
          <el-select v-model="form.unit_id" filterable clearable placeholder="请选择单位" style="width: 100%">
            <el-option v-for="u in allUnits" :key="u.id" :label="u.name" :value="u.id" />
          </el-select>
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="出生日期">
              <el-date-picker v-model="form.birth_date" type="date" placeholder="选择日期" style="width: 100%"
                value-format="YYYY-MM-DD" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="职务类型">
              <el-select v-model="form.position_type" clearable style="width: 100%">
                <el-option label="正职" value="正职" />
                <el-option label="副职" value="副职" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="最高学历">
              <el-input v-model="form.education" placeholder="如：研究生" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="全日制学历">
              <el-input v-model="form.fulltime_education" placeholder="如：硕士研究生" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="政治面貌">
              <el-select v-model="form.political_status" clearable style="width: 100%">
                <el-option label="中共党员" value="中共党员" />
                <el-option label="民主党派" value="民主党派" />
                <el-option label="无党派" value="无党派" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="民族">
              <el-input v-model="form.ethnicity" placeholder="如：汉族" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="专业领域">
          <el-input v-model="form.specialty" placeholder="如：公共管理" />
        </el-form-item>
        <el-form-item label="擅长领域">
          <el-input v-model="form.expertise" placeholder="多个用逗号分隔，如：行政审批,政策研究" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getCadres, createCadre, updateCadre, deleteCadre,
  batchDeleteCadres, importCadres, exportCadres, downloadCadreTemplate
} from '../api/cadre'
import { getUnits } from '../api/unit'

const search = ref('')
const filterUnitId = ref(null)
const cadres = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const checkedIds = ref([])
const loading = ref(false)

const allUnits = ref([])

const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const form = reactive({
  name: '', unit_id: null, gender: '男', birth_date: null,
  education: '', fulltime_education: '', political_status: '',
  ethnicity: '', position_type: '', specialty: '', expertise: ''
})
const formRef = ref(null)
const rules = { name: [{ required: true, message: '请输入姓名', trigger: 'blur' }] }

async function loadUnits() {
  const res = await getUnits({ page_size: 9999 })
  allUnits.value = res.data.items || []
}

async function load() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (search.value) params.search = search.value
    if (filterUnitId.value) params.unit_id = filterUnitId.value
    const res = await getCadres(params)
    cadres.value = res.data.items || []
    total.value = res.data.total || 0
  } finally {
    loading.value = false
  }
}

function onSelectionChange(selection) { checkedIds.value = selection.map(r => r.id) }

function openCreate() {
  isEdit.value = false
  Object.assign(form, {
    name: '', unit_id: null, gender: '男', birth_date: null,
    education: '', fulltime_education: '', political_status: '',
    ethnicity: '', position_type: '', specialty: '', expertise: ''
  })
  dialogVisible.value = true
}
function openEdit(row) {
  isEdit.value = true; editId.value = row.id
  Object.assign(form, {
    name: row.name, unit_id: row.unit_id, gender: row.gender || '男',
    birth_date: row.birth_date, education: row.education || '',
    fulltime_education: row.fulltime_education || '', political_status: row.political_status || '',
    ethnicity: row.ethnicity || '', position_type: row.position_type || '',
    specialty: row.specialty || '', expertise: row.expertise || ''
  })
  dialogVisible.value = true
}

function resetForm() { editId.value = null }

async function handleSave() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  const data = { ...form }
  if (isEdit.value) {
    await updateCadre(editId.value, data)
    ElMessage.success('更新成功')
  } else {
    await createCadre(data)
    ElMessage.success('创建成功')
  }
  dialogVisible.value = false
  load()
}

async function handleDelete(row) {
  await ElMessageBox.confirm(`确认删除干部「${row.name}」？`, '提示', { type: 'warning' })
  await deleteCadre(row.id)
  ElMessage.success('删除成功')
  load()
}

async function handleBatchDelete() {
  await ElMessageBox.confirm(`确认删除选中的 ${checkedIds.value.length} 名干部？`, '提示', { type: 'warning' })
  await batchDeleteCadres(checkedIds.value)
  ElMessage.success('删除成功')
  load()
}

async function handleImport(file) {
  try {
    const res = await importCadres(file)
    ElMessage.success(res.msg || '导入成功')
    load()
  } catch (e) { /* error handled by interceptor */ }
  return false
}

async function downloadTpl() {
  const res = await downloadCadreTemplate()
  const url = URL.createObjectURL(res.data)
  const a = document.createElement('a')
  a.href = url; a.download = '干部导入模板.xlsx'; a.click()
  URL.revokeObjectURL(url)
}

async function handleExport() {
  const res = await exportCadres()
  const url = URL.createObjectURL(res.data)
  const a = document.createElement('a')
  a.href = url; a.download = '干部列表.xlsx'; a.click()
  URL.revokeObjectURL(url)
}

onMounted(async () => { await loadUnits(); await load() })
</script>

<style scoped>
.toolbar { margin-bottom: 16px; display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.pagination-wrap { margin-top: 16px; display: flex; justify-content: flex-end; }
</style>
