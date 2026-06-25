const BASE = import.meta.env.VITE_API_URL || 'http://localhost:4087'

function headers() {
  const token = localStorage.getItem('gv_token')
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: 'Bearer ' + token } : {}),
  }
}

export async function apiFetch(path, opts = {}) {
  const res = await fetch(BASE + path, {
    ...opts,
    headers: { ...headers(), ...(opts.headers || {}) },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  if (res.status === 204) return null
  return res.json()
}

export const api = {
  listGraphs: () => apiFetch('/v1/graphs'),
  getGraph: (id) => apiFetch('/v1/graphs/' + id),
  deleteGraph: (id) => apiFetch('/v1/graphs/' + id, { method: 'DELETE' }),
  queryGraph: (id, question, limit = 20) =>
    apiFetch('/v1/graphs/' + id + '/query', {
      method: 'POST',
      body: JSON.stringify({ question, limit }),
    }),
  pushGraph: (body) =>
    apiFetch('/v1/graphs', { method: 'POST', body: JSON.stringify(body) }),
  htmlUrl: (id) => BASE + '/v1/graphs/' + id + '/html',
  downloadUrl: (id) => BASE + '/v1/graphs/' + id + '/download',
}
