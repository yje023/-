import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../store/auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { noAuth: true },
  },
  {
    path: '/change-password',
    name: 'ChangePassword',
    component: () => import('../views/ChangePassword.vue'),
    meta: { noAuth: true },
  },
  {
    path: '/',
    component: () => import('../views/Layout.vue'),
    redirect: '/dashboard',
    children: [
      { path: 'dashboard', name: 'Dashboard', component: () => import('../views/Dashboard.vue'), meta: { title: '首页' } },
      // 系统后台管理
      { path: 'orgs', name: 'Orgs', component: () => import('../views/Orgs.vue'), meta: { title: '机构管理' } },
      { path: 'units', name: 'Units', component: () => import('../views/Units.vue'), meta: { title: '单位管理' } },
      { path: 'users', name: 'Users', component: () => import('../views/Users.vue'), meta: { title: '用户管理' } },
      { path: 'roles', name: 'Roles', component: () => import('../views/Roles.vue'), meta: { title: '角色管理' } },
      // 生产端数据管理
      { path: 'plans', name: 'Plans', component: () => import('../views/Plans.vue'), meta: { title: '考核方案' } },
      { path: 'tasks', name: 'Tasks', component: () => import('../views/Tasks.vue'), meta: { title: '考核任务' } },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const auth = useAuthStore()
  if (to.meta.noAuth) {
    next()
  } else if (!auth.token) {
    next('/login')
  } else if (auth.mustChangePassword && to.path !== '/dashboard') {
    // 首次登录必须修改密码，但允许访问首页（首页会弹窗提示）
    next()
  } else {
    next()
  }
})

export default router
