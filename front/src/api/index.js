import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '../router'

const request = axios.create({
  baseURL: 'http://127.0.0.1:8000/api',
  timeout: 10000,
})

request.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) { config.headers.Authorization = 'Bearer ' + token }
  return config
})

request.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      const status = error.response.status
      if (status === 401) {
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        router.push('/login')
        ElMessage.error('登录已过期，请重新登录')
      } else if (status === 400) {
        const data = error.response.data
        // DRF 验证错误格式: { "field": ["错误信息"] }
        if (typeof data === 'object' && data !== null) {
          const messages = Object.values(data).flat().join('；')
          ElMessage.error(messages || '请求参数错误')
        } else {
          ElMessage.error(data?.detail || '请求参数错误')
        }
      } else if (status === 404) {
        ElMessage.error('资源不存在')
      } else {
        ElMessage.error('服务器错误')
      }
    }
    return Promise.reject(error)
  }
)

export const register = (data) => request.post('/register/', data)
export const login = (data) => request.post('/login/', data)
export const logout = () => request.post('/logout/')
export const getNotes = (params) => request.get('/notes/', { params })
export const createNote = (data) => request.post('/notes/', data)
export const getNote = (id) => request.get('/notes/' + id + '/')
export const updateNote = (id, data) => request.put('/notes/' + id + '/', data)
export const deleteNote = (id) => request.delete('/notes/' + id + '/')
export const getCategories = () => request.get('/categories/')
export const createCategory = (data) => request.post('/categories/', data)
export const updateCategory = (id, data) => request.put('/categories/' + id + '/', data)
export const deleteCategory = (id) => request.delete('/categories/' + id + '/')
export const getTags = () => request.get('/tags/')
export const createTag = (data) => request.post('/tags/', data)
export const updateTag = (id, data) => request.put('/tags/' + id + '/', data)
export const deleteTag = (id) => request.delete('/tags/' + id + '/')
export const getRecycleBin = () => request.get('/recycle-bin/')
export const recycleBinAction = (data) => request.post('/recycle-bin/', data)
export const getStats = () => request.get('/stats/')

// 修改密码
export const changePassword = (data) => request.post('/change-password/', data)

// 置顶/取消置顶笔记
export const pinNote = (id, isPinned) => request.post(`/notes/${id}/pin/`, { is_pinned: isPinned })

// 批量操作（delete/pin/unpin）
export const batchOperate = (action, noteIds) => request.post('/notes/batch/', { action, note_ids: noteIds })

// 导入 Markdown 文件为笔记
export const importNote = (file) => {
  const formData = new FormData()
  formData.append('file', file)
  return request.post('/notes/import/', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

// 导出笔记为 Markdown 或 PDF（文件下载）
export const exportNote = async (id, type) => {
  const res = await request.get(`/export-note/${id}/`, {
    params: { type },  // 用 type 而不是 format，避免和 DRF 内部参数冲突
    responseType: 'blob',
  })
  // 从响应头中解析文件名
  const disposition = res.headers['content-disposition'] || ''
  const match = disposition.match(/filename="?(.+?)"?$/)
  const filename = match ? match[1] : `note.${type}`
  // 创建临时下载链接，触发浏览器保存文件
  const blob = new Blob([res.data])
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  window.URL.revokeObjectURL(url)
}

export default request
