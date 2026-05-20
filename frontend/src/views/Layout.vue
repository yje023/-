<template>
  <el-container style="height:100vh">
    <el-aside width="220px" class="sidebar">
      <div class="logo">精准考核系统</div>
      <el-menu
        :default-active="activeMenu"
        background-color="#304156"
        text-color="#bfcbd9"
        active-text-color="#409eff"
        router
      >
        <el-menu-item index="/dashboard">
          <el-icon><HomeFilled /></el-icon>
          <span>首页</span>
        </el-menu-item>

        <el-sub-menu index="admin">
          <template #title>
            <el-icon><Setting /></el-icon>
            <span>系统后台管理</span>
          </template>
          <el-menu-item index="/orgs">
            <el-icon><Share /></el-icon>
            <span>机构管理</span>
          </el-menu-item>
          <el-menu-item index="/units">
            <el-icon><OfficeBuilding /></el-icon>
            <span>单位管理</span>
          </el-menu-item>
          <el-menu-item index="/users">
            <el-icon><User /></el-icon>
            <span>用户管理</span>
          </el-menu-item>
          <el-menu-item index="/roles">
            <el-icon><Avatar /></el-icon>
            <span>角色管理</span>
          </el-menu-item>
        </el-sub-menu>

        <el-sub-menu index="production">
          <template #title>
            <el-icon><Document /></el-icon>
            <span>生产端数据管理</span>
          </template>
          <el-menu-item index="/plans">
            <el-icon><Notebook /></el-icon>
            <span>考核方案</span>
          </el-menu-item>
          <el-menu-item index="/tasks">
            <el-icon><List /></el-icon>
            <span>考核任务</span>
          </el-menu-item>
        </el-sub-menu>
      </el-menu>

      <div class="version-info" @click="showVersionHistory">
        <span>{{ versionCurrent }}</span>
      </div>
    </el-aside>
    <el-container>
      <el-header class="top-header">
        <div class="header-left">
          <el-tag
            :type="auth.currentIdentity === 'assessor' ? 'primary' : 'success'"
            effect="dark"
            style="cursor:pointer;margin-right:12px"
            @click="handleSwitchIdentity"
          >
            {{ auth.currentIdentity === 'assessor' ? '当前身份：主考单位' : '当前身份：被考核单位' }}
            <el-icon style="margin-left:4px"><Switch /></el-icon>
          </el-tag>
        </div>
        <div class="header-right">
          <span style="margin-right:8px;color:#606266">{{ auth.userInfo?.username }}</span>
          <span style="margin-right:12px;color:#909399">| {{ auth.userInfo?.role_name || '无角色' }}</span>
          <el-dropdown @command="handleCommand">
            <span style="cursor:pointer;color:#409eff">
              <el-icon><Tools /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="password">修改密码</el-dropdown-item>
                <el-dropdown-item command="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      <el-main class="main-container">
        <router-view />
      </el-main>
    </el-container>
  </el-container>

  <!-- 版本历史 -->
  <el-dialog v-model="versionDialogVisible" title="版本历史" width="600px">
    <el-timeline>
      <el-timeline-item
        v-for="v in versionHistory"
        :key="v.version"
        :timestamp="v.date"
        placement="top"
      >
        <el-card shadow="hover">
          <h4>{{ v.label }}</h4>
          <p style="color:#909399;margin:0">{{ v.message }}</p>
        </el-card>
      </el-timeline-item>
    </el-timeline>
    <template #footer>
      <el-button @click="versionDialogVisible = false">关闭</el-button>
    </template>
  </el-dialog>

  <!-- 修改密码 -->
  <el-dialog v-model="pwdDialogVisible" title="修改密码" width="400px">
    <el-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules">
      <el-form-item prop="old_password">
        <el-input v-model="pwdForm.old_password" type="password" placeholder="旧密码" show-password />
      </el-form-item>
      <el-form-item prop="new_password">
        <el-input v-model="pwdForm.new_password" type="password" placeholder="新密码（至少6位）" show-password />
      </el-form-item>
      <el-form-item prop="confirm_password">
        <el-input v-model="pwdForm.confirm_password" type="password" placeholder="确认新密码" show-password />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="pwdDialogVisible = false">取消</el-button>
      <el-button type="primary" @click="handleChangePassword">确认修改</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, reactive, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../store/auth'
import { changePasswordApi } from '../api/auth'
import { ElMessage } from 'element-plus'
import http from '../api/index'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const activeMenu = computed(() => route.path)

// 版本信息
const versionCurrent = ref('')
const versionHistory = ref([])
const versionDialogVisible = ref(false)

async function fetchVersion() {
  try {
    const res = await http.get('/version')
    versionCurrent.value = res.data?.current || ''
    versionHistory.value = res.data?.history || []
  } catch {}
}

function showVersionHistory() {
  versionDialogVisible.value = true
}

onMounted(async () => {
  fetchVersion()
  if (!auth.userInfo) {
    try { await auth.fetchUserInfo() } catch {}
  }
  if (auth.mustChangePassword) {
    pwdForm.old_password = ''
    pwdForm.new_password = ''
    pwdForm.confirm_password = ''
    pwdDialogVisible.value = true
  }
})

// 修改密码
const pwdDialogVisible = ref(false)
const pwdFormRef = ref()
const pwdForm = reactive({ old_password: '', new_password: '', confirm_password: '' })
const pwdRules = {
  old_password: [{ required: true, message: '请输入旧密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '密码至少6位', trigger: 'blur' },
  ],
  confirm_password: [
    { required: true, message: '请确认新密码', trigger: 'blur' },
    { validator: (_, value, cb) => value === pwdForm.new_password ? cb() : cb(new Error('两次密码不一致')), trigger: 'blur' },
  ],
}

function handleCommand(cmd) {
  if (cmd === 'logout') {
    auth.logout()
    router.push('/login')
  } else if (cmd === 'password') {
    pwdForm.old_password = ''
    pwdForm.new_password = ''
    pwdForm.confirm_password = ''
    pwdDialogVisible.value = true
  }
}

async function handleChangePassword() {
  const valid = await pwdFormRef.value.validate().catch(() => false)
  if (!valid) return
  try {
    await changePasswordApi(pwdForm.old_password, pwdForm.new_password)
    pwdDialogVisible.value = false
    auth.userInfo.must_change_password = false
    ElMessage.success('密码修改成功')
  } catch { /* handled */ }
}

async function handleSwitchIdentity() {
  try {
    await auth.switchIdentity()
    ElMessage.success('身份切换成功')
  } catch { /* handled */ }
}
</script>

<style scoped>
.sidebar {
  position: relative;
}
.logo {
  height: 60px;
  line-height: 60px;
  text-align: center;
  color: #fff;
  font-size: 17px;
  font-weight: bold;
  background: #263445;
  overflow: hidden;
  white-space: nowrap;
}
.top-header {
  height: 60px;
  background: #fff;
  border-bottom: 1px solid #e6e6e6;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
}
.header-left, .header-right {
  display: flex;
  align-items: center;
}
.version-info {
  position: absolute;
  bottom: 0;
  left: 0;
  width: 100%;
  padding: 10px 16px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.45);
  background: #263445;
  cursor: pointer;
  text-align: center;
  box-sizing: border-box;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}
.version-info:hover {
  color: rgba(255, 255, 255, 0.75);
}
</style>
