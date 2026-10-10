<template>
  <div>
    <!-- 顶部操作栏 -->
    <div style="display: flex; justify-content: space-between; margin-bottom: 20px">
      <div style="display: flex; gap: 10px">
        <el-input v-model="keyword" placeholder="搜索笔记（标题+内容）..." style="width: 250px" clearable @clear="currentPage = 1; loadNotes()" @keyup.enter="currentPage = 1; loadNotes()">
          <template #append>
            <el-button @click="currentPage = 1; loadNotes()">搜索</el-button>
          </template>
        </el-input>
        <el-select v-model="filterCategory" placeholder="按分类筛选" clearable style="width: 150px" @change="currentPage = 1; loadNotes()">
          <el-option v-for="c in categories" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
        <el-select v-model="filterTag" placeholder="按标签筛选" clearable style="width: 150px" @change="currentPage = 1; loadNotes()">
          <el-option v-for="t in tags" :key="t.id" :label="t.name" :value="t.id" />
        </el-select>
      </div>
      <div style="display: flex; gap: 10px">
        <el-button :type="batchMode ? 'info' : 'default'" @click="toggleBatchMode">{{ batchMode ? '取消批量' : '批量操作' }}</el-button>
        <el-button type="primary" @click="showCategoryDialog = true">管理分类</el-button>
        <el-button type="warning" @click="showTagDialog = true">管理标签</el-button>
        <el-button @click="handleImportClick">导入</el-button>
        <el-button type="success" @click="router.push('/notes/create')">新建笔记</el-button>
      </div>
    </div>

    <!-- 批量操作栏 -->
    <div v-if="batchMode && selectedIds.length > 0" style="display: flex; align-items: center; gap: 10px; margin-bottom: 15px; padding: 10px 15px; background: #ecf5ff; border-radius: 4px">
      <span style="color: #409eff; font-weight: bold">已选 {{ selectedIds.length }} 项</span>
      <el-button type="danger" size="small" @click="handleBatchDelete">批量删除</el-button>
      <el-button type="warning" size="small" @click="handleBatchPin">批量置顶</el-button>
      <el-button size="small" @click="handleBatchUnpin">批量取消置顶</el-button>
      <el-button size="small" @click="selectedIds = []">清空选择</el-button>
    </div>

    <!-- 隐藏的文件选择器 -->
    <input ref="fileInputRef" type="file" accept=".md" style="display: none" @change="handleFileChange" />

    <!-- 笔记列表 -->
    <el-row :gutter="20">
      <el-col :span="8" v-for="note in notes" :key="note.id" style="margin-bottom: 20px">
        <el-card shadow="hover" :class="{ 'pinned-card': note.is_pinned }" @click="handleCardClick(note)" style="cursor: pointer">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center">
              <div style="display: flex; align-items: center; gap: 8px">
                <el-checkbox v-if="batchMode" :model-value="selectedIds.includes(note.id)" @change="(val) => toggleSelect(note.id, val)" @click.stop />
                <el-icon v-if="note.is_pinned" color="#e6a23c" size="16"><Top /></el-icon>
                <span style="font-weight: bold; font-size: 16px">{{ note.title }}</span>
              </div>
              <el-tag v-if="note.category_name" size="small" type="info">{{ note.category_name }}</el-tag>
            </div>
          </template>
          <p style="color: #666; overflow: hidden; text-overflow: ellipsis; white-space: nowrap">{{ stripMarkdown(note.content) }}</p>
          <div v-if="note.tags && note.tags.length > 0" style="margin-top: 8px">
            <el-tag v-for="tag in note.tags" :key="tag.id" size="small" style="margin-right: 5px; margin-bottom: 5px">{{ tag.name }}</el-tag>
          </div>
          <div style="margin-top: 10px; display: flex; justify-content: space-between; align-items: center">
            <span style="font-size: 12px; color: #999">{{ formatDate(note.create_at) }}</span>
            <div>
              <el-button :type="note.is_pinned ? 'warning' : 'default'" text size="small" @click.stop="handlePin(note)">
                {{ note.is_pinned ? '取消置顶' : '置顶' }}
              </el-button>
              <el-dropdown @click.stop @command="(cmd) => handleExport(note.id, cmd)" trigger="click">
                <el-button type="primary" text size="small" @click.stop>导出</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="md">Markdown</el-dropdown-item>
                    <el-dropdown-item command="pdf">PDF</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <el-button type="danger" text size="small" @click.stop="handleDelete(note.id)">删除</el-button>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-empty v-if="notes.length === 0" description="暂无笔记" />

    <!-- 分页 -->
    <div v-if="totalPages > 1" style="display: flex; justify-content: center; margin-top: 20px">
      <el-pagination v-model:current-page="currentPage" :page-size="pageSize" :total="total" layout="prev, pager, next, total" @current-change="handlePageChange" />
    </div>

    <!-- 分类管理对话框 -->
    <el-dialog v-model="showCategoryDialog" title="管理分类" width="500px">
      <div style="display: flex; gap: 10px; margin-bottom: 15px">
        <el-input v-model="newCategoryName" placeholder="输入新分类名称" />
        <el-button type="primary" @click="handleAddCategory">添加</el-button>
      </div>
      <el-table :data="categories" size="small">
        <el-table-column prop="name" label="分类名称" />
        <el-table-column prop="note_count" label="笔记数" width="80" />
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button type="danger" text size="small" @click="handleDeleteCategory(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 标签管理对话框 -->
    <el-dialog v-model="showTagDialog" title="管理标签" width="500px">
      <div style="display: flex; gap: 10px; margin-bottom: 15px">
        <el-input v-model="newTagName" placeholder="输入新标签名称" />
        <el-button type="primary" @click="handleAddTag">添加</el-button>
      </div>
      <el-table :data="tags" size="small">
        <el-table-column prop="name" label="标签名称" />
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button type="danger" text size="small" @click="handleDeleteTag(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Top } from '@element-plus/icons-vue'
import { getNotes, deleteNote, getCategories, createCategory, deleteCategory, getTags, createTag, deleteTag, exportNote, importNote, pinNote, batchOperate } from '../api'

