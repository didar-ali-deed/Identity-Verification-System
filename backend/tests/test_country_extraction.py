from app.services.pipeline.stage_0_acceptance import _extract_country_from_mrz


def test_country_extraction_does_not_read_fragments_of_page_words():
    assert _extract_country_from_mrz("PAKISTAN\nSurname\nSAMPLE\nGiven Names\nALEX") is None
    assert _extract_country_from_mrz("REPUBLIC OF PAKISTAN ID CARD") is None


def test_country_extraction_requires_mrz_header():
    assert _extract_country_from_mrz("Name\n" + "P<PAKSAMPLE<<ALEX".ljust(44, "<")) == "PAK"
