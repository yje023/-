<template>
  <div class="content-card">
    <div class="search-bar">
      <el-input v-model="search" placeholder="搜索单位名称" clearable @change="loadUnits" @keyup.enter="loadUnits" style="width:200px" />
      <el-button type="primary" @click="openCreate">新建单位</el-button>
      <el-button @click="downloadTpl">下载导入模板</el-button>
      <el-upload :show-file-list="false" :before-upload="handleImport" accept=".xlsx,.xls" style="display:inline-block">
        <el-button>导入xlsx</el-button>
      </el-upload>
      <el-button @click="handleExport">导出xlsx</el-button>
      <el-button v-if="checkedIds.length" type="danger" @click="handleBatchDelete">批量删除({{ checkedIds.length }})</el-button>
    </div>

    <el-row :gutter="20">
      <!-- 组织机构树 -->
      <el-col :span="10">
        <el-card shadow="never">
          <template #header><span style="font-weight:600">组织机构</span></template>
          <el-tree
            ref="treeRef"
            :data="orgTree"
            :props="{ label: 'name', children: 'children' }"
            node-key="id"
            highlight-current
            :expand-on-click-node="true"
            @node-click="onOrgNodeClick"
          >
            <template #default="{ node, data }">
              <span class="org-node" @dragover.prevent @drop="onUnitDrop($event, data)">
                <span>{{ node.label }}</span>
                <el-tag v-if="data.category === 'street'" size="small" type="success" style="margin-left:6px">镇街</el-tag>
                <el-tag v-else-if="data.category === 'dept'" size="small" type="primary" style="margin-left:6px">部门</el-tag>
                <span style="color:#909399;font-size:11px;margin-left:6px">({{ (orgUnits[data.id] || []).length }})</span>
              </span>
            </template>
          </el-tree>
        </el-card>
      </el-col>

      <!-- 单位标签区域 -->
      <el-col :span="14">
        <el-card shadow="never">
          <template #header>
            <span style="font-weight:600">
              {{ selectedOrg ? selectedOrg.name + ' — 单位列表' : '请选择一个机构' }}
              <span v-if="selectedOrg" style="color:#909399;font-size:12px">（共 {{ currentOrgUnits.length }} 个）</span>
            </span>
          </template>
          <div v-if="!selectedOrg" style="color:#909399;text-align:center;padding:40px 0">
            请在左侧组织机构树中点击选择一个机构
          </div>
          <div v-else-if="currentOrgUnits.length === 0" style="color:#909399;text-align:center;padding:40px 0">
            该机构下暂无单位
          </div>
          <div v-else class="unit-tags-container">
            <el-tag
              v-for="u in currentOrgUnits"
              :key="u.id"
              size="large"
              closable
              :disable-transitions="false"
              class="unit-tag"
              draggable="true"
              @dragstart="onDragStart($event, u)"
              @dragend="onDragEnd($event)"
              @click="openEdit(u)"
              @close="handleDeleteUnit(u)"
            >
              {{ u.name }}
            </el-tag>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 新建/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑单位' : '新建单位'" width="500px" @close="resetForm">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="单位名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入单位名称" />
        </el-form-item>
        <el-form-item label="所属机构" prop="org_id">
          <el-tree-select v-model="form.org_id" :data="orgTree" :props="{ label: 'name', value: 'id', children: 'children' }"
            placeholder="请选择机构" check-strictly style="width:100%" />
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
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getUnits, createUnit, updateUnit, deleteUnit, batchDeleteUnits, moveUnit, importUnits, downloadUnitTemplate, exportUnits } from '../api/unit'
import { getOrgs } from '../api/org'

const search = ref('')
const units = ref([])
const orgTree = ref([])
const selectedOrg = ref(null)
const checkedIds = ref([])
const treeRef = ref(null)

const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const formRef = ref(null)
const form = reactive({ name: '', org_id: null })
const rules = {
  name: [{ required: true, message: '请输入单位名称', trigger: 'blur' }],
}

