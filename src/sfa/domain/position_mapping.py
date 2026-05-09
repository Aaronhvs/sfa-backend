from sfa.infrastructure.models.enums import Position

# Mapeo base: API-Football position string → Position enum
BASE_POSITION_MAP: dict[str, Position] = {
    "Attacker":   Position.DEL,
    "Midfielder": Position.MC,
    "Defender":   Position.DC,
    "Goalkeeper": Position.GK,
}

# Diccionario de jugadores conocidos con posición refinada.
# Permite detectar EXT/LAT que API-Football no distingue.
KNOWN_POSITIONS: dict[str, Position] = {
    # La Liga — Extremos
    "Raphinha":              Position.EXT,
    "Lamine Yamal":          Position.EXT,
    "Dani Olmo":             Position.EXT,
    "Vinícius Júnior":       Position.EXT,
    "Rodrygo":               Position.EXT,
    "Nico Williams":         Position.EXT,
    "Ferran Torres":         Position.EXT,
    "Ansu Fati":             Position.EXT,
    "Bernardo Silva":        Position.EXT,
    # La Liga — Laterales
    "Alejandro Balde":       Position.LAT,
    "Jules Koundé":          Position.LAT,
    "Dani Carvajal":         Position.LAT,
    "Lucas Vázquez":         Position.LAT,
    "Ferland Mendy":         Position.LAT,
    # Premier League — Extremos
    "Bukayo Saka":           Position.EXT,
    "Marcus Rashford":       Position.EXT,
    "Gabriel Martinelli":    Position.EXT,
    "Phil Foden":            Position.EXT,
    "Jack Grealish":         Position.EXT,
    "Jarrod Bowen":          Position.EXT,
    "Omar Marmoush":         Position.EXT,
    # Premier League — Laterales
    "Trent Alexander-Arnold": Position.LAT,
    "Reece James":           Position.LAT,
    "Kyle Walker":           Position.LAT,
    "Andrew Robertson":      Position.LAT,
    # Bundesliga — Extremos
    "Jamal Musiala":         Position.EXT,
    "Florian Wirtz":         Position.EXT,
    "Kingsley Coman":        Position.EXT,
    "Leroy Sané":            Position.EXT,
    # Bundesliga — Laterales
    "Alejandro Grimaldo":    Position.LAT,
    "Alphonso Davies":       Position.LAT,
    # Serie A / Ligue 1 — Extremos
    "Rafael Leão":           Position.EXT,
    "Ousmane Dembélé":       Position.EXT,
    # ... se amplía progresivamente
}


def map_position(player_name: str, api_football_position: str) -> Position:
    """Determina la posición SFA de un jugador.

    1. Si el jugador está en KNOWN_POSITIONS, retorna esa posición.
    2. Si no, usa el mapeo base de API-Football.
    3. Si la posición de API-Football no se reconoce, retorna MC por defecto.
    """
    if player_name in KNOWN_POSITIONS:
        return KNOWN_POSITIONS[player_name]
    return BASE_POSITION_MAP.get(api_football_position, Position.MC)
