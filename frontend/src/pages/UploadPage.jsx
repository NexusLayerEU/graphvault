import { useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { api } from '../api.js'
import styles from './UploadPage.module.css'

function readFileAsText(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = (e) => resolve(e.target.result)
    reader.onerror = () => reject(new Error('Could not read file'))
    reader.readAsText(file)
  })
}

export default function UploadPage() {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [graphFile, setGraphFile] = useState(null)
  const [htmlFile, setHtmlFile] = useState(null)
  const [reportFile, setReportFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null) // { id, name }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!name.trim() || !graphFile) return

    setLoading(true)
    setError(null)
    setSuccess(null)

    try {
      const graphText = await readFileAsText(graphFile)
      let graphData
      try {
        graphData = JSON.parse(graphText)
      } catch {
        throw new Error('graph.json is not valid JSON. Check the file and try again.')
      }

      const htmlContent = htmlFile ? await readFileAsText(htmlFile) : null
      const reportContent = reportFile ? await readFileAsText(reportFile) : null

      const body = {
        project_name: name.trim(),
        description: description.trim() || undefined,
        graph_data: graphData,
        ...(htmlContent ? { html_content: htmlContent } : {}),
        ...(reportContent ? { report_content: reportContent } : {}),
      }

      const result = await api.pushGraph(body)
      setSuccess({ id: result.id, name: name.trim() })
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  if (success) {
    return (
      <div className={styles.page}>
        <motion.div
          className={styles.successCard}
          initial={{ opacity: 0, scale: 0.97 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.3 }}
        >
          <div className={styles.successIcon} aria-hidden="true">
            <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
              <circle cx="16" cy="16" r="14" stroke="currentColor" strokeWidth="1.5" />
              <polyline points="10,16 14,20 22,12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <h2 className={styles.successHeading}>Graph pushed</h2>
          <p className={styles.successBody}>
            <span className={styles.successName}>{success.name}</span> is now in the vault.
          </p>
          <div className={styles.successActions}>
            <Link to={`/project/${success.id}`} className={styles.primaryBtn}>
              View project →
            </Link>
            <Link to="/" className={styles.ghostBtn}>
              Back to vault
            </Link>
          </div>
        </motion.div>
      </div>
    )
  }

  return (
    <div className={styles.page}>
      <motion.div
        className={styles.card}
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
      >
        <div className={styles.cardHeader}>
          <h1 className={styles.heading}>Push a Graph</h1>
          <p className={styles.subheading}>
            Upload a graph.json exported by graphify, with an optional HTML visualization and report.
          </p>
        </div>

        <div className={styles.tierInfo}>
          <span className={styles.tierItem}>
            <span className={styles.tierBadge}>FREE</span>
            2 graphs · 10k nodes
          </span>
          <span className={styles.tierDivider} />
          <span className={styles.tierItem}>
            <span className={styles.tierBadge}>PRO</span>
            20 graphs
          </span>
          <span className={styles.tierDivider} />
          <span className={styles.tierItem}>
            <span className={styles.tierBadge}>MAX</span>
            Unlimited
          </span>
        </div>

        <form className={styles.form} onSubmit={handleSubmit}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="proj-name">
              Project name <span className={styles.required}>*</span>
            </label>
            <input
              id="proj-name"
              type="text"
              className={styles.input}
              placeholder="my-repo"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              disabled={loading}
            />
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="proj-desc">
              Description
            </label>
            <input
              id="proj-desc"
              type="text"
              className={styles.input}
              placeholder="Optional — what does this graph represent?"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={loading}
            />
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="graph-file">
              graph.json <span className={styles.required}>*</span>
            </label>
            <div className={styles.fileWrap}>
              <input
                id="graph-file"
                type="file"
                accept=".json"
                className={styles.fileInput}
                onChange={(e) => setGraphFile(e.target.files[0] || null)}
                required
                disabled={loading}
              />
              <span className={styles.fileLabel}>
                {graphFile ? graphFile.name : 'Choose file…'}
              </span>
            </div>
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="html-file">
              Interactive HTML
              <span className={styles.optional}> (optional, from graphify)</span>
            </label>
            <div className={styles.fileWrap}>
              <input
                id="html-file"
                type="file"
                accept=".html"
                className={styles.fileInput}
                onChange={(e) => setHtmlFile(e.target.files[0] || null)}
                disabled={loading}
              />
              <span className={styles.fileLabel}>
                {htmlFile ? htmlFile.name : 'Choose file…'}
              </span>
            </div>
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="report-file">
              Graph Report
              <span className={styles.optional}> (optional)</span>
            </label>
            <div className={styles.fileWrap}>
              <input
                id="report-file"
                type="file"
                accept=".md"
                className={styles.fileInput}
                onChange={(e) => setReportFile(e.target.files[0] || null)}
                disabled={loading}
              />
              <span className={styles.fileLabel}>
                {reportFile ? reportFile.name : 'Choose file…'}
              </span>
            </div>
          </div>

          {error && (
            <div className={styles.errorBox} role="alert">
              {error}
            </div>
          )}

          <button
            type="submit"
            className={styles.submitBtn}
            disabled={loading || !name.trim() || !graphFile}
          >
            {loading ? 'Pushing…' : 'Push to GraphVault'}
          </button>
        </form>
      </motion.div>
    </div>
  )
}
