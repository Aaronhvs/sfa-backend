import { Link } from 'react-router-dom'
import type { RankedPlayer } from '../../types'

interface Props {
  player: RankedPlayer
}

function initials(name: string): string {
  return name.split(' ').map((w) => w[0]).slice(0, 2).join('').toUpperCase()
}

function formatPts(pts: number): string {
  return pts.toLocaleString('es-ES', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

export default function RankingRow({ player }: Props) {
  const isTop = player.rank <= 3

  return (
    <Link to={`/player/${player.id}`} className="ranking-row">
      <span className={`ranking-row__rank${isTop ? ' ranking-row__rank--top' : ''}`}>
        {player.rank}
      </span>

      {player.photo_url ? (
        <img
          src={player.photo_url}
          alt={player.name}
          className="ranking-row__photo"
          onError={(e) => {
            e.currentTarget.style.display = 'none'
          }}
        />
      ) : (
        <div className="ranking-row__photo-placeholder">{initials(player.name)}</div>
      )}

      <div className="ranking-row__info">
        <div className="ranking-row__name">{player.name}</div>
        <div className="ranking-row__team">{player.team}</div>
      </div>

      <div className="ranking-row__competition">{player.competition}</div>

      <div>
        <span className="pos-badge">{player.position}</span>
      </div>

      <div className="ranking-row__pts">
        {formatPts(player.sfa_pts)}
        <span style={{ fontSize: '0.6rem', color: 'var(--gold-dim)', marginLeft: 4 }}>pts</span>
      </div>
    </Link>
  )
}
