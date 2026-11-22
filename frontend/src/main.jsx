import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { ChevronDown, ChevronRight, Clock3, ExternalLink, Globe2, Search, Settings2, Square } from 'lucide-react'
import { active, api } from './api.js'
import './style.css'

const storageKey = 'deep-search-job'
const statuses = {
  running: 'В работе', cancelling: 'Останавливается', completed: 'Готово', cancelled: 'Отменено',
  failed: 'Ошибка', interrupted: 'Прервано', queued: 'В очереди', searching: 'Ищем', following: 'Обход ссылок',
  finished: 'Готово', found: 'Найдено', empty: 'Пусто', empty_limit: 'Лимит пустых страниц',
  bot_challenge: 'Проверка на ботов', access_denied: 'Доступ закрыт', rate_limited: 'Частые запросы',
  request_budget: 'Лимит запросов', page_limit: 'Лимит страниц', source_error: 'Ошибка сайта',
  authentication_required: 'Нужен вход', job_failed: 'Ошибка задачи',
}
const groups = { sites: 'Общий каталог', cppreference: 'Документация', 'lk-sites': 'Дополнительные сайты' }
const numbers = [
  ['follow_depth', 'Глубина обхода', 1, 5, 1],
  ['follow_limit', 'Страниц обхода', 1, 100, 5],
  ['stop_after_empty', 'Порог пустых страниц', 0, 100, 5],
  ['max_requests_per_site', 'Запросов на сайт', 1, 300, 100],
]
const date = new Intl.DateTimeFormat('ru', { dateStyle: 'medium', timeStyle: 'short' })

function Badge({ code }) {
  const tone = ['completed', 'found'].includes(code) ? 'good'
    : ['running', 'searching', 'following', 'cancelling'].includes(code) ? 'busy'
    : code && !['queued', 'finished', 'empty'].includes(code) ? 'warn' : 'neutral'
  return <span className={'badge ' + tone} title={code}>{statuses[code] || 'См. детали'}</span>
}

function Link({ url }) {
  let safe = false
  try { safe = ['https:', 'http:'].includes(new URL(url).protocol) } catch { /* Display malformed addresses as text. */ }
  return safe ? <a href={url} target="_blank" rel="noreferrer">{url}<ExternalLink size={13}/></a> : <span>{url}</span>
}

function CacheControls() {
  const [stats, setStats] = useState(null)
  const [pending, setPending] = useState(false)
  const [message, setMessage] = useState('')
  async function load(action) {
    setPending(true)
    setMessage('')
    try {
      const data = await api('/cache', action ? { method: 'POST', body: { action } } : undefined)
      setStats(data)
      if (action) setMessage('Удалено записей: ' + data.removed)
    } catch (error) {
      setMessage(error.message)
    } finally {
      setPending(false)
    }
  }
  useEffect(() => { load() }, [])
  return <section className="cache-controls" aria-label="Кеш результатов">
    <h3>Кеш результатов</h3>
    {stats && <p className="muted">Актуальных: {stats.valid} · Просроченных: {stats.expired} · Срок: {stats.ttl_seconds / 86400} дней</p>}
    <div className="actions">
      <button type="button" disabled={pending} onClick={() => load()}>Обновить</button>
      <button type="button" disabled={pending || !stats?.expired} onClick={() => load('expired')}>Удалить просроченные</button>
      <button type="button" disabled={pending || !(stats?.valid || stats?.expired)} onClick={() => {
        if (window.confirm('Очистить кеш результатов поиска? История сохранится.')) load('all')
      }}>Очистить кеш</button>
    </div>
    {message && <p role="status">{message}</p>}
  </section>
}

const groupKey = 'deep-search-groups'

function readGroups() {
  try {
    const saved = JSON.parse(localStorage.getItem(groupKey))
    return Array.isArray(saved) ? saved : []
  } catch {
    return []
  }
}

function GroupToggle({ name, ids, selected, onToggle }) {
  const count = ids.filter(id => selected.includes(id)).length
  return <label className="group-toggle">
    <input type="checkbox" checked={count === ids.length && count > 0} disabled={!ids.length}
      ref={input => { if (input) input.indeterminate = count > 0 && count < ids.length }}
      onChange={() => onToggle(ids)}/>
    <span>{name}</span><small>{count}/{ids.length}</small>
  </label>
}

