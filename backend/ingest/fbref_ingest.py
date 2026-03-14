"""
SFA — Scraper directo de FBref
Usa requests + BeautifulSoup sin soccerdata.
Descarga stats de jugadores y tabla de posiciones.
"""
import requests
import pandas as pd
from bs4 import BeautifulSoup
import time
import logging

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.8,en-US;q=0.5",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


LEAGUE_URLS = {
    "La Liga":        "https://fbref.com/en/comps/12/stats/La-Liga-Stats",
    "Premier League": "https://fbref.com/en/comps/9/stats/Premier-League-Stats",
    "Champions League": "https://fbref.com/en/comps/8/stats/Champions-League-Stats",
    "Bundesliga":     "https://fbref.com/en/comps/20/stats/Bundesliga-Stats",
    "Serie A":        "https://fbref.com/en/comps/11/stats/Serie-A-Stats",
    "Ligue 1":        "https://fbref.com/en/comps/13/stats/Ligue-1-Stats",
}

STANDING_URLS = {
    "La Liga":        "https://fbref.com/en/comps/12/La-Liga-Stats",
    "Premier League": "https://fbref.com/en/comps/9/Premier-League-Stats",
    "Champions League": "https://fbref.com/en/comps/8/Champions-League-Stats",
}


def _get_soup(url: str, wait: float = 4.0) -> BeautifulSoup:
    """Descarga una página y devuelve BeautifulSoup. Espera entre requests."""
    time.sleep(wait)
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return BeautifulSoup(resp.content, "html.parser")


def fetch_player_stats(league: str = "La Liga") -> pd.DataFrame:
    """
    Descarga la tabla estándar de jugadores de FBref para una liga.
    Incluye: goles, asistencias, xG, xA, minutos.
    """
    url = LEAGUE_URLS.get(league)
    if not url:
        log.error(f"Liga no encontrada: {league}")
        return pd.DataFrame()

    log.info(f"📥 FBref stats: {league}")
    try:
        soup = _get_soup(url)

        # La tabla principal de jugadores en FBref tiene id="stats_standard"
        table = soup.find("table", {"id": "stats_standard"})
        if not table:
            # Intentar con el primer table grande
            tables = soup.find_all("table")
            table = tables[0] if tables else None

        if not table:
            log.warning(f"⚠️  No se encontró tabla en {league}")
            return pd.DataFrame()

        df = pd.read_html(str(table))[0]

        # Aplanar columnas multi-nivel si las hay
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [' '.join(col).strip() for col in df.columns]

        # Limpiar filas de encabezado repetidas
        df = df[df.iloc[:, 0] != df.columns[0]]
        df = df.dropna(subset=[df.columns[0]])

        # Renombrar columnas clave
        col_map = {}
        for col in df.columns:
            cl = col.lower()
            if "player" in cl or "jugador" in cl:
                col_map[col] = "player"
            elif col.strip() == "Squad" or "squad" in cl or "team" in cl or "equipo" in cl:
                col_map[col] = "team"
            elif col.strip() == "Pos" or cl == "pos":
                col_map[col] = "pos"
            elif col.strip() == "Min" or "min" in cl and "90" not in cl:
                col_map[col] = "minutes"
            elif col.strip() == "Gls" or cl in ("gls", "goals", "goles"):
                col_map[col] = "goals"
            elif col.strip() == "Ast" or cl in ("ast", "assists", "asistencias"):
                col_map[col] = "assists"
            elif col.strip() == "xG" or cl == "xg":
                col_map[col] = "xg"
            elif col.strip() == "xAG" or col.strip() == "xA" or cl in ("xag", "xa"):
                col_map[col] = "xa"
            elif "prog" in cl and "pass" in cl or col.strip() == "PrgP":
                col_map[col] = "progressive_passes"
            elif "prog" in cl and "carr" in cl or col.strip() == "PrgC":
                col_map[col] = "progressive_carries"

        df = df.rename(columns=col_map)

        # Asegurar columnas mínimas
        for c in ["player", "team", "pos", "goals", "assists", "xg", "xa",
                  "progressive_passes", "progressive_carries", "minutes"]:
            if c not in df.columns:
                df[c] = 0

        # Convertir a numérico
        for c in ["goals", "assists", "xg", "xa", "progressive_passes",
                  "progressive_carries", "minutes"]:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

        # Filtrar filas sin jugador
        df = df[df["player"].notna() & (df["player"] != "") & (df["player"] != "Player")]
        df["league"] = league

        log.info(f"✅ {league}: {len(df)} jugadores")
        return df[["player", "team", "pos", "league", "minutes",
                   "goals", "assists", "xg", "xa",
                   "progressive_passes", "progressive_carries"]].copy()

    except Exception as e:
        log.error(f"❌ Error en {league}: {e}")
        return pd.DataFrame()


def fetch_standings(league: str = "La Liga") -> pd.DataFrame:
    """Descarga la tabla de posiciones de una liga."""
    url = STANDING_URLS.get(league, LEAGUE_URLS.get(league))
    if not url:
        return pd.DataFrame()

    log.info(f"📥 FBref standings: {league}")
    try:
        soup = _get_soup(url)

        # Buscar tabla de standings
        table = soup.find("table", {"id": lambda x: x and "standings" in x.lower()})
        if not table:
            tables = soup.find_all("table")
            table = tables[0] if tables else None

        if not table:
            return pd.DataFrame()

        df = pd.read_html(str(table))[0]
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [' '.join(col).strip() for col in df.columns]

        # Encontrar columna de equipo y posición
        team_col = next((c for c in df.columns if "squad" in c.lower() or "team" in c.lower()), None)
        rank_col = next((c for c in df.columns if c.strip() in ("Rk", "#", "Pos", "Rank")), df.columns[0])

        if not team_col:
            return pd.DataFrame()

        result = pd.DataFrame({
            "team":     df[team_col],
            "position": pd.to_numeric(df[rank_col], errors="coerce"),
            "league":   league,
        }).dropna(subset=["team", "position"])

        result["position"] = result["position"].astype(int)
        log.info(f"✅ Standings {league}: {len(result)} equipos")
        return result

    except Exception as e:
        log.error(f"❌ Error standings {league}: {e}")
        return pd.DataFrame()


def run_full_ingestion(leagues: list = None) -> dict:
    """Ingesta completa para todas las ligas indicadas."""
    if leagues is None:
        leagues = ["La Liga", "Premier League"]

    all_players  = []
    all_standings = []

    for league in leagues:
        df = fetch_player_stats(league)
        if not df.empty:
            all_players.append(df)

        st = fetch_standings(league)
        if not st.empty:
            all_standings.append(st)

        time.sleep(3)  # Respetar rate limit de FBref

    players_df   = pd.concat(all_players,   ignore_index=True) if all_players   else pd.DataFrame()
    standings_df = pd.concat(all_standings, ignore_index=True) if all_standings else pd.DataFrame()

    return {
        "players":   players_df,
        "standings": standings_df,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    result = run_full_ingestion(["La Liga"])
    df = result["players"]
    if not df.empty:
        print(f"\n✅ {len(df)} jugadores")
        print(df[["player", "team", "goals", "xg", "xa"]].head(10).to_string())
    else:
        print("⚠️  Sin datos")