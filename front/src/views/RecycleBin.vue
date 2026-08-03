<template>
  <div>
    <h2 style="margin-top: 0">回收站</h2>
    <el-table :data="notes" stripe>
      <el-table-column prop="title" label="标题" />
      <el-table-column prop="content" label="内容" show-overflow-tooltip />
      <el-table-column prop="update_at" label="删除时间" width="180">
        <template #default="{ row }">{{ formatDate(row.update_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="200">
        <template #default="{ row }">
          <el-button type="success" text size="small" @click="handleRestore(row.id)">恢复</el-button>
          <el-button type="danger" text size="small" @click="handlePermanentDelete(row.id)">彻底删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="notes.length === 0" description="回收站是空的" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getRecycleBin, recycleBinAction } from '../api'

const notes = ref([])

const loadRecycleBin = async () => {
  const res = await getRecycleBin()
  notes.value = res.data
}

const handleRestore = async (id) => {
  await recycleBinAction({ action: 'restore', note_id: id })
  ElMessage.success('笔记已恢复')
  loadRecycleBin()
}

const handlePermanentDelete = async (id) => {
  await ElMessageBox.confirm('彻底删除后无法恢复，确定吗？', '警告', { type: 'error' })
  await recycleBinAction({ action: 'delete', note_id: id })
  ElMessage.success('已彻底删除')
  loadRecycleBin()
}

const formatDate = (dateStr) => {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleString('zh-CN')
}

onMounted(loadRecycleBin)
</script>
