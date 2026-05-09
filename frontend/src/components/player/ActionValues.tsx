const ACTIONS = [
  { name: 'Gol', pts: '500' },
  { name: 'Asistencia', pts: '300' },
  { name: 'Pre-asistencia', pts: '120' },
  { name: 'Duelo ganado', pts: '25' },
  { name: 'Regate', pts: '20' },
  { name: 'Recuperación', pts: '30' },
]

export default function ActionValues() {
  return (
    <>
      <p className="section-title">Valor de cada acción</p>
      <div className="action-grid">
        {ACTIONS.map((a) => (
          <div key={a.name} className="action-item">
            <span className="action-item__name">{a.name}</span>
            <span className="action-item__pts">{a.pts} <span style={{ fontSize: '0.65rem', color: 'var(--gold-dim)' }}>pts</span></span>
          </div>
        ))}
      </div>
    </>
  )
}
