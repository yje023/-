import http from './index'

export function getRoles(search) {
  return http.get('/roles', { params: { search } })
}
export function createRole(data) {
  return http.post('/roles', data)
}
export function updateRole(id, data) {
  return http.put(`/roles/${id}`, data)
}
export function deleteRole(id) {
  return http.delete(`/roles/${id}`)
}
export function getMenus() {
  return http.get('/roles/menus')
}
