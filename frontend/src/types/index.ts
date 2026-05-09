export interface RankedPlayer {
  rank: number
  id: number
  name: string
  team: string
  position: string
  competition: string
  sfa_pts: number
  matches: number
  photo_url: string | null
}

export interface RankingResponse {
  season: string
  total: number
  ranking: RankedPlayer[]
}

export interface BreakdownEntry {
  count: number
  pts: number
}

export interface PlayerDetail {
  id: number
  name: string
  team: string
  position: string
  competition: string
  sfa_pts: number
  matches: number
  photo_url: string | null
  global_rank: number
  season: string
  breakdown: Record<string, BreakdownEntry> | null
  competitions: string[]
}

export interface PlayerEvent {
  id: number
  competition: string
  stage: string
  fixture_id: number
  home_team: string
  away_team: string
  played_at: string
  minute: number
  event_type: string
  score_before: string | null
  score_diff: number | null
  m1: number
  m2: number
  m3: number
  m4: number
  mvisit: number
  pts: number
}

export interface PlayerFixture {
  fixture_id: number
  competition: string
  stage: string
  home_team: string
  away_team: string
  played_at: string
  sfa_pts: number
  events_count: number
  minutes: number
  duels_won: number
  dribbles_won: number
}
