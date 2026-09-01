import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from smoodie_api.db import Base, pg_enum

if TYPE_CHECKING:
    from smoodie_api.models.post import Post


class Difficulty(enum.StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class Recipe(Base):
    """The structured half of a recipe post.

    Existence of this row is what makes a post a valid recipe. The listing
    requirements are enforced in Pydantic where the errors can be addressed to
    individual form fields; the constraints here are the backstop that stops a
    bad row arriving by any other route.
    """

    __tablename__ = "recipes"
    __table_args__ = (
        CheckConstraint("servings >= 1", name="ck_recipes_servings"),
        CheckConstraint(
            "prep_time_minutes IS NULL OR prep_time_minutes >= 0", name="ck_recipes_prep_time"
        ),
        CheckConstraint(
            "cook_time_minutes IS NULL OR cook_time_minutes >= 0", name="ck_recipes_cook_time"
        ),
        # A recipe with no time at all tells the reader nothing about the
        # commitment, and Gate A needs something to compare a cook against.
        CheckConstraint(
            "prep_time_minutes IS NOT NULL OR cook_time_minutes IS NOT NULL",
            name="ck_recipes_some_time_given",
        ),
        CheckConstraint("version >= 1", name="ck_recipes_version"),
        Index("ix_recipes_dietary_tags", "dietary_tags", postgresql_using="gin"),
        Index("ix_recipes_cuisine", "cuisine"),
    )

    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True
    )

    # Authors edit recipes. Reviews pin the version they cooked so a verdict is
    # never silently attributed to a recipe that has since changed underneath it.
    version: Mapped[int] = mapped_column(Integer, default=1)

    servings: Mapped[int] = mapped_column(Integer)
    yield_text: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prep_time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cook_time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_time_minutes: Mapped[int | None] = mapped_column(
        Integer,
        Computed("COALESCE(prep_time_minutes, 0) + COALESCE(cook_time_minutes, 0)", persisted=True),
    )

    difficulty: Mapped[Difficulty | None] = mapped_column(
        pg_enum(Difficulty, "recipe_difficulty"), nullable=True
    )
    cuisine: Mapped[str | None] = mapped_column(String(60), nullable=True)
    dietary_tags: Mapped[list[str]] = mapped_column(
        ARRAY(String(40)), server_default="{}", default=list
    )

    # Gate A compares a cook session against these bands. Stored per recipe
    # because a cocktail and a braise are not comparable on a global average.
    expected_active_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_total_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    post: Mapped["Post"] = relationship(back_populates="recipe", lazy="raise")
    ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        cascade="all, delete-orphan",
        order_by="RecipeIngredient.position",
        lazy="raise",
    )
    steps: Mapped[list["RecipeStep"]] = relationship(
        cascade="all, delete-orphan",
        order_by="RecipeStep.position",
        lazy="raise",
    )


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"
    __table_args__ = (
        UniqueConstraint("recipe_post_id", "position", name="uq_recipe_ingredient_position"),
        # Either a measurable amount, or an explicit "to taste". Anything else
        # is an ingredient line a cook cannot act on.
        CheckConstraint("quantity IS NOT NULL OR to_taste", name="ck_ingredient_has_amount"),
        CheckConstraint("quantity IS NULL OR quantity > 0", name="ck_ingredient_quantity_positive"),
        Index("ix_recipe_ingredients_recipe", "recipe_post_id", "position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipe_post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recipes.post_id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(Integer)
    group_label: Mapped[str | None] = mapped_column(String(80), nullable=True)

    quantity: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ingredient_name: Mapped[str] = mapped_column(String(120))
    preparation_note: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_optional: Mapped[bool] = mapped_column(Boolean, default=False)
    to_taste: Mapped[bool] = mapped_column(Boolean, default=False)

    # Reserved for the phase-2 ingredient normalization that the recipe builder
    # needs. Nullable and unused until then.
    canonical_ingredient_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )


class RecipeStep(Base):
    __tablename__ = "recipe_steps"
    __table_args__ = (
        UniqueConstraint("recipe_post_id", "position", name="uq_recipe_step_position"),
        # A step too short to be an instruction is a formatting artifact.
        CheckConstraint("char_length(instruction) >= 10", name="ck_step_instruction_length"),
        Index("ix_recipe_steps_recipe", "recipe_post_id", "position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipe_post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recipes.post_id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(Integer)
    instruction: Mapped[str] = mapped_column(Text)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    media_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media.id", ondelete="SET NULL"), nullable=True
    )


class PostMedia(Base):
    """Photos attached to a post, in display order."""

    __tablename__ = "post_media"

    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True
    )
    media_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)


__all__ = ["Difficulty", "PostMedia", "Recipe", "RecipeIngredient", "RecipeStep"]
