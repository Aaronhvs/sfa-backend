import type { PlayerDetail, PlayerEvent, PlayerFixture, RankingResponse } from '../types'

const BASE = '/api/v1'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

export async function fetchRanking(params: {
  season?: string
  position?: string
  competition_id?: number
  limit?: number
}): Promise<RankingResponse> {
  const q = new URLSearchParams()
  if (params.season)        q.set('season', params.season)
  if (params.position)      q.set('position', params.position)
  if (params.competition_id != null) q.set('competition_id', String(params.competition_id))
  if (params.limit != null) q.set('limit', String(params.limit))
  const qs = q.toString()
  return get<RankingResponse>(`/ranking${qs ? `?${qs}` : ''}`)
}

export async function fetchPlayer(id: number, season?: string): Promise<PlayerDetail> {
  const q = season ? `?season=${season}` : ''
  return get<PlayerDetail>(`/players/${id}${q}`)
}

export async function fetchPlayerEvents(id: number, season?: string): Promise<PlayerEvent[]> {
  const q = season ? `?season=${season}` : ''
  return get<PlayerEvent[]>(`/players/${id}/events${q}`)
}

export async function fetchPlayerFixtures(id: number, season?: string): Promise<PlayerFixture[]> {
  const q = season ? `?season=${season}` : ''
  return get<PlayerFixture[]>(`/players/${id}/fixtures${q}`)
}
