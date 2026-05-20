<template>
  <div class="content-card">
    <div class="search-bar">
      <el-input v-model="search" placeholder="搜索用户名" clearable @change="onSearch" style="width:200px" />
      <el-select v-model="filterUnitId" placeholder="筛选单位" clearable @change="onFilterChange" style="width:200px">
        <el-option v-for="u in units" :key="u.id" :label="u.name" :value="u.id" />
      </el-select>
      <el-select v-model="filterRoleId" placeholder="筛选角色" clearable @change="onFilterChange" style="width:180px">
        <el-option v-for="r in roles" :key="r.id" :label="r.name" :value="r.id" />
      </el-select>
      <el-button type="primary" @click="openCreate">新建用户</el-button>
      <el-button v-if="checkedIds.length" type="danger" @click="handleBatchDelete">批量删除({{ checkedIds.length }})</el-button>
    </div>

    <el-table :data="users" border stripe @selection-change="onSelectionChange">
      <template #empty><el-empty description="暂无用户数据" :image-size="80" /></template>
      <el-table-column type="selection" width="50" />
      <el-table-column prop="username" label="用户名" />
      <el-table-column prop="unit_name" label="所属单位" />
      <el-table-column prop="role_name" label="角色">
        <template #default="{ row }"><el-tag size="small">{{ row.role_name || '未分配' }}</el-tag></template>
      </el-table-column>
      <el-table-column prop="current_identity" label="当前身份" width="110">
        <template #default="{ row }">
          <el-tag :type="row.current_identity === 'assessor' ? 'primary' : 'success'" size="small">
            {{ row.current_identity === 'assessor' ? '主考单位' : '被考核单位' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="must_change_password" label="密码状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.must_change_password ? 'warning' : 'success'" size="small">
            {{ row.must_change_password ? '待修改' : '已修改' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200">
        <template #default="{ row }">
          <el-button size="small" link @click="openEdit(row)">编辑</el-button>
          <el-button size="small" link type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination-wrap" v-if="userTotal > 0">
      <el-pagination
        v-model:current-page="userPage"
        v-model:page-size="userPageSize"
        :total="userTotal"
        :page-sizes="[50, 100, 150, 200]"
        layout="total, sizes, prev, pager, next"
        @current-change="loadUsers"
        @size-change="loadUsers"
      />
    </div>

    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑用户' : '新建用户'" width="500px">
      <el-form ref="formRef" :model="form" :rules="rules">
        <el-form-item label="所属单位" prop="unit_id">
          <el-select v-model="form.unit_id" placeholder="请选择单位" style="width:100%" filterable>
            <el-option v-for="u in units" :key="u.id" :label="u.name" :value="u.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" placeholder="请输入密码" type="password" show-password />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="form.role_id" placeholder="请选择角色" style="width:100%" clearable>
            <el-option v-for="r in roles" :key="r.id" :label="r.name" :value="r.id" />
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
import { getUsers, createUser, updateUser, deleteUser, batchDeleteUsers } from '../api/user'
import { getUnits } from '../api/unit'
import { getRoles } from '../api/role'

const search = ref('')
const filterUnitId = ref(null)
const filterRoleId = ref(null)
const users = ref([])
const userTotal = ref(0)
const userPage = ref(1)
const userPageSize = ref(50)
const checkedIds = ref([])
const units = ref([])
const roles = ref([])

function onSearch() { userPage.value = 1; loadUsers() }
function onFilterChange() { userPage.value = 1; loadUsers() }
function onSelectionChange(sel) { checkedIds.value = sel.map(r => r.id) }

async function loadUsers() {
  const params = { page: userPage.value, page_size: userPageSize.value }
  if (search.value) params.search = search.value
  if (filterUnitId.value) params.unit_id = filterUnitId.value
  if (filterRoleId.value) params.role_id = filterRoleId.value
  try {
    const res = await getUsers(params)
    if (res.data?.items) { users.value = res.data.items; userTotal.value = res.data.total }
    else { users.value = res.data || []; userTotal.value = users.value.length }
  } catch {}
}

const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const formRef = ref()
const form = reactive({ username: '', password: '', unit_id: null, role_id: null })
const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  unit_id: [{ required: true, message: '请选择单位', trigger: 'change' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }, { min: 6, message: '密码至少6位', trigger: 'blur' }],
}

function openCreate() {
  isEdit.value = false; editId.value = null
  form.username = ''; form.password = ''; form.unit_id = null; form.role_id = null
  rules.password[0].required = true
  dialogVisible.value = true
}
function openEdit(row) {
  isEdit.value = true; editId.value = row.id
  form.username = row.username; form.password = row.password || ''; form.unit_id = row.unit_id; form.role_id = row.role_id
  rules.password[0].required = true
  dialogVisible.value = true
}

async function handleSave() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  try {
    const data = { username: form.username, role_id: form.role_id }
    if (isEdit.value) {
      data.password = form.password
      await updateUser(editId.value, data)
      ElMessage.success('编辑成功')
    } else {
      data.password = form.password
      data.unit_id = form.unit_id
      await createUser(data)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    await loadUsers()
  } catch {}
}

async function handleDelete(row) {
  await ElMessageBox.confirm(`确定删除用户「${row.username}」？`, '确认删除', { type: 'warning' })
  try { await deleteUser(row.id); ElMessage.success('删除成功'); await loadUsers() } catch {}
}

async function handleBatchDelete() {
  await ElMessageBox.confirm(`确定删除选中的 ${checkedIds.value.length} 个用户？`, '确认批量删除', { type: 'warning' })
  try { await batchDeleteUsers(checkedIds.value); ElMessage.success('批量删除成功'); await loadUsers() } catch {}
}

onMounted(async () => {
  await loadUsers()
  try { const r1 = await getUnits({ page_size: 999 }); units.value = r1.data?.items || r1.data || [] } catch {}
  try { const r2 = await getRoles(); roles.value = r2.data || [] } catch {}
})
</script>
