import { useEffect, useState, useRef } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { api } from '../api.js'
import styles from './ProjectPage.module.css'

function StatBar({ graph }) {
  const stats = [
    { label: 'Nodes', value: graph.node_count?.toLocaleString() ?? '—' },
    { label: 'Edges', value: graph.edge_count?.toLocaleString() ?? '—' },
    { label: 'Communities', value: graph.community_count?.toLocaleString() ?? '—' },
    {
      label: 'Updated',
      value: graph.updated_at || graph.created_at
        ? new Date(graph.updated_at || graph.created_at).toLocaleDateString('en-GB', {
            day: 'numeric', month: 'short', year: 'numeric',
          })
        : '—',
    },
  ]
  return (
    <div className={styles.statBar}>
      {stats.map((s) => (
        <div key={s.label} className={styles.statItem}>
          <span className={styles.statValue}>{s.value}</span>
          <span className={styles.statLabel}>{s.label}</span>
        </div>
      ))}
    </div>
  )
}

function QuerySection({ graphId }) {
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const inputRef = useRef(null)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!question.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const data = await api.queryGraph(graphId, question.trim())
      setResult(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className={styles.section}>
      <h2 className={styles.sectionTitle}>Query</h2>
      <form className={styles.queryForm} onSubmit={handleSubmit}>
        <input
          ref={inputRef}
          type="text"
          className={styles.queryInput}
          placeholder="Ask about this graph…"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={loading}
        />
        <button type="submit" className={styles.queryBtn} disabled={loading || !question.trim()}>
          {loading ? 'Searching…' : 'Search'}
        </button>
      </form>

      {error && (
        <p className={styles.queryError}>Query failed: {error}</p>
      )}

      {result && (
        <motion.div
          className={styles.queryResults}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
        >
          {result.nodes?.length > 0 && (
            <div className={styles.resultGroup}>
              <h3 className={styles.resultGroupTitle}>Nodes</h3>
              <div className={styles.resultList}>
                {result.nodes.map((n) => (
                  <div key={n.id} className={styles.resultNode}>
                    <span className={styles.resultId}>{n.id}</span>
                    <span className={styles.resultLabel}>{n.label || n.name || '—'}</span>
                    {n.source_file && (
                      <span className={styles.resultMeta}>{n.source_file}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {result.edges?.length > 0 && (
            <div className={styles.resultGroup}>
              <h3 className={styles.resultGroupTitle}>Edges</h3>
              <div className={styles.resultList}>
                {result.edges.map((e, i) => (
                  <div key={i} className={styles.resultEdge}>
                    <span className={styles.resultId}>{e.source}</span>
                    <span className={styles.resultRelation}>{e.relation || '→'}</span>
                    <span className={styles.resultId}>{e.target}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {(!result.nodes?.length && !result.edges?.length) && (
            <p className={styles.queryEmpty}>No results for that query.</p>
          )}
        </motion.div>
      )}
    </section>
  )
}

export default function ProjectPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [graph, setGraph] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [deleting, setDeleting] = useState(false)

  const token = localStorage.getItem('gv_token')

  useEffect(() => {
    api.getGraph(id)
      .then(setGraph)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [id])

  async function handleDelete() {
    if (!window.confirm(`Delete "${graph?.project_name}"? This cannot be undone.`)) return
    setDeleting(true)
    try {
      await api.deleteGraph(id)
      navigate('/')
    } catch (e) {
      alert('Delete failed: ' + e.message)
      setDeleting(false)
    }
  }

  if (loading) {
    return (
      <div className={styles.loadingState}>
        <span className={styles.loadingMono}>loading graph…</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className={styles.loadingState}>
        <p className={styles.errorText}>Failed to load: {error}</p>
        <Link to="/" className={styles.backLink}>← Back to vault</Link>
      </div>
    )
  }

  const vizUrl = api.htmlUrl(id) + (token ? `?token=${token}` : '')
  const downloadUrl = api.downloadUrl(id)

  return (
    <motion.div
      className={styles.page}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
    >
      {/* Breadcrumb */}
      <div className={styles.breadcrumb}>
        <Link to="/" className={styles.breadcrumbLink}>Graphs</Link>
        <span className={styles.breadcrumbSep}>/</span>
        <span className={styles.breadcrumbCurrent}>{graph.project_name}</span>
      </div>

      {/* Stats bar */}
      <StatBar graph={graph} />

      {/* Description */}
      {graph.description && (
        <p className={styles.description}>{graph.description}</p>
      )}

      {/* Visualization */}
      {graph.has_html && (
        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Visualization</h2>
          <div className={styles.iframeWrap}>
            <iframe
              src={vizUrl}
              className={styles.iframe}
              title={`Graph visualization — ${graph.project_name}`}
              sandbox="allow-scripts allow-same-origin"
            />
          </div>
        </section>
      )}

      {/* Query */}
      <QuerySection graphId={id} />

      {/* Report */}
      {graph.report_content && (
        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Report</h2>
          <pre className={styles.report}>{graph.report_content}</pre>
        </section>
      )}

      {/* Actions */}
      <div className={styles.actions}>
        <a
          href={downloadUrl}
          download="graph.json"
          className={styles.downloadBtn}
        >
          Download graph.json
        </a>
        <button
          className={styles.deleteBtn}
          onClick={handleDelete}
          disabled={deleting}
        >
          {deleting ? 'Deleting…' : 'Delete project'}
        </button>
      </div>
    </motion.div>
  )
}
