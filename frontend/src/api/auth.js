import http from './index'

export function loginApi(username, password) {
  return http.post('/auth/login', { username, password })
}

export function getUserInfoApi() {
  return http.get('/auth/me')
}

export function changePasswordApi(oldPwd, newPwd) {
  return http.put('/auth/password', { old_password: oldPwd, new_password: newPwd })
}

export function switchIdentityApi() {
  return http.put('/auth/identity')
}