function SiteDetails({ result, reason }) {
  return <div className="details">
    {reason && <p className="muted">Причина завершения <code>{reason}</code></p>}
    {result?.error && <p role="status">{result.error}</p>}
    {result && <div className="detail-columns">
      <div>
        <h3>Найденные ссылки</h3>
        {result.urls.length ? <ul>{result.urls.map(url => <li key={url}><Link url={url}/></li>)}</ul> : <p className="muted">Ссылок нет</p>}
        {!!result.matches.length && <><h3>Совпадения</h3><ul>{result.matches.map(match => <li key={match.text}>{match.text}</li>)}</ul></>}
      </div>
      <div>
        <h3>Проверенные страницы</h3>
        <ul>{result.checked_pages.map(url => <li key={url}><Link url={url}/>
          {result.network_errors?.[url] && <div className="muted">{result.network_errors[url]}</div>}</li>)}</ul>
        {result.followed?.map(page => <details key={page.source_url}><summary>Глубина {page.depth} · {page.source_url}</summary>
          {page.error && <p>{page.error}</p>}
          <ul>{page.urls.map(url => <li key={url}><Link url={url}/></li>)}</ul>
        </details>)}
        <p className="muted">HTTP: {result.http_requests} · Playwright: {result.browser_renders}</p>
      </div>
    </div>}
  </div>
}

function Results({ job, sites, busy, onCancel, onRetry }) {
  const [expanded, setExpanded] = useState(null)
  const [retrying, setRetrying] = useState(false)
  const [chosen, setChosen] = useState([])
  const progress = Object.entries(job?.site_progress || {})
  return <section className="results" aria-label="Результаты поиска">
    <div className="section-title">
      <div><h2>Результаты поиска</h2>{job && <p className="muted">{job.request.query} · {job.finished_sites} из {job.total_sites} сайтов</p>}</div>
      {job && <div className="actions"><Badge code={job.status}/>
        {active(job) ? <button type="button" disabled={busy || job.status === 'cancelling'} onClick={onCancel}><Square size={14}/> Остановить</button>
          : <button type="button" disabled={busy} onClick={() => { setChosen(job.request.sites); setRetrying(value => !value) }}>Повторить</button>}
      </div>}
    </div>
    {retrying && !active(job) && <div className="retry">
      {job.request.sites.map(id => <label key={id}><input type="checkbox" checked={chosen.includes(id)}
        onChange={() => setChosen(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])}/>{sites[id]?.name || id}</label>)}
      <button className="primary" disabled={busy || !chosen.length} onClick={() => onRetry(chosen)}>Запустить повтор</button>
    </div>}
    {job?.error && <p role="alert" className="notice">{job.error}</p>}
    {!job ? <div className="empty"><Search size={27}/><h3>Пока нет результатов</h3>
      <p>Выберите сайты и введите поисковый запрос.</p></div> :
      <div className="result-list">
        <div className="table-head result-grid"><span>Сайт</span><span>Статус</span><span>Ссылки</span></div>
        {progress.map(([id, item]) => {
          const result = job.results[id]
          const open = expanded === id
          const hasDetails = Boolean(result || item.reason)
          const Arrow = open ? ChevronDown : ChevronRight
          return <div className="result-item" key={id}>
            <button className="result-row result-grid" aria-expanded={open} disabled={!hasDetails}
              onClick={() => setExpanded(open ? null : id)}>
              <span className="site-cell"><Arrow size={15}/><span><strong>{sites[id]?.name || id}</strong>
                <small>{result?.base_url || sites[id]?.base_url}</small></span></span>
              <span><Badge code={item.reason || item.stage}/></span><span>{result ? result.urls.length : '—'}</span>
            </button>
            {open && <SiteDetails result={result} reason={item.reason}/>}
          </div>
        })}
      </div>}
  </section>
}

