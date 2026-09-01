"""Post payloads, and the recipe listing requirements.

Every rule below produces an error addressed to the specific field that broke
it, because the composer renders these inline next to the offending row. A
generic "invalid recipe" would be true and useless.

The database carries matching CHECK constraints as a backstop; these are the
version a person actually sees.
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from smoodie_api.models.post import PostStatus, PostType
from smoodie_api.models.recipe import Difficulty
from smoodie_api.services.units import UnknownUnit, normalize_unit

# --- The listing requirements, in one place so they can be quoted in errors ---
MIN_INGREDIENTS = 2
MIN_STEPS = 2
MIN_STEP_LENGTH = 10
MAX_JAR_AXES = 4

DIETARY_TAGS = frozenset(
    {
        "vegan",
        "vegetarian",
        "pescatarian",
        "gluten-free",
        "dairy-free",
        "nut-free",
        "egg-free",
        "soy-free",
        "shellfish-free",
        "halal",
        "kosher",
        "low-carb",
        "keto",
        "paleo",
        "whole30",
        "sugar-free",
        "low-sodium",
    }
)


class IngredientIn(BaseModel):
    position: int = Field(ge=1)
    group_label: str | None = Field(default=None, max_length=80)
    quantity: float | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, max_length=32)
    ingredient_name: str = Field(min_length=1, max_length=120)
    preparation_note: str | None = Field(default=None, max_length=120)
    is_optional: bool = False
    to_taste: bool = False

    @field_validator("ingredient_name", "group_label", "preparation_note")
    @classmethod
    def _tidy(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        return cleaned or None

    @field_validator("unit")
    @classmethod
    def _known_unit(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return normalize_unit(value)
        except UnknownUnit as exc:
            raise ValueError(str(exc)) from exc

    @model_validator(mode="after")
    def _amount_is_actionable(self) -> "IngredientIn":
        """An ingredient line a cook cannot act on is not a listing."""
        if self.to_taste:
            return self
        if self.quantity is None:
            raise ValueError(
                f"How much {self.ingredient_name or 'of this'}? "
                "Give an amount, or mark it as to taste."
            )
        if self.unit is None:
            raise ValueError(
                f"What unit is the {self.quantity} of {self.ingredient_name or 'this'}? "
                "Pick a unit, or mark it as to taste."
            )
        return self


class StepIn(BaseModel):
    position: int = Field(ge=1)
    instruction: str = Field(min_length=1)
    duration_minutes: int | None = Field(default=None, ge=0)
    media_id: uuid.UUID | None = None

    @field_validator("instruction")
    @classmethod
    def _long_enough_to_be_an_instruction(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < MIN_STEP_LENGTH:
            raise ValueError(
                f"Steps need at least {MIN_STEP_LENGTH} characters — say what to do with what."
            )
        return cleaned


class RecipeIn(BaseModel):
    servings: int = Field(ge=1, le=100)
    yield_text: str | None = Field(default=None, max_length=120)
    prep_time_minutes: int | None = Field(default=None, ge=0, le=10080)
    cook_time_minutes: int | None = Field(default=None, ge=0, le=10080)
    difficulty: Difficulty | None = None
    cuisine: str | None = Field(default=None, max_length=60)
    dietary_tags: list[str] = Field(default_factory=list)
    ingredients: list[IngredientIn]
    steps: list[StepIn]

    @field_validator("dietary_tags")
    @classmethod
    def _known_tags(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for tag in values:
            normalized = tag.strip().lower()
            if normalized not in DIETARY_TAGS:
                raise ValueError(f"'{tag}' isn't a dietary tag we recognize.")
            if normalized not in cleaned:
                cleaned.append(normalized)
        return cleaned

    @model_validator(mode="after")
    def _meets_listing_requirements(self) -> "RecipeIn":
        if len(self.ingredients) < MIN_INGREDIENTS:
            raise ValueError(
                f"A recipe needs at least {MIN_INGREDIENTS} ingredients. "
                "If it really has one, it might fit better as a discussion post."
            )
        if len(self.steps) < MIN_STEPS:
            raise ValueError(f"A recipe needs at least {MIN_STEPS} steps.")
        if self.prep_time_minutes is None and self.cook_time_minutes is None:
            raise ValueError(
                "Give a prep time, a cook time, or both — otherwise nobody knows "
                "what they're committing to."
            )

        for label, items in (("ingredients", self.ingredients), ("steps", self.steps)):
            positions = [item.position for item in items]
            if len(set(positions)) != len(positions):
                raise ValueError(f"Two {label} share the same position.")
            if sorted(positions) != list(range(1, len(positions) + 1)):
                raise ValueError(f"The {label} are numbered with a gap in the sequence.")
        return self


class PostBase(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    body_md: str | None = Field(default=None, max_length=50_000)
    media_ids: list[uuid.UUID] = Field(default_factory=list, max_length=12)
    status: Literal[PostStatus.DRAFT, PostStatus.PUBLISHED] = PostStatus.PUBLISHED

    @field_validator("title")
    @classmethod
    def _tidy_title(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 3:
            raise ValueError("Titles need at least 3 characters.")
        return cleaned


class DiscussionCreate(PostBase):
    type: Literal[PostType.DISCUSSION] = PostType.DISCUSSION

    @model_validator(mode="after")
    def _has_something_to_say(self) -> "DiscussionCreate":
        if not self.body_md and not self.media_ids:
            raise ValueError("Add something to your post — text or a photo.")
        return self


class RecipeCreate(PostBase):
    type: Literal[PostType.RECIPE] = PostType.RECIPE
    recipe: RecipeIn

    @model_validator(mode="after")
    def _published_recipes_need_a_photo(self) -> "RecipeCreate":
        """Drafts are exempt: a photo is the last thing you have, and being
        unable to save work in progress would be worse than a photoless feed."""
        if self.status is PostStatus.PUBLISHED and not self.media_ids:
            raise ValueError("Add at least one photo before publishing a recipe.")
        return self


PostCreate = Annotated[DiscussionCreate | RecipeCreate, Field(discriminator="type")]


class PostUpdate(BaseModel):
    """PATCH. Only what is present changes.

    Sending `recipe` replaces the whole ingredient and step set atomically and
    bumps the recipe version — a partial edit of a step list is ambiguous in a
    way that silently corrupts an ordered sequence.
    """

    title: str | None = Field(default=None, min_length=3, max_length=200)
    body_md: str | None = Field(default=None, max_length=50_000)
    media_ids: list[uuid.UUID] | None = Field(default=None, max_length=12)
    status: Literal[PostStatus.DRAFT, PostStatus.PUBLISHED] | None = None
    recipe: RecipeIn | None = None


# ------------------------------------------------------------------ output


class IngredientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position: int
    group_label: str | None
    quantity: float | None
    unit: str | None
    ingredient_name: str
    preparation_note: str | None
    is_optional: bool
    to_taste: bool


class StepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position: int
    instruction: str
    duration_minutes: int | None
    media_id: uuid.UUID | None


class RecipeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version: int
    servings: int
    yield_text: str | None
    prep_time_minutes: int | None
    cook_time_minutes: int | None
    total_time_minutes: int | None
    difficulty: Difficulty | None
    cuisine: str | None
    dietary_tags: list[str]
    ingredients: list[IngredientOut] = Field(default_factory=list)
    steps: list[StepOut] = Field(default_factory=list)


class AuthorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str
    display_name: str
    avatar_media_id: uuid.UUID | None


class PostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: PostType
    status: PostStatus
    title: str
    slug: str
    body_md: str | None
    author: AuthorOut
    media_ids: list[uuid.UUID] = Field(default_factory=list)

    comment_count: int
    save_count: int
    vote_score: int
    review_count: int
    # "X% would make again (n)" — the only score this platform publishes.
    make_again_pct: float | None
    wilson_lb: float | None

    recipe: RecipeOut | None = None
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None


class PostSummary(BaseModel):
    """Feed row. Deliberately narrower than PostOut: a feed of fifty posts
    should not carry fifty full ingredient lists."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: PostType
    title: str
    slug: str
    author: AuthorOut
    media_ids: list[uuid.UUID] = Field(default_factory=list)
    comment_count: int
    save_count: int
    vote_score: int
    review_count: int
    make_again_pct: float | None
    total_time_minutes: int | None = None
    created_at: datetime


class PostPage(BaseModel):
    items: list[PostSummary]
    # Opaque by design: callers should not construct one by hand.
    next_cursor: str | None = None
