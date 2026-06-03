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

// 芯片排序偏好
export function getChipSortOrder(page) {
  return http.get('/user/chip-sort-order', { params: { page } })
}
export function saveChipSortOrder(page, dimensionKey, sortOrder) {
  return http.put('/user/chip-sort-order', { page, dimension_key: dimensionKey, sort_order: sortOrder })
}
