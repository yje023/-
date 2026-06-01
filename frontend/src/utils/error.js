import { ElMessage } from 'element-plus'

/**
 * 统一错误处理 — 替换所有视图中的空 catch 块
 * @param {Error|object} err - 错误对象
 * @param {string} context - 操作描述（如 "加载方案"、"保存任务"）
 */
export function handleError(err, context = '操作') {
  const msg = err?.response?.data?.msg || err?.message || `${context}失败`
  ElMessage.error(msg)
  console.error(`[${context}]`, err)
}

/**
 * 静默错误处理 — 非关键操作失败时仅日志，不弹窗
 * @param {Error|object} err - 错误对象
 * @param {string} context - 操作描述
 */
export function logError(err, context = '操作') {
  console.warn(`[${context}]`, err?.response?.data?.msg || err?.message || err)
}
