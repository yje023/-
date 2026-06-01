<template>
  <div class="checklists-page">
    <div class="toolbar">
      <el-input v-model="search" placeholder="搜索清单名称..." style="width: 240px" clearable @change="load" />
      <el-select v-model="filterUnitId" placeholder="按单位筛选" style="width: 240px; margin-left: 8px" clearable @change="load"
        filterable>
        <el-option v-for="u in allUnits" :key="u.id" :label="u.name" :value="u.id" />
      </el-select>
      <el-button type="primary" @click="openCreate" style="margin-left: 8px">新建清单</el-button>
      <el-button @click="downloadTpl">下载导入模板</el-button>
      <el-upload :show-file-list="false" :before-upload="handleImport" accept=".xlsx,.xls"
        style="display:inline-block;margin-left:8px">
        <el-button>导入xlsx</el-button>
      </el-upload>
      <el-button @click="handleExport">导出xlsx</el-button>
      <el-button type="danger" v-if="checkedIds.length > 0" @click="handleBatchDelete">批量删除 ({{
        checkedIds.length }})</el-button>
    </div>

    <el-table :data="checklists" style="width: 100%" @selection-change="onSelectionChange" v-loading="loading">
      <el-table-column type="selection" width="50" />
      <el-table-column prop="name" label="清单名称" min-width="200" />
      <el-table-column label="关联单位数" width="120">
        <template #default="{ row }">
          <el-tag size="small" type="info">{{ row.unit_count }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="关联单位" min-width="300">
        <template #default="{ row }">
          <span v-if="row.unit_names?.length">{{ row.unit_names.join('、') }}</span>
          <span v-else style="color: #909399">未关联</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
      <template #empty>暂无清单数据</template>
    </el-table>

    <div v-if="total > 0" class="pagination-wrap">
      <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="total"
        :page-sizes="[20, 50, 100, 200]" layout="total, sizes, prev, pager, next, jumper"
        @current-change="load" @size-change="load" />
    </div>

    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑清单' : '新建清单'" width="520px" @close="resetForm">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="清单名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入清单名称" />
        </el-form-item>
        <el-form-item label="关联单位">
          <el-select v-model="form.unit_ids" multiple filterable placeholder="请选择关联单位（可多选）" style="width: 100%">
            <el-option v-for="u in allUnits" :key="u.id" :label="u.name" :value="u.id" />
          </el-select>
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
  getChecklists, createChecklist, updateChecklist, deleteChecklist,
  batchDeleteChecklists, importChecklists, exportChecklists, downloadChecklistTemplate
} from '../api/checklist'
import { getUnits } from '../api/unit'

const search = ref('')
const filterUnitId = ref(null)
const checklists = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const checkedIds = ref([])
const loading = ref(false)

const allUnits = ref([])

const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const form = reactive({ name: '', unit_ids: [] })
const formRef = ref(null)
const rules = { name: [{ required: true, message: '请输入清单名称', trigger: 'blur' }] }

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
    const res = await getChecklists(params)
    checklists.value = res.data.items || []
    total.value = res.data.total || 0
  } finally {
    loading.value = false
  }
}

function onSelectionChange(selection) { checkedIds.value = selection.map(r => r.id) }

function openCreate() { isEdit.value = false; form.name = ''; form.unit_ids = []; dialogVisible.value = true }
function openEdit(row) {
  isEdit.value = true; editId.value = row.id
  form.name = row.name; form.unit_ids = [...(row.unit_ids || [])]
  dialogVisible.value = true
}

function resetForm() { form.name = ''; form.unit_ids = []; editId.value = null }

async function handleSave() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  const data = { name: form.name, unit_ids: form.unit_ids }
  if (isEdit.value) {
    await updateChecklist(editId.value, data)
    ElMessage.success('更新成功')
  } else {
    await createChecklist(data)
    ElMessage.success('创建成功')
  }
  dialogVisible.value = false
  load()
}

async function handleDelete(row) {
  await ElMessageBox.confirm(`确认删除清单「${row.name}」？`, '提示', { type: 'warning' })
  await deleteChecklist(row.id)
  ElMessage.success('删除成功')
  load()
}

async function handleBatchDelete() {
  await ElMessageBox.confirm(`确认删除选中的 ${checkedIds.value.length} 个清单？`, '提示', { type: 'warning' })
  await batchDeleteChecklists(checkedIds.value)
  ElMessage.success('删除成功')
  load()
}

async function handleImport(file) {
  try {
    const res = await importChecklists(file)
    ElMessage.success(res.msg || '导入成功')
    load()
  } catch (e) { /* error handled by interceptor */ }
  return false
}

async function downloadTpl() {
  const res = await downloadChecklistTemplate()
  const url = URL.createObjectURL(res)
  const a = document.createElement('a')
  a.href = url; a.download = '清单导入模板.xlsx'; a.click()
  URL.revokeObjectURL(url)
}

async function handleExport() {
  const res = await exportChecklists()
  const url = URL.createObjectURL(res)
  const a = document.createElement('a')
  a.href = url; a.download = '清单列表.xlsx'; a.click()
  URL.revokeObjectURL(url)
}

onMounted(async () => { await loadUnits(); await load() })
</script>

<style scoped>
.toolbar { margin-bottom: 16px; display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.pagination-wrap { margin-top: 16px; display: flex; justify-content: flex-end; }
</style>
