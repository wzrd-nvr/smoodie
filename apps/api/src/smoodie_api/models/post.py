import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from smoodie_api.db import Base, pg_enum

if TYPE_CHECKING:
    # Import-time cycles: these modules import Post in turn, so the names exist
    # only for the type checker and are resolved by SQLAlchemy at mapper config.
    from smoodie_api.models.recipe import PostMedia, Recipe
    from smoodie_api.models.user import User


class PostType(enum.StrEnum):
    DISCUSSION = "discussion"
    RECIPE = "recipe"


class PostStatus(enum.StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    REMOVED = "removed"


class Post(Base):
    """A discussion thread or a recipe.

    Both live in one table because everything the platform does to a post —
    comments, saves, moderation, feeds — applies to both kinds. What differs is
    the structured recipe body, which lives in its own 1:1 extension.
    """

    __tablename__ = "posts"
    __table_args__ = (
        CheckConstraint("char_length(title) BETWEEN 3 AND 200", name="ck_posts_title_length"),
        CheckConstraint("rating_count >= 0", name="ck_posts_rating_count_positive"),
        # Feed reads: newest published posts of a kind.
        Index("ix_posts_feed", "type", "status", "created_at"),
        # Top reads: best-scoring recipes only, so the index stays small.
        Index(
            "ix_posts_top",
            "wilson_lb",
            # Cast is required: status is an enum type, and Postgres will not
            # compare it to a bare string literal inside an index predicate.
            postgresql_where=text("status = 'published'::post_status"),
        ),
        Index("ix_posts_author", "author_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[PostType] = mapped_column(pg_enum(PostType, "post_type"))
    status: Mapped[PostStatus] = mapped_column(
        pg_enum(PostStatus, "post_status"), default=PostStatus.DRAFT
    )

    title: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(220), index=True)
    body_md: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Denormalized counters. Recomputed by the services that own them rather
    # than by triggers, so the arithmetic is visible and testable in Python.
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    save_count: Mapped[int] = mapped_column(Integer, default=0)
    vote_score: Mapped[int] = mapped_column(Integer, default=0)

    # Recipe scoring. Public display is "X% would make again (n)" — never stars.
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    rating_count: Mapped[int] = mapped_column(Integer, default=0)
    make_again_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    wilson_lb: Mapped[float | None] = mapped_column(Numeric(6, 5), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    author: Mapped["User"] = relationship(lazy="raise")
    recipe: Mapped["Recipe | None"] = relationship(
        back_populates="post", cascade="all, delete-orphan", uselist=False, lazy="raise"
    )
    media_links: Mapped[list["PostMedia"]] = relationship(
        cascade="all, delete-orphan",
        order_by="PostMedia.position",
        lazy="raise",
    )
