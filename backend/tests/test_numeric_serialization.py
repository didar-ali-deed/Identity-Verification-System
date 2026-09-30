import json

import numpy as np
import pytest

from app.database import serialize_json


def test_nested_model_numbers_are_valid_database_json():
    result = json.loads(
        serialize_json(
            {"evidence": {"score": np.float32(1.0162), "passed": np.bool_(True), "regions": np.array([1, 2])}}
        )
    )
    assert result["evidence"]["score"] == pytest.approx(1.0162)
    assert result["evidence"]["passed"] is True
    assert result["evidence"]["regions"] == [1, 2]


def test_unknown_and_nonfinite_values_are_rejected():
    with pytest.raises(TypeError):
        serialize_json(object())
    with pytest.raises(ValueError):
        serialize_json({"score": np.float32(float("nan"))})
