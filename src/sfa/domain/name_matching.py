from __future__ import annotations

import re
import unicodedata


def normalize(name: str) -> str:
    """NFD decomposition + strip diacritics + lowercase + remove punctuation."""
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = name.lower()
    name = re.sub(r"[.\-'`]", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def get_tokens(name: str) -> set[str]:
    """Split into tokens, ignore tokens of ≤ 2 characters (initials)."""
    return {t for t in normalize(name).split() if len(t) > 2}


def match_score(source_name: str, db_name: str) -> float:
    """
    Strict score:
    - Jaccard over tokens
    - Bonus +0.3 if the longest token (main surname) matches exactly
    - Penalty ×0.4 if the main surname is NOT in the other name
    """
    tu = get_tokens(source_name)
    td = get_tokens(db_name)

    if not tu or not td:
        return 0.0

    common = tu & td
    if not common:
        return 0.0

    score = len(common) / len(tu | td)

    longest_u = max(tu, key=len) if tu else ""
    longest_d = max(td, key=len) if td else ""
    if longest_u and longest_d and longest_u == longest_d:
        score = min(1.0, score + 0.3)
    elif longest_u and longest_u not in td:
        score *= 0.4

    return score


def find_best_match(
    source_name: str, db_index: dict[str, object],
) -> tuple[object | None, float]:
    """
    Returns (object, score) or (None, 0.0) if:
    - No match with score >= 0.75
    - 2+ candidates differ by < 0.1 (ambiguous)
    """
    candidates = [
        (obj, match_score(source_name, db_name), db_name)
        for db_name, obj in db_index.items()
        if match_score(source_name, db_name) >= 0.75
    ]

    if not candidates:
        return None, 0.0

    candidates.sort(key=lambda x: x[1], reverse=True)

    if len(candidates) >= 2 and (candidates[0][1] - candidates[1][1]) < 0.1:
        return None, 0.0  # Ambiguous — discard

    return candidates[0][0], candidates[0][1]
