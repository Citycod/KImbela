from pathlib import Path

import pytest

from matchmaking.matchmake import _preferred_age_range
from models import MatchmakingPackage, MatchmakingRequest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "minimum,maximum",
    [(18, 25), (21, 35), (25, 40), (30, 55), (31, 31), (45, 65)],
)
def test_preferred_age_accepts_user_selected_adult_ranges(minimum, maximum):
    assert _preferred_age_range({
        "min_age": str(minimum),
        "max_age": str(maximum),
    }) == (minimum, maximum, None)


@pytest.mark.parametrize(
    ("minimum", "maximum", "message"),
    [
        (17, 25, "Minimum age must be at least 18."),
        (40, 30, "Maximum age must be greater than or equal to minimum age."),
        (25, 100, "Maximum age cannot be greater than 99."),
        ("18.5", 25, "Please enter a valid whole-number age."),
        ("age", 25, "Please enter a valid whole-number age."),
        (-1, 25, "Minimum age must be at least 18."),
    ],
)
def test_preferred_age_rejects_invalid_ranges(minimum, maximum, message):
    _min_age, _max_age, error = _preferred_age_range({
        "min_age": minimum,
        "max_age": maximum,
    })
    assert error == message


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
    assert 'value="18"' in min_field
    assert 'value="99"' in max_field
    assert "preferredAgeError" in source
    assert "Minimum age must be 31" not in source
    assert "minAgeInput.addEventListener('input'" not in source
    assert "maxAgeInput.addEventListener('input'" not in source
    assert "minAgeInput.addEventListener('blur', validatePreferredAgeRange)" in source
    assert "maxAgeInput.addEventListener('blur', validatePreferredAgeRange)" in source
    assert "minAgeInput.value = 31" not in source
    assert "maxAgeInput.value = minVal + 1" not in source


def test_preferred_age_editing_allows_temporary_empty_and_partial_values():
    source = (ROOT / "templates" / "requests.html").read_text()

    assert "syncAgeConstraints" not in source
    assert "addEventListener('input', validatePreferredAgeRange)" not in source
    assert "Please enter a valid whole-number age." in source


def test_preferred_age_replacement_examples_are_not_special_cased():
    source = (ROOT / "templates" / "requests.html").read_text()

    assert "minVal < 31" not in source
    assert "minVal + 1" not in source
    assert _preferred_age_range({"min_age": "25", "max_age": "40"}) == (
        25,
        40,
        None,
    )


def test_create_boost_preserves_selected_preferred_age_range(client, db, user):
    package = MatchmakingPackage(
        name="Age input regression package",
        description="Focused preferred-age integration test",
        price=3,
        duration_days=30,
        is_active=True,
    )
    db.session.add(package)
    db.session.commit()
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True

    response = client.post(
        "/create-request",
        json={
            "package_id": package.id,
            "request_data": {
                "min_age": "18",
                "max_age": "25",
                "partner_gender": "any",
                "partner_country": "Testland",
                "about_you": "A complete profile description",
                "ideal_partner": "A compatible adult partner",
            },
        },
    )

    assert response.status_code == 200
    request_row = MatchmakingRequest.query.filter_by(user_id=user.id).one()
    assert (request_row.min_age, request_row.max_age) == (18, 25)
