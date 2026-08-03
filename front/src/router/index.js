import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('../views/Register.vue'),
  },
  {
    path: '/',
    name: 'Layout',
    component: () => import('../views/Layout.vue'),
    redirect: '/notes',
    children: [
      { path: 'notes', name: 'NoteList', component: () => import('../views/NoteList.vue') },
      { path: 'notes/create', name: 'NoteCreate', component: () => import('../views/NoteEdit.vue') },
      { path: 'notes/:id/edit', name: 'NoteEdit', component: () => import('../views/NoteEdit.vue') },
      { path: 'recycle-bin', name: 'RecycleBin', component: () => import('../views/RecycleBin.vue') },
      { path: 'stats', name: 'Stats', component: () => import('../views/Stats.vue') },
    ],
  },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('access_token')
  if (to.path !== '/login' && to.path !== '/register' && !token) {
    next('/login')
  } else { next() }
})

export default router
