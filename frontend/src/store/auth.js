import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { loginApi, getUserInfoApi, switchIdentityApi } from '../api/auth'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const userInfo = ref(null)

  const isLoggedIn = computed(() => !!token.value)
  const mustChangePassword = computed(() => userInfo.value?.must_change_password === true)
  const currentIdentity = computed(() => userInfo.value?.current_identity || 'assessed')

  function hasPerm(permCode) {
    if (!userInfo.value) return false
    // admin 角色拥有所有权限
    if (userInfo.value.role?.is_system) return true
    const perms = userInfo.value.role?.permissions || []
    return perms.some(p => p.can_access && p.menu_code === permCode)
  }

  function hasAnyPerm(...permCodes) {
    return permCodes.some(code => hasPerm(code))
  }

  async function login(username, password) {
    const res = await loginApi(username, password)
    token.value = res.access_token
    localStorage.setItem('token', token.value)
    await fetchUserInfo()
  }

  async function fetchUserInfo() {
    const res = await getUserInfoApi()
    userInfo.value = res
  }

  async function switchIdentity() {
    const res = await switchIdentityApi()
    userInfo.value = res
  }

  function logout() {
    token.value = ''
    userInfo.value = null
    localStorage.removeItem('token')
  }

  return { token, userInfo, isLoggedIn, mustChangePassword, currentIdentity, hasPerm, hasAnyPerm, login, fetchUserInfo, switchIdentity, logout }
})
