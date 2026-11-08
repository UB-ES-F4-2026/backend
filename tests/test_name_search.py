"""Algoritmo de búsqueda por título, sin base de datos."""
import unittest

from app.core.name_search import MAX_DISTANCE, normalize, search_by_title, title_distance

TITLES = [
    "Rehabilitación de edificio en Girona",
    "Construcción de viviendas en Sabadell",
    "Local comercial en Lleida",
]


def search(query: str, titles=TITLES) -> list[str]:
    return search_by_title(query, titles, lambda title: title)


class NormalizeTest(unittest.TestCase):
    def test_ignores_case_accents_punctuation_and_extra_spaces(self):
        self.assertEqual(normalize("  Rehabilitación,  ÁTICO-Dúplex  "), "rehabilitacion atico duplex")

    def test_keeps_letters_without_accent_marks(self):
        self.assertEqual(normalize("Ñandú Çà"), "nandu ca")


class TitleDistanceTest(unittest.TestCase):
    def test_compares_with_the_closest_group_of_words(self):
        self.assertEqual(title_distance("girona", TITLES[0]), 0)
        self.assertEqual(title_distance("giorna", TITLES[0]), 2)
        self.assertEqual(title_distance("edifcio en", TITLES[0]), 1)

    def test_query_longer_than_the_title_uses_the_whole_title(self):
        self.assertEqual(title_distance("local comercial grande", "Local comercial"), 7)


class SearchByTitleTest(unittest.TestCase):
    def test_exact_match_is_case_and_accent_insensitive(self):
        self.assertEqual(search("REHABILITACION"), [TITLES[0]])
        self.assertEqual(search("lléida"), [TITLES[2]])

    def test_exact_match_finds_text_inside_the_title(self):
        self.assertEqual(search("viviendas en sab"), [TITLES[1]])

    def test_exact_matches_exclude_approximate_ones(self):
        titles = ["Piso en Girona", "Piso en Gerona"]
        # "girona" coincide exactamente con el primero; el segundo (distancia 1) no se añade.
        self.assertEqual(search("girona", titles), ["Piso en Girona"])

    def test_typos_up_to_the_maximum_distance_are_found(self):
        self.assertEqual(MAX_DISTANCE, 3)
        self.assertEqual(search("Zabadell"), [TITLES[1]])          # distancia 1
        self.assertEqual(search("Lerida"), [TITLES[2]])            # distancia 2
        self.assertEqual(search("Gxyzna"), [TITLES[0]])            # distancia 3

    def test_no_result_beyond_the_maximum_distance(self):
        self.assertEqual(search("Gwxyza"), [])                     # distancia 4
        self.assertEqual(search("Tarragona"), [])

    def test_approximate_results_are_ordered_by_distance(self):
        titles = ["Casa en Gerona", "Casa en Girona"]
        # "girnoa": distancia 2 a "girona" y 3 a "gerona".
        self.assertEqual(search("girnoa", titles), ["Casa en Girona", "Casa en Gerona"])

    def test_ties_keep_the_original_order(self):
        titles = ["Nave en Reus", "Nave en Rius"]
        # "rous": distancia 1 a ambos.
        self.assertEqual(search("Rous", titles), titles)

    def test_empty_list_gives_no_results(self):
        self.assertEqual(search("girona", []), [])


if __name__ == "__main__":
    unittest.main()
