import { useState } from 'react'

const CARDS = [
  {
    title: 'Fuerza del rival',
    range: '×0.5 — ×2.0',
    desc: 'Cuanto mejor clasificado esté el rival respecto a tu equipo, mayor es el multiplicador. Marcar contra el lider vale mucho mas que marcar contra el colista.',
  },
  {
    title: 'Competicion y fase',
    range: '×1.0 — ×2.7',
    desc: 'La fase del torneo amplifica la accion. Una final de Champions multiplica mas que una jornada de liga regular. Las ligas nacionales parten de ×1.0.',
  },
  {
    title: 'Momento del gol',
    range: '×0.6 — ×2.5',
    desc: 'Un gol en el minuto 85 perdiendo vale 2.5x. Un penalti tranquilizador con ventaja vale solo 0.6x. El contexto del marcador y el tiempo restante importan.',
  },
  {
    title: 'Dificultad del disparo',
    range: '×1.0 — ×1.8',
    desc: 'Basado en el PSxG (probabilidad de que ese disparo acabe en gol). Un gol de muy bajo PSxG (disparo dificil) recibe mayor multiplicador que un gol cantado.',
  },
]

export default function ScoringExplainer() {
  const [open, setOpen] = useState(false)

  return (
    <div className="mt-24">
      <button
        className="explainer-toggle"
        onClick={() => setOpen((v) => !v)}
      >
        <span>Como se calculan los puntos</span>
        <span className={`explainer-toggle__icon${open ? ' explainer-toggle__icon--open' : ''}`}>
          ▼
        </span>
      </button>

      {open && (
        <div className="explainer-cards">
          {CARDS.map((card) => (
            <div key={card.title} className="card explainer-card">
              <div className="explainer-card__title">{card.title}</div>
              <div className="explainer-card__range">{card.range}</div>
              <div className="explainer-card__desc">{card.desc}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
