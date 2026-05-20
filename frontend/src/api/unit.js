import http from './index'

export function getUnits(params) {
  return http.get('/units', { params })
}
export function createUnit(data) {
  return http.post('/units', data)
}
export function updateUnit(id, data) {
  return http.put(`/units/${id}`, data)
}
export function deleteUnit(id) {
  return http.delete(`/units/${id}`)
}
export function moveUnit(id, orgId) {
  return http.put(`/units/${id}/move`, { org_id: orgId })
}
export function batchDeleteUnits(ids) {
  return http.post('/units/batch-delete', { ids })
}
export function importUnits(file) {
  const fd = new FormData()
  fd.append('file', file)
  return http.post('/units/import', fd)
}
export function downloadUnitTemplate() {
  return http.get('/units/template', { responseType: 'blob' })
}
export function exportUnits() {
  return http.get('/units/export', { responseType: 'blob' })
}
