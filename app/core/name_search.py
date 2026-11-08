"""Búsqueda de oportunidades por título, sin distinguir mayúsculas ni acentos.

1. Si algún título contiene el texto buscado, se devuelven solo esas coincidencias.
2. Si no, se devuelven los títulos a distancia de Levenshtein ≤ MAX_DISTANCE,
   de la más cercana a la más lejana.
3. Si ninguno queda a esa distancia, no hay resultados.
"""
import re
import unicodedata
from collections.abc import Callable, Iterable
from typing import TypeVar

import Levenshtein

MAX_DISTANCE = 3

T = TypeVar("T")

_NON_ALPHANUMERIC = re.compile(r"[^0-9a-z]+")


def normalize(text: str) -> str:
    """Minúsculas, sin acentos y con la puntuación convertida en espacios simples."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _NON_ALPHANUMERIC.sub(" ", without_accents).strip()


def title_distance(query: str, title: str) -> int:
    """Distancia mínima entre la búsqueda y cada grupo de palabras consecutivas del título.

    Cada grupo tiene tantas palabras como la búsqueda: así una errata en una
    palabra se detecta aunque el título completo sea mucho más largo.
    """
    query_words = normalize(query).split()
    title_words = normalize(title).split()
    target = " ".join(query_words)
    size = len(query_words)
    if len(title_words) <= size:
        return Levenshtein.distance(target, " ".join(title_words))
    return min(
        Levenshtein.distance(target, " ".join(title_words[start:start + size]))
        for start in range(len(title_words) - size + 1)
    )


def search_by_title(query: str, items: Iterable[T], title: Callable[[T], str]) -> list[T]:
    """Filtra `items` según la búsqueda; conserva el orden original entre empates."""
    items = list(items)
    normalized_query = normalize(query)

    exact = [item for item in items if normalized_query in normalize(title(item))]
    if exact:
        return exact

    scored = [(title_distance(query, title(item)), item) for item in items]
    # sorted es estable: a igual distancia se mantiene el orden recibido.
    return [
        item
        for distance, item in sorted(scored, key=lambda pair: pair[0])
        if distance <= MAX_DISTANCE
    ]
