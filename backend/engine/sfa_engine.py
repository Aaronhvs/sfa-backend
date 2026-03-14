"""
SFA Engine — Motor de cálculo de puntos
Implementa la fórmula: Puntos = base_pts × MIN(MAX(M1×M2×M3×M4, 0.3), 5.0)
"""

# ─── PUNTOS BASE POR TIPO DE ACCIÓN ──────────────────────────────────────────

BASE_POINTS = {
    # Ofensivas
    "goal":                  500,
    "goal_penalty":          300,
    "assist":                300,
    "pre_assist":            120,
    "shot":                  0,     # Se calcula como xG × 400
    "key_pass":              0,     # Se calcula como xA × 250

    # Progresión
    "progressive_pass":       18,
    "progressive_carry":      22,
    "through_ball":           28,

    # Defensivas
    "recovery_opponent_half": 35,
    "recovery_own_half":      20,
    "pressure_success":       25,
    "aerial_duel_won":        15,
    "tackle_won":             15,
    "block":                  30,
    "clearance_goal_line":    80,
}

# Competiciones y sus factores M2
COMPETITION_FACTORS = {
    "Champions League":       1.5,
    "UEFA Champions League":  1.5,
    "Europa League":          1.2,
    "Copa del Rey":           1.2,
    "FA Cup":                 1.2,
    "DFB-Pokal":              1.2,
    "Coupe de France":        1.2,
    "Coppa Italia":           1.2,
    "La Liga":                1.0,
    "Premier League":         1.0,
    "Bundesliga":             1.0,
    "Serie A":                1.0,
    "Ligue 1":                1.0,
    "default":                1.0,
}

# Instancias y sus factores M2
STAGE_FACTORS = {
    "final":       1.8,
    "semi":        1.4,
    "semi_final":  1.4,
    "quarter":     1.2,
    "quarter_final": 1.2,
    "round_of_16": 1.1,
    "group":       1.0,
    "regular":     1.0,
    "default":     1.0,
}


# ─── M1: POSICIÓN DEL RIVAL EN LA TABLA ──────────────────────────────────────

def calc_m1_rival_factor(player_team_pos: int, opponent_pos: int) -> float:
    """
    Calcula M1 basado en la diferencia de posición entre el equipo del jugador
    y el rival. Limitado entre 0.5 y 2.0.

    Ejemplo:
      Mallorca (9°) vs Madrid (1°): distancia = 9-1 = 8 → M1 = 1.0 + 8/20 = 1.40
      Madrid (1°) vs Celta (14°):   distancia = 1-14 = -13 → M1 = 1.0 - 13/20 = 0.35 → piso 0.5
    """
    if player_team_pos is None or opponent_pos is None:
        return 1.0  # Dato no disponible → neutro

    distance = player_team_pos - opponent_pos  # positivo = rival mejor ubicado
    m1 = 1.0 + (distance / 20.0)
    return round(max(0.5, min(2.0, m1)), 3)


# ─── M2: COMPETICIÓN × INSTANCIA ─────────────────────────────────────────────

def calc_m2_competition_factor(competition_name: str, stage: str) -> float:
    """
    Combina el factor de competición con el factor de instancia.
    Ejemplo: Champions + Final = 1.5 × 1.8 = 2.70
    """
    comp_factor  = COMPETITION_FACTORS.get(competition_name, COMPETITION_FACTORS["default"])
    stage_factor = STAGE_FACTORS.get(stage, STAGE_FACTORS["default"])
    return round(comp_factor * stage_factor, 3)


# ─── M3: MINUTO × MARCADOR ───────────────────────────────────────────────────

def calc_m3_moment_factor(
    minute: int,
    score_diff: int,    # diferencia de goles DESDE LA PERSPECTIVA DEL JUGADOR
                        # positivo = su equipo va ganando, negativo = perdiendo
    is_penalty: bool = False
) -> float:
    """
    Combina el minuto de la acción con el contexto del marcador.
    score_diff = goles_equipo_jugador - goles_rival

    Tabla:
      Min 80-90, perdiendo o empate (≤0)  → ×2.5
      Min 70-80, empate (=0)              → ×1.8
      Min 80-90, ganando por 1            → ×1.4
      Min 45-70, empate (=0)              → ×1.2
      Min 1-30,  cualquier marcador       → ×1.0
      Min 80-90, ganando por 2+           → ×0.7
      Penalti                             → ×0.6
    """
    if is_penalty:
        return 0.6

    if minute is None:
        return 1.0

    # Tramo final decisivo
    if minute >= 80:
        if score_diff <= 0:
            return 2.5   # Empate o perdiendo en los últimos 10 min
        elif score_diff == 1:
            return 1.4   # Ganando por 1, aún hay tensión
        else:
            return 0.7   # Partido decidido

    # Tramo 70-80
    if 70 <= minute < 80:
        if score_diff == 0:
            return 1.8
        elif score_diff < 0:
            return 1.6
        else:
            return 1.0

    # Tramo medio 45-70
    if 45 <= minute < 70:
        if score_diff == 0:
            return 1.2
        elif score_diff < 0:
            return 1.3
        else:
            return 1.0

    # Primer tercio 1-45
    return 1.0


# ─── M4: DIFICULTAD DEL DISPARO (PSxG) ───────────────────────────────────────

