<template>
  <div>
    <h2 style="margin-top: 0">数据统计</h2>
    <el-row :gutter="20" style="margin-bottom: 20px">
      <el-col :span="6">
        <el-card shadow="hover">
          <div style="text-align: center">
            <div style="font-size: 36px; font-weight: bold; color: #409eff">{{ stats.total_notes }}</div>
            <div style="color: #999; margin-top: 5px">笔记总数</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div style="text-align: center">
            <div style="font-size: 36px; font-weight: bold; color: #67c23a">{{ stats.category_stats.length }}</div>
            <div style="color: #999; margin-top: 5px">分类数量</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div style="text-align: center">
            <div style="font-size: 36px; font-weight: bold; color: #e6a23c">{{ stats.trash_count }}</div>
            <div style="color: #999; margin-top: 5px">回收站</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div style="text-align: center">
            <div style="font-size: 36px; font-weight: bold; color: #f56c6c">{{ recentCount }}</div>
            <div style="color: #999; margin-top: 5px">最近7天</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20">
      <el-col :span="12">
        <el-card>
          <template #header>分类统计</template>
          <el-table :data="stats.category_stats" size="small">
            <el-table-column prop="category__name" label="分类" />
            <el-table-column prop="count" label="笔记数" width="100" />
          </el-table>
          <el-empty v-if="stats.category_stats.length === 0" description="暂无数据" :image-size="60" />
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card>
          <template #header>最近7天创建趋势</template>
          <el-table :data="stats.daily_stats" size="small">
            <el-table-column prop="date" label="日期" />
            <el-table-column prop="count" label="创建数" width="100" />
          </el-table>
          <el-empty v-if="stats.daily_stats.length === 0" description="暂无数据" :image-size="60" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { getStats } from '../api'

const stats = ref({ total_notes: 0, category_stats: [], daily_stats: [], trash_count: 0 })

const recentCount = computed(() => {
  return stats.value.daily_stats.reduce((sum, item) => sum + item.count, 0)
})

const loadStats = async () => {
  const res = await getStats()
  stats.value = res.data
}

onMounted(loadStats)
</script>
