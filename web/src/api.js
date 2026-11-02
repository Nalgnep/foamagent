import { reactive } from 'vue'

// Demo user only (the old frontend's X-User header). This is NOT production
// IAM/SSO; see LIMITATIONS.md in the repo root.
export const userState = reactive({
  username: 'process_engineer',
  users: []
})

export async function api(path, method = 'GET', body = null) {
  const res = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-User': userState.username },
    body: body ? JSON.stringify(body) : null
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail || JSON.stringify(data))
  return data
}

export async function loadUsers() {
  userState.users = await api('/api/users')
}

export function tagTypeForStatus(s) {
  const text = String(s || '')
  if (text.includes('达标') || text.includes('改善')) return 'success'
  if (text.includes('未验证')) return 'info'
  if (text.includes('演示口径')) return ''
  if (text.includes('未达') || text.includes('恶化')) return 'danger'
  if (text.includes('待验证') || text.includes('待办')) return 'warning'
  return 'info'
}