// 按 org_id 分组的单位
const orgUnits = computed(() => {
  const map = {}
  for (const u of units.value) {
    const oid = u.org_id || '__none__'
    if (!map[oid]) map[oid] = []
    map[oid].push(u)
  }
  return map
})

const currentOrgUnits = computed(() => {
  if (!selectedOrg.value) return []
  return orgUnits.value[selectedOrg.value.id] || []
})

async function loadOrgs() {
  try {
    const res = await getOrgs()
    orgTree.value = res.data || []
  } catch {}
}

async function loadUnits() {
  try {
    const params = { page_size: 9999 }
    if (search.value) params.search = search.value
    const res = await getUnits(params)
    units.value = res.data.items || []
  } catch {}
}

function onOrgNodeClick(data) {
  selectedOrg.value = data
}

// Drag and drop
let draggedUnit = null
function onDragStart(e, unit) {
  draggedUnit = unit
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData('text/plain', String(unit.id))
}

function onDragEnd(e) {
  draggedUnit = null
}

async function onUnitDrop(e, orgData) {
  if (!draggedUnit) return
  if (draggedUnit.org_id === orgData.id) return
  try {
    await moveUnit(draggedUnit.id, orgData.id)
    ElMessage.success(`已将「${draggedUnit.name}」移动到「${orgData.name}」`)
    await loadUnits()
  } catch {}
}

function openCreate() {
  isEdit.value = false; editId.value = null
  form.name = ''; form.org_id = selectedOrg.value?.id || null
  dialogVisible.value = true
}

function openEdit(unit) {
  isEdit.value = true; editId.value = unit.id
  form.name = unit.name; form.org_id = unit.org_id
  dialogVisible.value = true
}

function resetForm() {
  form.name = ''; form.org_id = null; editId.value = null
}

async function handleSave() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  try {
    if (isEdit.value) {
      await updateUnit(editId.value, { name: form.name, org_id: form.org_id })
      ElMessage.success('编辑成功')
    } else {
      await createUnit({ name: form.name, org_id: form.org_id })
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    await loadUnits()
  } catch {}
}

async function handleDeleteUnit(unit) {
  await ElMessageBox.confirm(`确定删除单位「${unit.name}」？`, '确认删除', { type: 'warning' })
  try {
    await deleteUnit(unit.id)
    ElMessage.success('删除成功')
    await loadUnits()
  } catch {}
}

async function handleBatchDelete() {
  await ElMessageBox.confirm(`确定删除选中的 ${checkedIds.value.length} 个单位？`, '确认批量删除', { type: 'warning' })
  try {
    await batchDeleteUnits(checkedIds.value)
    ElMessage.success('批量删除成功')
    await loadUnits()
  } catch {}
}

async function handleImport(file) {
  try {
    const res = await importUnits(file)
    ElMessage.success(res.msg || '导入成功')
    if (res.errors) ElMessage.warning('部分行导入失败：' + res.errors.join('; '))
    await loadUnits()
  } catch {}
  return false
}

async function downloadTpl() {
  try {
    const res = await downloadUnitTemplate()
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a'); a.href = url; a.download = '单位导入模板.xlsx'; a.click()
    URL.revokeObjectURL(url)
  } catch {}
}

async function handleExport() {
  try {
    const res = await exportUnits()
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a'); a.href = url; a.download = '单位列表.xlsx'; a.click()
    URL.revokeObjectURL(url)
  } catch {}
}

onMounted(async () => { await Promise.all([loadOrgs(), loadUnits()]) })
</script>

<style scoped>
.search-bar { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
.org-node { display: flex; align-items: center; width: 100%; flex: 1; }
.unit-tags-container { display: flex; flex-wrap: wrap; gap: 10px; padding: 8px 0; }
.unit-tag { cursor: pointer; user-select: none; font-size: 14px; padding: 8px 14px; }
.unit-tag:hover { transform: scale(1.05); }
.unit-tag:active { cursor: grabbing; }
</style>
