"""
SFA — Descarga fotos de jugadores desde Wikipedia
Busca la imagen principal de cada jugador y guarda la URL en la DB.
"""
import sys, os, time, requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

from backend.db.models import SessionLocal, Player, create_tables
from sqlalchemy import text

WIKI_API = "https://en.wikipedia.org/w/api.php"
HEADERS  = {"User-Agent": "SFA-Bot/1.0 (football stats app)"}

# Nombres alternativos para búsqueda en Wikipedia (cuando el nombre exacto no funciona)
SEARCH_OVERRIDES = {
    "Vinícius Jr":           "Vinicius Junior",
    "Alexander Sørloth":     "Alexander Sørloth",
    "Heung-min Son":         "Son Heung-min",
    "Trent Alexander-Arnold":"Trent Alexander-Arnold",
    "Kevin De Bruyne":       "Kevin De Bruyne",
    "Virgil van Dijk":       "Virgil van Dijk",
    "Ousmane Dembélé":       "Ousmane Dembélé",
    "Florian Wirtz":         "Florian Wirtz",
    "Jamal Musiala":         "Jamal Musiala",
    "Fermín López":          "Fermín López",
    "Artem Dovbyk":          "Artem Dovbyk",
}


def get_wiki_photo(player_name: str) -> str | None:
    """
    Busca la foto principal de un jugador en Wikipedia.
    Devuelve la URL de la imagen o None si no se encuentra.
    """
    search_name = SEARCH_OVERRIDES.get(player_name, player_name)

    try:
        # Paso 1: buscar el artículo
        search_resp = requests.get(WIKI_API, params={
            "action":  "query",
            "list":    "search",
            "srsearch": search_name + " footballer",
            "srlimit": 1,
            "format":  "json",
        }, headers=HEADERS, timeout=10)
        search_data = search_resp.json()

        results = search_data.get("query", {}).get("search", [])
        if not results:
            return None

        page_title = results[0]["title"]

        # Paso 2: obtener la imagen principal del artículo
        img_resp = requests.get(WIKI_API, params={
            "action":    "query",
            "titles":    page_title,
            "prop":      "pageimages",
            "pithumbsize": 300,
            "format":    "json",
        }, headers=HEADERS, timeout=10)
        img_data = img_resp.json()

        pages = img_data.get("query", {}).get("pages", {})
        for page in pages.values():
            thumb = page.get("thumbnail", {})
            if thumb and thumb.get("source"):
                return thumb["source"]

        return None

    except Exception as e:
        print(f"  ⚠️  Error buscando {player_name}: {e}")
        return None


def add_photo_column():
    """Añade la columna photo_url a la tabla players si no existe."""
    db = SessionLocal()
    try:
        db.execute(text("ALTER TABLE players ADD COLUMN photo_url TEXT"))
        db.commit()
        print("✅ Columna photo_url añadida")
    except Exception:
        pass  # Ya existe
    finally:
        db.close()


def fetch_all_photos():
    """Descarga y guarda fotos para todos los jugadores en la DB."""
    print("\n" + "="*55)
    print("📸 SFA — Descargando fotos de Wikipedia")
    print("="*55)

    add_photo_column()

    db = SessionLocal()
    try:
        players = db.query(Player).all()
        total   = len(players)
        found   = 0

        for i, player in enumerate(players, 1):
            print(f"  [{i:02d}/{total}] {player.name:<28}", end=" ")

            photo_url = get_wiki_photo(player.name)

            if photo_url:
                db.execute(
                    text("UPDATE players SET photo_url = :url WHERE id = :id"),
                    {"url": photo_url, "id": player.id}
                )
                db.commit()
                print(f"✅ foto encontrada")
                found += 1
            else:
                print(f"— sin foto")

            time.sleep(0.5)  # Respetar rate limit de Wikipedia

        print(f"\n{'='*55}")
        print(f"✅ {found}/{total} fotos descargadas")
        print(f"   Reinicia el servidor para ver los cambios: python run.py")
        print(f"{'='*55}\n")

    finally:
        db.close()


if __name__ == "__main__":
    fetch_all_photos()
