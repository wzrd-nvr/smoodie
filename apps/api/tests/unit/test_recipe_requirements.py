"""The recipe listing requirements, rule by rule.

Every rejection must name the field that caused it, because the composer
renders these inline next to the offending row. A test that only asserts
"raises" would pass on a generic 'invalid recipe' message that helps nobody.
"""

from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from smoodie_api.models.post import PostStatus
from smoodie_api.schemas.post import (
    MIN_INGREDIENTS,
    MIN_STEP_LENGTH,
    MIN_STEPS,
    PostCreate,
)

adapter: TypeAdapter[Any] = TypeAdapter(PostCreate)


def _ingredient(position: int = 1, **kw: Any) -> dict[str, Any]:
    base = {
        "position": position,
        "quantity": 200,
        "unit": "g",
        "ingredient_name": "flour",
    }
    base.update(kw)
    return base


def _step(position: int = 1, **kw: Any) -> dict[str, Any]:
    base = {"position": position, "instruction": "Mix everything together well."}
    base.update(kw)
    return base


def _recipe(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "servings": 4,
        "prep_time_minutes": 10,
        "cook_time_minutes": 25,
        "ingredients": [_ingredient(1), _ingredient(2, ingredient_name="water", unit="ml")],
        "steps": [_step(1), _step(2, instruction="Bake until it is golden brown.")],
    }
    base.update(kw)
    return base


def _post(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "type": "recipe",
        "title": "A dependable weeknight loaf",
        "media_ids": ["3f2504e0-4f89-41d3-9a0c-0305e82c3301"],
        "recipe": _recipe(),
    }
    base.update(kw)
    return base


def _fields(exc: ValidationError) -> set[str]:
    return {str(part) for err in exc.errors() for part in err["loc"]}


def _messages(exc: ValidationError) -> str:
    return " ".join(err["msg"] for err in exc.errors())


# ------------------------------------------------------------ the happy path


def test_a_complete_recipe_is_accepted() -> None:
    parsed = adapter.validate_python(_post())
    assert parsed.recipe.servings == 4
    assert len(parsed.recipe.ingredients) == MIN_INGREDIENTS


def test_a_discussion_post_needs_no_recipe() -> None:
    parsed = adapter.validate_python(
        {"type": "discussion", "title": "What is everyone cooking?", "body_md": "Tell me."}
    )
    assert parsed.type == "discussion"


# ------------------------------------------------------------------ amounts


def test_an_ingredient_without_an_amount_is_rejected() -> None:
    payload = _post(
        recipe=_recipe(
            ingredients=[_ingredient(1, quantity=None), _ingredient(2, ingredient_name="water")]
        )
    )
    with pytest.raises(ValidationError) as exc:
        adapter.validate_python(payload)
    assert "How much" in _messages(exc.value)


def test_an_ingredient_without_a_unit_is_rejected() -> None:
    payload = _post(
        recipe=_recipe(
            ingredients=[_ingredient(1, unit=None), _ingredient(2, ingredient_name="water")]
        )
    )
    with pytest.raises(ValidationError) as exc:
        adapter.validate_python(payload)
    assert "unit" in _messages(exc.value).lower()


def test_to_taste_needs_neither_amount_nor_unit() -> None:
    payload = _post(
        recipe=_recipe(
            ingredients=[
                _ingredient(1, quantity=None, unit=None, ingredient_name="salt", to_taste=True),
                _ingredient(2, ingredient_name="water"),
            ]
        )
    )
    parsed = adapter.validate_python(payload)
    assert parsed.recipe.ingredients[0].to_taste is True


def test_a_negative_quantity_is_rejected() -> None:
    payload = _post(
        recipe=_recipe(
            ingredients=[_ingredient(1, quantity=-5), _ingredient(2, ingredient_name="water")]
        )
    )
    with pytest.raises(ValidationError) as exc:
        adapter.validate_python(payload)
    assert "quantity" in _fields(exc.value)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("teaspoon", "tsp"),
        ("Tablespoons", "tbsp"),
        ("GRAMS", "g"),
        ("cups", "cup"),
        ("lbs", "lb"),
        ("ml.", "ml"),
        ("  oz  ", "oz"),
        ("cloves", "clove"),
        ("tins", "can"),
    ],
)
def test_common_unit_spellings_are_normalized(raw: str, expected: str) -> None:
    """People type 'Tablespoons'; the warehouse needs one spelling."""
    payload = _post(
        recipe=_recipe(
            ingredients=[_ingredient(1, unit=raw), _ingredient(2, ingredient_name="water")]
        )
    )
    parsed = adapter.validate_python(payload)
    assert parsed.recipe.ingredients[0].unit == expected


@pytest.mark.parametrize("bogus", ["glug", "handful", "smidge", "tins of love", ""])
def test_invented_units_are_rejected_with_a_way_forward(bogus: str) -> None:
    payload = _post(
        recipe=_recipe(
            ingredients=[_ingredient(1, unit=bogus), _ingredient(2, ingredient_name="water")]
        )
    )
    with pytest.raises(ValidationError) as exc:
        adapter.validate_python(payload)
    assert "to taste" in _messages(exc.value)


# -------------------------------------------------------------------- counts


