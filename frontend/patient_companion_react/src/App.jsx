import { useEffect, useState } from 'react'
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import './index.css'

const API_BASE = 'http://127.0.0.1:8000'

// Icones par defaut Leaflet (contournement d'un bug connu avec les bundlers)
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})

function AccessibilitySection({ patientId }) {
  const [data, setData] = useState(null)

  useEffect(() => {
    if (!patientId) return
    fetch(`${API_BASE}/api/patient/${patientId}/accessibility`)
      .then((r) => r.json())
      .then(setData)
  }, [patientId])

  if (!data || !data.primary_center) return null

  const center = [data.home_latitude, data.home_longitude]

  return (
    <div className="accessibility-card">
      <h2>Accessibilite aux soins</h2>
      <p className="notes-hint">
        Position approximative estimee a des fins de demonstration (aucune
        adresse reelle n'est collectee).
      </p>

      <div className="accessibility-stats">
        <div>
          <span className="stat-value">{data.primary_center.distance_km} km</span>
          <span className="stat-label">Distance jusqu'a mon centre</span>
        </div>
        <div>
          <span className="stat-value">{data.travel_time_min} min</span>
          <span className="stat-label">Temps de trajet estime</span>
        </div>
        <div>
          <span className="stat-value">{data.accessibility_score}/100</span>
          <span className="stat-label">Score d'accessibilite</span>
        </div>
      </div>

      {!data.uses_nearest_center && (
        <p className="accessibility-hint">
          ⓘ Un centre plus proche existe : {data.nearest_center.name} a{' '}
          {data.nearest_center.distance_km} km.
        </p>
      )}

      <MapContainer center={center} zoom={9} style={{ height: '280px', borderRadius: '8px' }}>
        <TileLayer
          attribution='&copy; OpenStreetMap contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <Marker position={center}>
          <Popup>Domicile (approximatif)</Popup>
        </Marker>
        <Marker position={[data.primary_center.latitude, data.primary_center.longitude]}>
          <Popup>{data.primary_center.name} (mon centre)</Popup>
        </Marker>
        {!data.uses_nearest_center && (
          <Marker position={[data.nearest_center.latitude, data.nearest_center.longitude]}>
            <Popup>{data.nearest_center.name} (plus proche)</Popup>
          </Marker>
        )}
      </MapContainer>
    </div>
  )
}

const EVENT_LABELS = {
  appointment: 'Rendez-vous',
  lab_result: 'Resultat de laboratoire',
  treatment: 'Traitement',
  hospitalization: 'Hospitalisation',
  discharge: 'Sortie',
  followup: 'Suivi',
}

const STATUS_LABELS = {
  scheduled: 'Planifie',
  completed: 'Termine',
  missed: 'Manque',
  cancelled: 'Annule',
}

function TimelineStep({ event }) {
  return (
    <div className={`timeline-step status-${event.status}`}>
      <div className="timeline-dot" />
      <div className="timeline-content">
        <p className="timeline-date">{event.event_timestamp}</p>
        <p className="timeline-title">{EVENT_LABELS[event.event_type] || event.event_type}</p>
        <p className="timeline-meta">{event.center_name}</p>
        <span className={`timeline-badge badge-${event.status}`}>
          {STATUS_LABELS[event.status] || event.status}
        </span>
      </div>
    </div>
  )
}

function NotesBook({ patientId }) {
  const [notes, setNotes] = useState([])
  const [newNote, setNewNote] = useState('')
  const [saving, setSaving] = useState(false)

  function loadNotes() {
    fetch(`${API_BASE}/api/patient/${patientId}/notes`)
      .then((r) => r.json())
      .then(setNotes)
  }

  useEffect(() => {
    loadNotes()
  }, [patientId])

  async function handleAdd() {
    if (!newNote.trim()) return
    setSaving(true)
    await fetch(`${API_BASE}/api/patient/${patientId}/notes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: newNote }),
    })
    setNewNote('')
    setSaving(false)
    loadNotes()
  }

  return (
    <div className="notes-card">
      <h2>Questions pour mon medecin</h2>
      <p className="notes-hint">
        Notez ici vos questions ou symptomes a discuter lors de votre prochain
        rendez-vous. Ces notes sont personnelles, elles ne sont pas analysees
        automatiquement.
      </p>

      <div className="notes-input-row">
        <textarea
          value={newNote}
          onChange={(e) => setNewNote(e.target.value)}
          placeholder="Ex: J'ai ressenti une fatigue inhabituelle depuis 3 jours..."
          rows={3}
        />
        <button onClick={handleAdd} disabled={saving || !newNote.trim()}>
          {saving ? 'Enregistrement...' : 'Ajouter'}
        </button>
      </div>

      <ul className="notes-list">
        {notes.map((n, i) => (
          <li key={i}>
            <span className="note-date">{n.created_at}</span>
            <p>{n.text}</p>
          </li>
        ))}
        {notes.length === 0 && <p className="notes-empty">Aucune note pour l'instant.</p>}
      </ul>
    </div>
  )
}

export default function App() {
  const [patientIds, setPatientIds] = useState([])
  const [selectedPatient, setSelectedPatient] = useState(null)
  const [journey, setJourney] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch(`${API_BASE}/api/patient-ids`)
      .then((r) => r.json())
      .then((ids) => {
        setPatientIds(ids)
        setSelectedPatient(ids[0])
        setLoading(false)
      })
      .catch((err) => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  useEffect(() => {
    if (!selectedPatient) return
    fetch(`${API_BASE}/api/patient/${selectedPatient}/journey`)
      .then((r) => r.json())
      .then(setJourney)
  }, [selectedPatient])

  if (loading) return <div className="center-message">Chargement...</div>
  if (error) {
    return (
      <div className="center-message error">
        Impossible de contacter l'API ({API_BASE}). Verifiez qu'elle tourne bien
        (uvicorn api.main:app --reload --port 8000) et que ce port ({window.location.port})
        est bien autorise dans la configuration CORS de l'API.
      </div>
    )
  }

  const nextAppointment = journey
    .filter((e) => e.event_type === 'appointment' && e.status === 'scheduled')
    .sort((a, b) => new Date(a.event_timestamp) - new Date(b.event_timestamp))[0]

  return (
    <div className="companion-app">
      <div className="patient-switcher">
        <label>
          Patient (demo — pas d'authentification) :
          <select value={selectedPatient || ''} onChange={(e) => setSelectedPatient(e.target.value)}>
            {patientIds.map((id) => (
              <option key={id} value={id}>{id}</option>
            ))}
          </select>
        </label>
      </div>

      <header className="companion-header">
        <h1>Mon parcours de soin</h1>
        <p className="companion-sub">CancerCare360 — Espace patient</p>
      </header>

      <section className="next-appointment-card">
        {nextAppointment ? (
          <>
            <p className="next-label">Prochain rendez-vous</p>
            <p className="next-date">{nextAppointment.event_timestamp}</p>
            <p className="next-meta">{nextAppointment.center_name}</p>
          </>
        ) : (
          <p className="next-empty">Aucun rendez-vous a venir n'est planifie pour le moment.</p>
        )}
      </section>

      <section className="timeline-section">
        <h2>Mes etapes</h2>
        <div className="timeline">
          {journey.map((event) => (
            <TimelineStep key={event.event_id} event={event} />
          ))}
        </div>
      </section>

      <NotesBook patientId={selectedPatient} />

      <AccessibilitySection patientId={selectedPatient} />
    </div>
  )
}