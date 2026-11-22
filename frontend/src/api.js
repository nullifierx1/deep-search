export async function api(path, { body, method = 'GET', signal } = {}) {
  let response
  try {
    response = await fetch('/api/v1' + path, {
      method, signal,
      ...(body === undefined ? {} : {
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      }),
    })
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw new Error('Не удалось подключиться к API Deep Search.')
  }
  const data = await response.json().catch(() => null)
  if (!response.ok || !data) {
    const error = new Error(data?.error || 'API Deep Search недоступен.')
    error.code = data?.code
    throw error
  }
  return data
}

export const active = job => ['running', 'cancelling'].includes(job?.status)
