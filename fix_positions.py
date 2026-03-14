"""
fix_positions.py — Corrige posiciones de jugadores conocidos en la DB.
Ejecutar: python fix_positions.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backend.db.models import SessionLocal, Player

KNOWN_POSITIONS = {
    # La Liga
    "Raphinha":              "EXT",
    "Lamine Yamal":          "EXT",
    "Dani Olmo":             "EXT",
    "Ferran Torres":         "EXT",
    "Ansu Fati":             "EXT",
    "Robert Lewandowski":    "DEL",
    "Antoine Griezmann":     "DEL",
    "Álvaro Morata":         "DEL",
    "Vinícius Júnior":       "EXT",
    "Rodrygo":               "EXT",
    "Kylian Mbappé":         "DEL",
    "Nico Williams":         "EXT",
    "Alejandro Balde":       "LAT",
    "Ferland Mendy":         "LAT",
    "David Alaba":           "DC",
    "Thibaut Courtois":      "GK",
    "Andriy Lunin":          "GK",
    "Marc-André ter Stegen": "GK",
    "Iñaki Peña":            "GK",
    "Jules Koundé":          "LAT",
    "Dani Carvajal":         "LAT",
    "Lucas Vázquez":         "LAT",
    "Fede Valverde":         "MC",
    "Pedri":                 "MC",
    "Gavi":                  "MC",
    "Luka Modric":           "MC",
    "Toni Kroos":            "MC",
    "Aurélien Tchouaméni":   "MC",
    "Ronald Araújo":         "DC",
    "Pau Cubarsí":           "DC",
    "Éder Militão":          "DC",
    "Antonio Rüdiger":       "DC",
    "Artem Dovbyk":          "DEL",
    "Dušan Vlahović":        "DEL",
    # Premier League
    "Mohamed Salah":         "DEL",
    "Erling Haaland":        "DEL",
    "Alexander Isak":        "DEL",
    "Ollie Watkins":         "DEL",
    "Dominic Solanke":       "DEL",
    "Marcus Rashford":       "EXT",
    "Bukayo Saka":           "EXT",
    "Gabriel Martinelli":    "EXT",
    "Phil Foden":            "EXT",
    "Jack Grealish":         "EXT",
    "Omar Marmoush":         "EXT",
    "Jarrod Bowen":          "EXT",
    "Trent Alexander-Arnold":"LAT",
    "Reece James":           "LAT",
    "Kyle Walker":           "LAT",
    "Andrew Robertson":      "LAT",
    "Virgil van Dijk":       "DC",
    "William Saliba":        "DC",
    "Rúben Dias":            "DC",
    "Alisson":               "GK",
    "Ederson":               "GK",
    "David Raya":            "GK",
    "Bernardo Silva":        "EXT",
    "Kevin De Bruyne":       "MC",
    "Rodri":                 "MC",
    # Bundesliga
    "Harry Kane":            "DEL",
    "Jamal Musiala":         "EXT",
    "Kingsley Coman":        "EXT",
    "Leroy Sané":            "EXT",
    "Florian Wirtz":         "EXT",
    "Granit Xhaka":          "MC",
    "Alejandro Grimaldo":    "LAT",
    "Alphonso Davies":       "LAT",
    "Dayot Upamecano":       "DC",
    "Manuel Neuer":          "GK",
    "Oliver Baumann":        "GK",
    # Serie A
    "Mateo Retegui":         "DEL",
    "Romelu Lukaku":         "DEL",
    "Rafael Leão":           "EXT",
    "Khvicha Kvaratskhelia": "EXT",
    "Federico Chiesa":       "EXT",
    "Gianluigi Donnarumma":  "GK",
    "Mike Maignan":          "GK",
    "Yann Sommer":           "GK",
    "Alessandro Bastoni":    "DC",
    "Giorgio Scalvini":      "DC",
    "Stefan de Vrij":        "DC",
    "Benjamin Pavard":       "LAT",
    "Achraf Hakimi":         "LAT",
    # Ligue 1
    "Kylian Mbappé":         "DEL",
    "Bradley Barcola":       "EXT",
    "Vitinha":               "MC",
    "Achraf Hakimi":         "LAT",
    "Gianluigi Donnarumma":  "GK",
}

def fix():
    db = SessionLocal()
    players = db.query(Player).all()
    fixed = 0
    for p in players:
        new_pos = KNOWN_POSITIONS.get(p.name)
        if new_pos and p.position != new_pos:
            print(f"  {p.name}: {p.position} → {new_pos}")
            p.position = new_pos
            fixed += 1
    db.commit()
    db.close()
    print(f"✅ {fixed}/{len(players)} posiciones corregidas")

if __name__ == "__main__":
    fix()
