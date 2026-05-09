const POSITIONS = ['DEL', 'EXT', 'MC', 'DC', 'LAT'] as const

interface Props {
  position: string
  onPosition: (p: string) => void
}

export default function FilterBar({ position, onPosition }: Props) {
  return (
    <div className="filter-bar">
      <div className="filter-bar__group">
        <button
          className={`filter-btn${position === '' ? ' filter-btn--active' : ''}`}
          onClick={() => onPosition('')}
        >
          Todos
        </button>
        {POSITIONS.map((p) => (
          <button
            key={p}
            className={`filter-btn${position === p ? ' filter-btn--active' : ''}`}
            onClick={() => onPosition(p)}
          >
            {p}
          </button>
        ))}
      </div>
    </div>
  )
}
