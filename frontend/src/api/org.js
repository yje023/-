import http from './index'

export function getOrgs(search) {
  return http.get('/orgs', { params: { search } })
}
export function createOrg(data) {
  return http.post('/orgs', data)
}
export function updateOrg(id, data) {
  return http.put(`/orgs/${id}`, data)
}
export function deleteOrg(id) {
  return http.delete(`/orgs/${id}`)
}
export function batchDeleteOrgs(ids) {
  return http.post('/orgs/batch-delete', { ids })
}
export function importOrgs(file) {
  const fd = new FormData()
  fd.append('file', file)
  return http.post('/orgs/import', fd)
}
export function downloadTemplate() {
  return http.get('/orgs/template', { responseType: 'blob' })
}
export function exportOrgs() {
  return http.get('/orgs/export', { responseType: 'blob' })
}
