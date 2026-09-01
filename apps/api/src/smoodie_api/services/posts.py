"""Post creation, editing and feeds."""

import base64
import binascii
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from smoodie_api.models.media import Media, MediaStatus
from smoodie_api.models.post import Post, PostStatus, PostType
from smoodie_api.models.recipe import PostMedia, Recipe, RecipeIngredient, RecipeStep
from smoodie_api.models.user import User
from smoodie_api.schemas.post import DiscussionCreate, PostUpdate, RecipeCreate, RecipeIn
from smoodie_api.services.events import record_event
from smoodie_api.services.slugs import slugify

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50


class MediaNotUsable(ValueError):
    """A referenced image is missing, unfinished, or someone else's."""


@dataclass(frozen=True)
class Cursor:
    """Keyset pagination.

    Ordered by (sort key, id) so a post inserted mid-scroll cannot shift rows
    across a page boundary the way OFFSET does.
    """

    sort_value: str
    post_id: uuid.UUID

    def encode(self) -> str:
        raw = json.dumps({"v": self.sort_value, "id": str(self.post_id)})
        return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")

    @staticmethod
    def decode(token: str) -> "Cursor | None":
        try:
            padded = token + "=" * (-len(token) % 4)
            data = json.loads(base64.urlsafe_b64decode(padded))
            return Cursor(sort_value=data["v"], post_id=uuid.UUID(data["id"]))
        except (ValueError, KeyError, TypeError, binascii.Error):
            # A malformed cursor means the caller hand-made one. Starting from
            # the top is friendlier than a 400 they cannot act on.
            return None


async def _usable_media(
    session: AsyncSession, owner: User, media_ids: list[uuid.UUID]
) -> list[uuid.UUID]:
    """Confirm every image is the author's own finished upload."""
    if not media_ids:
        return []
    rows = await session.execute(
        select(Media.id).where(
            Media.id.in_(media_ids),
            Media.owner_id == owner.id,
            Media.status == MediaStatus.READY,
        )
    )
    found = {row[0] for row in rows}
    missing = [mid for mid in media_ids if mid not in found]
    if missing:
        raise MediaNotUsable("One of those images isn't available. Upload it again before posting.")
    # Preserve the order the author chose.
    return media_ids


def _recipe_snapshot(recipe: RecipeIn) -> dict[str, Any]:
    """The full recipe as written, for the event stream.

    This is the ML training corpus for the phase-2 recipe builder, so it stores
    the whole thing rather than a reference — a recipe edited or deleted later
    must not silently rewrite history the model already learned from.
    """
    return {
        "servings": recipe.servings,
        "prep_time_minutes": recipe.prep_time_minutes,
        "cook_time_minutes": recipe.cook_time_minutes,
        "difficulty": recipe.difficulty.value if recipe.difficulty else None,
        "cuisine": recipe.cuisine,
        "dietary_tags": list(recipe.dietary_tags),
        "ingredients": [
            {
                "position": i.position,
                "quantity": float(i.quantity) if i.quantity is not None else None,
                "unit": i.unit,
                "name": i.ingredient_name,
                "preparation": i.preparation_note,
                "optional": i.is_optional,
                "to_taste": i.to_taste,
            }
            for i in recipe.ingredients
        ],
        "steps": [
            {
                "position": s.position,
                "instruction": s.instruction,
                "duration_minutes": s.duration_minutes,
            }
            for s in recipe.steps
        ],
    }


async def _write_recipe_body(session: AsyncSession, post_id: uuid.UUID, body: RecipeIn) -> None:
    """Replace the ingredient and step sets wholesale.

    Rows are deleted and rewritten rather than diffed: positions form an ordered
    sequence, and a partial update of an ordered set is ambiguous in a way that
    corrupts it quietly.
    """
    await session.execute(
        delete(RecipeIngredient).where(RecipeIngredient.recipe_post_id == post_id)
    )
    await session.execute(delete(RecipeStep).where(RecipeStep.recipe_post_id == post_id))
    await session.flush()

    for item in body.ingredients:
        session.add(
            RecipeIngredient(
                recipe_post_id=post_id,
                position=item.position,
                group_label=item.group_label,
                quantity=item.quantity,
                unit=item.unit,
                ingredient_name=item.ingredient_name,
                preparation_note=item.preparation_note,
                is_optional=item.is_optional,
                to_taste=item.to_taste,
            )
        )
    for step in body.steps:
        session.add(
            RecipeStep(
                recipe_post_id=post_id,
                position=step.position,
                instruction=step.instruction,
                duration_minutes=step.duration_minutes,
                media_id=step.media_id,
            )
        )
    await session.flush()


async def _attach_media(
    session: AsyncSession, post_id: uuid.UUID, media_ids: list[uuid.UUID]
) -> None:
    await session.execute(delete(PostMedia).where(PostMedia.post_id == post_id))
    await session.flush()
    for position, media_id in enumerate(media_ids):
        session.add(PostMedia(post_id=post_id, media_id=media_id, position=position))
    await session.flush()


