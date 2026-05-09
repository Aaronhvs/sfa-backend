import type { PlayerDetail } from '../../types'

interface Props {
  player: PlayerDetail
}

interface StatItem {
  label: string
  value: string | number
  gold?: boolean
}

export default function StatBar({ player }: Props) {
  const bd = player.breakdown ?? {}

  const goals =
    (bd['goal']?.count ?? 0) + (bd['goal_penalty']?.count ?? 0)

  const assists =
    (bd['assist']?.count ?? 0) + (bd['corner_assist']?.count ?? 0)

  const totalActions = Object.values(bd).reduce(
    (sum, entry) => sum + (entry?.count ?? 0),
    0,
  )

  const items: StatItem[] = [
    { label: 'Partidos', value: player.matches },
    { label: 'Goles', value: goals },
    { label: 'Asist.', value: assists },
    { label: 'Acciones', value: totalActions },
    { label: 'SFA Total', value: Math.round(player.sfa_pts).toLocaleString('es-ES'), gold: true },
    { label: 'Rank global', value: `#${player.global_rank}` },
  ]

  return (
    <div className="card stat-bar">
      {items.map((item) => (
        <div key={item.label} className="stat-bar__item">
          <span className={`stat-bar__num${item.gold ? ' stat-bar__num--gold' : ''}`}>
            {item.value}
          </span>
          <span className="stat-bar__label">{item.label}</span>
        </div>
      ))}
    </div>
  )
}
