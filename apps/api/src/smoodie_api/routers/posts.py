"""Posts: discussions and recipes."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from smoodie_api.auth.dependencies import CurrentUser
from smoodie_api.db import get_session
from smoodie_api.models.post import Post, PostStatus, PostType
from smoodie_api.schemas.post import (
    AuthorOut,
    PostCreate,
    PostOut,
    PostPage,
    PostSummary,
    PostUpdate,
    RecipeOut,
)
from smoodie_api.services import posts as post_service
from smoodie_api.services.posts import MediaNotUsable

router = APIRouter(prefix="/v1/posts", tags=["posts"])


def _to_out(post: Post) -> PostOut:
    return PostOut(
        id=post.id,
        type=post.type,
        status=post.status,
        title=post.title,
        slug=post.slug,
        body_md=post.body_md,
        author=AuthorOut.model_validate(post.author),
        media_ids=[link.media_id for link in post.media_links],
        comment_count=post.comment_count,
        save_count=post.save_count,
        vote_score=post.vote_score,
        review_count=post.review_count,
        make_again_pct=float(post.make_again_pct) if post.make_again_pct is not None else None,
        wilson_lb=float(post.wilson_lb) if post.wilson_lb is not None else None,
        recipe=RecipeOut.model_validate(post.recipe) if post.recipe else None,
        created_at=post.created_at,
        updated_at=post.updated_at,
        published_at=post.published_at,
    )


def _to_summary(post: Post) -> PostSummary:
    return PostSummary(
        id=post.id,
        type=post.type,
        title=post.title,
        slug=post.slug,
        author=AuthorOut.model_validate(post.author),
        media_ids=[link.media_id for link in post.media_links],
        comment_count=post.comment_count,
        save_count=post.save_count,
        vote_score=post.vote_score,
        review_count=post.review_count,
        make_again_pct=float(post.make_again_pct) if post.make_again_pct is not None else None,
        total_time_minutes=post.recipe.total_time_minutes if post.recipe else None,
        created_at=post.created_at,
    )


@router.get("", response_model=PostPage)
async def list_posts(
    session: Annotated[AsyncSession, Depends(get_session)],
    type: PostType | None = None,
    sort: Annotated[str, Query(pattern="^(new|top)$")] = "new",
    cuisine: str | None = None,
    dietary: Annotated[list[str] | None, Query()] = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=post_service.MAX_PAGE_SIZE)] = (
        post_service.DEFAULT_PAGE_SIZE
    ),
) -> PostPage:
    items, next_cursor = await post_service.list_posts(
        session,
        post_type=type,
        cuisine=cuisine,
        dietary=dietary,
        sort=sort,
        cursor=cursor,
        limit=limit,
    )
    return PostPage(items=[_to_summary(p) for p in items], next_cursor=next_cursor)


@router.post("", response_model=PostOut, status_code=status.HTTP_201_CREATED)
async def create_post(
    body: PostCreate,
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PostOut:
    try:
        post = await post_service.create_post(session, user, body)
    except MediaNotUsable as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    await session.commit()
    created = await post_service.get_post(session, post.id)
    assert created is not None
    return _to_out(created)


@router.get("/{post_id}", response_model=PostOut)
async def read_post(
    post_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PostOut:
    post = await post_service.get_post(session, post_id)
    # Drafts are private to their author until published.
    if post is None or post.status is PostStatus.REMOVED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such post.")
    return _to_out(post)


@router.patch("/{post_id}", response_model=PostOut)
async def update_post(
    post_id: uuid.UUID,
    body: PostUpdate,
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PostOut:
    post = await post_service.get_post(session, post_id)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such post.")
    if post.author_id != user.id:
        # 404 rather than 403: someone else's draft should not be discoverable.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such post.")
    if body.recipe is not None and post.type is not PostType.RECIPE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="This post isn't a recipe.",
        )

    try:
        await post_service.update_post(session, user, post, body)
    except MediaNotUsable as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    await session.commit()
    updated = await post_service.get_post(session, post_id)
    assert updated is not None
    return _to_out(updated)


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    post_id: uuid.UUID,
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    post = await post_service.get_post(session, post_id)
    if post is None or post.author_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such post.")

    # Soft delete: comments and reviews written by other people stay coherent.
    from datetime import UTC, datetime

    post.deleted_at = datetime.now(UTC)
    post.status = PostStatus.REMOVED
    await session.commit()
