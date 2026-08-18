"""
test_stage_pcs_agent.py
Unit-tests for stage_pcs_agent.py's beskyttelse af egengenererede
hoejdeprofiler (STG-030).

Baggrund: save_stages() upserter med Prefer: resolution=merge-duplicates.
Naar PCS fandt et profilbillede, skrev den elevation_image_url uden at roere
elevation_image_source — saa en etape med vores eget genererede billede
(source='generated') beholdt "generated", mens URL'en blev erstattet af en
PCS-hotlink. Frontenden gater paa source === 'generated' (LEG-001) og viste
derfor PCS-billedet som vores eget; PCS svarer 403 paa hotlinks, saa billedet
kunne slet ikke indlaeses.

Netvaerks-/DB-integrationen testes ikke her — kun den rene filtrerings-logik.

Koer: python agents/test_stage_pcs_agent.py
"""

import unittest

from stage_pcs_agent import strip_generated_image_urls


def _record(stage_number: int, url: str | None = "https://pcs.example/p.jpg") -> dict:
    rec = {"race_id": "r1", "stage_number": stage_number, "name": f"Etape {stage_number}"}
    if url is not None:
        rec["elevation_image_url"] = url
    return rec


class TestStripGeneratedImageUrls(unittest.TestCase):

    def test_beskytter_etape_med_egengenereret_profil(self):
        """Kernefejlen: PCS-URL maa ikke overskrive et egengenereret billede."""
        records = [_record(1)]
        stripped = strip_generated_image_urls(records, {1})
        self.assertEqual(stripped, 1)
        self.assertNotIn("elevation_image_url", records[0])

    def test_roerer_ikke_ubeskyttede_etaper(self):
        """Etaper uden egengenereret profil skal stadig faa PCS-billedet."""
        records = [_record(2)]
        stripped = strip_generated_image_urls(records, {1})
        self.assertEqual(stripped, 0)
        self.assertEqual(records[0]["elevation_image_url"], "https://pcs.example/p.jpg")

    def test_blandet_batch(self):
        records = [_record(1), _record(2), _record(3)]
        stripped = strip_generated_image_urls(records, {1, 3})
        self.assertEqual(stripped, 2)
        self.assertNotIn("elevation_image_url", records[0])
        self.assertIn("elevation_image_url", records[1])
        self.assertNotIn("elevation_image_url", records[2])

    def test_oevrige_felter_bevares(self):
        """Kun billedfeltet fjernes — resten af etapedataen skal stadig gemmes."""
        records = [_record(1)]
        strip_generated_image_urls(records, {1})
        self.assertEqual(records[0]["name"], "Etape 1")
        self.assertEqual(records[0]["stage_number"], 1)
        self.assertEqual(records[0]["race_id"], "r1")

    def test_haandterer_raekke_uden_billednoegle(self):
        """Raekker hvor PCS intet fandt (noeglen allerede fjernet) maa ikke fejle."""
        records = [_record(1, url=None)]
        stripped = strip_generated_image_urls(records, {1})
        self.assertEqual(stripped, 0)
        self.assertNotIn("elevation_image_url", records[0])

    def test_tom_beskyttelsesmaengde(self):
        records = [_record(1), _record(2)]
        stripped = strip_generated_image_urls(records, set())
        self.assertEqual(stripped, 0)
        self.assertTrue(all("elevation_image_url" in r for r in records))


if __name__ == "__main__":
    unittest.main(verbosity=2)
