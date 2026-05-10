"""
Seed script: applies DDL (adds top_n and providers columns if missing)
and upserts the 6 initial competition rows.

Idempotent: safe to run multiple times.

Usage:
    python scripts/seed_league_configs.py
"""
import asyncio
import json
import sys
import os

# Allow running from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sqlalchemy import text
from sfa.infrastructure.database import AsyncSessionLocal

LEAGUES = [
    {"name": "La Liga",          "country": "ESP", "comp_factor": 1.0, "top_n": 6,  "providers": {"api-football": 140}},
    {"name": "Premier League",   "country": "ENG", "comp_factor": 1.0, "top_n": 6,  "providers": {"api-football": 39}},
    {"name": "Bundesliga",       "country": "GER", "comp_factor": 1.0, "top_n": 6,  "providers": {"api-football": 78}},
    {"name": "Serie A",          "country": "ITA", "comp_factor": 1.0, "top_n": 6,  "providers": {"api-football": 135}},
    {"name": "Ligue 1",          "country": "FRA", "comp_factor": 1.0, "top_n": 6,  "providers": {"api-football": 61}},
    {"name": "Champions League", "country": "EUR", "comp_factor": 1.5, "top_n": 24, "providers": {"api-football": 2}},
]

DDL_STATEMENTS = [
    "ALTER TABLE IF EXISTS competitions ADD COLUMN IF NOT EXISTS top_n INTEGER NOT NULL DEFAULT 6",
    "ALTER TABLE IF EXISTS competitions ADD COLUMN IF NOT EXISTS providers JSONB NOT NULL DEFAULT '{}'::jsonb",
]

UPSERT = """
INSERT INTO competitions (name, country, competition_factor, top_n, providers)
VALUES (:name, :country, :comp_factor, :top_n, CAST(:providers AS jsonb))
ON CONFLICT (name) DO UPDATE SET
    top_n = EXCLUDED.top_n,
    providers = EXCLUDED.providers
"""


async def main() -> None:
    async with AsyncSessionLocal() as session:
        # 1. Apply DDL (each statement separately — asyncpg rejects multi-command strings)
        for stmt in DDL_STATEMENTS:
            await session.execute(text(stmt))
        await session.commit()
        print("[seed] DDL applied (columns top_n and providers ensured).")

        # 2. Upsert competitions
        for league in LEAGUES:
            await session.execute(
                text(UPSERT),
                {
                    "name": league["name"],
                    "country": league["country"],
                    "comp_factor": league["comp_factor"],
                    "top_n": league["top_n"],
                    "providers": json.dumps(league["providers"]),
                },
            )
        await session.commit()
        print(f"[seed] Upserted {len(LEAGUES)} competition rows.")


if __name__ == "__main__":
    asyncio.run(main())
