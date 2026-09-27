import { useEffect, useState } from 'react'
import './index.css'

const API_BASE = 'http://127.0.0.1:8000'

function KpiCard({ label, value }) {
  return (
    <div className="kpi-card">
      <div className="kpi-value">{value}</div>
      <div className="kpi-label">{label}</div>
    </div>
  )
}

function SignalCard({ signal, missedCount }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="signal-card">
      <button className="signal-card-header" onClick={() => setExpanded(!expanded)}>
        <span className="status-dot" />
        <span className="signal-patient">{signal.patient_id}</span>
        <span className="signal-meta">Dernier contact : {signal.last_event_date}</span>
        <span className="chevron">{expanded ? '▾' : '▸'}</span>
      </button>

      {expanded && (
        <div className="signal-card-body">
          <p className="factors-title">Facteurs contributifs :</p>
          <ul className="factors-list">
            {signal.contributing_factors.map((factor, i) => (
              <li key={i}>{factor}</li>
            ))}
          </ul>
          <p className="review-notice">
            ⓘ Ce signal necessite une revue humaine avant toute action.
          </p>
          <button className="btn-review" disabled>
            Marquer comme revu (a venir)
          </button>
        </div>
      )}
    </div>
  )
}

export default function App() {
  const [patients, setPatients] = useState([])
  const [signals, setSignals] = useState([])
  const [statusFilter, setStatusFilter] = useState('Tous')
  const [minMissed, setMinMissed] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE}/api/patients`).then((r) => r.json()),
      fetch(`${API_BASE}/api/signals`).then((r) => r.json()),
    ])
      .then(([patientsData, signalsData]) => {
        setPatients(patientsData)
        setSignals(signalsData)
        setLoading(false)
      })
      .catch((err) => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  if (loading) return <div className="center-message">Chargement du Care Command Center...</div>
  if (error) {
    return (
      <div className="center-message error">
        Impossible de contacter l'API ({API_BASE}). Verifiez qu'elle tourne bien
        (uvicorn api.main:app --reload --port 8000).
      </div>
    )
  }

  const missedByPatient = Object.fromEntries(
    patients.map((p) => [p.patient_id, p.missed_appointments_count])
  )

  const statuses = ['Tous', ...new Set(signals.map((s) => s.status))]
  const maxMissed = Math.max(0, ...patients.map((p) => p.missed_appointments_count))

  const filtered = signals
    .filter((s) => statusFilter === 'Tous' || s.status === statusFilter)
    .filter((s) => (missedByPatient[s.patient_id] ?? 0) >= minMissed)

  const openCount = signals.filter((s) => s.status === 'open').length
  const signalRate = patients.length
    ? Math.round((100 * signals.length) / patients.length)
    : 0
  const avgDelay = patients.length
    ? Math.round(
        patients.reduce((sum, p) => sum + p.days_since_last_contact, 0) / patients.length
      )
    : 0

  return (
    <div className="app">
      <header className="app-header">
        <h1>Care Command Center</h1>
        <p className="subtitle">
          CancerCare360 — Vue professionnelle du parcours patient. Aucun signal
          ci-dessous n'est un diagnostic : chaque signal necessite une revue
          humaine.
        </p>
      </header>

      <section className="kpi-row">
        <KpiCard label="Patients actifs" value={patients.length} />
        <KpiCard label="Signaux ouverts" value={openCount} />
        <KpiCard label="Taux de signal" value={`${signalRate}%`} />
        <KpiCard label="Delai moyen dernier contact" value={`${avgDelay} j`} />
      </section>

      <section className="filters">
        <label>
          Statut du signal
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            {statuses.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>

        <label>
          Rendez-vous manques (min.) : {minMissed}
          <input
            type="range"
            min="0"
            max={maxMissed}
            value={minMissed}
            onChange={(e) => setMinMissed(Number(e.target.value))}
          />
        </label>
      </section>

      <section className="signal-list">
        <p className="results-count">{filtered.length} signal(aux) correspondant aux filtres.</p>
        {filtered.length === 0 && (
          <p className="empty-state">Aucun signal ne correspond aux filtres selectionnes.</p>
        )}
        {filtered.map((s) => (
          <SignalCard key={s.patient_id} signal={s} missedCount={missedByPatient[s.patient_id]} />
        ))}
      </section>
    </div>
  )
}