<template>
  <div class="content-card" v-loading="checking" element-loading-text="正在检测中，请稍候...">
    <!-- 搜索栏 -->
    <div class="search-bar">
      <el-select v-model="filterPlanId" placeholder="选择考核方案" style="width:240px" @change="onPlanChange">
        <el-option v-for="p in plans" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <el-button v-if="auth.hasPerm('quality_manage')" type="primary" @click="runCheck" :loading="checking" :disabled="!filterPlanId">开始检测</el-button>
      <el-input v-model="searchKey" placeholder="搜索问题内容..." clearable @clear="onSearch" @keyup.enter="onSearch" style="width:200px;margin-left:8px" />
      <el-button type="primary" @click="onSearch">搜索</el-button>
      <el-button v-if="activeFilterCount" @click="clearAllChips">清除筛选({{ activeFilterCount }})</el-button>
      <el-button v-if="allIssues.length || proxyPairs.length" @click="refreshAll">刷新</el-button>
      <el-button @click="openManageDialog">问题管理</el-button>
      <el-dropdown @command="handleExport" style="margin-left:4px" v-if="allIssues.length || proxyPairs.length">
        <el-button type="success">导出 <el-icon><ArrowDown /></el-icon></el-button>
        <template #dropdown>
          <el-dropdown-item command="all">📥 导出全量问题清单</el-dropdown-item>
          <el-dropdown-item command="filtered">📋 导出当前筛选结果</el-dropdown-item>
          <el-dropdown-item command="proxy">📊 导出代理指标清单</el-dropdown-item>
        </template>
      </el-dropdown>
    </div>

    <!-- 标签页切换 -->
    <el-tabs v-model="activeTab" @tab-change="onTabChange">
      <!-- ========== 标签页1：任务质检 ========== -->
      <el-tab-pane label="任务质检" name="issues">
        <div class="chip-filter-area">
          <div v-for="dim in chipDimensions" :key="dim.key" class="chip-dim-row">
            <span class="chip-dim-label">{{ dim.label }}</span>
            <div :ref="el => setChipGridRef(dim.key, el)" :class="['chip-grid', { collapsed: dim.collapsed }]">
              <span class="chip-toggle" @click="dim.collapsed = !dim.collapsed">{{ dim.collapsed ? '▼' : '▲' }}</span>
              <span v-if="!dim.options.length" class="chip-empty">暂无数据</span>
              <template v-for="(item, ci) in dim.options" :key="item.id || item">
                <div
                  :class="['chip-item', { active: isChipSelected(dim.key, item), disabled: chipStates[dim.key]?.[ci]?.active === false && !isChipSelected(dim.key, item) }]"
                  draggable="true"
                  @dragstart="onChipDragStart($event, dim.key, ci)"
                  @dragover.prevent="onChipDragOver($event, dim.key, ci)"
                  @dragenter.prevent="onChipDragEnter($event, dim.key, ci)"
                  @dragleave="onChipDragLeave($event)"
                  @drop="onChipDrop($event, dim.key, ci)"
                  @dragend="onChipDragEnd($event)"
                  @click="chipStates[dim.key]?.[ci]?.active !== false && toggleChip(dim.key, item)"
                >{{ item.name || item }}</div>
              </template>
            </div>
          </div>
        </div>

        <div v-if="summary" class="summary-row">
          <div class="sum-card"><div class="sum-num">{{ summary.total_tasks }}</div><div class="sum-label">检测任务数</div></div>
          <div class="sum-card" v-for="(count, type) in summary.summary" :key="type"><div class="sum-num" :style="{color: count > 0 ? '#f56c6c' : '#10b981'}">{{ count }}</div><div class="sum-label">{{ type }}</div></div>
          <div class="sum-card total"><div class="sum-num">{{ summary.total_issues }}</div><div class="sum-label">问题总数</div></div>
          <div v-if="searchKey || activeFilterCount" class="sum-card" style="background:#f0f9ff"><div class="sum-num" style="color:#409eff">{{ filteredTotal }}</div><div class="sum-label">筛选结果</div></div>
        </div>

        <el-table :data="pagedIssues" border stripe v-loading="loadingIssues" element-loading-text="加载中..."
          @row-click="openEdit" style="cursor:pointer" empty-description="请选择方案后点击「开始检测」">
          <el-table-column label="问题类型" width="180">
            <template #default="{ row }"><el-tag v-for="t in row._types" :key="t" size="small" :type="tagType(t)" style="margin-right:4px;margin-bottom:2px">{{ t }}</el-tag></template>
          </el-table-column>
          <el-table-column prop="assessor_unit_name" label="主考单位" width="130" />
          <el-table-column label="主要任务" min-width="180">
            <template #default="{ row }"><span class="cell-wrap" v-html="highlight(row.main_task)"></span></template>
          </el-table-column>
          <el-table-column label="被考核单位" min-width="200">
            <template #default="{ row }">
              <span style="font-size:12px;color:#606266">{{ row._units.length }} 个单位：</span>
              <el-tag v-for="u in row._units" :key="u" size="small" type="info" style="margin-right:3px;margin-bottom:2px">{{ u }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="问题数" width="70">
            <template #default="{ row }"><span style="font-weight:600;color:#f56c6c">{{ row._issues.length }}</span></template>
          </el-table-column>
        </el-table>

        <div v-if="filteredTotal > 0" class="pagination-wrap">
          <el-pagination v-model:current-page="issuePage" v-model:page-size="issuePageSize" :total="filteredTotal"
            :page-sizes="[20, 50, 100, 200]" layout="total, sizes, prev, pager, next, jumper"
            @size-change="issuePage = 1" @current-change="issuePage = $event" />
        </div>
      </el-tab-pane>

      <!-- ========== 标签页2：疑似以指标考指标 ========== -->
      <el-tab-pane :label="proxyTabLabel" name="proxy">
        <div v-if="proxySummary" class="summary-row">
          <div class="sum-card"><div class="sum-num" style="color:#f56c6c">{{ proxySummary.pending }}</div><div class="sum-label">待处理</div></div>
          <div class="sum-card"><div class="sum-num" style="color:#10b981">{{ proxySummary.confirmed }}</div><div class="sum-label">已确认</div></div>
          <div class="sum-card"><div class="sum-num" style="color:#409eff">{{ proxySummary.resolved }}</div><div class="sum-label">已修正</div></div>
          <div class="sum-card total"><div class="sum-num">{{ proxySummary.total }}</div><div class="sum-label">合计</div></div>
        </div>

        <div class="chip-filter-area" v-if="proxyFilterOptions.middle_units?.length">
          <div class="chip-dim-row">
            <span class="chip-dim-label">中间单位</span>
            <div class="chip-grid">
              <span
                v-for="u in proxyFilterOptions.middle_units"
                :key="u.id"
                :class="['chip-item', { active: proxyFilter.middle_unit_id === u.id }]"
                @click="proxyFilter.middle_unit_id = proxyFilter.middle_unit_id === u.id ? null : u.id"
              >{{ u.name }}</span>
            </div>
          </div>
          <div class="chip-dim-row">
            <span class="chip-dim-label">状态</span>
            <div class="chip-grid">
              <span
                v-for="s in proxyStatusOptions"
                :key="s.value"
                :class="['chip-item', { active: proxyFilter.status === s.value }]"
                @click="proxyFilter.status = proxyFilter.status === s.value ? '' : s.value"
              >{{ s.label }} ({{ proxySummary?.[s.value] || 0 }})</span>
            </div>
          </div>
          <div style="margin-top:4px">
            <el-button v-if="proxyFilter.middle_unit_id || proxyFilter.status" size="small" @click="clearProxyFilter">清除筛选</el-button>
            <el-button v-if="selectedProxyIds.length" size="small" type="warning" @click="batchConfirmPairs">批量确认({{ selectedProxyIds.length }})</el-button>
          </div>
        </div>

        <el-table :data="pagedProxyPairs" border stripe v-loading="loadingProxy"
          @selection-change="onProxySelectionChange" empty-description="暂无疑似以指标考指标问题">
          <el-table-column type="selection" width="40" :selectable="row => row.status === 'pending'" />
          <el-table-column label="中间单位" width="120" prop="middle_unit_name" />
          <el-table-column label="源主考单位" width="120" prop="source_unit_name" />
          <el-table-column label="接收任务" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">{{ row.task_a_summary }}</template>
          </el-table-column>
          <el-table-column label="下发任务" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">{{ row.task_b_summary }}</template>
          </el-table-column>
          <el-table-column label="目标单位" width="120" prop="target_unit_name" />
          <el-table-column label="相似度" width="80" align="center">
            <template #default="{ row }">
              <span :style="{color: row.similarity > 0.5 ? '#f56c6c' : row.similarity > 0.3 ? '#e6a23c' : '#909399', fontWeight: 600}">
                {{ (row.similarity * 100).toFixed(0) }}%
              </span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag :type="pairStatusTag(row.status)" size="small">{{ pairStatusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="备注" width="140" show-overflow-tooltip prop="remark" />
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <el-button size="small" text type="primary" @click.stop="openPairDetail(row)">查看详情</el-button>
              <el-button v-if="row.status === 'pending'" size="small" text type="warning" @click.stop="confirmSinglePair(row)">确认无误</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="proxyTotal > 0" class="pagination-wrap">
          <el-pagination v-model:current-page="proxyPage" v-model:page-size="proxyPageSize" :total="proxyTotal"
            :page-sizes="[20, 50, 100]" layout="total, sizes, prev, pager, next, jumper"
            @size-change="proxyPage = 1" />
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- ========== 常规问题编辑弹窗 ========== -->
    <el-dialog v-model="editVisible" title="编辑任务" width="66%" top="3vh" @close="editTaskId = null; editIssues = []; editSimilarTasks = []; editActiveTab = 0; editUnitSiblings = []; editUnitTab = 0">
      <el-tabs v-if="editUnitSiblings.length > 1" v-model="editUnitTab" type="card" @tab-change="onUnitTabChange" style="margin-bottom:12px">
        <el-tab-pane v-for="(ut, uti) in editUnitSiblings" :key="uti" :label="ut.unit_name || '单位' + (uti + 1)" />
      </el-tabs>
      <el-tabs v-if="editSimilarTasks.length" v-model="editActiveTab" type="card" @tab-change="onSimilarTabChange" style="margin-bottom:12px">
        <el-tab-pane v-for="(st, sti) in editSimilarTasks" :key="sti" :label="st._tabLabel || '任务' + (sti + 1) + '：' + (st.assessor_unit_name || '') + ' → ' + (st.unit_name || '')" />
      </el-tabs>
      <div v-if="editIssues.length" style="margin-bottom:16px;padding:10px 14px;background:#fef0f0;border-radius:6px;border:1px solid #fbc4c4">
        <div style="font-weight:600;color:#f56c6c;margin-bottom:6px">当前任务待处理问题（共 {{ editIssues.length }} 个）</div>
        <div v-for="(iss, idx) in editIssues" :key="idx" style="font-size:13px;color:#606266;margin-bottom:4px">
          <el-tag size="small" :type="tagType(iss.issue_type)" style="margin-right:6px">{{ iss.column_name || iss.column }}</el-tag>
          <span>{{ iss.text }}</span>
          <span v-if="iss.suggestion" style="color:#f56c6c"> → {{ iss.suggestion }}</span>
          <span v-if="iss.autoFixable" style="color:#10b981;margin-left:4px">（可自动更正）</span>
        </div>
      </div>
      <el-form v-if="editTask" :model="editForm" label-width="90px">
        <el-form-item label="考核维度">
          <el-select v-model="editForm.assessment_dimension_id" style="width:100%">
            <el-option v-for="d in availableDims" :key="d.id" :label="d.name" :value="d.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="被考核单位">
          <el-select v-model="editForm.unit_id" filterable style="width:100%">
            <el-option v-for="u in allUnits" :key="u.id" :label="u.name" :value="u.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="主考单位">
          <el-select v-model="editForm.assessor_unit_id" style="width:100%">
            <el-option v-for="u in assessorUnits" :key="u.id" :label="u.name" :value="u.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="重点工作" :class="{ 'error-field': activeErrorFields.includes('重点工作') }">
          <el-input v-model="editForm.key_work" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="主要任务" :class="{ 'error-field': activeErrorFields.includes('主要任务') }">
          <el-input v-model="editForm.main_task" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="评分说明" :class="{ 'error-field': activeErrorFields.includes('评分说明') }">
          <el-input v-model="editForm.scoring_note" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="晾晒周期">
          <el-select v-model="editForm.review_period" style="width:100%">
            <el-option v-for="p in periods" :key="p.value" :label="p.label" :value="p.value" />
          </el-select>
        </el-form-item>
        <el-alert v-if="siblingCount > 1" type="info" :closable="false" show-icon
          title="批量更正提示" :description="'同一主考单位下，此项涉及 ' + siblingCount + ' 条任务（' + editSiblingUnits + '），保存后将全部更正。'" />
      </el-form>
      <template #footer>
        <div style="display:flex;flex-direction:column;gap:8px;width:100%">
          <div style="display:flex;justify-content:space-between;width:100%">
            <el-button type="warning" @click="confirmBatch" :loading="saving">确认无误（{{ siblingCount }}条任务全部移除）</el-button>
            <div>
              <el-button @click="editVisible = false">取消</el-button>
              <el-button type="primary" @click="saveSingle" :loading="saving">保存并更正当前</el-button>
              <el-button type="primary" @click="saveBatch" :loading="saving">保存并更正全部（{{ siblingCount }}条）</el-button>
            </div>
          </div>
          <div v-if="autoFixCount > 0" style="display:flex;justify-content:flex-end;gap:8px;width:100%;border-top:1px dashed #e4e7ed;padding-top:8px">
            <span style="color:#10b981;font-size:13px;line-height:32px;margin-right:auto">{{ autoFixCount }} 条建议可自动更正</span>
            <el-button type="success" @click="autoSaveSingle" :loading="saving">根据建议保存并更正</el-button>
            <el-button type="success" @click="autoSaveBatch" :loading="saving">根据建议保存并全部更正（{{ siblingCount }}条）</el-button>
          </div>
        </div>
      </template>
    </el-dialog>

    <!-- ========== 代理指标详情弹窗 ========== -->
    <el-dialog v-model="pairDetailVisible" title="疑似以指标考指标 — 详情" width="750px" top="5vh" @close="pairDetail = null; editingProxyTask = false">
      <template v-if="pairDetail">
        <div class="proxy-chain">
          <div class="chain-node source">
            <div class="chain-label">源主考单位</div>
            <div class="chain-name">{{ pairDetail.source_unit_name }}</div>
          </div>
          <div class="chain-arrow">→</div>
          <div class="chain-node middle">
            <div class="chain-label">中间单位</div>
            <div class="chain-name">{{ pairDetail.middle_unit_name }}</div>
          </div>
          <div class="chain-arrow">→</div>
          <div class="chain-node target">
            <div class="chain-label">目标被考核单位</div>
            <div class="chain-name">{{ pairDetail.target_unit_name }}</div>
          </div>
        </div>

        <el-alert type="warning" :closable="false" show-icon style="margin-bottom:16px">
          <template #title>
            文本相似度：<strong>{{ (pairDetail.similarity * 100).toFixed(0) }}%</strong>
            （置信度：{{ pairDetail.confidence === 'high' ? '高' : '中' }}）
          </template>
        </el-alert>

        <el-card shadow="never" style="margin-bottom:12px">
          <template #header>
            <el-tag type="info" size="small">接收方任务</el-tag>
            <span style="margin-left:8px;color:#909399;font-size:13px">{{ pairDetail.source_unit_name }} → {{ pairDetail.middle_unit_name }}</span>
          </template>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="重点工作">{{ pairDetail.recv_kw }}</el-descriptions-item>
            <el-descriptions-item label="主要任务">{{ pairDetail.recv_mt }}</el-descriptions-item>
          </el-descriptions>
        </el-card>

        <el-card shadow="never" style="margin-bottom:12px">
          <template #header>
            <el-tag type="warning" size="small">下发方任务</el-tag>
            <span style="margin-left:8px;color:#909399;font-size:13px">{{ pairDetail.middle_unit_name }} → {{ pairDetail.target_unit_name }}</span>
            <el-button size="small" text type="primary" style="float:right" @click="editProxyTask">编辑下发任务</el-button>
          </template>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="重点工作">
              <template v-if="editingProxyTask">
                <el-input v-model="proxyEditForm.key_work" type="textarea" :rows="2" />
              </template>
              <template v-else>{{ pairDetail.asgn_kw }}</template>
            </el-descriptions-item>
            <el-descriptions-item label="主要任务">
              <template v-if="editingProxyTask">
                <el-input v-model="proxyEditForm.main_task" type="textarea" :rows="3" />
              </template>
              <template v-else>{{ pairDetail.asgn_mt }}</template>
            </el-descriptions-item>
          </el-descriptions>
          <div v-if="editingProxyTask" style="margin-top:8px;text-align:right">
            <el-button size="small" @click="editingProxyTask = false">取消</el-button>
            <el-button size="small" type="primary" :loading="savingProxyTask" @click="saveProxyTask">保存修改</el-button>
          </div>
        </el-card>

        <div style="margin-bottom:12px">
          <el-input v-model="proxyRemark" placeholder="添加备注说明..." clearable>
            <template #append>
              <el-button @click="saveProxyRemark" :loading="savingRemark">保存备注</el-button>
            </template>
          </el-input>
        </div>

        <div style="text-align:right">
          <el-button v-if="pairDetail.status === 'pending'" type="warning" @click="confirmSinglePair(pairDetail)">确认无误（排除）</el-button>
          <el-button v-if="pairDetail.status === 'pending'" type="success" @click="resolveSinglePair(pairDetail)">标记为已修正</el-button>
          <el-button @click="pairDetailVisible = false">关闭</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- ========== 问题管理弹窗 ========== -->
    <el-dialog v-model="manageVisible" title="问题管理" width="950px">
      <div class="search-bar" style="margin-bottom:12px">
        <el-button @click="loadManageIssues">刷新</el-button>
        <span style="margin-left:16px;color:#909399;font-size:13px">共 {{ mGrouped.length }} 个主要任务 | 确认无误 {{ mTotalConfirmed }} 条 | 已更正 {{ mTotalResolved }} 条</span>
      </div>
      <el-tabs v-model="mTab">
        <el-tab-pane label="确认无误（系统误报）" name="confirmed">
          <el-table :data="mGrouped.filter(g => g.confirmed_count > 0)" border stripe max-height="400" row-key="main_task">
            <el-table-column label="主考单位" width="130" prop="assessor_name" />
            <el-table-column label="主要任务" min-width="180" prop="main_task" show-overflow-tooltip />
            <el-table-column label="涉及单位" min-width="200"><template #default="{ row }"><span style="font-size:12px;color:#606266">{{ row.unit_names.join('、') }}</span></template></el-table-column>
            <el-table-column label="误报数" width="80" prop="confirmed_count" />
            <el-table-column label="操作" width="80"><template #default="{ row }"><el-button size="small" type="primary" link @click="undoGroup(row, 'confirmed')">撤回全部</el-button></template></el-table-column>
          </el-table>
          <el-empty v-if="!mGrouped.filter(g => g.confirmed_count > 0).length" description="暂无确认无误记录" :image-size="60" />
        </el-tab-pane>
        <el-tab-pane label="已更正（实际修改）" name="resolved">
          <el-table :data="mGrouped.filter(g => g.resolved_count > 0)" border stripe max-height="400" row-key="main_task">
            <el-table-column label="主考单位" width="130" prop="assessor_name" />
            <el-table-column label="主要任务" min-width="180" prop="main_task" show-overflow-tooltip />
            <el-table-column label="涉及单位" min-width="200"><template #default="{ row }"><span style="font-size:12px;color:#606266">{{ row.unit_names.join('、') }}</span></template></el-table-column>
            <el-table-column label="更正数" width="80" prop="resolved_count" />
            <el-table-column label="操作" width="80"><template #default="{ row }"><el-button size="small" type="primary" link @click="undoGroup(row, 'resolved')">撤回全部</el-button></template></el-table-column>
          </el-table>
          <el-empty v-if="!mGrouped.filter(g => g.resolved_count > 0).length" description="暂无已更正记录" :image-size="60" />
        </el-tab-pane>
      </el-tabs>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive, watch, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getPlans, getPlan } from '../api/plan'
import { getUnits } from '../api/unit'
import http from '../api/index'
import { useAuthStore } from '../store/auth'
import { getChipSortOrder, saveChipSortOrder } from '../api/user'
import {
  getQualityIssues, getProxyIssues, runQualityCheck, batchCorrectTask,
  correctSingleTask, batchConfirmIssues, confirmProxyMetric,
  getGroupedIssues, batchUpdateIssueStatus, exportQualityIssues,
  getProxyMetricPairs, getProxyMetricPair, updateProxyMetricPair,
  batchConfirmProxyPairs, batchResolveProxyPairs,
  updateProxyPairRemark, getProxyMetricFilterOptions, exportProxyMetrics,
} from '../api/quality-check'
const auth = useAuthStore()

// ===== 共享状态 =====
const activeTab = ref('issues')
const filterPlanId = ref(null)
const checking = ref(false)
const plans = ref([])
const allUnits = ref([])
const assessorUnits = ref([])
const availableDims = ref([])
const searchKey = ref('')
const periods = [
  { label: '月度', value: 'monthly' }, { label: '季度', value: 'quarterly' },
  { label: '半年度', value: 'semiannual' }, { label: '年度', value: 'annual' },
]

// ===== 标签页1：任务质检 =====
const loadingIssues = ref(false)
const summary = ref(null)
const allIssues = ref([])
const issuePage = ref(1)
const issuePageSize = ref(50)

const chipDimensions = reactive([
  { key: 'issue_type', label: '问题类型', options: [], selected: [], collapsed: true },
  { key: 'assessor', label: '主考单位', options: [], selected: [], collapsed: true },
  { key: 'unit', label: '被考核单位', options: [], selected: [], collapsed: true },
])

const activeFilterCount = computed(() => chipDimensions.reduce((s, d) => s + d.selected.length, 0))

let loadId = 0

const chipGridRefs = {}
function setChipGridRef(key, el) { if (el) chipGridRefs[key] = el }

function checkChipOverflow() {
  for (const dim of chipDimensions) {
    if (dim.options.length > 6) dim.collapsed = true; else dim.collapsed = false
  }
}

function buildChipOptions() {
  const all = allIssues.value.filter(i => i.status === 'pending')
  const types = [...new Set(all.map(i => i.issue_type).filter(Boolean))].sort()
  chipDimensions[0].options = types.map(t => ({ id: t, name: t }))
  const assessors = [...new Set(all.map(i => i.assessor_unit_name).filter(Boolean))].sort()
  chipDimensions[1].options = assessors.map(n => ({ id: n, name: n }))
  const units = [...new Set(all.map(i => i.unit_name).filter(Boolean))].sort()
  chipDimensions[2].options = units.map(n => ({ id: n, name: n }))
  checkChipOverflow()
  applySortOrders()
}

function isChipSelected(dimKey, item) {
  const dim = chipDimensions.find(d => d.key === dimKey)
  if (!dim) return false
  const id = item.id || item
  return dim.selected.some(s => (s.id || s) === id)
}

function toggleChip(dimKey, item) {
  const dim = chipDimensions.find(d => d.key === dimKey)
  if (!dim) return
  const id = item.id || item
  const idx = dim.selected.findIndex(s => (s.id || s) === id)
  if (idx >= 0) dim.selected.splice(idx, 1)
  else dim.selected.push(item)
}

function clearAllChips() { chipDimensions.forEach(d => d.selected = []) }

// 级联禁用（客户端实时计算）
const chipStates = computed(() => {
  const baseSet = allIssues.value.filter(i => i.status === 'pending')
  const states = {}
  for (const dim of chipDimensions) {
    states[dim.key] = dim.options.map(opt => {
      let testSet = [...baseSet]
      for (const otherDim of chipDimensions) {
        if (otherDim.key === dim.key) continue
        if (otherDim.selected.length > 0) {
          const ids = new Set(otherDim.selected.map(c => c.id || c))
          if (otherDim.key === 'issue_type') testSet = testSet.filter(i => ids.has(i.issue_type))
          else if (otherDim.key === 'assessor') testSet = testSet.filter(i => ids.has(i.assessor_unit_name))
          else if (otherDim.key === 'unit') testSet = testSet.filter(i => ids.has(i.unit_name))
        }
      }
      const optId = opt.id || opt
      const wouldYield = testSet.some(i => {
        if (dim.key === 'issue_type') return i.issue_type === optId
        if (dim.key === 'assessor') return i.assessor_unit_name === optId
        if (dim.key === 'unit') return i.unit_name === optId
        return false
      })
      return { active: wouldYield }
    })
  }
  return states
})

// 芯片拖拽排序
const dragState = reactive({ sourceDimKey: null, sourceIndex: -1 })
const chipPageId = 'quality_check'

function onChipDragStart(e, dimKey, index) {
  dragState.sourceDimKey = dimKey; dragState.sourceIndex = index
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData('text/plain', dimKey + ':' + index)
  setTimeout(() => e.target.classList.add('dragging'), 0)
}
function onChipDragOver(e, dimKey, index) { e.dataTransfer.dropEffect = 'move' }
function onChipDragEnter(e, dimKey, index) {
  if (dimKey !== dragState.sourceDimKey) return
  e.target.classList.add('drag-over')
}
function onChipDragLeave(e) { e.target.classList.remove('drag-over') }
function onChipDrop(e, dimKey, index) {
  e.target.classList.remove('drag-over')
  if (dimKey !== dragState.sourceDimKey) return
  if (dragState.sourceIndex === index) return
  const dim = chipDimensions.find(d => d.key === dimKey)
  if (!dim) return
  const [removed] = dim.options.splice(dragState.sourceIndex, 1)
  dim.options.splice(index, 0, removed)
  const sortOrder = dim.options.map(o => String(o.id || o))
  saveChipSortOrder(chipPageId, dimKey, sortOrder).catch(() => {})
  dragState.sourceDimKey = null; dragState.sourceIndex = -1
}
function onChipDragEnd(e) {
  e.target.classList.remove('dragging')
  document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'))
}

let savedSortOrders = {}
async function loadChipSortOrders() {
  try {
    const res = await getChipSortOrder(chipPageId)
    savedSortOrders = res.data || res || {}
  } catch { savedSortOrders = {} }
}
function applySortOrders() {
  for (const dim of chipDimensions) {
    const order = savedSortOrders[dim.key]
    if (order && order.length) {
      const orderMap = new Map(order.map((id, i) => [String(id), i]))
      dim.options.sort((a, b) => {
        const aOrder = orderMap.get(String(a.id || a))
        const bOrder = orderMap.get(String(b.id || b))
        if (aOrder !== undefined && bOrder !== undefined) return aOrder - bOrder
        if (aOrder !== undefined) return -1
        if (bOrder !== undefined) return 1
        return 0
      })
    }
  }
}

function onSearch() { issuePage.value = 1 }

function escapeHtml(text) {
  if (!text) return ''
  const div = document.createElement('div'); div.textContent = String(text); return div.innerHTML
}
function highlight(text) {
  if (!searchKey.value || !text) return escapeHtml(String(text))
  const esc = escapeHtml(String(text)); const kw = searchKey.value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return esc.replace(new RegExp(kw, 'gi'), m => '<mark style="background:#fef08a;padding:0 2px">' + m + '</mark>')
}

const sortedIssues = computed(() => {
  const arr = [...allIssues.value].filter(i => i.status === 'pending')
  arr.sort((a, b) => {
    const aa = (a.assessor_unit_name || ''); const ba = (b.assessor_unit_name || '')
    if (aa !== ba) return aa.localeCompare(ba, 'zh')
    const am = (a.main_task || ''); const bm = (b.main_task || '')
    if (am !== bm) return am.localeCompare(bm, 'zh')
    return (a.unit_name || '').localeCompare(b.unit_name || '', 'zh')
  })
  return arr
})

const filteredIssues = computed(() => {
  let arr = [...sortedIssues.value]
  for (const dim of chipDimensions) {
    if (dim.selected.length) {
      const ids = new Set(dim.selected.map(c => c.id || c))
      if (dim.key === 'issue_type') arr = arr.filter(i => ids.has(i.issue_type))
      else if (dim.key === 'assessor') arr = arr.filter(i => ids.has(i.assessor_unit_name))
      else if (dim.key === 'unit') arr = arr.filter(i => ids.has(i.unit_name))
    }
  }
  if (searchKey.value) {
    const kw = searchKey.value.toLowerCase()
    arr = arr.filter(i =>
      (i.text || '').toLowerCase().includes(kw) || (i.suggestion || '').toLowerCase().includes(kw) ||
      (i.main_task || '').toLowerCase().includes(kw) || (i.unit_name || '').toLowerCase().includes(kw) ||
      (i.assessor_unit_name || '').toLowerCase().includes(kw) || (i.issue_type || '').toLowerCase().includes(kw))
  }
  return arr
})

const filteredTotal = computed(() => groupedIssues.value.length)

const groupedIssues = computed(() => {
  const groups = new Map()
  for (const iss of filteredIssues.value) {
    const key = (iss.assessor_unit_name || '') + '|||' + (iss.main_task || '')
    if (!groups.has(key)) {
      groups.set(key, { _key: key, _units: new Set(), _taskIds: [], _unitTaskMap: {}, _issues: [], _typeSet: new Set(),
        assessor_unit_name: iss.assessor_unit_name, main_task: iss.main_task, status: iss.status, issue_type: iss.issue_type })
    }
    const g = groups.get(key)
    g._units.add(iss.unit_name || '')
    g._taskIds.push(iss.task_id)
    if (iss.unit_name) g._unitTaskMap[iss.unit_name] = iss.task_id
    g._issues.push(iss)
    g._typeSet.add(iss.issue_type)
  }
  return [...groups.values()].map(g => ({ ...g, _units: [...g._units], _types: [...g._typeSet], _unitTaskMap: g._unitTaskMap }))
})

const pagedIssues = computed(() => {
  const start = (issuePage.value - 1) * issuePageSize.value
  return groupedIssues.value.slice(start, start + issuePageSize.value)
})

watch([searchKey, ...chipDimensions.map(d => () => d.selected.length)], () => { issuePage.value = 1 })

// 编辑弹窗
const editVisible = ref(false); const editTaskId = ref(null); const editTask = ref(null)
const saving = ref(false); const siblingCount = ref(0); const editSiblingUnits = ref('')
const editForm = reactive({ assessment_dimension_id: null, unit_id: null, assessor_unit_id: null, key_work: '', main_task: '', scoring_note: '', review_period: 'monthly' })
const editIssues = ref([]); const editSimilarTasks = ref([]); const editActiveTab = ref(0)
const editUnitSiblings = ref([]); const editUnitTab = ref(0)

const COLUMN_TO_FIELD = { '重点工作': 'key_work', '主要任务': 'main_task', '评分说明': 'scoring_note' }

const activeErrorFields = computed(() => {
  const fields = new Set()
  for (const iss of editIssues.value) { const col = iss.column_name || iss.column || ''; for (const label of Object.keys(COLUMN_TO_FIELD)) { if (col === label) fields.add(label) } }
  return [...fields]
})

const autoFixableIssues = computed(() => editIssues.value.filter(i => i.autoFixable))
const autoFixCount = computed(() => autoFixableIssues.value.length)

function isAutoFixable(issue) {
  const col = issue.column_name || issue.column || ''
  if (!COLUMN_TO_FIELD[col]) return false
  if ((issue.issue_type || '').includes('错别字')) return !!parseSuggestion(issue.suggestion || '')
  if ((issue.issue_type || '').includes('标点')) return ['英文逗号', '英文括号', '缺少结尾'].some(t => (issue.issue_type || '').includes(t))
  return false
}

function parseSuggestion(suggestion) {
  if (!suggestion) return null
  const m = suggestion.match(/"(.+?)"应为"(.+?)"/); if (m) return { from: m[1], to: m[2] }
  return null
}

function autoFixForm() {
  for (const iss of autoFixableIssues.value) {
    const col = iss.column_name || iss.column || ''; const field = COLUMN_TO_FIELD[col]
    if (!field) continue
    let newVal = editForm[field] || ''; const oldVal = newVal; const itype = iss.issue_type || ''
    if (itype.includes('错别字') && iss._parsed) newVal = oldVal.replace(iss._parsed.from, iss._parsed.to)
    else if (itype.includes('英文逗号')) newVal = oldVal.replace(/(?<![0-9]),(?![0-9])/g, '，')
    else if (itype.includes('英文括号')) newVal = oldVal.replace(/\(([^)]{2,})\)/g, '（$1）')
    else if (itype.includes('缺少结尾')) { const trimmed = oldVal.trimEnd(); if (trimmed && !trimmed.endsWith('。')) newVal = trimmed + '。' }
    if (newVal !== oldVal) editForm[field] = newVal
  }
}

async function autoSaveSingle() { autoFixForm(); await saveSingle() }
async function autoSaveBatch() { autoFixForm(); await saveBatch() }

async function onSimilarTabChange(tabIndex) {
  if (tabIndex === 0) { const task = editTask.value; if (task) fillFormFromTask(task); editTaskId.value = task?.id }
  else { const st = editSimilarTasks.value[tabIndex]; if (st) { fillFormFromTask(st); editTaskId.value = st.id } }
}

async function onUnitTabChange(tabIndex) {
  const ut = editUnitSiblings.value[tabIndex]
  if (ut && ut.id) {
    try {
      const r = await http.get('/tasks/' + ut.id); const task = r.data || r
      if (task) { editTask.value = task; fillFormFromTask(task); editTaskId.value = task.id
        editIssues.value = allIssues.value.filter(i => i.task_id === task.id && i.status === 'pending').map(i => { const parsed = parseSuggestion(i.suggestion || ''); return { ...i, _parsed: parsed, autoFixable: isAutoFixable(i) } }) }
    } catch { /* ignore */ }
  }
}

function fillFormFromTask(task) {
  editForm.assessment_dimension_id = task.assessment_dimension_id; editForm.unit_id = task.unit_id
  editForm.assessor_unit_id = task.assessor_unit_id; editForm.key_work = task.key_work || ''
  editForm.main_task = task.main_task || ''; editForm.scoring_note = task.scoring_note || ''; editForm.review_period = task.review_period || 'monthly'
}

function tagType(type) {
  if (!type) return 'info'
  if (type.includes('错别字')) return 'danger'
  if (type.includes('重复')) return 'warning'
  if (type.includes('标点')) return 'primary'
  return 'info'
}

async function loadPlans() {
  try { const r = await getPlans(); plans.value = r.data?.items || []; if (plans.value.length > 0) { const latest = plans.value.reduce((a, b) => (a.id > b.id ? a : b)); filterPlanId.value = latest.id } } catch {}
}
async function loadUnits() { try { const r = await getUnits({ page_size: 9999 }); allUnits.value = r.data?.items || [] } catch {} }

function onPlanChange() { summary.value = null; allIssues.value = []; proxyPairs.value = []; searchKey.value = ''; clearAllChips(); loadIssues(); loadProxyPairs() }

watch(filterPlanId, async (pid) => {
  if (pid) {
    try { const r = await getPlan(pid); assessorUnits.value = r.data?.assessor_units || []; const dim = r.data?.evaluation_dimensions?.find(d => d.is_actual_assessment); availableDims.value = dim?.assessment_dimensions || []; await loadIssues(); await loadProxyPairs() } catch { assessorUnits.value = []; availableDims.value = [] }
  }
})

async function loadIssues() {
  if (!filterPlanId.value) return
  const thisId = ++loadId; loadingIssues.value = true
  try {
    const r = await getQualityIssues({ plan_id: filterPlanId.value, page_size: 2000 })
    if (thisId !== loadId) return
    const data = r.data?.data || r.data || {}; const items = (data.items || []).map(i => ({ ...i, column: i.column_name || i.column, status: i.status || 'pending' }))
    allIssues.value = items
    const pending = items.filter(i => i.status === 'pending'); const typeCounts = {}
    pending.forEach(i => { const t = i.issue_type || ''; if (t.includes('错别字')) typeCounts['错别字'] = (typeCounts['错别字'] || 0) + 1; else if (t.includes('逻辑')) typeCounts['逻辑问题'] = (typeCounts['逻辑问题'] || 0) + 1; else if (t.includes('标点')) typeCounts['标点符号'] = (typeCounts['标点符号'] || 0) + 1; else if (t.includes('重复')) typeCounts['重复任务'] = (typeCounts['重复任务'] || 0) + 1 })
    summary.value = { total_tasks: summary.value?.total_tasks ?? 0, summary: { '错别字': typeCounts['错别字'] || 0, '逻辑问题': typeCounts['逻辑问题'] || 0, '标点符号': typeCounts['标点符号'] || 0, '重复任务': typeCounts['重复任务'] || 0 }, total_issues: pending.length }
    const maxPage = Math.max(1, Math.ceil(pending.length / issuePageSize.value)); if (issuePage.value > maxPage) issuePage.value = maxPage
    buildChipOptions()
  } catch (e) { if (thisId !== loadId) return; console.error('加载问题列表失败:', e) }
  finally { if (thisId === loadId) loadingIssues.value = false }
}

async function runCheck() {
  if (!filterPlanId.value) return
  const thisId = ++loadId; checking.value = true; summary.value = null; allIssues.value = []; proxyPairs.value = []; issuePage.value = 1
  try {
    const r = await runQualityCheck(filterPlanId.value)
    if (thisId !== loadId) return
    const data = r.data || r
    summary.value = { total_tasks: data.total_tasks, summary: data.summary, total_issues: data.total_issues }
    allIssues.value = (data.issues || []).map(i => ({ ...i, column: i.column_name || i.column, status: i.status || 'pending' }))
    ElMessage.success(r.msg || '检测完成')
    buildChipOptions()
    // 检测完成后刷新代理指标列表
    await loadProxyPairs()
  } catch (e) { if (thisId !== loadId) return; ElMessage.error('检测失败：' + (e.response?.data?.msg || e.message || '请检查后端服务')) }
  finally { if (thisId === loadId) checking.value = false }
}

async function openEdit(row) {
  try {
    const initTaskId = row._issues ? row._taskIds[0] : row.task_id
    const r = await http.get('/tasks/' + initTaskId); const task = r.data || r
    if (!task) { ElMessage.warning('未找到关联任务'); return }
    editTask.value = task; editSimilarTasks.value = [task]; editActiveTab.value = 0; editUnitSiblings.value = []; editUnitTab.value = 0
    fillFormFromTask(task); editTaskId.value = task.id

    if (row._issues && row._units.length > 1) {
      const sr = await http.get('/tasks', { params: { plan_id: filterPlanId.value, assessor_unit_id: task.assessor_unit_id, search: task.main_task, search_type: 'main_task', page_size: 2000 } })
      const allTasks = (sr.data?.items || sr.data || [])
      const siblings = allTasks.filter(t => Number(t.assessor_unit_id) === Number(task.assessor_unit_id) && t.main_task === task.main_task)
      editUnitSiblings.value = siblings.map(t => ({ id: t.id, unit_name: t.unit_name || (t.unit?.name) || '' }))
      const currentUnit = row._units[0]; const tabIdx = editUnitSiblings.value.findIndex(ut => ut.unit_name === currentUnit)
      if (tabIdx >= 0) editUnitTab.value = tabIdx
      siblingCount.value = siblings.length; editSiblingUnits.value = [...new Set(siblings.map(s => s.unit_name).filter(Boolean))].join('、')
    } else {
      const sr = await http.get('/tasks', { params: { plan_id: filterPlanId.value, assessor_unit_id: task.assessor_unit_id, search: task.main_task, search_type: 'main_task', page_size: 2000 } })
      const allTasks = (sr.data?.items || sr.data || [])
      const siblings = allTasks.filter(t => Number(t.assessor_unit_id) === Number(task.assessor_unit_id) && t.main_task === task.main_task)
      siblingCount.value = siblings.length; editSiblingUnits.value = [...new Set(siblings.map(s => s.unit_name).filter(Boolean))].join('、')
    }

    editIssues.value = allIssues.value.filter(i => i.task_id === task.id && i.status === 'pending').map(i => { const parsed = parseSuggestion(i.suggestion || ''); return { ...i, _parsed: parsed, autoFixable: isAutoFixable(i) } })

    // 只加载重复任务的相似任务（非代理）
    const dupIssues = editIssues.value.filter(i => (i.issue_type || '').includes('重复'))
    if (dupIssues.length) {
      const seenIds = new Set([task.id])
      for (const di of dupIssues) { const simId = di.task_id_b; if (simId && !seenIds.has(simId)) { seenIds.add(simId); try { const sr2 = await http.get('/tasks/' + simId); const simTask = sr2.data || sr2; if (simTask && simTask.id) editSimilarTasks.value.push({ ...simTask, assessor_unit_name: simTask.assessor_unit_name || (simTask.assessor_unit?.name), unit_name: simTask.unit_name || (simTask.unit?.name) }) } catch {} } }
    }

    editVisible.value = true
  } catch (e) { console.error('加载任务失败:', e); ElMessage.error('加载任务失败，请重试') }
}

async function saveSingle() {
  if (!editTaskId.value) return; saving.value = true
  try {
    const allFields = ['key_work', 'main_task', 'scoring_note', 'assessment_dimension_id', 'unit_id', 'assessor_unit_id', 'review_period']
    const updates = {}; const orig = editTask.value || {}
    for (const f of allFields) { const oldVal = (orig[f] ?? ''); const newVal = (editForm[f] ?? ''); if (oldVal !== newVal) updates[f] = newVal }
    await correctSingleTask(editTaskId.value, Object.keys(updates).length > 0 ? updates : { _noop: true })
    ElMessage.success('单条更正成功'); editVisible.value = false; editTaskId.value = null; await loadIssues()
  } catch (e) { ElMessage.error('保存失败，请重试') }
  finally { saving.value = false }
}

async function saveBatch() {
  if (!editTaskId.value) return; saving.value = true
  try {
    const allFields = ['key_work', 'main_task', 'scoring_note', 'assessment_dimension_id', 'unit_id', 'assessor_unit_id', 'review_period']
    const updates = {}; const orig = editTask.value || {}
    for (const f of allFields) { const oldVal = (orig[f] ?? ''); const newVal = (editForm[f] ?? ''); if (oldVal !== newVal) updates[f] = newVal }
    await batchCorrectTask(editTaskId.value, Object.keys(updates).length > 0 ? updates : { _noop: true })
    ElMessage.success('批量更正成功（' + siblingCount.value + ' 条任务）'); editVisible.value = false; editTaskId.value = null; await loadIssues()
  } catch (e) { ElMessage.error('保存失败，请重试') }
  finally { saving.value = false }
}

async function confirmBatch() {
  if (!editTaskId.value) return; saving.value = true
  try {
    const r = await batchConfirmIssues(editTaskId.value); ElMessage.success(r.msg || '已确认无误')
    editVisible.value = false; editTaskId.value = null; await loadIssues()
  } catch (e) { ElMessage.error('操作失败，请重试') }
  finally { saving.value = false }
}

// 问题管理弹窗
const manageVisible = ref(false); const mTab = ref('confirmed'); const mGrouped = ref([])
const mTotalConfirmed = ref(0); const mTotalResolved = ref(0)

async function openManageDialog() { manageVisible.value = true; await loadManageIssues() }
async function loadManageIssues() {
  if (!filterPlanId.value) return
  try { const r = await getGroupedIssues(filterPlanId.value); mGrouped.value = (r.data || r || []); mTotalConfirmed.value = mGrouped.value.reduce((s, g) => s + g.confirmed_count, 0); mTotalResolved.value = mGrouped.value.reduce((s, g) => s + g.resolved_count, 0) } catch {}
}
async function undoGroup(group, type) {
  try {
    const items = type === 'confirmed' ? (group.confirmed_items || []) : (group.resolved_items || [])
    if (!items || items.length === 0) { ElMessage.warning('没有可撤回的问题'); return }
    const ids = items.map(i => i.id); await batchUpdateIssueStatus(ids, 'pending')
    ElMessage.success('已撤回 ' + ids.length + ' 条问题，回到待处理列表'); await loadManageIssues(); await loadIssues()
  } catch (e) { ElMessage.error('撤回失败，请重试') }
}

async function handleExport(mode) {
  if (!filterPlanId.value) return
  try {
    if (mode === 'proxy') {
      const r = await exportProxyMetrics({ plan_id: filterPlanId.value })
      const url = URL.createObjectURL(r.data || r); const a = document.createElement('a')
      a.href = url; a.download = '疑似以指标考指标清单.xlsx'; a.click(); URL.revokeObjectURL(url); ElMessage.success('导出成功')
    } else {
      const params = { plan_id: filterPlanId.value, mode }
      if (mode === 'filtered') {
        const typeDim = chipDimensions.find(d => d.key === 'issue_type'); if (typeDim && typeDim.selected.length) params.issue_type = typeDim.selected.map(c => c.name || c).join(',')
        if (searchKey.value) params.search = searchKey.value
      }
      const r = await exportQualityIssues(params)
      const url = URL.createObjectURL(r.data || r); const a = document.createElement('a')
      a.href = url; a.download = '质检问题清单_' + (mode === 'all' ? '全量' : '筛选结果') + '.xlsx'; a.click(); URL.revokeObjectURL(url); ElMessage.success('导出成功')
    }
  } catch (e) { ElMessage.error('导出失败') }
}

function refreshAll() {
  if (activeTab.value === 'issues') loadIssues()
  else loadProxyPairs()
}

// ===== 标签页2：疑似以指标考指标 =====
const proxyPairs = ref([])
const loadingProxy = ref(false)
const proxyPage = ref(1)
const proxyPageSize = ref(50)
const proxyFilter = reactive({ middle_unit_id: null, status: '' })
const proxyFilterOptions = ref({ middle_units: [], status_counts: {} })
const selectedProxyIds = ref([])
const pairDetailVisible = ref(false)
const pairDetail = ref(null)
const editingProxyTask = ref(false)
const savingProxyTask = ref(false)
const savingRemark = ref(false)
const proxyRemark = ref('')
const proxyEditForm = reactive({ key_work: '', main_task: '' })

const proxyStatusOptions = [
  { label: '待处理', value: 'pending' },
  { label: '已确认', value: 'confirmed' },
  { label: '已修正', value: 'resolved' },
]

const proxyTabLabel = computed(() => {
  const pending = proxySummary.value?.pending || 0
  return '疑似以指标考指标' + (pending > 0 ? ' (' + pending + ')' : '')
})

const proxySummary = computed(() => {
  const counts = proxyFilterOptions.value.status_counts || {}
  return {
    pending: counts.pending || 0,
    confirmed: counts.confirmed || 0,
    resolved: counts.resolved || 0,
    total: proxyPairs.value.length,
  }
})

const proxyTotal = computed(() => proxyPairs.value.length)

const pagedProxyPairs = computed(() => {
  const start = (proxyPage.value - 1) * proxyPageSize.value
  return proxyPairs.value.slice(start, start + proxyPageSize.value)
})

function onProxySelectionChange(selection) {
  selectedProxyIds.value = selection.map(s => s.id)
}

async function loadProxyPairs() {
  if (!filterPlanId.value) return
  loadingProxy.value = true
  try {
    const params = { plan_id: filterPlanId.value, page_size: 2000 }
    if (proxyFilter.middle_unit_id) params.middle_unit_id = proxyFilter.middle_unit_id
    if (proxyFilter.status) params.status = proxyFilter.status

    // 同时加载数据列表和筛选选项
    const [r, fo] = await Promise.all([
      getProxyMetricPairs(params),
      getProxyMetricFilterOptions(filterPlanId.value),
    ])
    proxyPairs.value = (r.data?.items || r.items || [])
    proxyFilterOptions.value = (fo.data || fo || { middle_units: [], status_counts: {} })
    proxyPage.value = 1
  } catch (e) { console.error('加载代理指标失败:', e) }
  finally { loadingProxy.value = false }
}

async function openPairDetail(row) {
  try {
    const r = await getProxyMetricPair(row.id)
    pairDetail.value = r.data || r
    proxyRemark.value = pairDetail.value.remark || ''
    proxyEditForm.key_work = pairDetail.value.asgn_kw || ''
    proxyEditForm.main_task = pairDetail.value.asgn_mt || ''
    editingProxyTask.value = false
    pairDetailVisible.value = true
  } catch (e) { ElMessage.error('加载详情失败') }
}

function editProxyTask() {
  editingProxyTask.value = true
}

async function saveProxyTask() {
  if (!pairDetail.value) return
  savingProxyTask.value = true
  try {
    // 更新下发方任务 (task_id_b)
    await http.put('/tasks/' + pairDetail.value.task_id_b, {
      key_work: proxyEditForm.key_work,
      main_task: proxyEditForm.main_task,
    })
    ElMessage.success('下发任务已更新，重新检测后该对可能自动消失')
    // 标记该对为已修正
    await updateProxyMetricPair(pairDetail.value.id, { status: 'resolved' })
    editingProxyTask.value = false
    pairDetail.value.asgn_kw = proxyEditForm.key_work
    pairDetail.value.asgn_mt = proxyEditForm.main_task
    pairDetail.value.status = 'resolved'
    await loadProxyPairs()
  } catch (e) { ElMessage.error('保存失败') }
  finally { savingProxyTask.value = false }
}

async function saveProxyRemark() {
  if (!pairDetail.value) return
  savingRemark.value = true
  try {
    await updateProxyPairRemark(pairDetail.value.id, proxyRemark.value)
    ElMessage.success('备注已保存')
    pairDetail.value.remark = proxyRemark.value
    await loadProxyPairs()
  } catch (e) { ElMessage.error('保存备注失败') }
  finally { savingRemark.value = false }
}

async function confirmSinglePair(row) {
  try {
    await ElMessageBox.confirm('确认该代理指标对为误报？确认后不再出现在待处理列表中。', '确认无误', { confirmButtonText: '确认', cancelButtonText: '取消', type: 'warning' })
    await updateProxyMetricPair(row.id, { status: 'confirmed' })
    ElMessage.success('已确认该对为误报')
    if (pairDetailVisible.value) {
      pairDetail.value.status = 'confirmed'
      pairDetailVisible.value = false
    }
    await loadProxyPairs()
  } catch (e) { /* cancelled */ }
}

async function resolveSinglePair(row) {
  try {
    await updateProxyMetricPair(row.id, { status: 'resolved' })
    ElMessage.success('已标记为已修正')
    if (pairDetailVisible.value) {
      pairDetail.value.status = 'resolved'
    }
    await loadProxyPairs()
  } catch (e) { ElMessage.error('操作失败') }
}

async function batchConfirmPairs() {
  if (!selectedProxyIds.value.length) { ElMessage.warning('请先勾选要确认的记录'); return }
  try {
    await ElMessageBox.confirm('确认将 ' + selectedProxyIds.value.length + ' 条记录标记为误报？', '批量确认', { confirmButtonText: '确认', cancelButtonText: '取消', type: 'warning' })
    await batchConfirmProxyPairs(selectedProxyIds.value)
    ElMessage.success('已批量确认 ' + selectedProxyIds.value.length + ' 条')
    selectedProxyIds.value = []
    await loadProxyPairs()
  } catch (e) { /* cancelled */ }
}

function clearProxyFilter() {
  proxyFilter.middle_unit_id = null
  proxyFilter.status = ''
  loadProxyPairs()
}

function pairStatusTag(status) {
  const map = { pending: 'danger', confirmed: 'info', resolved: 'success', ignored: 'warning' }
  return map[status] || 'info'
}
function pairStatusLabel(status) {
  const map = { pending: '待处理', confirmed: '已确认', resolved: '已修正', ignored: '已忽略' }
  return map[status] || status
}

function onTabChange(tabName) {
  if (tabName === 'issues') loadIssues()
  else if (tabName === 'proxy') loadProxyPairs()
}

// 监听代理筛选变化
watch([() => proxyFilter.middle_unit_id, () => proxyFilter.status], () => {
  loadProxyPairs()
})

onMounted(async () => {
  await loadChipSortOrders()
  await loadPlans()
  await loadUnits()
  if (filterPlanId.value) {
    await loadIssues()
    await loadProxyPairs()
  }
})
</script>

<style scoped>
.summary-row { display: flex; gap: 14px; margin-bottom: 18px; flex-wrap: wrap; }
.sum-card { flex: 1; min-width: 100px; background: #fff; border-radius: 8px; padding: 14px 16px; text-align: center; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
.sum-card.total { background: #fef0f0; }
.sum-num { font-size: 28px; font-weight: 700; color: #303133; }
.sum-label { font-size: 13px; color: #909399; margin-top: 4px; }
.cell-wrap { white-space: pre-wrap; word-break: break-all; }

.chip-filter-area { margin-bottom: 14px; padding: 12px; background: #f5f7fa; border-radius: 8px; border: 1px solid #e4e7ed; }
.chip-dim-row { margin-bottom: 8px; }
.chip-dim-row:last-child { margin-bottom: 0; }
.chip-dim-label { display: inline-block; font-size: 12px; font-weight: 600; color: #606266; min-width: 80px; vertical-align: top; padding-top: 7px; }
.chip-grid { display: inline-flex; flex-wrap: wrap; gap: 8px; max-height: 120px; overflow-y: auto; max-width: calc(100% - 88px); transition: max-height 0.25s; }
.chip-grid.collapsed { max-height: 30px; overflow-y: hidden; }
.chip-toggle { display: inline-block; padding: 4px 8px; border-radius: 6px; font-size: 11px; cursor: pointer; color: #909399; background: #f0f2f5; border: 1px dashed #dcdfe6; user-select: none; white-space: nowrap; transition: all 0.2s; }
.chip-toggle:hover { color: #409eff; border-color: #409eff; background: #ecf5ff; }
.chip-item { display: inline-block; padding: 4px 12px; border-radius: 6px; font-size: 12px; cursor: pointer; background: #fff; border: 1px solid #dcdfe6; color: #606266; transition: all 0.2s; user-select: none; white-space: nowrap; }
.chip-item:hover { border-color: #409eff; color: #409eff; }
.chip-item.active { background: #409eff; color: #fff; border-color: #409eff; }
.chip-item.disabled { color: #f56c6c; border-color: #fbc4c4; background: #fef0f0; cursor: not-allowed; }
.chip-item.disabled:hover { border-color: #fbc4c4; color: #f56c6c; }
.chip-item.dragging { opacity: 0.4; }
.chip-item.drag-over { border-color: #409eff; background: #ecf5ff; transform: scale(1.05); }
.chip-empty { font-size: 12px; color: #c0c4cc; padding: 4px 0; }

.error-field :deep(.el-input__inner), .error-field :deep(.el-textarea__inner) { border-color: #f56c6c; border-width: 2px; }
.error-field::before { content: '⚠ '; color: #f56c6c; }

/* 代理指标链路图 */
.proxy-chain { display: flex; align-items: center; justify-content: center; gap: 16px; margin-bottom: 20px; padding: 20px; background: linear-gradient(135deg, #f5f7fa 0%, #e8edf2 100%); border-radius: 12px; }
.chain-node { text-align: center; padding: 12px 20px; background: #fff; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); min-width: 120px; }
.chain-node.source { border: 2px solid #409eff; }
.chain-node.middle { border: 2px solid #e6a23c; }
.chain-node.target { border: 2px solid #10b981; }
.chain-label { font-size: 11px; color: #909399; margin-bottom: 4px; }
.chain-name { font-size: 14px; font-weight: 600; color: #303133; }
.chain-arrow { font-size: 24px; color: #c0c4cc; font-weight: bold; }

.pagination-wrap { display: flex; justify-content: flex-end; margin-top: 14px; }
</style>