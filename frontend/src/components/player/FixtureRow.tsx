import { useState } from 'react'
import type { PlayerEvent, PlayerFixture } from '../../types'

interface Props {
  fixture: PlayerFixture
  events: PlayerEvent[]
}

const EVENT_LABELS: Record<string, string> = {
  goal:         'GOL',
  goal_penalty: 'PENALTI',
  assist:       'ASIST.',
  corner_assist: 'PRE-ASIST.',
  stats:        'ESTADISTICAS',
}

const GOAL_TYPES = new Set(['goal', 'goal_penalty'])

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric' })
}

function teamAbbr(name: string): string {
  return name.split(' ').map((w) => w[0]).slice(0, 3).join('').toUpperCase()
}

function eventContext(e: PlayerEvent): string {
  const parts: string[] = []

  if (e.m1 >= 1.3) parts.push('Rival de elite')
  else if (e.m1 >= 1.1) parts.push('Rival superior')
  else if (e.m1 <= 0.7) parts.push('Rival inferior')

  if (e.stage && e.stage !== 'regular') parts.push(e.stage)

  if (e.score_before) {
    if (e.score_diff != null && e.score_diff < 0) parts.push(`Perdiendo ${e.score_before}`)
    else if (e.score_diff === 0)                  parts.push(`Empate ${e.score_before}`)
    else                                          parts.push(`Ganando ${e.score_before}`)
  }

  if (e.mvisit > 1) parts.push('A domicilio')

  return parts.join(' · ')
}

function EventRows({ events, fixture }: { events: PlayerEvent[]; fixture: PlayerFixture }) {
  const pointEvents = events.filter((e) => e.event_type !== 'stats')
  const statsEvents = events.filter((e) => e.event_type === 'stats')

  return (
    <div className="events-panel">
      {pointEvents.map((e) => (
        <div key={e.id} className="event-row">
          <div>
            <div className="event-row__minute">{e.minute}'</div>
            <div className="event-row__minute-label">min</div>
          </div>

          <div className="event-row__desc">{eventContext(e) || e.competition}</div>

          <span className={`event-type-badge${GOAL_TYPES.has(e.event_type) ? ' event-type-badge--goal' : ''}`}>
            {EVENT_LABELS[e.event_type] ?? e.event_type.toUpperCase()}
          </span>

          <div className="event-row__pts">
            {e.pts.toLocaleString('es-ES', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
            <span style={{ fontSize: '0.6rem', color: 'var(--text-subtle)', marginLeft: 2 }}>pts</span>
          </div>
        </div>
      ))}

      {statsEvents.length > 0 && (
        <div className="events-stats-row">
          <div className="events-stats-item">
            <span className="events-stats-item__num">{fixture.minutes}'</span>
            <span className="events-stats-item__label">Minutos</span>
          </div>
          {fixture.duels_won > 0 && (
            <div className="events-stats-item">
              <span className="events-stats-item__num">{fixture.duels_won}</span>
              <span className="events-stats-item__label">Duelos gan.</span>
            </div>
          )}
          {fixture.dribbles_won > 0 && (
            <div className="events-stats-item">
              <span className="events-stats-item__num">{fixture.dribbles_won}</span>
              <span className="events-stats-item__label">Regates</span>
            </div>
          )}
          {statsEvents.map((e) => (
            <div key={e.id} className="events-stats-item">
              <span className="events-stats-item__num">
                {e.pts.toLocaleString('es-ES', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                <span style={{ fontSize: '0.6rem', color: 'var(--text-subtle)', marginLeft: 2 }}>pts</span>
              </span>
              <span className="events-stats-item__label">SFA stats</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function FixtureRow({ fixture, events }: Props) {
  const [open, setOpen] = useState(false)

  const fixtureEvents = events.filter((e) => e.fixture_id === fixture.fixture_id)

  return (
    <div className="fixture-row">
      <button className="fixture-row__header" onClick={() => setOpen((v) => !v)}>
        <div className="fixture-row__match">
          <div className="fixture-row__shield">
            <div className="team-logo-placeholder">{teamAbbr(fixture.home_team)}</div>
            <span className="fixture-row__vs">vs</span>
            <div className="team-logo-placeholder">{teamAbbr(fixture.away_team)}</div>
          </div>
          <div className="fixture-row__teams">
            <div className="fixture-row__matchup">
              {fixture.home_team} vs {fixture.away_team}
            </div>
            <div className="fixture-row__meta">
              {fixture.competition} &middot; {fixture.stage} &middot; {formatDate(fixture.played_at)}
            </div>
          </div>
        </div>

        <div>
          <span className="fixture-row__pts">
            {fixture.sfa_pts.toLocaleString('es-ES', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
          </span>
          <span className="fixture-row__pts-label">pts</span>
        </div>

        <span className={`fixture-row__chevron${open ? ' fixture-row__chevron--open' : ''}`}>
          ▼
        </span>
      </button>

      {open && fixtureEvents.length > 0 && (
        <EventRows events={fixtureEvents} fixture={fixture} />
      )}

      {open && fixtureEvents.length === 0 && (
        <div className="events-panel" style={{ padding: '16px 18px', color: 'var(--text-subtle)', fontSize: '0.8rem' }}>
          Sin eventos registrados para este partido.
        </div>
      )}
    </div>
  )
}
