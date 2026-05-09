import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Navbar from './components/layout/Navbar'
import PlayerPage from './pages/PlayerPage'
import RankingPage from './pages/RankingPage'

export default function App() {
  return (
    <BrowserRouter>
      <Navbar />
      <main className="main-content">
        <Routes>
          <Route path="/" element={<Navigate to="/ranking" replace />} />
          <Route path="/ranking" element={<RankingPage />} />
          <Route path="/player/:id" element={<PlayerPage />} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}
