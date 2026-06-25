import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { api } from '../api.js'
import styles from './Dashboard.module.css'

// Ambient graph canvas — procedural nodes+edges at very low opacity
// Disabled via prefers-reduced-motion
function AmbientGraph() {
  const canvasRef = useRef(null)
  const rafRef = useRef(null)

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    if (mq.matches) return

    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')

    let W, H, nodes

    function resize() {
      W = canvas.offsetWidth
      H = canvas.offsetHeight
      canvas.width = W
      canvas.height = H
      nodes = Array.from({ length: 28 }, () => ({
        x: Math.random() * W,
        y: Math.random() * H,
        vx: (Math.random() - 0.5) * 0.18,
        vy: (Math.random() - 0.5) * 0.18,
        r: 1.5 + Math.random() * 2,
      }))
    }

    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(canvas)

    function draw() {
      ctx.clearRect(0, 0, W, H)

      // Draw edges between nearby nodes
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[i].x - nodes[j].x
          const dy = nodes[i].y - nodes[j].y
          const dist = Math.sqrt(dx * dx + dy * dy)
          if (dist < 180) {
            const alpha = (1 - dist / 180) * 0.07
            ctx.beginPath()
            ctx.moveTo(nodes[i].x, nodes[i].y)
            ctx.lineTo(nodes[j].x, nodes[j].y)
            ctx.strokeStyle = `rgba(74,240,196,${alpha})`
            ctx.lineWidth = 0.8
            ctx.stroke()
          }
        }
      }

      // Draw nodes
      for (const n of nodes) {
        ctx.beginPath()
        ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2)
        ctx.fillStyle = 'rgba(74,240,196,0.18)'
        ctx.fill()
      }

      // Move nodes
      for (const n of nodes) {
        n.x += n.vx
        n.y += n.vy
        if (n.x < 0 || n.x > W) n.vx *= -1
        if (n.y < 0 || n.y > H) n.vy *= -1
      }

      rafRef.current = requestAnimationFrame(draw)
    }

    draw()

    return () => {
      cancelAnimationFrame(rafRef.current)
      ro.disconnect()
    }
  }, [])

  return <canvas ref={canvasRef} className={styles.ambientCanvas} aria-hidden="true" />
}

function relativeTime(iso) {
  if (!iso) return '—'
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

function StatChip({ label, value }) {
  return (
    <span className={styles.statChip}>
      <span className={styles.statValue}>{value?.toLocaleString() ?? '—'}</span>
      <span className={styles.statLabel}>{label}</span>
    </span>
  )
}

function GraphCard({ graph, index }) {
  return (
    <motion.div
      className={styles.card}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: index * 0.06, ease: 'easeOut' }}
      whileHover={{ y: -2 }}
    >
      <div className={styles.cardTop}>
        <div className={styles.cardHeader}>
          <h3 className={styles.cardName}>{graph.project_name}</h3>
          {graph.has_html ? (
            <span className={styles.badgeLive}>LIVE</span>
          ) : (
            <span className={styles.badgeNoViz}>NO VIZ</span>
          )}
        </div>
        {graph.description && (
          <p className={styles.cardDesc}>{graph.description}</p>
        )}
      </div>

      <div className={styles.cardStats}>
        <StatChip label="nodes" value={graph.node_count} />
        <StatChip label="edges" value={graph.edge_count} />
        <StatChip label="communities" value={graph.community_count} />
      </div>

      <div className={styles.cardFooter}>
        <Link to={`/project/${graph.id}`} className={styles.viewLink}>
          View →
        </Link>
        <span className={styles.updatedAt}>
          Updated {relativeTime(graph.updated_at || graph.created_at)}
        </span>
      </div>
    </motion.div>
  )
}

export default function Dashboard() {
  const [graphs, setGraphs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.listGraphs()
      .then(setGraphs)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className={styles.page}>
      <div className={styles.hero}>
        <AmbientGraph />
        <div className={styles.heroContent}>
          <motion.h1
            className={styles.heading}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, ease: 'easeOut' }}
          >
            Your Graphs
          </motion.h1>
          <motion.p
            className={styles.subtitle}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.08, ease: 'easeOut' }}
          >
            // knowledge graphs stored in the vault
          </motion.p>
        </div>
      </div>

      <div className={styles.body}>
        {loading && (
          <div className={styles.centerState}>
            <span className={styles.loadingDots}>
              <span />
              <span />
              <span />
            </span>
            <p className={styles.loadingText}>Loading graphs…</p>
          </div>
        )}

        {error && (
          <div className={styles.centerState}>
            <p className={styles.errorText}>Could not load graphs: {error}</p>
          </div>
        )}

        {!loading && !error && graphs.length === 0 && (
          <motion.div
            className={styles.emptyState}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.4 }}
          >
            <div className={styles.emptyIcon} aria-hidden="true">
              <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                <circle cx="12" cy="24" r="4" stroke="currentColor" strokeWidth="1.5" strokeOpacity="0.4" />
                <circle cx="36" cy="12" r="4" stroke="currentColor" strokeWidth="1.5" strokeOpacity="0.4" />
                <circle cx="36" cy="36" r="4" stroke="currentColor" strokeWidth="1.5" strokeOpacity="0.4" />
                <line x1="16" y1="24" x2="32" y2="14" stroke="currentColor" strokeWidth="1" strokeOpacity="0.25" />
                <line x1="16" y1="24" x2="32" y2="34" stroke="currentColor" strokeWidth="1" strokeOpacity="0.25" />
              </svg>
            </div>
            <h2 className={styles.emptyHeading}>No graphs yet</h2>
            <p className={styles.emptyBody}>
              Push your first graph with the CLI or upload button.
            </p>
            <Link to="/upload" className={styles.emptyAction}>
              Upload Graph →
            </Link>
          </motion.div>
        )}

        {!loading && !error && graphs.length > 0 && (
          <div className={styles.grid}>
            {graphs.map((g, i) => (
              <GraphCard key={g.id} graph={g} index={i} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