def test_a_single_ingredient_is_not_a_recipe() -> None:
    payload = _post(recipe=_recipe(ingredients=[_ingredient(1)]))
    with pytest.raises(ValidationError) as exc:
        adapter.validate_python(payload)
    assert f"at least {MIN_INGREDIENTS} ingredients" in _messages(exc.value)


def test_a_single_step_is_not_a_recipe() -> None:
    payload = _post(recipe=_recipe(steps=[_step(1)]))
    with pytest.raises(ValidationError) as exc:
        adapter.validate_python(payload)
    assert f"at least {MIN_STEPS} steps" in _messages(exc.value)


def test_a_step_too_short_to_be_an_instruction_is_rejected() -> None:
    payload = _post(recipe=_recipe(steps=[_step(1, instruction="Stir"), _step(2)]))
    with pytest.raises(ValidationError) as exc:
        adapter.validate_python(payload)
    assert f"at least {MIN_STEP_LENGTH} characters" in _messages(exc.value)


# --------------------------------------------------------------------- times


def test_a_recipe_with_no_time_at_all_is_rejected() -> None:
    payload = _post(recipe=_recipe(prep_time_minutes=None, cook_time_minutes=None))
    with pytest.raises(ValidationError) as exc:
        adapter.validate_python(payload)
    assert "committing to" in _messages(exc.value)


@pytest.mark.parametrize("prep,cook", [(10, None), (None, 30), (5, 5)])
def test_either_time_alone_is_enough(prep: int | None, cook: int | None) -> None:
    """A no-cook salad has no cook time; a slow braise has almost no prep."""
    payload = _post(recipe=_recipe(prep_time_minutes=prep, cook_time_minutes=cook))
    assert adapter.validate_python(payload).recipe.prep_time_minutes == prep


# ------------------------------------------------------------------ servings


@pytest.mark.parametrize("servings", [0, -1, 101])
def test_implausible_serving_counts_are_rejected(servings: int) -> None:
    payload = _post(recipe=_recipe(servings=servings))
    with pytest.raises(ValidationError) as exc:
        adapter.validate_python(payload)
    assert "servings" in _fields(exc.value)


# -------------------------------------------------------------------- photos


def test_publishing_a_recipe_without_a_photo_is_rejected() -> None:
    payload = _post(media_ids=[])
    with pytest.raises(ValidationError) as exc:
        adapter.validate_python(payload)
    assert "photo" in _messages(exc.value)


def test_a_draft_recipe_may_have_no_photo_yet() -> None:
    """The photo is the last thing you have. Being unable to save work in
    progress would be worse than a photoless draft."""
    parsed = adapter.validate_python(_post(media_ids=[], status="draft"))
    assert parsed.status is PostStatus.DRAFT


# ------------------------------------------------------------------ ordering


def test_duplicate_positions_are_rejected() -> None:
    payload = _post(
        recipe=_recipe(ingredients=[_ingredient(1), _ingredient(1, ingredient_name="water")])
    )
    with pytest.raises(ValidationError) as exc:
        adapter.validate_python(payload)
    assert "same position" in _messages(exc.value)


def test_a_gap_in_the_numbering_is_rejected() -> None:
    payload = _post(recipe=_recipe(steps=[_step(1), _step(3)]))
    with pytest.raises(ValidationError) as exc:
        adapter.validate_python(payload)
    assert "gap" in _messages(exc.value)


# ---------------------------------------------------------------------- tags


def test_unknown_dietary_tags_are_rejected() -> None:
    payload = _post(recipe=_recipe(dietary_tags=["vegan", "made-of-magic"]))
    with pytest.raises(ValidationError) as exc:
        adapter.validate_python(payload)
    assert "made-of-magic" in _messages(exc.value)


def test_dietary_tags_are_normalized_and_deduplicated() -> None:
    payload = _post(recipe=_recipe(dietary_tags=["VEGAN", "vegan", " Gluten-Free "]))
    parsed = adapter.validate_python(payload)
    assert parsed.recipe.dietary_tags == ["vegan", "gluten-free"]


# --------------------------------------------------------------------- title


@pytest.mark.parametrize("title", ["ab", "  a  ", ""])
def test_a_title_too_short_to_mean_anything_is_rejected(title: str) -> None:
    with pytest.raises(ValidationError) as exc:
        adapter.validate_python(_post(title=title))
    assert "title" in _fields(exc.value)


def test_titles_have_their_whitespace_tidied() -> None:
    parsed = adapter.validate_python(_post(title="  Roast   chicken  "))
    assert parsed.title == "Roast chicken"


# ----------------------------------------------------------- discussion side


def test_an_empty_discussion_post_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        adapter.validate_python({"type": "discussion", "title": "Nothing here"})
    assert "text or a photo" in _messages(exc.value)


def test_a_discussion_post_with_only_a_photo_is_fine() -> None:
    parsed = adapter.validate_python(
        {
            "type": "discussion",
            "title": "Tonight's dinner",
            "media_ids": ["3f2504e0-4f89-41d3-9a0c-0305e82c3301"],
        }
    )
    assert parsed.media_ids


def test_the_type_field_picks_the_right_shape() -> None:
    """A discussion payload must not be silently accepted as a recipe."""
    with pytest.raises(ValidationError):
        adapter.validate_python({"type": "recipe", "title": "No recipe body here"})
