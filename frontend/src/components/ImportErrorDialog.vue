<template>
  <el-dialog
    v-model="visible"
    title="导入数据校验"
    width="1500px"
    :close-on-click-modal="false"
    @close="$emit('close')"
  >
    <!-- 摘要栏 -->
    <el-alert type="warning" :closable="false" style="margin-bottom:16px">
      <template #title>
        共 {{ totalRowsCount }} 行数据，{{ errorCount }} 个问题 —
        <span style="color:#409eff;font-weight:bold">{{ confirmedCount }}</span> 个已确认，
        <span style="color:#67c23a;font-weight:bold">{{ validCount }}</span> 个已通过校验，
        <span style="color:#e6a23c;font-weight:bold">{{ unvalidatedCount }}</span> 个待校验
        <span v-if="failedCount > 0" style="color:#f56c6c;font-weight:bold">，{{ failedCount }} 个校验未通过</span>
      </template>
    </el-alert>

    <!-- 工具栏 -->
    <div style="margin-bottom:12px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <el-button type="warning" :disabled="autoFixableAndUnconfirmedCount === 0" @click="autoFixAll">
        一键更正 ({{ autoFixableAndUnconfirmedCount }})
      </el-button>
      <el-button :disabled="confirmedCount === 0" @click="undoFixAll">
        一键撤销 ({{ confirmedCount }})
      </el-button>
      <el-button type="info" :disabled="confirmedAndUnvalidatedCount === 0" :loading="isBatchValidating" @click="validateAll">
        一键校验 ({{ confirmedAndUnvalidatedCount }})
      </el-button>
      <el-button type="primary" :disabled="!canImport" @click="confirmImport">
        确认导入 ({{ totalRowsCount }} 条)
      </el-button>
      <el-button :disabled="fixedCount === 0 && deleted.size === 0" @click="undoAll">
        撤销全部
      </el-button>
      <el-button @click="$emit('download-report')">下载错误报告</el-button>

      <el-select v-if="errorFiles.length > 1" v-model="activeFile" style="width:220px;margin-left:auto">
        <el-option v-for="f in errorFiles" :key="f.filename" :label="f.filename" :value="f.filename">
          <span>{{ f.filename }}</span>
        </el-option>
      </el-select>
    </div>

    <!-- 工作表标签 -->
    <el-tabs v-model="activeTab" v-if="currentFile">
      <el-tab-pane
        v-for="sheet in errorSheets"
        :key="sheet.sheet_name"
        :name="sheet.sheet_name"
      >
        <template #label>
          <span :style="{ color: sheetHasError(currentFile.filename, sheet.sheet_name) ? '#f56c6c' : '#303133', fontWeight: sheetHasError(currentFile.filename, sheet.sheet_name) ? 'bold' : 'normal' }">{{ sheet.sheet_name }}</span>
        </template>
        <el-table :data="displayRows(sheet, currentFile.filename)" border stripe max-height="520" row-key="uid" size="small">
          <el-table-column label="序号" width="60" align="center">
            <template #default="{ row }">
              {{ row.original?.seq || row.row_idx }}
            </template>
          </el-table-column>

          <el-table-column label="主要任务" min-width="160">
            <template #default="{ row }">
              <span style="font-size:13px">{{ row.original?.main_task || '-' }}</span>
            </template>
          </el-table-column>

          <el-table-column label="字段" width="100">
            <template #default="{ row }">
              <el-tag :type="statusType(row)" size="small">
                {{ FIELD_LABELS[row.error.field] || row.error.field }}
              </el-tag>
            </template>
          </el-table-column>

          <el-table-column label="原始值" min-width="130">
            <template #default="{ row }">
              <span :style="{ textDecoration: isValidated(row) ? 'line-through' : 'none', color: isValidated(row) ? '#909399' : '#f56c6c' }">{{ getOriginalValue(row) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="修正值" min-width="220">
            <template #default="{ row }">
              <el-input
                v-model="fixes[fKey(row._filename, row._sheet, row.row_idx, row.error.field)]"
                size="small"
                :placeholder="row.error.suggestion || '输入修正值'"
                style="width:100%"
                :disabled="isValidating === fKey(row._filename, row._sheet, row.row_idx, row.error.field)"
                @change="onFixInput(row)"
              />
            </template>
          </el-table-column>

          <el-table-column label="校验结果" width="130">
            <template #default="{ row }">
              <span v-if="isValidated(row)" style="color:#67c23a;font-size:13px">
                ✓ {{ validationResults[fKey(row._filename, row._sheet, row.row_idx, row.error.field)]?.matched_name || '通过' }}
              </span>
              <span v-else-if="validationErrors[fKey(row._filename, row._sheet, row.row_idx, row.error.field)]" style="color:#f56c6c;font-size:13px">
                ✗ {{ validationErrors[fKey(row._filename, row._sheet, row.row_idx, row.error.field)] }}
              </span>
              <span v-else style="color:#909399;font-size:13px">待校验</span>
            </template>
          </el-table-column>

          <el-table-column label="问题说明" min-width="150">
            <template #default="{ row }">
              <span :style="{ color: isValidated(row) ? '#67c23a' : '#e6a23c', fontSize: '13px' }">{{ row.error.message }}</span>
            </template>
          </el-table-column>

          <el-table-column label="操作" width="220" align="center">
            <template #default="{ row }">
              <!-- State A: Unfixed, auto_fixable → show 更正 -->
              <el-button
                v-if="!isConfirmed(row) && !isValidated(row) && row.error.auto_fixable && row.error.suggestion"
                size="small" type="warning"
                @click="fixOne(row)"
              >更正</el-button>

              <!-- State B: Confirmed but not validated → show 撤销（undo confirmation） -->
              <el-button
                v-else-if="isConfirmed(row) && !isValidated(row)"
                size="small"
                @click="undoFixOne(row)"
              >撤销</el-button>

              <!-- State C: Validated → show 撤销（undo validation） -->
              <el-button
                v-else-if="isValidated(row)"
                size="small"
                @click="undoOne(row)"
              >撤销</el-button>

              <!-- 校验 button: visible when confirmed and not yet validated -->
              <el-button
                v-if="isConfirmed(row) && !isValidated(row)"
                size="small" type="primary"
                :loading="isValidating === fKey(row._filename, row._sheet, row.row_idx, row.error.field)"
                @click="validateOne(row)"
              >校验</el-button>

              <!-- 删除: always visible -->
              <el-button size="small" type="danger" plain @click="deleteRow(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <template #footer>
      <el-button @click="visible = false; $emit('close')">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as api from '../api/task'

const props = defineProps({
  modelValue: Boolean,
  previewData: { type: Object, required: true },
  planId: { type: Number, required: true },
})
const emit = defineEmits(['update:modelValue', 'close', 'import-complete', 'download-report'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const FIELD_LABELS = {
  unit: '被考核单位', dimension: '维度', assessor: '评价部门',
  key_work: '重点工作', main_task: '主要任务', scoring_note: '评分说明',
  period: '晾晒周期', seq: '序号', source: '指标来源', remark: '备注',
  file: '文件',
}

// ---- Tab state ----
const activeFile = ref('')
const activeTab = ref('')

// ---- Key helpers (MUST be before any computed/watcher that uses them) ----
function fKey(filename, sheet, rowIdx, field) {
  return `${filename}::${sheet}::${rowIdx}::${field}`
}
function dKey(filename, sheet, rowIdx) {
  return `${filename}::${sheet}::${rowIdx}`
}

// ---- State stores (MUST be before fileHasError/sheetHasError which reference them) ----
const fixes = reactive({})
const confirmed = reactive({})
const validated = reactive({})
const validationResults = reactive({})
const validationErrors = reactive({})
const deleted = reactive(new Set())
const isValidating = ref(null)
const isBatchValidating = ref(false)

// ---- File/sheet error indicators (MUST be before errorFiles/errorSheets computed) ----
function fileHasError(filename) {
  const f = props.previewData.files?.find(x => x.filename === filename)
  if (!f) return false
  return f.sheets.some(s => s.rows.some(r => r.errors.length > 0 && !deleted.has(dKey(filename, s.sheet_name, r.row_idx))))
}
function sheetHasError(filename, sheetName) {
  const f = props.previewData.files?.find(x => x.filename === filename)
  if (!f) return false
  const s = f.sheets.find(x => x.sheet_name === sheetName)
  if (!s) return false
  return s.rows.some(r => r.errors.length > 0 && !deleted.has(dKey(filename, sheetName, r.row_idx)))
}

// ---- Tab computed ----
const currentFile = computed(() =>
  props.previewData.files?.find(f => f.filename === activeFile.value)
)

// ---- Error-only filters ----
const errorFiles = computed(() =>
  props.previewData.files?.filter(f => fileHasError(f.filename)) || []
)

const errorSheets = computed(() => {
  if (!currentFile.value) return []
  return currentFile.value.sheets.filter(s =>
    sheetHasError(currentFile.value.filename, s.sheet_name)
  )
})

watch(() => props.previewData, (data) => {
  if (data?.files?.length) {
    const firstErrorFile = data.files.find(f =>
      f.sheets.some(s => s.rows.some(r => r.errors.length > 0))
    )
    if (firstErrorFile) {
      activeFile.value = firstErrorFile.filename
      const firstErrorSheet = firstErrorFile.sheets.find(s =>
        s.rows.some(r => r.errors.length > 0)
      )
      if (firstErrorSheet) {
        activeTab.value = firstErrorSheet.sheet_name
      }
    }
  }
}, { immediate: true })

// Auto-switch when current file no longer has errors
watch(errorFiles, (files) => {
  if (files.length > 0 && !files.find(f => f.filename === activeFile.value)) {
    activeFile.value = files[0].filename
  }
})

// Auto-switch when current sheet no longer has errors
watch(errorSheets, (sheets) => {
  if (sheets.length > 0 && !sheets.find(s => s.sheet_name === activeTab.value)) {
    activeTab.value = sheets[0].sheet_name
  }
})

// ---- Helpers ----
function getDisplayKey(row) {
  if (!row?.error) return null
  return fKey(row._filename, row._sheet, row.row_idx, row.error.field)
}

function isValidated(row) {
  const k = getDisplayKey(row)
  return k && validated[k]
}

function isConfirmed(row) {
  const k = getDisplayKey(row)
  return k && confirmed[k]
}

function statusType(row) {
  if (isValidated(row)) return 'success'
  if (isConfirmed(row)) return ''
  if (row.error.auto_fixable && row.error.suggestion) return 'warning'
  return 'danger'
}

function isDeleted(row) {
  return deleted.has(dKey(row._filename, row._sheet, row.row_idx))
}

function getOriginalValue(row) {
  if (!row?.original || !row?.error) return ''
  const v = row.original[row.error.field]
  return v || '(空)'
}

// ---- Display ----
function displayRows(sheet, filename) {
  const result = []
  for (const row of sheet.rows) {
    if (deleted.has(dKey(filename, sheet.sheet_name, row.row_idx))) continue
    if (row.errors.length === 0) continue
    for (const err of row.errors) {
      result.push({
        ...row,
        uid: `err-${filename}-${sheet.sheet_name}-${row.row_idx}-${err.field}`,
        error: err,
        _filename: filename,
        _sheet: sheet.sheet_name,
      })
    }
  }
  return result
}

// ---- Manual input handler ----
function onFixInput(row) {
  const k = getDisplayKey(row)
  if (!k) return
  delete validated[k]
  delete validationResults[k]
  delete validationErrors[k]
  if (!fixes[k] || !fixes[k].trim()) {
    delete confirmed[k]
  } else {
    confirmed[k] = true
  }
}

// ---- Validate one field ----
async function validateOne(row) {
  const k = fKey(row._filename, row._sheet, row.row_idx, row.error.field)
  const value = fixes[k] || ''
  if (!value.trim()) {
    validationErrors[k] = '请输入修正值'
    return
  }

  isValidating.value = k
  delete validationErrors[k]
  try {
    const res = await api.validateField(props.planId, row.error.field, value.trim())
    const result = res.data || res
    if (result.valid) {
      validated[k] = true
      delete validationErrors[k]
      const names = (result.matched || []).map(m => m.name).join('、')
      const ids = (result.matched || []).map(m => m.id)
      validationResults[k] = { matched_name: names, matched_ids: ids }
      fixes[k] = names
      ElMessage.success(`「${value.trim()}」→「${names}」校验通过`)
    } else {
      validated[k] = false
      validationErrors[k] = result.message || '校验未通过'
      if (result.unmatched && result.unmatched.length > 0) {
        const details = result.unmatched.map(u => {
          let d = u.error
          if (u.suggestion) d += `（建议：${u.suggestion}）`
          return d
        }).join('；')
        validationErrors[k] = details
      }
      ElMessage.warning(validationErrors[k])
    }
  } catch (e) {
    validated[k] = false
    validationErrors[k] = e.response?.data?.message || '校验请求失败'
  }
  isValidating.value = null
}

// ---- Single-row actions ----
function fixOne(row) {
  const k = fKey(row._filename, row._sheet, row.row_idx, row.error.field)
  if (row.error.auto_fixable && row.error.suggestion) {
    fixes[k] = row.error.suggestion
    confirmed[k] = true
    delete validated[k]
    delete validationResults[k]
    delete validationErrors[k]
  }
}

function undoFixOne(row) {
  const k = fKey(row._filename, row._sheet, row.row_idx, row.error.field)
  delete confirmed[k]
  delete validated[k]
  delete validationResults[k]
  delete validationErrors[k]
  if (row.error.suggestion && fixes[k] === row.error.suggestion) {
    delete fixes[k]
  }
}

// ---- Batch actions ----
function autoFixAll() {
  for (const file of props.previewData.files) {
    for (const sheet of file.sheets) {
      for (const row of sheet.rows) {
        if (deleted.has(dKey(file.filename, sheet.sheet_name, row.row_idx))) continue
        for (const err of row.errors) {
          const k = fKey(file.filename, sheet.sheet_name, row.row_idx, err.field)
          if (err.auto_fixable && err.suggestion && !confirmed[k]) {
            fixes[k] = err.suggestion
            confirmed[k] = true
          }
        }
      }
    }
  }
  ElMessage.success('已填入全部建议值并确认，请点击"一键校验"通过后端校验')
}

function undoFixAll() {
  for (const file of props.previewData.files) {
    for (const sheet of file.sheets) {
      for (const row of sheet.rows) {
        if (deleted.has(dKey(file.filename, sheet.sheet_name, row.row_idx))) continue
        for (const err of row.errors) {
          const k = fKey(file.filename, sheet.sheet_name, row.row_idx, err.field)
          if (confirmed[k]) {
            delete confirmed[k]
            delete validated[k]
            delete validationResults[k]
            delete validationErrors[k]
            if (fixes[k] === err.suggestion) {
              delete fixes[k]
            }
          }
        }
      }
    }
  }
  ElMessage.success('已撤销全部更正（手动编辑的值保留但需重新确认）')
}

async function validateAll() {
  const keysToValidate = []
  for (const file of props.previewData.files) {
    for (const sheet of file.sheets) {
      for (const row of sheet.rows) {
        if (deleted.has(dKey(file.filename, sheet.sheet_name, row.row_idx))) continue
        for (const err of row.errors) {
          const k = fKey(file.filename, sheet.sheet_name, row.row_idx, err.field)
          if (confirmed[k] && !validated[k] && !validationErrors[k]) {
            const value = fixes[k] || ''
            if (value.trim()) {
              keysToValidate.push({
                key: k,
                field: err.field,
                value: value.trim(),
                row: { _filename: file.filename, _sheet: sheet.sheet_name, row_idx: row.row_idx, error: err }
              })
            }
          }
        }
      }
    }
  }

  if (keysToValidate.length === 0) {
    ElMessage.info('没有需要校验的项')
    return
  }

  isBatchValidating.value = true
  let successCount = 0
  let failCount = 0

  for (const item of keysToValidate) {
    const { key, field, value } = item
    isValidating.value = key
    delete validationErrors[key]

    try {
      const res = await api.validateField(props.planId, field, value)
      const result = res.data || res
      if (result.valid) {
        validated[key] = true
        delete validationErrors[key]
        const names = (result.matched || []).map(m => m.name).join('、')
        const ids = (result.matched || []).map(m => m.id)
        validationResults[key] = { matched_name: names, matched_ids: ids }
        fixes[key] = names
        successCount++
      } else {
        validated[key] = false
        if (result.unmatched && result.unmatched.length > 0) {
          const details = result.unmatched.map(u => {
            let d = u.error
            if (u.suggestion) d += `（建议：${u.suggestion}）`
            return d
          }).join('；')
          validationErrors[key] = details
        } else {
          validationErrors[key] = result.message || '校验未通过'
        }
        failCount++
      }
    } catch (e) {
      validated[key] = false
      validationErrors[key] = e.response?.data?.message || '校验请求失败'
      failCount++
    }

    isValidating.value = null
  }

  isBatchValidating.value = false
  if (failCount === 0) {
    ElMessage.success(`一键校验完成：${successCount} 项全部通过 ✓`)
  } else {
    ElMessage.warning(`一键校验完成：${successCount} 项通过，${failCount} 项未通过，请手动修正`)
  }
}

function undoOne(row) {
  const k = fKey(row._filename, row._sheet, row.row_idx, row.error.field)
  delete validated[k]
  delete validationResults[k]
  delete validationErrors[k]
  delete confirmed[k]
  if (row.error.suggestion) {
    fixes[k] = row.error.suggestion
  } else {
    delete fixes[k]
  }
}

function undoAll() {
  for (const k of Object.keys(validated)) delete validated[k]
  for (const k of Object.keys(validationResults)) delete validationResults[k]
  for (const k of Object.keys(validationErrors)) delete validationErrors[k]
  for (const k of Object.keys(confirmed)) delete confirmed[k]
  for (const k of Object.keys(fixes)) delete fixes[k]
  deleted.clear()
  ElMessage.success('已撤销全部修正和删除')
}

function deleteRow(row) {
  deleted.add(dKey(row._filename, row._sheet, row.row_idx))
  for (const store of [fixes, validated, validationResults, validationErrors, confirmed]) {
    for (const k of Object.keys(store)) {
      if (k.startsWith(`${row._filename}::${row._sheet}::${row.row_idx}::`)) delete store[k]
    }
  }
}

// ---- Computed stats ----
const totalRowsCount = computed(() => {
  let c = 0
  for (const f of props.previewData.files)
    for (const s of f.sheets)
      for (const r of s.rows)
        if (!deleted.has(dKey(f.filename, s.sheet_name, r.row_idx)))
          c++
  return c
})

const errorCount = computed(() => {
  let c = 0
  for (const f of props.previewData.files)
    for (const s of f.sheets)
      for (const r of s.rows) {
        if (deleted.has(dKey(f.filename, s.sheet_name, r.row_idx))) continue
        c += r.errors.length
      }
  return c
})

const autoFixableAndUnconfirmedCount = computed(() => {
  let c = 0
  for (const f of props.previewData.files)
    for (const s of f.sheets)
      for (const r of s.rows) {
        if (deleted.has(dKey(f.filename, s.sheet_name, r.row_idx))) continue
        for (const e of r.errors) {
          const k = fKey(f.filename, s.sheet_name, r.row_idx, e.field)
          if (e.auto_fixable && e.suggestion && !confirmed[k]) c++
        }
      }
  return c
})

const confirmedCount = computed(() => {
  let c = 0
  for (const f of props.previewData.files)
    for (const s of f.sheets)
      for (const r of s.rows) {
        if (deleted.has(dKey(f.filename, s.sheet_name, r.row_idx))) continue
        for (const e of r.errors) {
          const k = fKey(f.filename, s.sheet_name, r.row_idx, e.field)
          if (confirmed[k]) c++
        }
      }
  return c
})

const confirmedAndUnvalidatedCount = computed(() => {
  let c = 0
  for (const f of props.previewData.files)
    for (const s of f.sheets)
      for (const r of s.rows) {
        if (deleted.has(dKey(f.filename, s.sheet_name, r.row_idx))) continue
        for (const e of r.errors) {
          const k = fKey(f.filename, s.sheet_name, r.row_idx, e.field)
          if (confirmed[k] && !validated[k] && !validationErrors[k]) c++
        }
      }
  return c
})

const validCount = computed(() => {
  let c = 0
  for (const f of props.previewData.files)
    for (const s of f.sheets)
      for (const r of s.rows) {
        if (deleted.has(dKey(f.filename, s.sheet_name, r.row_idx))) continue
        for (const e of r.errors) {
          const k = fKey(f.filename, s.sheet_name, r.row_idx, e.field)
          if (validated[k]) c++
        }
      }
  return c
})

const unvalidatedCount = computed(() => {
  let c = 0
  for (const f of props.previewData.files)
    for (const s of f.sheets)
      for (const r of s.rows) {
        if (deleted.has(dKey(f.filename, s.sheet_name, r.row_idx))) continue
        for (const e of r.errors) {
          const k = fKey(f.filename, s.sheet_name, r.row_idx, e.field)
          if (!validated[k]) c++
        }
      }
  return c
})

const failedCount = computed(() => {
  let c = 0
  for (const f of props.previewData.files)
    for (const s of f.sheets)
      for (const r of s.rows) {
        if (deleted.has(dKey(f.filename, s.sheet_name, r.row_idx))) continue
        for (const e of r.errors) {
          const k = fKey(f.filename, s.sheet_name, r.row_idx, e.field)
          if (validationErrors[k]) c++
        }
      }
  return c
})

const fixedCount = computed(() => {
  let c = 0
  for (const f of props.previewData.files)
    for (const s of f.sheets)
      for (const r of s.rows) {
        if (deleted.has(dKey(f.filename, s.sheet_name, r.row_idx))) continue
        for (const e of r.errors) {
          const k = fKey(f.filename, s.sheet_name, r.row_idx, e.field)
          if (validated[k] || confirmed[k]) c++
        }
      }
  return c
})

const canImport = computed(() => {
  return unvalidatedCount.value === 0 && failedCount.value === 0 && totalRowsCount.value > 0
})

// ---- Confirm import ----
async function confirmImport() {
  if (!canImport.value) {
    ElMessage.warning('还有未通过校验的问题，请校验所有修正值后再导入')
    return
  }

  const taskList = []
  for (const f of props.previewData.files) {
    for (const s of f.sheets) {
      for (const r of s.rows) {
        if (deleted.has(dKey(f.filename, s.sheet_name, r.row_idx))) continue

        const data = { ...r.original }
        for (const e of r.errors) {
          const k = fKey(f.filename, s.sheet_name, r.row_idx, e.field)
          if (validated[k] && fixes[k]) {
            data[e.field] = fixes[k]
          }
        }

        const task = {
          dimension_name: data.dimension || '',
          unit_name: data.unit || '',
          assessor_name: data.assessor || '',
          key_work: data.key_work || '',
          main_task: data.main_task || '',
          scoring_note: data.scoring_note || '',
          review_period: data.period || '月度',
        }

        for (const e of r.errors) {
          const k = fKey(f.filename, s.sheet_name, r.row_idx, e.field)
          if (validated[k] && validationResults[k]?.matched_ids?.length === 1) {
            if (e.field === 'dimension') task.assessment_dimension_id = validationResults[k].matched_ids[0]
            if (e.field === 'assessor') task.assessor_unit_id = validationResults[k].matched_ids[0]
            if (e.field === 'unit') task.unit_id = validationResults[k].matched_ids[0]
          }
        }

        taskList.push(task)
      }
    }
  }

  if (taskList.length === 0) {
    ElMessage.warning('没有可导入的任务')
    return
  }

  try {
    const result = await api.importConfirm(props.planId, taskList)
    ElMessage.success(result.msg || `成功导入 ${taskList.length} 个任务`)
    visible.value = false
    emit('import-complete', result)
  } catch (e) {
    const errData = e.response?.data
    if (errData?.errors && errData.errors.length > 0) {
      ElMessageBox.alert(
        `${errData.msg}\n\n${errData.errors.slice(0, 10).map(e => `第${e.index + 1}条: ${e.errors.map(er => er.msg).join('；')}`).join('\n')}${errData.errors.length > 10 ? `\n... 共 ${errData.errors.length} 个错误` : ''}`,
        '导入失败',
        { confirmButtonText: '知道了', type: 'error' }
      )
    } else {
      ElMessage.error(errData?.msg || '导入失败，请重试')
    }
  }
}
</script>
