"""Post CRUD, feeds and recipe versioning."""

from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smoodie_api.models.event import EventOutbox
from smoodie_api.models.recipe import Recipe, RecipeIngredient
from tests.fakes import FakeObjectStore, FakeVerifier


async def _sign_in(client: httpx.AsyncClient, verifier: FakeVerifier, token: str = "tok", **kw):
    verifier.register(token, **kw)
    assert (await client.post("/v1/auth/session", json={"id_token": token})).status_code == 200


async def _photo(client: httpx.AsyncClient, store: FakeObjectStore) -> str:
    ticket = (await client.post("/v1/media/uploads", json={"content_type": "image/jpeg"})).json()
    store.put(store.signed[-1][0], size=1024, content_type="image/jpeg")
    assert (await client.post(f"/v1/media/{ticket['media_id']}/complete")).status_code == 200
    return ticket["media_id"]


def _recipe_body(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "servings": 4,
        "prep_time_minutes": 10,
        "cook_time_minutes": 25,
        "cuisine": "italian",
        "dietary_tags": ["vegetarian"],
        "ingredients": [
            {"position": 1, "quantity": 200, "unit": "g", "ingredient_name": "flour"},
            {"position": 2, "quantity": 300, "unit": "ml", "ingredient_name": "water"},
        ],
        "steps": [
            {"position": 1, "instruction": "Combine the flour and water."},
            {"position": 2, "instruction": "Bake until golden and firm."},
        ],
    }
    base.update(kw)
    return base


