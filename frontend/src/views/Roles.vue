<template>
  <div class="content-card">
    <div class="search-bar">
      <el-input v-model="search" placeholder="搜索角色名称" clearable @change="loadRoles" style="width:240px" />
      <el-button type="primary" @click="openCreate">新建角色</el-button>
    </div>

    <el-table :data="roles" border stripe>
      <el-table-column prop="name" label="角色名称" />
      <el-table-column prop="is_system" label="类型" width="100">
        <template #default="{ row }">
          <el-tag :type="row.is_system ? 'info' : ''" size="small">{{ row.is_system ? '系统预置' : '自定义' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="拥有权限" min-width="300">
        <template #default="{ row }">
          <el-tag v-for="m in getPermNames(row.permissions)" :key="m" size="small" style="margin:2px">{{ m }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-button size="small" link @click="openEdit(row)">编辑</el-button>
          <el-button v-if="!row.is_system" size="small" link type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑角色' : '新建角色'" width="550px">
      <el-form ref="formRef" :model="form" :rules="rules">
        <el-form-item label="角色名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入角色名称" />
        </el-form-item>
        <el-form-item label="菜单权限">
          <el-checkbox-group v-model="form.permCodes">
            <div v-for="cat in menuCats" :key="cat.name" style="margin-bottom:12px">
              <div style="font-weight:bold;margin-bottom:4px;color:#606266">{{ cat.name }}</div>
              <el-checkbox v-for="m in cat.menus" :key="m.code" :label="m.code" :value="m.code" style="margin-right:16px">{{ m.name }}</el-checkbox>
            </div>
          </el-checkbox-group>
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
import { getRoles, createRole, updateRole, deleteRole, getMenus } from '../api/role'

const search = ref('')
const roles = ref([])
const allMenus = ref([])

const menuCats = computed(() => {
  const cats = {}
  for (const m of allMenus.value) {
    if (!cats[m.category]) cats[m.category] = { name: m.category, menus: [] }
    cats[m.category].menus.push(m)
  }
  return Object.values(cats)
})

function getPermNames(perms) {
  return allMenus.value.filter(m => perms[m.code]).map(m => m.name)
}

async function loadRoles() {
  try { const res = await getRoles(search.value); roles.value = res.data || [] } catch {}
}

const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const formRef = ref()
const form = reactive({ name: '', permCodes: [] })
const rules = { name: [{ required: true, message: '请输入角色名称', trigger: 'blur' }] }

function openCreate() {
  isEdit.value = false; editId.value = null
  form.name = ''; form.permCodes = []
  dialogVisible.value = true
}
function openEdit(row) {
  isEdit.value = true; editId.value = row.id
  form.name = row.name
  form.permCodes = Object.keys(row.permissions).filter(k => row.permissions[k])
  dialogVisible.value = true
}

async function handleSave() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  const perms = {}
  for (const c of form.permCodes) perms[c] = true
  try {
    if (isEdit.value) {
      await updateRole(editId.value, { name: form.name, permissions: perms })
      ElMessage.success('编辑成功')
    } else {
      await createRole({ name: form.name, permissions: perms })
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    await loadRoles()
  } catch {}
}

async function handleDelete(row) {
  await ElMessageBox.confirm(`确定删除角色「${row.name}」？`, '确认删除', { type: 'warning' })
  try { await deleteRole(row.id); ElMessage.success('删除成功'); await loadRoles() } catch {}
}

onMounted(async () => {
  try { const r = await getMenus(); allMenus.value = r.data || [] } catch {}
  await loadRoles()
})
</script>
