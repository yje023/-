<template>
  <div class="content-card">
    <div class="search-bar">
      <el-input v-model="search" placeholder="搜索机构名称" clearable @change="loadOrgs" style="width:240px" />
      <el-button type="primary" @click="openCreate(null)">新建机构</el-button>
      <el-button @click="downloadTpl">下载导入模板</el-button>
      <el-upload :show-file-list="false" :before-upload="handleImport" accept=".xlsx,.xls" style="display:inline-block">
        <el-button>导入xlsx</el-button>
      </el-upload>
      <el-button @click="handleExport">导出xlsx</el-button>
      <el-button v-if="checkedIds.length" type="danger" @click="handleBatchDelete">批量删除({{ checkedIds.length }})</el-button>
    </div>

    <el-table :data="treeList" row-key="id" default-expand-all :tree-props="{ children: 'children' }" :indent="30" @selection-change="onSelectionChange" ref="tableRef">
      <el-table-column type="selection" width="50" />
      <el-table-column prop="name" label="机构名称" />
      <el-table-column label="操作" width="260">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="openCreate(row.id)">新建子机构</el-button>
          <el-button size="small" link @click="openEdit(row)">编辑</el-button>
          <el-button size="small" link type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新建/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑机构' : '新建机构'" width="500px">
      <el-form ref="formRef" :model="form" :rules="rules">
        <el-form-item label="上级机构" prop="parent_id" v-if="!isEdit">
          <el-tree-select v-model="form.parent_id" :data="treeList" :props="{ label: 'name', value: 'id', children: 'children' }" placeholder="不选则为顶级机构" check-strictly clearable style="width:100%" />
        </el-form-item>
        <el-form-item label="机构名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入机构名称" />
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
import { getOrgs, createOrg, updateOrg, deleteOrg, batchDeleteOrgs, importOrgs, downloadTemplate, exportOrgs } from '../api/org'

const search = ref('')
const treeList = ref([])
const checkedIds = ref([])
const tableRef = ref()
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const formRef = ref()
const form = reactive({ name: '', parent_id: null })
const rules = {
  name: [{ required: true, message: '请输入机构名称', trigger: 'blur' }],
}

function onSelectionChange(selection) {
  checkedIds.value = selection.map(r => r.id)
}

async function loadOrgs() {
  try {
    const res = await getOrgs(search.value)
    treeList.value = res.data || []
  } catch {}
}

function openCreate(parentId) {
  isEdit.value = false
  editId.value = null
  form.name = ''
  form.parent_id = parentId
  dialogVisible.value = true
}

function openEdit(row) {
  isEdit.value = true
  editId.value = row.id
  form.name = row.name
  form.parent_id = row.parent_id
  dialogVisible.value = true
}

async function handleSave() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  try {
    if (isEdit.value) {
      await updateOrg(editId.value, { name: form.name, parent_id: form.parent_id || null })
      ElMessage.success('编辑成功')
    } else {
      await createOrg({ name: form.name, parent_id: form.parent_id || null })
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    await loadOrgs()
  } catch {}
}

async function handleDelete(row) {
  await ElMessageBox.confirm(`确定删除机构「${row.name}」？子机构将上移。`, '确认删除', { type: 'warning' })
  try {
    await deleteOrg(row.id)
    ElMessage.success('删除成功')
    await loadOrgs()
  } catch {}
}

async function handleBatchDelete() {
  await ElMessageBox.confirm(`确定删除选中的 ${checkedIds.value.length} 个机构？`, '确认批量删除', { type: 'warning' })
  try {
    await batchDeleteOrgs(checkedIds.value)
    ElMessage.success('批量删除成功')
    await loadOrgs()
  } catch {}
}

async function handleImport(file) {
  try {
    const res = await importOrgs(file)
    ElMessage.success(res.msg || '导入成功')
    if (res.errors) {
      ElMessage.warning('部分行导入失败：' + res.errors.join('; '))
    }
    await loadOrgs()
  } catch {}
  return false
}

async function downloadTpl() {
  try {
    const res = await downloadTemplate()
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = '组织机构导入模板.xlsx'
    a.click()
    URL.revokeObjectURL(url)
  } catch {}
}

async function handleExport() {
  try {
    const res = await exportOrgs()
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = '组织机构.xlsx'
    a.click()
    URL.revokeObjectURL(url)
  } catch {}
}

onMounted(loadOrgs)
</script>