async def _create_recipe(
    client: httpx.AsyncClient, store: FakeObjectStore, **kw: Any
) -> dict[str, Any]:
    photo = await _photo(client, store)
    payload: dict[str, Any] = {
        "type": "recipe",
        "title": "A dependable weeknight loaf",
        "media_ids": [photo],
        "recipe": _recipe_body(),
    }
    payload.update(kw)
    resp = await client.post("/v1/posts", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_creating_a_recipe_returns_the_whole_thing(
    client: httpx.AsyncClient, verifier: FakeVerifier, store: FakeObjectStore
) -> None:
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")

    post = await _create_recipe(client, store)

    assert post["type"] == "recipe"
    assert post["slug"] == "a-dependable-weeknight-loaf"
    assert post["recipe"]["version"] == 1
    assert post["recipe"]["total_time_minutes"] == 35
    assert [i["ingredient_name"] for i in post["recipe"]["ingredients"]] == ["flour", "water"]
    assert post["author"]["username"] == "angel"


async def test_creating_a_recipe_emits_a_full_snapshot(
    client: httpx.AsyncClient, verifier: FakeVerifier, store: FakeObjectStore, db: AsyncSession
) -> None:
    """The snapshot is the ML training corpus — a later edit or delete must not
    rewrite what the model already learned from."""
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")
    await _create_recipe(client, store)

    event = (
        (await db.execute(select(EventOutbox).where(EventOutbox.event_type == "recipe_created")))
        .scalars()
        .one()
    )
    assert event.payload["version"] == 1
    assert len(event.payload["ingredients"]) == 2
    assert event.payload["ingredients"][0]["name"] == "flour"
    assert len(event.payload["steps"]) == 2


async def test_posting_requires_auth(client: httpx.AsyncClient) -> None:
    resp = await client.post("/v1/posts", json={"type": "discussion", "title": "x", "body_md": "y"})
    assert resp.status_code == 401


async def test_an_incomplete_recipe_is_blocked_with_a_field_error(
    client: httpx.AsyncClient, verifier: FakeVerifier, store: FakeObjectStore
) -> None:
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")
    photo = await _photo(client, store)

    resp = await client.post(
        "/v1/posts",
        json={
            "type": "recipe",
            "title": "Half a recipe",
            "media_ids": [photo],
            "recipe": _recipe_body(steps=[{"position": 1, "instruction": "Do the thing well."}]),
        },
    )

    assert resp.status_code == 422
    assert "at least 2 steps" in str(resp.json()["detail"])


async def test_a_recipe_cannot_borrow_someone_elses_photo(
    client: httpx.AsyncClient, verifier: FakeVerifier, store: FakeObjectStore
) -> None:
    await _sign_in(client, verifier, token="a", uid="u1", email="angel@example.com")
    stolen = await _photo(client, store)

    await _sign_in(client, verifier, token="b", uid="u2", email="other@example.com")
    resp = await client.post(
        "/v1/posts",
        json={
            "type": "recipe",
            "title": "Borrowed imagery",
            "media_ids": [stolen],
            "recipe": _recipe_body(),
        },
    )

    assert resp.status_code == 422
    assert "isn't available" in resp.json()["detail"]


async def test_editing_a_recipe_bumps_its_version(
    client: httpx.AsyncClient, verifier: FakeVerifier, store: FakeObjectStore
) -> None:
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")
    post = await _create_recipe(client, store)

    resp = await client.patch(
        f"/v1/posts/{post['id']}",
        json={"recipe": _recipe_body(servings=8)},
    )

    assert resp.status_code == 200
    assert resp.json()["recipe"]["version"] == 2
    assert resp.json()["recipe"]["servings"] == 8


async def test_editing_replaces_the_ingredient_set_atomically(
    client: httpx.AsyncClient, verifier: FakeVerifier, store: FakeObjectStore, db: AsyncSession
) -> None:
    """A partial update of an ordered sequence corrupts it quietly, so the
    whole set is rewritten."""
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")
    post = await _create_recipe(client, store)

    await client.patch(
        f"/v1/posts/{post['id']}",
        json={
            "recipe": _recipe_body(
                ingredients=[
                    {"position": 1, "quantity": 1, "unit": "cup", "ingredient_name": "rice"},
                    {"position": 2, "quantity": 2, "unit": "cup", "ingredient_name": "stock"},
                    {"position": 3, "ingredient_name": "salt", "to_taste": True},
                ]
            )
        },
    )

    rows = (await db.execute(select(RecipeIngredient))).scalars().all()
    assert sorted(r.ingredient_name for r in rows) == ["rice", "salt", "stock"]
    assert len(rows) == 3, "old ingredients must not linger alongside the new set"


async def test_only_the_author_can_edit(
    client: httpx.AsyncClient, verifier: FakeVerifier, store: FakeObjectStore
) -> None:
    await _sign_in(client, verifier, token="a", uid="u1", email="angel@example.com")
    post = await _create_recipe(client, store)

    await _sign_in(client, verifier, token="b", uid="u2", email="other@example.com")
    resp = await client.patch(f"/v1/posts/{post['id']}", json={"title": "Hijacked title"})

    assert resp.status_code == 404, "someone else's post should not be distinguishable"


async def test_a_discussion_post_rejects_a_recipe_body(
    client: httpx.AsyncClient, verifier: FakeVerifier
) -> None:
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")
    created = await client.post(
        "/v1/posts",
        json={"type": "discussion", "title": "Just talking", "body_md": "Hello."},
    )
    post_id = created.json()["id"]

    resp = await client.patch(f"/v1/posts/{post_id}", json={"recipe": _recipe_body()})

    assert resp.status_code == 422
    assert "isn't a recipe" in resp.json()["detail"]


async def test_changing_the_title_moves_the_slug(
    client: httpx.AsyncClient, verifier: FakeVerifier, store: FakeObjectStore
) -> None:
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")
    post = await _create_recipe(client, store)

    resp = await client.patch(f"/v1/posts/{post['id']}", json={"title": "Renamed loaf"})

    assert resp.json()["slug"] == "renamed-loaf"


async def test_deleting_hides_the_post(
    client: httpx.AsyncClient, verifier: FakeVerifier, store: FakeObjectStore
) -> None:
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")
    post = await _create_recipe(client, store)

    assert (await client.delete(f"/v1/posts/{post['id']}")).status_code == 204
    assert (await client.get(f"/v1/posts/{post['id']}")).status_code == 404


async def test_a_draft_needs_no_photo_and_publishing_later_works(
    client: httpx.AsyncClient, verifier: FakeVerifier, store: FakeObjectStore
) -> None:
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")

    draft = await client.post(
        "/v1/posts",
        json={
            "type": "recipe",
            "title": "Work in progress loaf",
            "media_ids": [],
            "status": "draft",
            "recipe": _recipe_body(),
        },
    )
    assert draft.status_code == 201
    assert draft.json()["published_at"] is None

    photo = await _photo(client, store)
    published = await client.patch(
        f"/v1/posts/{draft.json()['id']}",
        json={"status": "published", "media_ids": [photo]},
    )
    assert published.json()["status"] == "published"
    assert published.json()["published_at"] is not None


# ------------------------------------------------------------------- feeds


async def test_the_feed_shows_published_posts_newest_first(
    client: httpx.AsyncClient, verifier: FakeVerifier, store: FakeObjectStore
) -> None:
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")
    for n in range(3):
        await _create_recipe(client, store, title=f"Recipe number {n}")

    resp = await client.get("/v1/posts")

    titles = [item["title"] for item in resp.json()["items"]]
    assert titles == ["Recipe number 2", "Recipe number 1", "Recipe number 0"]


async def test_drafts_stay_out_of_the_feed(
    client: httpx.AsyncClient, verifier: FakeVerifier
) -> None:
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")
    await client.post(
        "/v1/posts",
        json={
            "type": "discussion",
            "title": "A private draft",
            "body_md": "Not ready.",
            "status": "draft",
        },
    )

    assert (await client.get("/v1/posts")).json()["items"] == []


async def test_the_feed_can_be_filtered_by_type(
    client: httpx.AsyncClient, verifier: FakeVerifier, store: FakeObjectStore
) -> None:
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")
    await _create_recipe(client, store)
    await client.post(
        "/v1/posts", json={"type": "discussion", "title": "Just chatting", "body_md": "Hi."}
    )

    recipes = await client.get("/v1/posts", params={"type": "recipe"})
    assert len(recipes.json()["items"]) == 1
    assert recipes.json()["items"][0]["type"] == "recipe"


async def test_dietary_filters_require_every_tag(
    client: httpx.AsyncClient, verifier: FakeVerifier, store: FakeObjectStore
) -> None:
    """Someone filtering vegan and gluten-free cannot eat a dish that is only one."""
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")
    await _create_recipe(
        client, store, title="Only vegetarian", recipe=_recipe_body(dietary_tags=["vegetarian"])
    )
    await _create_recipe(
        client,
        store,
        title="Both tags present",
        recipe=_recipe_body(dietary_tags=["vegetarian", "gluten-free"]),
    )

    resp = await client.get(
        "/v1/posts", params=[("dietary", "vegetarian"), ("dietary", "gluten-free")]
    )

    titles = [i["title"] for i in resp.json()["items"]]
    assert titles == ["Both tags present"]


async def test_paging_walks_every_post_exactly_once(
    client: httpx.AsyncClient, verifier: FakeVerifier, store: FakeObjectStore
) -> None:
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")
    for n in range(5):
        await _create_recipe(client, store, title=f"Paged recipe {n}")

    seen: list[str] = []
    cursor = None
    for _ in range(10):  # bounded so a broken cursor cannot spin forever
        params = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        page = (await client.get("/v1/posts", params=params)).json()
        seen.extend(item["id"] for item in page["items"])
        cursor = page["next_cursor"]
        if not cursor:
            break

    assert len(seen) == 5
    assert len(set(seen)) == 5, "a post appeared on two pages"


async def test_a_nonsense_cursor_starts_from_the_top(
    client: httpx.AsyncClient, verifier: FakeVerifier, store: FakeObjectStore
) -> None:
    """A hand-made cursor is friendlier to reset than to reject."""
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")
    await _create_recipe(client, store)

    resp = await client.get("/v1/posts", params={"cursor": "not-a-real-cursor"})

    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1


@pytest.mark.parametrize("sort", ["new", "top"])
async def test_both_sorts_are_accepted(
    client: httpx.AsyncClient, verifier: FakeVerifier, store: FakeObjectStore, sort: str
) -> None:
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")
    await _create_recipe(client, store)
    resp = await client.get("/v1/posts", params={"sort": sort})
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1


async def test_an_unknown_sort_is_rejected(client: httpx.AsyncClient) -> None:
    assert (await client.get("/v1/posts", params={"sort": "sideways"})).status_code == 422


async def test_the_feed_omits_recipe_bodies(
    client: httpx.AsyncClient, verifier: FakeVerifier, store: FakeObjectStore
) -> None:
    """Fifty posts should not carry fifty full ingredient lists."""
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")
    await _create_recipe(client, store)

    item = (await client.get("/v1/posts")).json()["items"][0]

    assert "ingredients" not in item
    assert item["total_time_minutes"] == 35


async def test_recipe_version_survives_an_unrelated_edit(
    client: httpx.AsyncClient, verifier: FakeVerifier, store: FakeObjectStore, db: AsyncSession
) -> None:
    """Renaming a post does not change the recipe anyone cooked."""
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")
    post = await _create_recipe(client, store)

    await client.patch(f"/v1/posts/{post['id']}", json={"title": "Just a new name"})

    recipe = (await db.execute(select(Recipe))).scalar_one()
    assert recipe.version == 1
