import { NavLink } from 'react-router-dom'

export default function Navbar() {
  return (
    <nav className="navbar">
      <div className="container navbar__inner">
        <NavLink to="/ranking" className="navbar__logo">
          SFA<span>.</span>
        </NavLink>
        <NavLink
          to="/ranking"
          className={({ isActive }) =>
            `navbar__link${isActive ? ' navbar__link--active' : ''}`
          }
        >
          Ranking
        </NavLink>
      </div>
    </nav>
  )
}
