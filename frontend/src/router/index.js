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
      { path: 'checklists', name: 'Checklists', component: () => import('../views/Checklists.vue'), meta: { title: '清单管理' } },
      { path: 'cadres', name: 'Cadres', component: () => import('../views/Cadres.vue'), meta: { title: '干部管理' } },
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
  // 桌面版：跳过登录，直接进入系统
  if (to.path === '/login') {
    next('/dashboard')
  } else {
    next()
  }
})

export default router
