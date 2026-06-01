import http from './index'

export function getCadres(params) {
  return http.get('/cadres', { params })
}

export function createCadre(data) {
  return http.post('/cadres', data)
}

export function updateCadre(id, data) {
  return http.put(`/cadres/${id}`, data)
}

export function deleteCadre(id) {
  return http.delete(`/cadres/${id}`)
}

export function batchDeleteCadres(ids) {
  return http.post('/cadres/batch-delete', { ids })
}

export function importCadres(file) {
  const formData = new FormData()
  formData.append('file', file)
  return http.post('/cadres/import', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
}

export function exportCadres(params = {}) {
  return http.get('/cadres/export', { params, responseType: 'blob' })
}

export function downloadCadreTemplate() {
  return http.get('/cadres/template', { responseType: 'blob' })
}
