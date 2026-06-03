import http from './index'

// ============ 常规质检 API ============

/** 运行质检 */
export function runQualityCheck(planId) {
  return http.post('/quality-check/run', { plan_id: planId }, { timeout: 120000 })
}

/** 获取质检问题列表 */
export function getQualityIssues(params) {
  return http.get('/quality-check/issues', { params })
}

/** 获取代理指标（兼容旧接口，从新表读取） */
export function getProxyIssues(planId) {
  return http.get('/quality-check/proxy-issues', { params: { plan_id: planId } })
}

/** 获取质检筛选选项 */
export function getQualityFilterOptions(planId) {
  return http.get('/quality-check/filter-options', { params: { plan_id: planId } })
}

/** 更新单个问题 */
export function updateQualityIssue(id, data) {
  return http.put(`/quality-check/issues/${id}`, data)
}

/** 批量更新问题状态 */
export function batchUpdateIssueStatus(ids, status) {
  return http.post('/quality-check/issues/batch-status', { ids, status })
}

/** 批量更正任务 */
export function batchCorrectTask(taskId, updates) {
  return http.post('/quality-check/batch-correct', { task_id: taskId, updates })
}

/** 单条更正任务 */
export function correctSingleTask(taskId, updates) {
  return http.post('/quality-check/correct-single', { task_id: taskId, updates })
}

/** 批量确认无误（常规质检） */
export function batchConfirmIssues(taskId) {
  return http.post('/quality-check/batch-confirm', { task_id: taskId })
}

/** 确认代理指标为误报（兼容旧接口） */
export function confirmProxyMetric(planId, taskIdA, taskIdB) {
  return http.post('/quality-check/proxy-metrics/confirm', {
    plan_id: planId, task_id_a: taskIdA, task_id_b: taskIdB,
  })
}

/** 获取已管理的问题列表 */
export function getManagedIssues(params) {
  return http.get('/quality-check/issues/managed', { params })
}

/** 获取分组问题列表（管理弹窗用） */
export function getGroupedIssues(planId) {
  return http.get('/quality-check/issues/grouped', { params: { plan_id: planId } })
}

/** 导出质检问题 */
export function exportQualityIssues(params) {
  return http.get('/quality-check/export', { params, responseType: 'blob' })
}

// ============ 代理指标 API（新） ============

/** 获取代理指标对列表 */
export function getProxyMetricPairs(params) {
  return http.get('/proxy-metrics/pairs', { params })
}

/** 获取单个代理指标对详情 */
export function getProxyMetricPair(id) {
  return http.get(`/proxy-metrics/pairs/${id}`)
}

/** 更新代理指标对 */
export function updateProxyMetricPair(id, data) {
  return http.put(`/proxy-metrics/pairs/${id}`, data)
}

/** 批量确认代理指标对 */
export function batchConfirmProxyPairs(ids) {
  return http.post('/proxy-metrics/pairs/batch-confirm', { ids })
}

/** 批量标记代理指标对为已修正 */
export function batchResolveProxyPairs(ids) {
  return http.post('/proxy-metrics/pairs/batch-resolve', { ids })
}

/** 更新代理指标对备注 */
export function updateProxyPairRemark(id, remark) {
  return http.put(`/proxy-metrics/pairs/${id}/remark`, { remark })
}

/** 获取代理指标筛选选项 */
export function getProxyMetricFilterOptions(planId) {
  return http.get('/proxy-metrics/filter-options', { params: { plan_id: planId } })
}

/** 导出代理指标清单 */
export function exportProxyMetrics(params) {
  return http.get('/proxy-metrics/export', { params, responseType: 'blob' })
}
