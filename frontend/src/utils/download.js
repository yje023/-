/**
 * 统一文件下载 — 将 blob 保存为文件
 * @param {Blob|object} data - Blob 数据或 Axios blob 响应对象
 * @param {string} filename - 下载文件名
 */
export function downloadBlob(data, filename) {
  // 兼容 Axios blob 响应（res.data 是 blob）
  const blob = data instanceof Blob ? data : data?.data
  if (!blob) return
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
