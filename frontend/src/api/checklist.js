import http from './index'

export function getChecklists(params) {
  return http.get('/checklists', { params })
}

export function createChecklist(data) {
  return http.post('/checklists', data)
}

export function updateChecklist(id, data) {
  return http.put(`/checklists/${id}`, data)
}

export function deleteChecklist(id) {
  return http.delete(`/checklists/${id}`)
}

export function batchDeleteChecklists(ids) {
  return http.post('/checklists/batch-delete', { ids })
}

export function importChecklists(file) {
  const fd = new FormData()
  fd.append('file', file)
  return http.post('/checklists/import', fd)
}

export function exportChecklists() {
  return http.get('/checklists/export', { responseType: 'blob' })
}

export function downloadChecklistTemplate() {
  return http.get('/checklists/template', { responseType: 'blob' })
}
