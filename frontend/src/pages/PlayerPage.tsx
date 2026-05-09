import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import type { PlayerDetail, PlayerEvent, PlayerFixture } from '../types'
import { fetchPlayer, fetchPlayerEvents, fetchPlayerFixtures } from '../api/client'
import PlayerHeader from '../components/player/PlayerHeader'
import StatBar from '../components/player/StatBar'
import ActionValues from '../components/player/ActionValues'
import ScoringExplainer from '../components/player/ScoringExplainer'
import FixtureList from '../components/player/FixtureList'

const SEASON = '2024'

export default function PlayerPage() {
  const { id } = useParams<{ id: string }>()

  const [player, setPlayer] = useState<PlayerDetail | null>(null)
  const [events, setEvents] = useState<PlayerEvent[]>([])
  const [fixtures, setFixtures] = useState<PlayerFixture[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    const playerId = Number(id)

    setLoading(true)
    setError(null)

    Promise.all([
      fetchPlayer(playerId, SEASON),
      fetchPlayerEvents(playerId, SEASON),
      fetchPlayerFixtures(playerId, SEASON),
    ])
      .then(([p, ev, fx]) => {
        setPlayer(p)
        setEvents(ev)
        setFixtures(fx)
      })
      .catch((e) => setError(e.message ?? 'Error al cargar el jugador'))
      .finally(() => setLoading(false))
  }, [id])

  if (loading) {
    return (
      <div className="page-container">
        <div className="loading-state">
          <div className="spinner" />
        </div>
      </div>
    )
  }

  if (error || !player) {
    return (
      <div className="page-container">
        <Link to="/ranking" className="back-link">← Volver al ranking</Link>
        <div className="empty-state">{error ?? 'Jugador no encontrado.'}</div>
      </div>
    )
  }

  return (
    <div className="page-container">
      <Link to="/ranking" className="back-link">← Volver al ranking</Link>

      <PlayerHeader player={player} />
      <StatBar player={player} />

      <div className="card mt-24">
        <ActionValues />
        <ScoringExplainer />
      </div>

      <p className="section-title mt-32">Historial de partidos</p>
      <FixtureList fixtures={fixtures} events={events} />
    </div>
  )
}
