<template>
  <el-container style="height: 100vh">
    <!-- 侧边栏 -->
    <el-aside width="220px" style="background: #304156; color: #fff">
      <div class="logo">NoteVault</div>
      <el-menu
        :default-active="route.path"
        router
        background-color="#304156"
        text-color="#bfcbd9"
        active-text-color="#409eff"
      >
        <el-menu-item index="/notes">
          <el-icon><Document /></el-icon>
          <span>我的笔记</span>
        </el-menu-item>
        <el-menu-item index="/recycle-bin">
          <el-icon><Delete /></el-icon>
          <span>回收站</span>
        </el-menu-item>
        <el-menu-item index="/stats">
          <el-icon><DataAnalysis /></el-icon>
          <span>数据统计</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <!-- 主内容区 -->
    <el-container>
      <el-header style="background: #fff; border-bottom: 1px solid #eee; display: flex; align-items: center; justify-content: space-between; padding: 0 20px">
        <span style="font-size: 18px; font-weight: bold; color: #333">NoteVault</span>
        <div style="display: flex; align-items: center; gap: 10px">
          <el-button type="primary" text @click="showPasswordDialog = true">修改密码</el-button>
          <el-button type="danger" text @click="handleLogout">退出登录</el-button>
        </div>
      </el-header>
      <el-main style="padding: 20px; background: #f5f7fa">
        <router-view />
      </el-main>
    </el-container>

    <!-- 修改密码对话框 -->
    <el-dialog v-model="showPasswordDialog" title="修改密码" width="400px">
      <el-form :model="passwordForm" label-width="80px">
        <el-form-item label="旧密码">
          <el-input v-model="passwordForm.old_password" type="password" placeholder="请输入旧密码" show-password />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="passwordForm.new_password" type="password" placeholder="至少8位" show-password />
        </el-form-item>
        <el-form-item label="确认密码">
          <el-input v-model="passwordForm.confirm_password" type="password" placeholder="再次输入新密码" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showPasswordDialog = false">取消</el-button>
        <el-button type="primary" @click="handleChangePassword">确认修改</el-button>
      </template>
    </el-dialog>
  </el-container>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Document, Delete, DataAnalysis } from '@element-plus/icons-vue'
import { logout, changePassword } from '../api'

const router = useRouter()
const route = useRoute()

const showPasswordDialog = ref(false)
const passwordForm = ref({
  old_password: '',
  new_password: '',
  confirm_password: '',
})

const handleChangePassword = async () => {
  const { old_password, new_password, confirm_password } = passwordForm.value
  if (!old_password || !new_password || !confirm_password) {
    ElMessage.error('请填写所有字段')
    return
  }
  if (new_password.length < 8) {
    ElMessage.error('新密码长度不能少于8位')
    return
  }
  if (new_password !== confirm_password) {
    ElMessage.error('两次输入的新密码不一致')
    return
  }
  try {
    await changePassword({ old_password, new_password })
    ElMessage.success('密码修改成功，请重新登录')
    showPasswordDialog.value = false
    passwordForm.value = { old_password: '', new_password: '', confirm_password: '' }
    // 修改密码后清除登录状态，要求重新登录
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    router.push('/login')
  } catch (e) {
    // 错误已被拦截器处理
  }
}

const handleLogout = async () => {
  try {
    await ElMessageBox.confirm('确定要退出登录吗？', '提示', { type: 'warning' })
    await logout()
  } catch (e) {}
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
  router.push('/login')
}
</script>

<style scoped>
.logo {
  height: 60px; line-height: 60px; text-align: center;
  font-size: 20px; font-weight: bold; color: #fff;
  border-bottom: 1px solid #3a4a5e;
}
</style>
