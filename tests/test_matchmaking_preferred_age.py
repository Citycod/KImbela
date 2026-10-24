from pathlib import Path

import pytest

from matchmaking.matchmake import _preferred_age_range


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("minimum,maximum", [(18, 25), (25, 40), (31, 31)])
def test_preferred_age_accepts_user_selected_adult_ranges(minimum, maximum):
    assert _preferred_age_range({
        "min_age": str(minimum),
        "max_age": str(maximum),
    }) == (minimum, maximum, None)


@pytest.mark.parametrize(
    ("minimum", "maximum", "message"),
    [
        (17, 25, "at least 18"),
        (40, 25, "greater than or equal"),
        (25, 100, "above 99"),
        ("18.5", 25, "whole number"),
    ],
)
def test_preferred_age_rejects_invalid_ranges(minimum, maximum, message):
    _min_age, _max_age, error = _preferred_age_range({
        "min_age": minimum,
        "max_age": maximum,
    })
    assert message in error


def test_preferred_age_fields_are_editable_typed_number_inputs():
    source = (ROOT / "templates" / "requests.html").read_text()

    min_id = source.index('id="minAge"')
    max_id = source.index('id="maxAge"')
    min_field = source[source.rfind('<input', 0, min_id):source.index('/>', min_id)]
    max_field = source[source.rfind('<input', 0, max_id):source.index('/>', max_id)]
    for field in (min_field, max_field):
        assert 'type="number"' in field
        assert 'min="18"' in field
        assert 'max="99"' in field
        assert 'step="1"' in field
        assert "readonly" not in field
        assert "disabled" not in field
    assert "Minimum age" in source
    assert "Maximum age" in source
    assert "Number.isInteger(minAge)" in source
    assert "preferredAgeError" in source
    assert "Minimum age must be 31" not in source
