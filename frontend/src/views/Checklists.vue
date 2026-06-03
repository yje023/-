<template>
  <div class="content-card">
    <div class="search-bar">
      <el-input v-model="search" placeholder="搜索事项名称..." style="width:200px" clearable @change="load" @keyup.enter="load" />
      <el-select v-model="filterUnitId" placeholder="按单位筛选" style="width:200px;margin-left:8px" clearable filterable @change="load">
        <el-option v-for="u in filteredUnits" :key="u.id" :label="u.name" :value="u.id" />
      </el-select>
      <el-button type="primary" @click="openCreate" style="margin-left:8px">新建事项</el-button>
      <el-button @click="downloadTpl">下载导入模板</el-button>
      <el-upload :show-file-list="false" :before-upload="handleImport" accept=".xlsx,.xls" style="display:inline-block;margin-left:8px">
        <el-button>导入xlsx</el-button>
      </el-upload>
      <el-button @click="handleExport">导出xlsx</el-button>
      <el-button type="danger" v-if="checkedIds.length > 0" @click="handleBatchDelete">批量删除({{ checkedIds.length }})</el-button>
    </div>

    <!-- 顶部Tab：镇街/部门 -->
    <el-tabs v-model="orgTab" @tab-change="onOrgTabChange" type="border-card" style="margin-top:8px">
      <el-tab-pane label="镇街履职事项清单" name="street" />
      <el-tab-pane label="部门履职事项清单" name="dept" />
    </el-tabs>

    <!-- 子Tab：基本/配合/收回 -->
    <el-tabs v-model="itemTab" @tab-change="load" style="margin-top:0">
      <template v-if="orgTab === 'street'">
        <el-tab-pane label="基本履职事项" name="basic" />
        <el-tab-pane label="配合履职事项" name="cooperative" />
        <el-tab-pane label="上级部门收回事项" name="recall" />
      </template>
      <template v-else>
        <el-tab-pane label="基本履职事项" name="basic" />
        <el-tab-pane label="镇街配合履职事项" name="cooperative" />
        <el-tab-pane label="本部门收回事项" name="recall" />
      </template>
    </el-tabs>

    <!-- 表格 -->
    <el-table :data="items" style="width:100%" @selection-change="onSelectionChange" v-loading="loading"
      :row-class-name="rowClassName">
      <el-table-column v-if="!isReadonly" type="selection" width="50" />
      <el-table-column prop="seq_num" label="序号" width="70" />
      <el-table-column prop="name" label="事项名称" min-width="200" />

      <!-- 镇街-配合：对应上级部门 | 上级部门职责 | 镇街配合职责 -->
      <template v-if="orgTab === 'street' && itemTab === 'cooperative'">
        <el-table-column label="对应上级部门" width="150">
          <template #default="{ row }">{{ row.unit_name }}</template>
        </el-table-column>
        <el-table-column prop="superior_dept_duty" label="上级部门职责" min-width="160" />
        <el-table-column prop="street_duty" label="镇街配合职责" min-width="160" />
      </template>

      <!-- 镇街-收回：承接部门 | 工作方式 -->
      <template v-else-if="orgTab === 'street' && itemTab === 'recall'">
        <el-table-column label="承接部门" width="150">
          <template #default="{ row }">{{ row.unit_name }}</template>
        </el-table-column>
        <el-table-column prop="工作方式" label="工作方式" min-width="200" />
      </template>

      <!-- 部门-配合(只读)：关联镇街 | 本部门职责 | 镇街配合职责 -->
      <template v-else-if="orgTab === 'dept' && itemTab === 'cooperative'">
        <el-table-column label="关联镇街" width="150">
          <template #default="{ row }">{{ row.street_unit_name }}</template>
        </el-table-column>
        <el-table-column prop="superior_dept_duty" label="本部门职责" min-width="160" />
        <el-table-column prop="street_duty" label="镇街配合职责" min-width="160" />
      </template>

      <!-- 部门-收回(只读)：关联镇街 | 工作方式 -->
      <template v-else-if="orgTab === 'dept' && itemTab === 'recall'">
        <el-table-column label="关联镇街" width="150">
          <template #default="{ row }">{{ row.street_unit_name }}</template>
        </el-table-column>
        <el-table-column prop="工作方式" label="工作方式" min-width="200" />
      </template>

      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" link @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
      <template #empty><el-empty description="暂无事项数据" :image-size="80" /></template>
    </el-table>

    <div v-if="total > 0" class="pagination-wrap">
      <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="total"
        :page-sizes="[20, 50, 100, 200]" layout="total, sizes, prev, pager, next, jumper"
        @current-change="load" @size-change="load" />
    </div>

    <!-- 新建/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑事项' : '新建事项'" width="600px" @close="resetForm">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="序号" prop="seq_num">
          <el-input-number v-model="form.seq_num" :min="0" style="width:100%" />
        </el-form-item>
        <el-form-item label="事项名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入事项名称" />
        </el-form-item>
        <el-form-item v-if="!isBasic" label="关联单位" prop="unit_id">
          <el-select v-model="form.unit_id" placeholder="请选择一个单位" style="width:100%" filterable>
            <el-option v-for="u in deptUnits" :key="u.id" :label="u.name" :value="u.id" />
          </el-select>
        </el-form-item>
        <template v-if="orgTab === 'street' && itemTab === 'cooperative'">
          <el-form-item label="来源镇街">
            <el-select v-model="form.street_unit_id" placeholder="选择来源镇街" style="width:100%" filterable>
              <el-option v-for="u in streetUnits" :key="u.id" :label="u.name" :value="u.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="上级部门职责">
            <el-input v-model="form.superior_dept_duty" placeholder="上级部门职责" />
          </el-form-item>
          <el-form-item label="镇街配合职责">
            <el-input v-model="form.street_duty" placeholder="镇街配合职责" />
          </el-form-item>
        </template>
        <template v-if="orgTab === 'street' && itemTab === 'recall'">
          <el-form-item label="来源镇街">
            <el-select v-model="form.street_unit_id" placeholder="选择来源镇街" style="width:100%" filterable>
              <el-option v-for="u in streetUnits" :key="u.id" :label="u.name" :value="u.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="工作方式">
            <el-input v-model="form.工作方式" placeholder="工作方式" />
          </el-form-item>
        </template>
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
import {
  getChecklistItems, createChecklistItem, updateChecklistItem, deleteChecklistItem,
  batchDeleteChecklistItems, importChecklistItems, exportChecklistItems, downloadChecklistTemplate
} from '../api/checklist'
import { getUnits } from '../api/unit'
import { getOrgs } from '../api/org'

