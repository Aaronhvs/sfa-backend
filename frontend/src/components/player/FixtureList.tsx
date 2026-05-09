import type { PlayerEvent, PlayerFixture } from '../../types'
import FixtureRow from './FixtureRow'

interface Props {
  fixtures: PlayerFixture[]
  events: PlayerEvent[]
}

export default function FixtureList({ fixtures, events }: Props) {
  if (fixtures.length === 0) {
    return (
      <div className="empty-state">
        Sin partidos registrados para esta temporada.
      </div>
    )
  }

  const sorted = [...fixtures].sort(
    (a, b) => new Date(b.played_at).getTime() - new Date(a.played_at).getTime(),
  )

  return (
    <div className="fixture-list">
      {sorted.map((f) => (
        <FixtureRow key={f.fixture_id} fixture={f} events={events} />
      ))}
    </div>
  )
}
