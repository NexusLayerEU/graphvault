import { Link } from 'react-router-dom'
import styles from './Nav.module.css'

function decodeJwtEmail(token) {
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    return payload.sub || payload.email || null
  } catch {
    return null
  }
}

export default function Nav() {
  const token = localStorage.getItem('gv_token')
  const email = token ? decodeJwtEmail(token) : null

  return (
    <nav className={styles.nav}>
      <Link to="/" className={styles.logo}>
        <span className={styles.logoGlyph}>⬡</span>
        <span className={styles.logoText}>GraphVault</span>
      </Link>

      <div className={styles.right}>
        {email && (
          <span className={styles.email}>{email}</span>
        )}
        <Link to="/upload" className={styles.uploadBtn}>
          Upload Graph
        </Link>
      </div>
    </nav>
  )
}
