<template>
  <div class="login-container">
    <div class="login-card">
      <h2 class="login-title">修改初始密码</h2>
      <p style="text-align:center;color:#909399;margin-bottom:20px">为了账号安全，首次登录请修改密码</p>
      <el-form ref="formRef" :model="form" :rules="rules" size="large">
        <el-form-item prop="old_password">
          <el-input v-model="form.old_password" type="password" placeholder="旧密码" show-password prefix-icon="Lock" />
        </el-form-item>
        <el-form-item prop="new_password">
          <el-input v-model="form.new_password" type="password" placeholder="新密码（至少6位）" show-password prefix-icon="Key" />
        </el-form-item>
        <el-form-item prop="confirm_password">
          <el-input v-model="form.confirm_password" type="password" placeholder="确认新密码" show-password prefix-icon="Key" @keyup.enter="handleSubmit" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" style="width:100%" @click="handleSubmit">确认修改并登录</el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../store/auth'
import { changePasswordApi } from '../api/auth'
import { ElMessage } from 'element-plus'

const router = useRouter()
const auth = useAuthStore()
const formRef = ref()
const loading = ref(false)

const form = reactive({ old_password: '', new_password: '', confirm_password: '' })
const rules = {
  old_password: [{ required: true, message: '请输入旧密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '密码至少6位', trigger: 'blur' },
  ],
  confirm_password: [
    { required: true, message: '请确认新密码', trigger: 'blur' },
    { validator: (_, value, cb) => value === form.new_password ? cb() : cb(new Error('两次密码不一致')), trigger: 'blur' },
  ],
}

async function handleSubmit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    await changePasswordApi(form.old_password, form.new_password)
    auth.userInfo.must_change_password = false
    ElMessage.success('密码修改成功')
    router.push('/')
  } catch {
    // 错误已在拦截器中处理
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #409eff 0%, #66b1ff 50%, #a0cfff 100%);
}
.login-card {
  width: 420px;
  padding: 40px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.15);
}
.login-title {
  text-align: center;
  margin-bottom: 8px;
  color: #409eff;
  font-size: 22px;
}
</style>
