<template>
  <div style="max-width: 1000px; margin: 0 auto">
    <el-card>
      <h2 style="margin-top: 0">{{ isEdit ? '编辑笔记' : '新建笔记' }}</h2>
      <el-form label-width="80px">
        <el-form-item label="标题">
          <el-input v-model="form.title" placeholder="请输入标题" />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="form.category" placeholder="选择分类" clearable style="width: 100%">
            <el-option v-for="c in categories" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="标签">
          <el-select
            v-model="form.tag_ids"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="输入或选择标签"
            style="width: 100%"
          >
            <el-option v-for="t in tags" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="内容">
          <MdEditor
            v-model="form.content"
            :style="{ height: '500px' }"
            placeholder="请输入笔记内容（支持 Markdown）"
            :preview="true"
            :toolbars="toolbars"
            language="zh-CN"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSave" :loading="saving">保存</el-button>
          <el-button @click="router.back()">取消</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { MdEditor } from 'md-editor-v3'
import 'md-editor-v3/lib/style.css'
import { getNote, createNote, updateNote, getCategories, getTags } from '../api'

const route = useRoute()
const router = useRouter()
const saving = ref(false)
const categories = ref([])
const tags = ref([])
const isEdit = computed(() => !!route.params.id)

// 自定义工具栏，保留常用功能
const toolbars = [
  'bold', 'underline', 'italic', 'strikeThrough', '-',
  'title', 'quote', 'unorderedList', 'orderedList', '-',
  'codeRow', 'code', 'link', 'image', 'table', '-',
  'revoke', 'next', '=',
  'preview', 'catalog'
]

const form = reactive({ title: '', content: '', category: null, tag_ids: [] })

const loadCategories = async () => {
  const res = await getCategories()
  categories.value = res.data
}

const loadTags = async () => {
  const res = await getTags()
  tags.value = res.data
}

const loadNote = async () => {
  if (!route.params.id) return
  const res = await getNote(route.params.id)
  const note = res.data
  form.title = note.title
  form.content = note.content
  form.category = note.category
  form.tag_ids = note.tags ? note.tags.map(t => t.id) : []
}

const handleSave = async () => {
  if (!form.title.trim()) { ElMessage.warning('请输入标题'); return }
  saving.value = true
  try {
    const data = {
      title: form.title.trim(),
      content: form.content,
      category: form.category || null,
      tag_ids: form.tag_ids
    }
    if (isEdit.value) {
      await updateNote(route.params.id, data)
      ElMessage.success('笔记已更新')
    } else {
      await createNote(data)
      ElMessage.success('笔记已创建')
    }
    router.push('/notes')
  } catch (e) {} finally {
    saving.value = false
  }
}

onMounted(() => { loadCategories(); loadTags(); loadNote() })
</script>

<style scoped>
:deep(.md-editor) {
  border: 1px solid #dcdfe6;
  border-radius: 4px;
}
</style>