function App() {
  const [view, setView] = useState('search')
  const [sites, setSites] = useState([])
  const [selected, setSelected] = useState([])
  const [savedGroups, setSavedGroups] = useState(readGroups)
  const [groupName, setGroupName] = useState('')
  const [filter, setFilter] = useState('')
  const [query, setQuery] = useState('')
  const [paths, setPaths] = useState({})
  const [editing, setEditing] = useState(null)
  const [regex, setRegex] = useState('')
  const [options, setOptions] = useState({})
  const [settings, setSettings] = useState(false)
  const [job, setJob] = useState(null)
  const [jobId, setJobId] = useState(() => localStorage.getItem(storageKey))
  const [history, setHistory] = useState([])
  const [nextOffset, setNextOffset] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [generation, setGeneration] = useState(0)
  const catalog = Object.fromEntries(sites.map(site => [site.id, site]))
  const visible = sites.filter(site => [site.name, site.id, site.base_url].some(value => value.toLowerCase().includes(filter.toLowerCase())))
  const grouped = new Map()
  for (const site of visible) {
    if (!grouped.has(site.group)) grouped.set(site.group, [])
    grouped.get(site.group).push(site)
  }

  useEffect(() => {
    const controller = new AbortController()
    api('/sites', { signal: controller.signal }).then(data => setSites(data.sites))
      .catch(err => { if (err.name !== 'AbortError') setError(err.message) })
    return () => controller.abort()
  }, [generation])

  useEffect(() => {
    if (!jobId) return
    const controller = new AbortController()
    let timer
    async function poll() {
      try {
        const data = await api('/searches/' + jobId, { signal: controller.signal })
        if (controller.signal.aborted) return
        setJob(data)
        if (active(data)) timer = setTimeout(poll, 800)
      } catch (err) {
        if (controller.signal.aborted) return
        if (err.code === 'not_found') {
          localStorage.removeItem(storageKey)
          setJobId(null)
          setJob(null)
        } else setError(err.message)
      }
    }
    poll()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [jobId, generation])

  useEffect(() => {
    if (view !== 'history') return
    const controller = new AbortController()
    api('/searches', { signal: controller.signal }).then(data => {
      setHistory(data.searches)
      setNextOffset(data.next_offset)
    }).catch(err => { if (err.name !== 'AbortError') setError(err.message) })
    return () => controller.abort()
  }, [view, generation, job?.status])

  function openJob(id, data = null) {
    localStorage.setItem(storageKey, id)
    setJob(current => data || (current?.id === id ? current : null))
    setJobId(id)
    setView('search')
    setGeneration(value => value + 1)
  }

  async function run(action) {
    setBusy(true)
    setError('')
    try {
      await action()
    } catch (err) {
      if (err.code === 'search_busy') {
        try {
          const recent = await api('/searches')
          const running = recent.searches.find(active)
          if (running) { openJob(running.id); return }
        } catch { /* Keep the original error if recovery fails. */ }
      }
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  function submit(event) {
    event.preventDefault()
    run(async () => {
      const overrides = Object.fromEntries(selected.flatMap(id => {
        const entries = paths[id]?.split('\n').map(line => line.trim()).filter(Boolean)
        return entries?.length ? [[id, entries]] : []
      }))
      const result = await api('/searches', { method: 'POST', body: {
        sites: selected, query: query.trim(), paths: overrides, regex_pattern: regex, options,
      } })
      openJob(result.id, result)
    })
  }

  const toggle = id => setSelected(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])
  const toggleGroup = ids => setSelected(prev => ids.every(id => prev.includes(id))
    ? prev.filter(id => !ids.includes(id)) : [...new Set([...prev, ...ids])])
  function updateGroups(next) {
    localStorage.setItem(groupKey, JSON.stringify(next))
    setSavedGroups(next)
  }
  function saveGroup(event) {
    event.preventDefault()
    const name = groupName.trim()
    if (!name || !selected.length) return
    const replacement = { name, sites: [...selected] }
    updateGroups([...savedGroups.filter(group => group.name !== name), replacement])
    setGroupName('')
  }
  const retryConnection = () => { setError(''); setGeneration(value => value + 1) }
  return <div className="shell">
    <aside className="sidebar">
      <div className="brand"><Search size={25}/><span>Deep Search</span></div>
      <nav aria-label="Рабочая область">
        <button aria-current={view === 'search' ? 'page' : undefined} onClick={() => setView('search')}><Search size={17}/> Поиск</button>
        <button aria-current={view === 'history' ? 'page' : undefined} onClick={() => setView('history')}><Clock3 size={17}/> История</button>
      </nav>
      {view === 'search' && <div className="sources">
        <div className="source-heading"><h2>Источники</h2><span>{selected.length}</span></div>
        <input className="source-filter" aria-label="Фильтр сайтов" placeholder="Найти сайт…" value={filter} onChange={e => setFilter(e.target.value)}/>
        <button className="text-button" disabled={!visible.length} onClick={() => {
          const ids = visible.map(site => site.id)
          setSelected(ids.every(id => selected.includes(id)) ? selected.filter(id => !ids.includes(id)) : [...new Set([...selected, ...ids])])
        }}>{visible.length && visible.every(site => selected.includes(site.id)) ? 'Снять выбор' : 'Выбрать видимые'}</button>
        <details className="saved-groups" open={savedGroups.length > 0 ? true : undefined}>
          <summary>Мои группы</summary>
          {savedGroups.map(group => <div className="source-row" key={group.name}>
            <GroupToggle name={group.name} ids={group.sites.filter(id => catalog[id])} selected={selected} onToggle={toggleGroup}/>
            <button className="icon-button" aria-label={'Удалить группу ' + group.name}
              onClick={() => updateGroups(savedGroups.filter(item => item !== group))}>×</button>
          </div>)}
          <form className="group-form" onSubmit={saveGroup}>
            <input aria-label="Имя группы" placeholder="Имя группы" maxLength={50} value={groupName} onChange={event => setGroupName(event.target.value)}/>
            <button disabled={!groupName.trim() || !selected.length}>Сохранить выбранные</button>
          </form>
        </details>
        {[...grouped].map(([group, entries]) => <div className="source-group" key={group}>
          <h3><GroupToggle name={groups[group] || group} ids={sites.filter(site => site.group === group).map(site => site.id)}
            selected={selected} onToggle={toggleGroup}/></h3>
          {entries.map(site => <div className="source-item" key={site.id}>
            <div className="source-row"><label><input type="checkbox" checked={selected.includes(site.id)} onChange={() => toggle(site.id)}/>{site.name}</label>
              <button className="icon-button" aria-label={'Пути для ' + site.name} aria-expanded={editing === site.id}
                title="Пути сайта" onClick={() => setEditing(editing === site.id ? null : site.id)}><Settings2 size={15}/></button></div>
            {editing === site.id && <div className="path-editor"><label>Пути, каждый с новой строки
              <textarea rows="3" placeholder="/mail" value={paths[site.id] ?? site.paths.join('\n')}
                onChange={e => setPaths(prev => ({ ...prev, [site.id]: e.target.value }))}/></label>
              <button className="text-button" onClick={() => setPaths(prev => {
                const next = { ...prev }
                delete next[site.id]
                return next
              })}>Вернуть пути по умолчанию</button></div>}
          </div>)}
        </div>)}
      </div>}
    </aside>
    <main>
      <header className="breadcrumb">Рабочая область <span>/</span> {view === 'search' ? 'Поиск' : 'История'}</header>
      <div className="content">
        <h1>{view === 'search' ? 'Поиск по сайтам' : 'История поисков'}</h1>
        {error && <div role="alert" className="notice"><span>{error}</span><button onClick={retryConnection}>Повторить подключение</button></div>}
        {view === 'search' ? <>
          <form onSubmit={submit}>
            <div className="query-row">
              <label className="query"><Search size={19}/><input aria-label="Поисковый запрос" placeholder="Введите поисковый запрос" maxLength="200" required
                value={query} onChange={e => setQuery(e.target.value)}/></label>
              <button className="primary" disabled={busy || active(job) || !selected.length || !query.trim()}>Найти</button>
              <button type="button" aria-expanded={settings} onClick={() => setSettings(!settings)}><Settings2 size={16}/> Настройки <ChevronDown size={15}/></button>
            </div>
            {settings && <div className="settings">
              <label>Регулярное выражение<input value={regex} maxLength="500" onChange={e => setRegex(e.target.value)}/></label>
              {numbers.map(([key, label, min, max, fallback]) => <label key={key}>{label}<input type="number"
                min={min} max={max} value={options[key] ?? fallback} required
                onChange={e => setOptions(prev => ({ ...prev, [key]: e.target.value === '' ? '' : Number(e.target.value) }))}/></label>)}
              {Object.entries({ follow_links: 'Обходить ссылки', use_playwright: 'Включить Playwright', use_cache: 'Использовать кеш' })
                .map(([key, label]) => <label className="flag" key={key}><input type="checkbox" checked={options[key] ?? true}
                  onChange={e => setOptions(prev => ({ ...prev, [key]: e.target.checked }))}/>{label}</label>)}
              <CacheControls/>
            </div>}
          </form>
          <Results key={job?.id ?? 'empty'} job={job} sites={catalog} busy={busy}
            onCancel={() => run(async () => {
              const data = await api('/searches/' + job.id + '/cancel', { method: 'POST' })
              openJob(data.id, data)
            })}
            onRetry={ids => run(async () => {
              const data = await api('/searches/' + job.id + '/retry', { method: 'POST', body: { sites: ids } })
              openJob(data.id, data)
            })}/>
        </> : <section aria-label="История поисков">
          {history.length ? <>
            <div className="table-head history-grid"><span>Запрос</span><span>Время</span><span>Статус</span></div>
            {history.map(item => <button className="history-row history-grid" key={item.id} onClick={() => openJob(item.id)}>
              <span><strong>{item.request.query}</strong><small>{item.finished_sites} из {item.total_sites} сайтов</small></span>
              <span>{date.format(new Date(item.created_at * 1000))}</span><span><Badge code={item.status}/></span>
            </button>)}
            {nextOffset !== null && <button className="more" disabled={busy} onClick={() => run(async () => {
              const data = await api('/searches?offset=' + nextOffset)
              setHistory(prev => [...new Map([...prev, ...data.searches].map(item => [item.id, item])).values()])
              setNextOffset(data.next_offset)
            })}>Загрузить ещё</button>}
          </> : <div className="empty"><Clock3 size={27}/><h3>История пуста</h3><p>Запущенные поиски появятся здесь.</p></div>}
        </section>}
      </div>
    </main>
  </div>
}

createRoot(document.getElementById('root')).render(<App/>)
