"""Database-level guarantees for the core schema.

Recipe listing requirements are enforced in Pydantic, where errors can be
addressed to individual form fields. These tests cover the backstop: the
constraints that hold even when a row arrives by some other route.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from smoodie_api.models.post import Post, PostStatus, PostType
from smoodie_api.models.recipe import Recipe, RecipeIngredient, RecipeStep
from smoodie_api.models.review import Fidelity, Outcome, Review
from smoodie_api.models.social import Follow, PostVote
from smoodie_api.models.user import User


async def _user(db: AsyncSession, name: str = "cook") -> User:
    user = User(firebase_uid=f"uid-{name}", username=name, display_name=name)
    db.add(user)
    await db.flush()
    return user


async def _post(db: AsyncSession, author: User, kind: PostType = PostType.RECIPE) -> Post:
    post = Post(
        author_id=author.id,
        type=kind,
        status=PostStatus.PUBLISHED,
        title="A perfectly reasonable title",
        slug="a-perfectly-reasonable-title",
    )
    db.add(post)
    await db.flush()
    return post


async def _recipe(db: AsyncSession, post: Post, **kw: object) -> Recipe:
    defaults = {"servings": 4, "prep_time_minutes": 10, "cook_time_minutes": 20}
    defaults.update(kw)
    recipe = Recipe(post_id=post.id, **defaults)  # type: ignore[arg-type]
    db.add(recipe)
    await db.flush()
    return recipe


# --------------------------------------------------------------- recipes


async def test_total_time_is_computed_from_its_parts(db: AsyncSession) -> None:
    user = await _user(db)
    post = await _post(db, user)
    recipe = await _recipe(db, post, prep_time_minutes=15, cook_time_minutes=45)
    await db.refresh(recipe)
    assert recipe.total_time_minutes == 60


async def test_a_recipe_with_no_time_at_all_is_rejected(db: AsyncSession) -> None:
    """A recipe that states neither prep nor cook time tells a cook nothing,
    and leaves Gate A with no band to check a session against."""
    user = await _user(db)
    post = await _post(db, user)
    with pytest.raises(IntegrityError):
        await _recipe(db, post, prep_time_minutes=None, cook_time_minutes=None)


async def test_zero_servings_is_rejected(db: AsyncSession) -> None:
    user = await _user(db)
    post = await _post(db, user)
    with pytest.raises(IntegrityError):
        await _recipe(db, post, servings=0)


async def test_an_ingredient_needs_an_amount_or_to_taste(db: AsyncSession) -> None:
    user = await _user(db)
    post = await _post(db, user)
    await _recipe(db, post)
    db.add(
        RecipeIngredient(
            recipe_post_id=post.id,
            position=1,
            ingredient_name="salt",
            quantity=None,
            to_taste=False,
        )
    )
    with pytest.raises(IntegrityError):
        await db.flush()


async def test_to_taste_ingredients_need_no_quantity(db: AsyncSession) -> None:
    user = await _user(db)
    post = await _post(db, user)
    await _recipe(db, post)
    db.add(
        RecipeIngredient(
            recipe_post_id=post.id, position=1, ingredient_name="salt", quantity=None, to_taste=True
        )
    )
    await db.flush()


async def test_ingredient_positions_are_unique_within_a_recipe(db: AsyncSession) -> None:
    user = await _user(db)
    post = await _post(db, user)
    await _recipe(db, post)
    db.add(
        RecipeIngredient(recipe_post_id=post.id, position=1, ingredient_name="flour", quantity=1)
    )
    await db.flush()
    db.add(
        RecipeIngredient(recipe_post_id=post.id, position=1, ingredient_name="sugar", quantity=1)
    )
    with pytest.raises(IntegrityError):
        await db.flush()


async def test_a_step_too_short_to_be_an_instruction_is_rejected(db: AsyncSession) -> None:
    user = await _user(db)
    post = await _post(db, user)
    await _recipe(db, post)
    db.add(RecipeStep(recipe_post_id=post.id, position=1, instruction="Stir."))
    with pytest.raises(IntegrityError):
        await db.flush()


# ---------------------------------------------------------------- social


async def test_following_yourself_is_rejected(db: AsyncSession) -> None:
    user = await _user(db)
    db.add(Follow(follower_id=user.id, followee_id=user.id))
    with pytest.raises(IntegrityError):
        await db.flush()


async def test_a_vote_must_be_up_or_down(db: AsyncSession) -> None:
    user = await _user(db)
    post = await _post(db, user, kind=PostType.DISCUSSION)
    db.add(PostVote(post_id=post.id, user_id=user.id, value=5))
    with pytest.raises(IntegrityError):
        await db.flush()


# --------------------------------------------------------------- reviews


async def test_one_standing_review_per_person_per_recipe(db: AsyncSession) -> None:
    """Cooking something twice updates the verdict; it does not stack."""
    user = await _user(db)
    post = await _post(db, user)
    await _recipe(db, post)
    for _ in range(2):
        db.add(
            Review(
                recipe_post_id=post.id,
                user_id=user.id,
                make_again=True,
                fidelity=Fidelity.AS_WRITTEN,
                outcome=Outcome.WORKED,
            )
        )
    with pytest.raises(IntegrityError):
        await db.flush()


async def test_a_review_note_is_capped(db: AsyncSession) -> None:
    user = await _user(db)
    post = await _post(db, user)
    await _recipe(db, post)
    db.add(
        Review(
            recipe_post_id=post.id,
            user_id=user.id,
            make_again=True,
            fidelity=Fidelity.AS_WRITTEN,
            outcome=Outcome.WORKED,
            note="x" * 281,
        )
    )
    with pytest.raises((IntegrityError, DBAPIError)):
        await db.flush()


async def test_a_review_pins_the_recipe_version_it_judged(db: AsyncSession) -> None:
    """An author's later edit must never silently reattribute a verdict."""
    user = await _user(db)
    post = await _post(db, user)
    recipe = await _recipe(db, post)
    review = Review(
        recipe_post_id=post.id,
        user_id=user.id,
        recipe_version=recipe.version,
        make_again=True,
        fidelity=Fidelity.AS_WRITTEN,
        outcome=Outcome.WORKED,
    )
    db.add(review)
    await db.flush()

    recipe.version += 1
    await db.flush()

    assert review.recipe_version == 1
    assert recipe.version == 2