def calc_m4_psxg_factor(psxg: float = None, action_type: str = "") -> float:
    """
    Solo aplica a goles y disparos. Para el resto de acciones devuelve 1.0.
    Fórmula: M4 = 1.0 + (1.0 - PSxG) × 0.8
    Ejemplo:
      PSxG = 0.05 (ángulo cerrado) → M4 = 1.0 + 0.95×0.8 = 1.76
      PSxG = 0.80 (tap-in)         → M4 = 1.0 + 0.20×0.8 = 1.16
    """
    if action_type not in ("goal", "shot"):
        return 1.0

    if psxg is None:
        return 1.0  # Dato no disponible → neutro

    m4 = 1.0 + (1.0 - psxg) * 0.8
    return round(max(1.0, min(2.0, m4)), 3)


# ─── MOTOR PRINCIPAL ─────────────────────────────────────────────────────────

def calc_base_points(action_type: str, xg: float = None, xa: float = None) -> float:
    """
    Calcula los puntos base según el tipo de acción.
    Los disparos y pases clave se calculan con xG/xA.
    """
    if action_type == "shot" and xg is not None:
        return round(xg * 400, 2)

    if action_type == "key_pass" and xa is not None:
        return round(xa * 250, 2)

    return BASE_POINTS.get(action_type, 0)


def score_event(
    action_type: str,
    player_team_pos: int,
    opponent_pos: int,
    competition_name: str,
    stage: str,
    minute: int,
    score_diff: int,
    is_penalty: bool = False,
    xg: float = None,
    xa: float = None,
    psxg: float = None,
) -> dict:
    """
    Calcula el puntaje SFA completo para una acción individual.
    Devuelve un dict con todos los componentes del cálculo.
    """
    base = calc_base_points(action_type, xg, xa)

    if base == 0:
        return {
            "action_type": action_type,
            "base_pts": 0,
            "m1": 1.0, "m2": 1.0, "m3": 1.0, "m4": 1.0,
            "m_final": 1.0,
            "total_pts": 0,
            "note": "Acción sin puntos base definidos"
        }

    m1 = calc_m1_rival_factor(player_team_pos, opponent_pos)
    m2 = calc_m2_competition_factor(competition_name, stage)
    m3 = calc_m3_moment_factor(minute, score_diff, is_penalty)
    m4 = calc_m4_psxg_factor(psxg, action_type)

    m_raw   = m1 * m2 * m3 * m4
    m_final = round(max(0.3, min(5.0, m_raw)), 3)   # Techo ×5.0 / Piso ×0.3
    total   = round(base * m_final, 2)

    return {
        "action_type":  action_type,
        "base_pts":     base,
        "m1":           m1,
        "m2":           m2,
        "m3":           m3,
        "m4":           m4,
        "m_raw":        round(m_raw, 3),
        "m_final":      m_final,
        "total_pts":    total,
        "capped":       m_raw > 5.0 or m_raw < 0.3,
    }


def score_match(events: list) -> dict:
    """
    Suma todos los puntos de los eventos de un jugador en un partido.
    events: lista de dicts devueltos por score_event()
    """
    total = sum(e["total_pts"] for e in events)
    return {
        "events":        events,
        "events_count":  len(events),
        "total_pts":     round(total, 2),
    }


def score_season(match_scores: list) -> dict:
    """
    Acumula puntos de todos los partidos de una temporada.
    match_scores: lista de dicts devueltos por score_match()
    """
    total   = sum(m["total_pts"] for m in match_scores)
    matches = len(match_scores)
    return {
        "matches_played": matches,
        "total_pts":      round(total, 2),
        "avg_per_match":  round(total / matches, 2) if matches > 0 else 0,
    }


# ─── DEMO ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("SFA ENGINE — Ejemplos de cálculo")
    print("=" * 60)

    # Ejemplo A: Gol épico del Mallorca en la final de Champions
    ej_a = score_event(
        action_type="goal",
        player_team_pos=9,   # Mallorca está 9°
        opponent_pos=1,      # Madrid está 1°
        competition_name="Champions League",
        stage="final",
        minute=89,
        score_diff=-1,       # Iban perdiendo
        psxg=0.08,           # Disparo difícil
    )
    print(f"\n🔥 Gol Mallorca vs Madrid, Final Champions, min 89, perdiendo:")
    print(f"   Base: {ej_a['base_pts']} pts")
    print(f"   M1 (rival): ×{ej_a['m1']}  |  M2 (comp×instancia): ×{ej_a['m2']}")
    print(f"   M3 (minuto×marcador): ×{ej_a['m3']}  |  M4 (PSxG): ×{ej_a['m4']}")
    print(f"   M_raw: ×{ej_a['m_raw']} → M_final (techo 5.0): ×{ej_a['m_final']}")
    print(f"   ✅ TOTAL: {ej_a['total_pts']} SFA pts {'(TECHO APLICADO)' if ej_a['capped'] else ''}")

    # Ejemplo B: Gol fácil del Madrid
    ej_b = score_event(
        action_type="goal",
        player_team_pos=1,
        opponent_pos=14,
        competition_name="La Liga",
        stage="regular",
        minute=15,
        score_diff=2,
        psxg=0.75,
    )
    print(f"\n😴 Gol Madrid vs Celta, Liga, min 15, ganando 2-0:")
    print(f"   M_final: ×{ej_b['m_final']}  →  TOTAL: {ej_b['total_pts']} SFA pts")

    # Ejemplo C: Recuperación de Rodri en Champions Semifinal
    ej_c = score_event(
        action_type="recovery_opponent_half",
        player_team_pos=2,
        opponent_pos=3,
        competition_name="Champions League",
        stage="semi",
        minute=75,
        score_diff=0,
    )
    print(f"\n💪 Recuperación Rodri, Champions Semifinal, min 75, empate:")
    print(f"   M_final: ×{ej_c['m_final']}  →  TOTAL: {ej_c['total_pts']} SFA pts")

    print("\n" + "=" * 60)
