<template>
  <div class="content-card">
    <div class="search-bar">
      <el-select v-model="filterPlanId" placeholder="选择考核方案" style="width:240px" @change="loadIssues">
        <el-option v-for="p in plans" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <el-select v-model="filterType" placeholder="筛选问题类型" clearable style="width:180px;margin-left:8px">
        <el-option v-for="t in issueTypes" :key="t" :label="t" :value="t" />
      </el-select>
      <el-select v-model="filterStatus" placeholder="筛选状态" clearable style="width:140px;margin-left:8px">
        <el-option label="确认无误" value="confirmed" />
        <el-option label="已修复" value="resolved" />
        <el-option label="已移除" value="ignored" />
      </el-select>
      <el-button @click="loadIssues">刷新</el-button>
      <el-button @click="$router.push('/quality-check')">← 返回报错</el-button>
    </div>

    <el-table :data="filteredIssues" border stripe>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag size="small" :type="row.status === 'confirmed' ? 'warning' : row.status === 'resolved' ? 'success' : 'info'">
            {{ row.status === 'confirmed' ? '确认无误' : row.status === 'resolved' ? '已修复' : '已移除' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="140">
        <template #default="{ row }">
          <el-tag size="small" :type="tagType(row.issue_type)">{{ row.issue_type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="unit_name" label="单位" width="130" />
      <el-table-column label="字段" width="90">
        <template #default="{ row }">{{ row.column_name }}</template>
      </el-table-column>
      <el-table-column label="问题内容" min-width="180">
        <template #default="{ row }"><span class="cell-wrap">{{ row.text }}</span></template>
      </el-table-column>
      <el-table-column prop="suggestion" label="修改建议" min-width="180" show-overflow-tooltip />
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="undoIssue(row)">撤回</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getPlans } from '../api/plan'
import http from '../api/index'

const filterPlanId = ref(null)
const filterType = ref('')
const filterStatus = ref('')
const plans = ref([])
const allIssues = ref([])

const issueTypes = computed(() => [...new Set(allIssues.value.map(i => i.issue_type))].sort())
const filteredIssues = computed(() => {
  let arr = allIssues.value.filter(i => i.status !== 'pending')
  if (filterType.value) arr = arr.filter(i => i.issue_type === filterType.value)
  if (filterStatus.value) arr = arr.filter(i => i.status === filterStatus.value)
  return arr
})

function tagType(type) {
  if (!type) return 'info'
  if (type.includes('错别字')) return 'danger'
  if (type.includes('重复')) return 'warning'
  if (type.includes('标点')) return 'primary'
  return 'info'
}

async function loadPlans() { try { const r = await getPlans(); plans.value = r.data?.items || [] } catch (_) { } }

async function loadIssues() {
  if (!filterPlanId.value) return
  try {
    const r = await http.get('/quality-check/issues', { params: { plan_id: filterPlanId.value, page_size: 500 } })
    allIssues.value = (r.data?.data?.items || r.data?.items || []).map(i => ({
      ...i, unit_name: '', status: i.status || 'pending',
    }))
  } catch (_) { }
}

async function undoIssue(row) {
  await ElMessageBox.confirm('确定撤回此问题？撤回后将重新出现在报错页面。', '提示', { type: 'warning' })
  try {
    await http.put(`/quality-check/issues/${row.id}`, { status: 'pending' })
    row.status = 'pending'
    ElMessage.success('已撤回，问题将重新报错')
    loadIssues()
  } catch (_) { ElMessage.error('撤回失败') }
}

onMounted(loadPlans)
</script>

<style scoped>
.cell-wrap { white-space: pre-wrap; word-break: break-all; }
</style>