const search = ref('')
const filterUnitId = ref(null)
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const checkedIds = ref([])
const loading = ref(false)

const allUnits = ref([])
const allOrgs = ref([])

// Tab 状态
const orgTab = ref('street')
const itemTab = ref('basic')

// 弹窗
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const formRef = ref(null)
const form = reactive({
  seq_num: 0, name: '', unit_id: null, street_unit_id: null,
  superior_dept_duty: '', street_duty: '', 工作方式: '',
})
const rules = {
  name: [{ required: true, message: '请输入事项名称', trigger: 'blur' }],
}

// 计算属性
const isBasic = computed(() => itemTab.value === 'basic')
const isReadonly = computed(() => orgTab.value === 'dept' && (itemTab.value === 'cooperative' || itemTab.value === 'recall'))

// 根据机构类别过滤单位
const deptOrgIds = computed(() => allOrgs.value.filter(o => o.category === 'dept').map(o => o.id))
const streetOrgIds = computed(() => allOrgs.value.filter(o => o.category === 'street').map(o => o.id))
const deptUnits = computed(() => allUnits.value.filter(u => deptOrgIds.value.includes(u.org_id)))
const streetUnits = computed(() => allUnits.value.filter(u => streetOrgIds.value.includes(u.org_id)))
const filteredUnits = computed(() => orgTab.value === 'street' ? streetUnits.value : deptUnits.value)

function rowClassName({ row }) {
  return row.is_synced ? 'synced-row' : ''
}

function onSelectionChange(selection) { checkedIds.value = selection.map(r => r.id) }
function onOrgTabChange() { itemTab.value = 'basic'; load() }

