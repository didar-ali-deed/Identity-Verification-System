import pytest

from app.services.pipeline.stage_3_normalization import normalize_date
from app.utils.dates import normalize_document_date


@pytest.mark.parametrize("value", ["01 FEB 1990", "01 February 1990", "01.02.1990", "1990-02-01", "19900201", "900201"])
def test_document_formats_share_the_same_canonical_date(value):
    assert normalize_document_date(value) == normalize_date(value) == "19900201"


@pytest.mark.parametrize("value", [None, "", "19900230", "31.02.1990", "01 XYZ 1990", "2024131"])
def test_invalid_dates_cannot_become_identity_evidence(value):
    assert normalize_document_date(value) is None