# ----------------------------------------------------------------- enums


async def test_enum_labels_are_stored_as_lowercase_values(db: AsyncSession) -> None:
    """The database, the API and the event stream must spell a state the same
    way — otherwise querying the warehouse means guessing which casing applies."""
    rows = await db.execute(
        text(
            "SELECT t.typname, e.enumlabel FROM pg_enum e "
            "JOIN pg_type t ON t.oid = e.enumtypid "
            "WHERE t.typname IN ('post_status', 'media_status', 'review_fidelity')"
        )
    )
    labels = [r[1] for r in rows]
    assert labels, "enum types should exist"
    assert all(label == label.lower() for label in labels), labels


async def test_saves_and_reviews_are_separate_tables(db: AsyncSession) -> None:
    """Tier 0 is demand signal, not quality signal. Keeping it structurally
    separate is what stops it ever leaking into a score."""
    rows = await db.execute(
        text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()"
        )
    )
    names = {r[0] for r in rows}
    assert {"saves", "reviews"} <= names
    cols = await db.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'saves' AND table_schema = current_schema()"
        )
    )
    save_cols = {r[0] for r in cols}
    assert not (save_cols & {"make_again", "outcome", "fidelity"})


async def test_phase_two_tables_exist_now(db: AsyncSession) -> None:
    """Cook sessions, reliability and the AI output tables ship with the core
    schema so live review data never has to be migrated into them later."""
    rows = await db.execute(
        text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()"
        )
    )
    names = {r[0] for r in rows}
    assert {
        "cook_sessions",
        "review_confidence",
        "user_reliability",
        "review_attributes",
        "recipe_review_axes",
        "comment_summaries",
        "review_aggregates",
    } <= names


async def test_deleting_a_recipe_post_takes_its_parts_with_it(db: AsyncSession) -> None:
    user = await _user(db)
    post = await _post(db, user)
    await _recipe(db, post)
    db.add(
        RecipeIngredient(recipe_post_id=post.id, position=1, ingredient_name="flour", quantity=2)
    )
    db.add(RecipeStep(recipe_post_id=post.id, position=1, instruction="Combine everything slowly."))
    await db.commit()

    await db.execute(text("DELETE FROM posts WHERE id = :i"), {"i": str(post.id)})
    await db.commit()

    remaining = await db.execute(text("SELECT count(*) FROM recipe_ingredients"))
    assert remaining.scalar_one() == 0
    steps = await db.execute(text("SELECT count(*) FROM recipe_steps"))
    assert steps.scalar_one() == 0


async def test_an_unknown_author_cannot_own_a_post(db: AsyncSession) -> None:
    db.add(
        Post(
            author_id=uuid.uuid4(),
            type=PostType.DISCUSSION,
            status=PostStatus.DRAFT,
            title="Orphaned post title",
            slug="orphaned-post-title",
        )
    )
    with pytest.raises(IntegrityError):
        await db.flush()