async def create_post(
    session: AsyncSession, author: User, body: DiscussionCreate | RecipeCreate
) -> Post:
    media_ids = await _usable_media(session, author, body.media_ids)

    post = Post(
        author_id=author.id,
        type=body.type,
        status=body.status,
        title=body.title,
        slug=slugify(body.title),
        body_md=body.body_md,
        published_at=datetime.now(UTC) if body.status is PostStatus.PUBLISHED else None,
    )
    session.add(post)
    await session.flush()

    if not post.slug:
        # A title with nothing transliterable in it still needs a URL.
        post.slug = str(post.id)

    await _attach_media(session, post.id, media_ids)

    if isinstance(body, RecipeCreate):
        recipe = Recipe(
            post_id=post.id,
            version=1,
            servings=body.recipe.servings,
            yield_text=body.recipe.yield_text,
            prep_time_minutes=body.recipe.prep_time_minutes,
            cook_time_minutes=body.recipe.cook_time_minutes,
            difficulty=body.recipe.difficulty,
            cuisine=body.recipe.cuisine,
            dietary_tags=list(body.recipe.dietary_tags),
        )
        session.add(recipe)
        await session.flush()
        await _write_recipe_body(session, post.id, body.recipe)

        await record_event(
            session,
            event_type="recipe_created",
            actor_id=author.id,
            entity_type="post",
            entity_id=post.id,
            payload={"version": 1, "title": post.title, **_recipe_snapshot(body.recipe)},
        )

    await record_event(
        session,
        event_type="post_created",
        actor_id=author.id,
        entity_type="post",
        entity_id=post.id,
        payload={
            "type": post.type.value,
            "status": post.status.value,
            "has_media": bool(media_ids),
        },
    )
    return post


async def update_post(session: AsyncSession, author: User, post: Post, body: PostUpdate) -> Post:
    changes = body.model_dump(exclude_unset=True)

    if "title" in changes and body.title:
        post.title = body.title
        post.slug = slugify(body.title) or str(post.id)
    if "body_md" in changes:
        post.body_md = body.body_md
    if "media_ids" in changes and body.media_ids is not None:
        media_ids = await _usable_media(session, author, body.media_ids)
        await _attach_media(session, post.id, media_ids)
    if "status" in changes and body.status is not None:
        if body.status is PostStatus.PUBLISHED and post.published_at is None:
            post.published_at = datetime.now(UTC)
        post.status = body.status

    if body.recipe is not None:
        recipe = (
            await session.execute(select(Recipe).where(Recipe.post_id == post.id))
        ).scalar_one()
        recipe.servings = body.recipe.servings
        recipe.yield_text = body.recipe.yield_text
        recipe.prep_time_minutes = body.recipe.prep_time_minutes
        recipe.cook_time_minutes = body.recipe.cook_time_minutes
        recipe.difficulty = body.recipe.difficulty
        recipe.cuisine = body.recipe.cuisine
        recipe.dietary_tags = list(body.recipe.dietary_tags)
        # Bumped so existing reviews stay pinned to what they actually judged.
        recipe.version += 1
        await session.flush()
        await _write_recipe_body(session, post.id, body.recipe)

        await record_event(
            session,
            event_type="recipe_created",
            actor_id=author.id,
            entity_type="post",
            entity_id=post.id,
            payload={
                "version": recipe.version,
                "title": post.title,
                **_recipe_snapshot(body.recipe),
            },
        )

    await session.flush()
    return post


def _loaded(stmt: Select[Any]) -> Select[Any]:
    return stmt.options(
        selectinload(Post.author),
        selectinload(Post.media_links),
        selectinload(Post.recipe).selectinload(Recipe.ingredients),
        selectinload(Post.recipe).selectinload(Recipe.steps),
    )


async def get_post(session: AsyncSession, post_id: uuid.UUID) -> Post | None:
    stmt = _loaded(select(Post).where(Post.id == post_id, Post.deleted_at.is_(None)))
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_posts(
    session: AsyncSession,
    *,
    post_type: PostType | None = None,
    cuisine: str | None = None,
    dietary: list[str] | None = None,
    sort: str = "new",
    cursor: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
) -> tuple[list[Post], str | None]:
    limit = max(1, min(limit, MAX_PAGE_SIZE))

    stmt = _loaded(
        select(Post).where(Post.status == PostStatus.PUBLISHED, Post.deleted_at.is_(None))
    )
    if post_type is not None:
        stmt = stmt.where(Post.type == post_type)
    if cuisine or dietary:
        stmt = stmt.join(Recipe, Recipe.post_id == Post.id)
        if cuisine:
            stmt = stmt.where(Recipe.cuisine == cuisine)
        if dietary:
            # Every requested tag must be present, not any of them: someone
            # filtering vegan + gluten-free cannot eat a dish that is only one.
            stmt = stmt.where(Recipe.dietary_tags.contains(dietary))

    # "top" ranks by the weighted Wilson lower bound, so a single glowing
    # verdict cannot outrank a recipe with a long, solid record.
    if sort == "top":
        stmt = stmt.order_by(Post.wilson_lb.desc().nullslast(), Post.id.desc())
    else:
        stmt = stmt.order_by(Post.created_at.desc(), Post.id.desc())

    decoded = Cursor.decode(cursor) if cursor else None
    if decoded is not None:
        if sort == "top":
            value: Any = float(decoded.sort_value)
            stmt = stmt.where(
                (Post.wilson_lb < value) | ((Post.wilson_lb == value) & (Post.id < decoded.post_id))
            )
        else:
            moment = datetime.fromisoformat(decoded.sort_value)
            stmt = stmt.where(
                (Post.created_at < moment)
                | ((Post.created_at == moment) & (Post.id < decoded.post_id))
            )

    rows = list((await session.execute(stmt.limit(limit + 1))).scalars().unique())
    has_more = len(rows) > limit
    items = rows[:limit]

    next_cursor = None
    if has_more and items:
        last = items[-1]
        raw = last.wilson_lb if sort == "top" else last.created_at
        if raw is not None:
            next_cursor = Cursor(
                sort_value=str(raw.isoformat() if isinstance(raw, datetime) else raw),
                post_id=last.id,
            ).encode()

    return items, next_cursor
