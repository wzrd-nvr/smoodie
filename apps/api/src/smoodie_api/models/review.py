"""The two-tier critique system.

The full model lands now, in one migration, even though the MVP only fills part
of it. Tier 2's columns, cook sessions and reliability are all nullable and
unused until M6/M7 — but retrofitting them later would mean migrating live
review data into a shape it was never written for.

Design reference: docs/review-system.html
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from smoodie_api.db import Base, pg_enum


class Fidelity(enum.StrEnum):
    AS_WRITTEN = "as_written"
    MINOR_CHANGE = "minor_change"
    MAJOR_CHANGE = "major_change"


class Outcome(enum.StrEnum):
    WORKED = "worked"
    FAILED = "failed"


class SessionKind(enum.StrEnum):
    # Live cook mode arrives in M6; retroactive is the MVP's only path.
    LIVE = "live"
    RETROACTIVE = "retroactive"


class SessionState(enum.StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class AbandonReason(enum.StrEnum):
    RAN_OUT_OF_TIME = "ran_out_of_time"
    MISSING_INGREDIENT = "missing_ingredient"
    STEP_UNCLEAR = "step_unclear"
    TECHNIQUE_FAILED = "technique_failed"
    CHANGED_PLANS = "changed_plans"
    EQUIPMENT_ISSUE = "equipment_issue"


class InstrumentLevel(enum.StrEnum):
    VERDICT = "verdict"
    REPORT = "report"
    CALIBRATED = "calibrated"


class AttributeKind(enum.StrEnum):
    JAR = "jar"
    CATA = "cata"
    MODALITY = "modality"


class CookSession(Base):
    """Evidence that a cook happened.

    Two kinds. A live session (M6) accumulates telemetry as someone cooks. A
    retroactive claim is the MVP's path: someone cooked from a propped-up
    tablet or a printed page, and answers a few recipe-derived questions
    afterwards. Blocking the second group would be unacceptable, so the model
    treats it as a first-class route with a lower confidence ceiling.
    """

    __tablename__ = "cook_sessions"
    __table_args__ = (
        Index("ix_cook_sessions_user_recipe", "user_id", "recipe_post_id"),
        CheckConstraint(
            "checklist_pct IS NULL OR checklist_pct BETWEEN 0 AND 100",
            name="ck_cook_sessions_checklist_pct",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    recipe_post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recipes.post_id", ondelete="CASCADE")
    )
    recipe_version: Mapped[int] = mapped_column(Integer, default=1)

    kind: Mapped[SessionKind] = mapped_column(pg_enum(SessionKind, "cook_session_kind"))
    state: Mapped[SessionState] = mapped_column(
        pg_enum(SessionState, "cook_session_state"),
        default=SessionState.ACTIVE,
    )

    # Sessions pause and resume: sourdough and cured meats span days, and a
    # plausible-time band computed against wall clock alone would fail them all.
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    timers_started: Mapped[int] = mapped_column(Integer, default=0)
    checklist_pct: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    # Survivorship bias mitigation: people who abandon never leave reviews, so
    # the abandonment itself is captured. Bucketed by step, this tells an author
    # more than a hundred glowing verdicts.
    abandoned_at_step: Mapped[int | None] = mapped_column(Integer, nullable=True)
    abandon_reason: Mapped[AbandonReason | None] = mapped_column(
        pg_enum(AbandonReason, "cook_abandon_reason"), nullable=True
    )

    # Retroactive claims only: answers to outcome-variance questions that have
    # no lookup-able correct answer, checked for internal consistency.
    plausibility_answers: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class Review(Base):
    """A verdict on a recipe.

    Tier 1 is the required core: did it work, did you follow it, would you make
    it again. Tier 2's hedonic, descriptive and execution blocks are nullable
    and only offered to accounts that have cleared Gate B.
    """

    __tablename__ = "reviews"
    __table_args__ = (
        # One standing review per person per recipe. Cooking it again updates
        # the verdict; the history lives in the event stream.
        UniqueConstraint("recipe_post_id", "user_id", name="uq_review_per_user_recipe"),
        CheckConstraint("tier IN (1, 2)", name="ck_reviews_tier"),
        CheckConstraint("note IS NULL OR char_length(note) <= 280", name="ck_reviews_note_length"),
        CheckConstraint(
            "overall_liking IS NULL OR overall_liking BETWEEN 1 AND 5",
            name="ck_reviews_overall_liking",
        ),
        Index("ix_reviews_recipe", "recipe_post_id", "created_at"),
        Index("ix_reviews_user", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipe_post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recipes.post_id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    cook_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cook_sessions.id", ondelete="SET NULL"), nullable=True
    )

    # Pinned so an author's later edit never silently reattributes this verdict.
    recipe_version: Mapped[int] = mapped_column(Integer, default=1)
    tier: Mapped[int] = mapped_column(SmallInteger, default=1)

    # --- Tier 1: three inputs, one screen ---
    make_again: Mapped[bool] = mapped_column(Boolean)
    fidelity: Mapped[Fidelity] = mapped_column(pg_enum(Fidelity, "review_fidelity"))
    # Separate from make_again on purpose: "it worked and I won't repeat it" and
    # "it failed and I'll retry" are both common and both meaningful.
    outcome: Mapped[Outcome] = mapped_column(pg_enum(Outcome, "review_outcome"))
    note: Mapped[str | None] = mapped_column(String(280), nullable=True)
    photo_media_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media.id", ondelete="SET NULL"), nullable=True
    )
    # Structured swaps captured as chips, not free text: three seconds to
    # answer, and no parsing problem afterwards.
    ingredient_swaps: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # --- Tier 2, all nullable until Gate B clears (M7) ---
    overall_liking: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    jar: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    cata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    execution: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    modality: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    context: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ReviewConfidence(Base):
    """Gate A's output, versioned.

    Confidence is not frozen at write time. A photo later matched to a stolen
    source, or a shift in the author's reliability, has to be able to move it —
    so each computation is a row carrying the model version that produced it,
    and only one is current.
    """

    __tablename__ = "review_confidence"
    __table_args__ = (
        CheckConstraint("cook_confidence BETWEEN 0 AND 1", name="ck_review_confidence_range"),
        Index(
            "ix_review_confidence_current",
            "review_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reviews.id", ondelete="CASCADE")
    )
    cook_confidence: Mapped[float] = mapped_column(Numeric(4, 3))
    model_version: Mapped[str] = mapped_column(String(16))
    # What the score was built from, so a later recompute can be explained.
    signals: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class UserReliability(Base):
    """Gate B state: what instrument this account has earned.

    Slow-moving and per-account, unlike confidence which is per-review. A
    first-time cook with perfect evidence still gets Tier 1 only; a calibrated
    veteran reviewing something they did not cook still fails Gate A.
    """

    __tablename__ = "user_reliability"
    __table_args__ = (
        CheckConstraint("reliability BETWEEN 0 AND 1", name="ck_user_reliability_range"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    reliability: Mapped[float] = mapped_column(Numeric(4, 3), default=1.0)
    instrument_level: Mapped[InstrumentLevel] = mapped_column(
        pg_enum(InstrumentLevel, "instrument_level"),
        default=InstrumentLevel.VERDICT,
    )
    verified_cooks: Mapped[int] = mapped_column(Integer, default=0)
    completed_reports: Mapped[int] = mapped_column(Integer, default=0)
    consensus_agreement: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    # Detects straggler behaviour: a user answering "just about right" to
    # everything is clicking through, not perceiving, and should not be handed
    # intensity sliders.
    jar_variance: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    scale_usage_correction: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    moderation_strikes: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ReviewAttribute(Base):
    """The JAR / CATA / modality vocabularies, per category."""

    __tablename__ = "review_attributes"
    __table_args__ = (UniqueConstraint("kind", "slug", name="uq_review_attribute_slug"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[AttributeKind] = mapped_column(pg_enum(AttributeKind, "review_attribute_kind"))
    slug: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(60))
    category: Mapped[str | None] = mapped_column(String(60), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class RecipeReviewAxis(Base):
    """The JAR axes an author chose for their recipe. At most four."""

    __tablename__ = "recipe_review_axes"
    __table_args__ = (
        # The composite primary key already makes the pair unique.
        CheckConstraint("position BETWEEN 1 AND 4", name="ck_recipe_axis_position"),
    )

    recipe_post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recipes.post_id", ondelete="CASCADE"), primary_key=True
    )
    attribute_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("review_attributes.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(SmallInteger)


class CommentSummary(Base):
    """Phase-2 output (M8). Created now so the AI work has somewhere to land."""

    __tablename__ = "comment_summaries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"), index=True
    )
    summary_md: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(64))
    comment_count_at_generation: Mapped[int] = mapped_column(Integer)
    # Lets a regeneration be skipped when the underlying comments have not moved.
    source_hash: Mapped[str] = mapped_column(String(64))
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ReviewAggregate(Base):
    """Phase-2 output (M8): pros, cons and sentiment rolled up from reviews."""

    __tablename__ = "review_aggregates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"), index=True
    )
    pros: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    cons: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    sentiment_score: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    review_count_at_generation: Mapped[int] = mapped_column(Integer)
    model: Mapped[str] = mapped_column(String(64))
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
