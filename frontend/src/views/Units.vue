<template>
  <div class="content-card">
    <div class="search-bar">
      <el-input v-model="search" placeholder="搜索单位名称" clearable @change="loadUnits" style="width:200px" />
      <el-select v-model="filterOrgId" placeholder="筛选机构" clearable @change="loadUnits" style="width:200px">
        <el-option v-for="o in flatOrgs" :key="o.id" :label="o.name" :value="o.id" />
      </el-select>
      <el-button type="primary" @click="openCreate">新建单位</el-button>
      <el-button @click="downloadTpl">下载导入模板</el-button>
      <el-upload :show-file-list="false" :before-upload="handleImport" accept=".xlsx,.xls" style="display:inline-block">
        <el-button>导入xlsx</el-button>
      </el-upload>
      <el-button @click="handleExport">导出xlsx</el-button>
      <el-button v-if="checkedIds.length" type="danger" @click="handleBatchDelete">批量删除({{ checkedIds.length }})</el-button>
    </div>

    <el-table :data="units" @selection-change="onSelectionChange" border stripe>
      <template #empty><el-empty description="暂无单位数据" :image-size="80" /></template>
      <el-table-column type="selection" width="50" />
      <el-table-column prop="name" label="单位名称" />
      <el-table-column prop="org_name" label="所属机构" />
      <el-table-column label="操作" width="280">
        <template #default="{ row }">
          <el-button size="small" link @click="openEdit(row)">编辑</el-button>
          <el-button size="small" link @click="openMove(row)">移动</el-button>
          <el-button size="small" link type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination-wrap" v-if="unitTotal > 0">
      <el-pagination
        v-model:current-page="unitPage"
        v-model:page-size="unitPageSize"
        :total="unitTotal"
        :page-sizes="[50, 100, 150, 200]"
        layout="total, sizes, prev, pager, next"
        @current-change="loadUnits"
        @size-change="loadUnits"
      />
    </div>

    <!-- 新建/编辑 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑单位' : '新建单位'" width="500px">
      <el-form ref="formRef" :model="form" :rules="rules">
        <el-form-item label="所属机构" prop="org_id">
          <el-tree-select v-model="form.org_id" :data="orgTree" :props="{ label: 'name', value: 'id', children: 'children' }" placeholder="请选择所属机构" check-strictly style="width:100%" />
        </el-form-item>
        <el-form-item label="单位名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入单位名称" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>

    <!-- 移动 -->
    <el-dialog v-model="moveVisible" title="移动到其他机构" width="400px">
      <el-tree-select v-model="moveTargetOrgId" :data="orgTree" :props="{ label: 'name', value: 'id', children: 'children' }" placeholder="请选择目标机构" check-strictly style="width:100%" />
      <template #footer>
        <el-button @click="moveVisible = false">取消</el-button>
        <el-button type="primary" @click="handleMove">确认移动</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getUnits, createUnit, updateUnit, deleteUnit, moveUnit, batchDeleteUnits, importUnits, downloadUnitTemplate, exportUnits } from '../api/unit'
import { getOrgs } from '../api/org'

const search = ref('')
const filterOrgId = ref(null)
const units = ref([])
const unitTotal = ref(0)
const unitPage = ref(1)
const unitPageSize = ref(50)
const checkedIds = ref([])
const orgTree = ref([])
const flatOrgs = ref([])

function flattenOrgs(nodes) {
  const result = []
  function walk(list) {
    for (const n of list) {
      result.push({ id: n.id, name: n.name })
      if (n.children) walk(n.children)
    }
  }
  walk(nodes)
  return result
}

async function loadOrgs() {
  try {
    const res = await getOrgs()
    orgTree.value = res.data || []
    flatOrgs.value = flattenOrgs(orgTree.value)
  } catch {}
}

function onSelectionChange(sel) { checkedIds.value = sel.map(r => r.id) }

async function loadUnits() {
  try {
    const params = { page: unitPage.value, page_size: unitPageSize.value }
    if (search.value) params.search = search.value
    if (filterOrgId.value) params.org_id = filterOrgId.value
    const res = await getUnits(params)
    if (res.data?.items) { units.value = res.data.items; unitTotal.value = res.data.total }
    else { units.value = res.data || []; unitTotal.value = units.value.length }
  } catch {}
}

const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const formRef = ref()
const form = reactive({ name: '', org_id: null })
const rules = {
  name: [{ required: true, message: '请输入单位名称', trigger: 'blur' }],
  org_id: [{ required: true, message: '请选择所属机构', trigger: 'change' }],
}

function openCreate() { isEdit.value = false; editId.value = null; form.name = ''; form.org_id = null; dialogVisible.value = true }
function openEdit(row) { isEdit.value = true; editId.value = row.id; form.name = row.name; form.org_id = row.org_id; dialogVisible.value = true }

async function handleSave() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  try {
    if (isEdit.value) {
      await updateUnit(editId.value, { name: form.name, org_id: form.org_id })
      ElMessage.success('编辑成功')
    } else {
      await createUnit({ name: form.name, org_id: form.org_id })
      ElMessage.success('创建成功，已自动生成初始用户账号')
    }
    dialogVisible.value = false
    await loadUnits()
  } catch {}
}

async function handleDelete(row) {
  await ElMessageBox.confirm(`确定删除单位「${row.name}」？其下用户账号将同步删除，考核任务不受影响。`, '确认删除', { type: 'warning' })
  try { await deleteUnit(row.id); ElMessage.success('删除成功'); await loadUnits() } catch {}
}

async function handleBatchDelete() {
  await ElMessageBox.confirm(`确定删除选中的 ${checkedIds.value.length} 个单位？其下用户账号将同步删除，考核任务不受影响。`, '确认批量删除', { type: 'warning' })
  try { await batchDeleteUnits(checkedIds.value); ElMessage.success('批量删除成功'); await loadUnits() } catch {}
}

const moveVisible = ref(false)
const moveTargetOrgId = ref(null)
const moveRow = ref(null)
function openMove(row) { moveRow.value = row; moveTargetOrgId.value = null; moveVisible.value = true }

async function handleMove() {
  if (!moveTargetOrgId.value) { ElMessage.warning('请选择目标机构'); return }
  try {
    await moveUnit(moveRow.value.id, moveTargetOrgId.value)
    ElMessage.success('移动成功')
    moveVisible.value = false
    await loadUnits()
  } catch {}
}

async function handleImport(file) {
  try {
    const res = await importUnits(file)
    ElMessage.success(res.msg || '导入成功')
    if (res.errors) ElMessage.warning('部分行失败：' + res.errors.join('; '))
    await loadUnits()
  } catch {}
  return false
}

async function downloadTpl() {
  const res = await downloadUnitTemplate()
  const url = URL.createObjectURL(res.data)
  const a = document.createElement('a'); a.href = url; a.download = '单位导入模板.xlsx'; a.click()
  URL.revokeObjectURL(url)
}

async function handleExport() {
  const res = await exportUnits()
  const url = URL.createObjectURL(res.data)
  const a = document.createElement('a'); a.href = url; a.download = '单位列表.xlsx'; a.click()
  URL.revokeObjectURL(url)
}

onMounted(async () => { await loadOrgs(); await loadUnits() })
</script>