async function loadUnits() {
  try {
    const r = await getUnits({ page_size: 9999 })
    allUnits.value = r.data.items || []
  } catch {}
}

async function loadOrgs() {
  try {
    const r = await getOrgs()
    // Flatten org tree
    const flat = []
    function walk(nodes) {
      for (const n of nodes) {
        flat.push(n)
        if (n.children) walk(n.children)
      }
    }
    walk(r.data || [])
    allOrgs.value = flat
  } catch {}
}

async function load() {
  loading.value = true
  try {
    const params = {
      page: page.value, page_size: pageSize.value,
      org_category: orgTab.value,
      item_category: itemTab.value,
    }
    if (search.value) params.search = search.value
    if (filterUnitId.value) params.unit_id = filterUnitId.value
    const res = await getChecklistItems(params)
    items.value = res.data.items || []
    total.value = res.data.total || 0
  } finally { loading.value = false }
}

function openCreate() {
  isEdit.value = false; editId.value = null
  form.seq_num = items.value.length + 1
  form.name = ''; form.unit_id = null; form.street_unit_id = null
  form.superior_dept_duty = ''; form.street_duty = ''; form.工作方式 = ''
  dialogVisible.value = true
}

function openEdit(row) {
  if (row.is_synced) return
  isEdit.value = true; editId.value = row.id
  form.seq_num = row.seq_num
  form.name = row.name
  form.unit_id = row.unit_id
  form.street_unit_id = row.street_unit_id
  form.superior_dept_duty = row.superior_dept_duty || ''
  form.street_duty = row.street_duty || ''
  form.工作方式 = row.工作方式 || ''
  dialogVisible.value = true
}

function resetForm() {
  form.seq_num = 0; form.name = ''; form.unit_id = null; form.street_unit_id = null
  form.superior_dept_duty = ''; form.street_duty = ''; form.工作方式 = ''
  editId.value = null
}

async function handleSave() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  const data = {
    org_category: orgTab.value,
    item_category: itemTab.value,
    seq_num: form.seq_num,
    name: form.name,
    unit_id: form.unit_id,
    street_unit_id: form.street_unit_id || null,
    superior_dept_duty: form.superior_dept_duty,
    street_duty: form.street_duty,
    工作方式: form.工作方式,
  }
  try {
    if (isEdit.value) {
      await updateChecklistItem(editId.value, data)
      ElMessage.success('更新成功')
    } else {
      await createChecklistItem(data)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    load()
  } catch {}
}

async function handleDelete(row) {
  if (row.is_synced) return
  await ElMessageBox.confirm(`确认删除事项「${row.name}」？`, '提示', { type: 'warning' })
  try {
    await deleteChecklistItem(row.id)
    ElMessage.success('删除成功')
    load()
  } catch {}
}

async function handleBatchDelete() {
  await ElMessageBox.confirm(`确认删除选中的 ${checkedIds.value.length} 个事项？`, '提示', { type: 'warning' })
  try {
    await batchDeleteChecklistItems(checkedIds.value)
    ElMessage.success('删除成功')
    load()
  } catch {}
}

async function handleImport(file) {
  try {
    const res = await importChecklistItems(file)
    ElMessage.success(res.msg || '导入成功')
    load()
  } catch {}
  return false
}

async function downloadTpl() {
  try {
    const res = await downloadChecklistTemplate()
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a'); a.href = url; a.download = '履职事项清单导入模板.xlsx'; a.click()
    URL.revokeObjectURL(url)
  } catch {}
}

async function handleExport() {
  try {
    const res = await exportChecklistItems({ org_category: orgTab.value, item_category: itemTab.value })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a'); a.href = url; a.download = '履职事项清单.xlsx'; a.click()
    URL.revokeObjectURL(url)
  } catch {}
}

onMounted(async () => { await Promise.all([loadUnits(), loadOrgs()]); await load() })
</script>

<style scoped>
.search-bar { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.pagination-wrap { margin-top: 16px; display: flex; justify-content: flex-end; }
:deep(.synced-row) { background: #f5f7fa; color: #909399; }
</style>
