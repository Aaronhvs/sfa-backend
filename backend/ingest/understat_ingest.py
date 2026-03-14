"""
SFA — Ingesta de datos desde Understat
Descarga xG por disparo y PSxG para el multiplicador M4.
"""
import requests
import json
import re
import pandas as pd
import logging

log = logging.getLogger(__name__)

UNDERSTAT_BASE = "https://understat.com"

LEAGUE_MAP = {
    "La Liga":        "La_liga",
    "Premier League": "EPL",
    "Bundesliga":     "Bundesliga",
    "Serie A":        "Serie_A",
    "Ligue 1":        "Ligue_1",
}


def _extract_json_from_page(html: str, var_name: str) -> list:
    """Extrae JSON embebido en las páginas de Understat."""
    pattern = rf"var\s+{var_name}\s*=\s*JSON\.parse\('(.+?)'\)"
    match = re.search(pattern, html)
    if not match:
        return []
    raw = match.group(1)
    # Decodificar escapes de Unicode
    raw = raw.encode("utf-8").decode("unicode_escape")
    return json.loads(raw)


def fetch_league_players(league: str = "La_liga", season: int = 2024) -> pd.DataFrame:
    """
    Descarga stats de jugadores de Understat para una liga y temporada.
    Incluye xG, xA, goles, disparos para calcular xG/disparo.
    """
    url = f"{UNDERSTAT_BASE}/league/{league}/{season}"
    log.info(f"📥 Understat: {url}")

    try:
        resp = requests.get(url, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (compatible; SFA-Bot/1.0)"
        })
        resp.raise_for_status()
        players_data = _extract_json_from_page(resp.text, "playersData")

        if not players_data:
            log.warning("⚠️  No se encontraron datos de jugadores en Understat")
            return pd.DataFrame()

        df = pd.DataFrame(players_data)

        # Renombrar columnas a nombres internos SFA
        rename = {
            "player_name": "player",
            "team_title":  "team",
            "goals":       "goals_understat",
            "assists":     "assists_understat",
            "xG":          "xg_understat",
            "xA":          "xa_understat",
            "shots":       "shots_understat",
            "time":        "minutes_understat",
            "npg":         "np_goals",
            "npxG":        "npxg_understat",
        }
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

        # Calcular xG por disparo (proxy para M4 cuando no hay PSxG exacto)
        if "xg_understat" in df.columns and "shots_understat" in df.columns:
            df["xg_per_shot"] = (
                pd.to_numeric(df["xg_understat"], errors="coerce") /
                pd.to_numeric(df["shots_understat"], errors="coerce").replace(0, 1)
            ).round(3)

        log.info(f"✅ Understat: {len(df)} jugadores descargados")
        return df

    except Exception as e:
        log.error(f"❌ Error en Understat: {e}")
        return pd.DataFrame()


def fetch_player_shots(player_id: str) -> pd.DataFrame:
    """
    Descarga los datos de cada disparo individual de un jugador.
    Cada fila incluye: xG, resultado, minuto, situación.
    Esto permite calcular M4 (PSxG) con precisión por disparo.
    """
    url = f"{UNDERSTAT_BASE}/player/{player_id}"
    log.info(f"📥 Understat shots: player {player_id}")

    try:
        resp = requests.get(url, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (compatible; SFA-Bot/1.0)"
        })
        resp.raise_for_status()
        shots_data = _extract_json_from_page(resp.text, "shotsData")

        if not shots_data:
            return pd.DataFrame()

        df = pd.DataFrame(shots_data)

        # Columnas relevantes para SFA
        cols_map = {
            "match_id":    "match_id",
            "minute":      "minute",
            "result":      "result",       # "Goal", "MissedShots", "SavedShot", etc.
            "X":           "x_pos",
            "Y":           "y_pos",
            "xG":          "xg",
            "situation":   "situation",    # "OpenPlay", "Penalty", "FromCorner", etc.
            "shotType":    "shot_type",
            "season":      "season",
        }
        df = df.rename(columns={k: v for k, v in cols_map.items() if k in df.columns})

        # Marcar penaltis
        if "situation" in df.columns:
            df["is_penalty"] = df["situation"] == "Penalty"

        # El PSxG de Understat es el xG del disparo — usamos eso como proxy
        if "xg" in df.columns:
            df["psxg"] = pd.to_numeric(df["xg"], errors="coerce")

        log.info(f"✅ {len(df)} disparos descargados para jugador {player_id}")
        return df

    except Exception as e:
        log.error(f"❌ Error en shots de jugador {player_id}: {e}")
        return pd.DataFrame()


def merge_fbref_understat(fbref_df: pd.DataFrame, understat_df: pd.DataFrame) -> pd.DataFrame:
    """
    Une los datos de FBref y Understat por nombre de jugador.
    Usa los datos de Understat para enriquecer M4 cuando estén disponibles.
    Cuando no hay match exacto, deja M4 = 1.0 (neutro).
    """
    if fbref_df.empty:
        return understat_df if not understat_df.empty else pd.DataFrame()

    if understat_df.empty:
        return fbref_df

    # Normalizar nombres para el merge
    fbref_df["_name_key"]      = fbref_df["player"].str.lower().str.strip()
    understat_df["_name_key"]  = understat_df["player"].str.lower().str.strip()

    merged = fbref_df.merge(
        understat_df[["_name_key", "xg_understat", "xa_understat", "xg_per_shot"]],
        on="_name_key",
        how="left"
    )
    merged = merged.drop(columns=["_name_key"])

    # Priorizar xG de FBref, usar Understat como fallback
    if "xg" not in merged.columns:
        merged["xg"] = merged.get("xg_understat", 0)

    if "xa" not in merged.columns:
        merged["xa"] = merged.get("xa_understat", 0)

    log.info(f"✅ Merge FBref+Understat: {len(merged)} jugadores")
    return merged


if __name__ == "__main__":
    df = fetch_league_players("La_liga", 2024)
    if not df.empty:
        print(df[["player", "team", "xg_understat", "xa_understat", "xg_per_shot"]].head(10).to_string())
    else:
        print("⚠️  Sin datos de Understat")