const router = useRouter()

const notes = ref([])
const categories = ref([])
const tags = ref([])
const keyword = ref('')
const filterCategory = ref('')
const filterTag = ref('')
const showCategoryDialog = ref(false)
const showTagDialog = ref(false)
const newCategoryName = ref('')
const newTagName = ref('')

const currentPage = ref(1)
const pageSize = ref(9)
const total = ref(0)
const totalPages = ref(0)

const fileInputRef = ref(null)

const batchMode = ref(false)
const selectedIds = ref([])

const loadNotes = async () => {
  const params = { page: currentPage.value, page_size: pageSize.value }
  if (keyword.value) params.q = keyword.value
  if (filterCategory.value) params.category = filterCategory.value
  if (filterTag.value) params.tag = filterTag.value
  const res = await getNotes(params)
  notes.value = res.data.results
  total.value = res.data.total
  totalPages.value = res.data.total_pages
}

const handlePageChange = (page) => { currentPage.value = page; loadNotes() }

const handleImportClick = () => { fileInputRef.value.click() }

const handleFileChange = async (event) => {
  const file = event.target.files[0]
  if (!file) return
  event.target.value = ''
  try {
    await importNote(file)
    ElMessage.success(`已导入「${file.name.replace(/\.md$/i, '')}」`)
    currentPage.value = 1
    loadNotes()
  } catch (e) {}
}

const handleCardClick = (note) => {
  if (batchMode.value) { toggleSelect(note.id) } else { router.push('/notes/' + note.id + '/edit') }
}

const toggleBatchMode = () => { batchMode.value = !batchMode.value; selectedIds.value = [] }

const toggleSelect = (id, val) => {
  if (val === false || selectedIds.value.includes(id)) {
    selectedIds.value = selectedIds.value.filter(i => i !== id)
  } else { selectedIds.value.push(id) }
}

const handleBatchDelete = async () => {
  await ElMessageBox.confirm(`确定要删除选中的 ${selectedIds.value.length} 条笔记吗？`, '批量删除', { type: 'warning' })
  await batchOperate('delete', selectedIds.value)
  ElMessage.success('已移至回收站')
  selectedIds.value = []
  loadNotes()
}

const handleBatchPin = async () => {
  await batchOperate('pin', selectedIds.value)
  ElMessage.success('已置顶')
  selectedIds.value = []
  loadNotes()
}

const handleBatchUnpin = async () => {
  await batchOperate('unpin', selectedIds.value)
  ElMessage.success('已取消置顶')
  selectedIds.value = []
  loadNotes()
}

const handlePin = async (note) => {
  try {
    await pinNote(note.id, !note.is_pinned)
    ElMessage.success(note.is_pinned ? '已取消置顶' : '已置顶')
    loadNotes()
  } catch (e) {}
}

const loadCategories = async () => { categories.value = (await getCategories()).data }
const loadTags = async () => { tags.value = (await getTags()).data }

const handleDelete = async (id) => {
  await ElMessageBox.confirm('确定要删除这条笔记吗？删除后可在回收站恢复', '提示', { type: 'warning' })
  await deleteNote(id)
  ElMessage.success('已移至回收站')
  loadNotes()
}

const handleAddCategory = async () => {
  if (!newCategoryName.value.trim()) return
  await createCategory({ name: newCategoryName.value.trim() })
  ElMessage.success('分类创建成功')
  newCategoryName.value = ''
  loadCategories()
}

const handleDeleteCategory = async (id) => {
  await ElMessageBox.confirm('删除分类后，该分类下的笔记将变为无分类', '提示', { type: 'warning' })
  await deleteCategory(id)
  ElMessage.success('分类已删除')
  loadCategories()
}

const handleAddTag = async () => {
  if (!newTagName.value.trim()) return
  await createTag({ name: newTagName.value.trim() })
  ElMessage.success('标签创建成功')
  newTagName.value = ''
  loadTags()
}

const handleDeleteTag = async (id) => {
  await ElMessageBox.confirm('确定要删除这个标签吗？', '提示', { type: 'warning' })
  await deleteTag(id)
  ElMessage.success('标签已删除')
  loadTags()
}

const handleExport = async (noteId, type) => {
  try {
    await exportNote(noteId, type)
    ElMessage.success(`已导出为 ${type.toUpperCase()} 文件`)
  } catch (e) { ElMessage.error('导出失败') }
}

const formatDate = (dateStr) => dateStr ? new Date(dateStr).toLocaleString('zh-CN') : ''

const stripMarkdown = (content) => {
  if (!content) return ''
  return content.replace(/#{1,6}\s/g, '').replace(/\*\*(.*?)\*\*/g, '$1').replace(/\*(.*?)\*/g, '$1')
    .replace(/~~(.*?)~~/g, '$1').replace(/`(.*?)`/g, '$1').replace(/\[\[(.*?)\]\]/g, '$1').replace(/\[(.*?)\]\(.*?\)/g, '$1')
    .replace(/!\[(.*?)\]\(.*?\)/g, '$1').replace(/>\s/g, '').replace(/[-*+]\s/g, '')
    .replace(/\d+\.\s/g, '').replace(/---/g, '').replace(/\n/g, ' ').trim().substring(0, 100)
}

onMounted(() => { loadNotes(); loadCategories(); loadTags() })
</script>

<style scoped>
.pinned-card { border-color: #e6a23c; }
</style>
