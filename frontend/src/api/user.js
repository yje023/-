import http from './index'

export function getUsers(params) {
  return http.get('/users', { params })
}
export function createUser(data) {
  return http.post('/users', data)
}
export function updateUser(id, data) {
  return http.put(`/users/${id}`, data)
}
export function deleteUser(id) {
  return http.delete(`/users/${id}`)
}
export function batchDeleteUsers(ids) {
  return http.post('/users/batch-delete', { ids })
}
