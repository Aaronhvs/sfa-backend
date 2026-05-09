import { useEffect, useState } from 'react'
import type { RankedPlayer } from '../types'
import { fetchRanking } from '../api/client'
import FilterBar from '../components/ranking/FilterBar'
import RankingRow from '../components/ranking/RankingRow'

const SEASON = '2024'

export default function RankingPage() {
  const [position, setPosition] = useState<string | undefined>(undefined)
  const [players, setPlayers] = useState<RankedPlayer[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchRanking({ season: SEASON, position, limit: 100 })
      .then((data) => setPlayers(data.ranking))
      .catch((e) => setError(e.message ?? 'Error al cargar el ranking'))
      .finally(() => setLoading(false))
  }, [position])

  return (
    <div className="page-container">
      <div className="ranking-header">
        <h1 className="ranking-title">Ranking Global</h1>
        <p className="ranking-subtitle">Temporada {SEASON} · Puntuación SFA</p>
      </div>

      <FilterBar position={position ?? ''} onPosition={(p) => setPosition(p || undefined)} />

      {loading && (
        <div className="loading-state">
          <div className="spinner" />
        </div>
      )}

      {!loading && error && (
        <div className="empty-state">{error}</div>
      )}

      {!loading && !error && players.length === 0 && (
        <div className="empty-state">Sin jugadores para los filtros seleccionados.</div>
      )}

      {!loading && !error && players.length > 0 && (
        <div className="ranking-table">
          <div className="ranking-cols">
            <span>#</span>
            <span>Jugador</span>
            <span>Competición</span>
            <span>Pos.</span>
            <span>SFA pts</span>
          </div>
          {players.map((p) => (
            <RankingRow key={p.id} player={p} />
          ))}
        </div>
      )}
    </div>
  )
}
