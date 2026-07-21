"""Public menu projection over HTTP (M3D, ADR-017).

Extends the permanent isolation matrix (docs/04) to the public menu: only
the Host selects a Business, only active Businesses have a menu, and the
projection exposes exactly the approved public fields.

Rows are seeded with direct SQL rather than through the administrative API
(the docs/06 bulk-fixture precedent): these tests are about what the public
projection *shows*, and driving dozens of visibility combinations through
authenticated admin calls would spend most of the runtime on Argon2.
Value-column defaults are application-side (ADR-017), so every seeded row
supplies them explicitly.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, text

from tests.security.conftest import CreateBusiness

_MENU = "/api/v1/public/menu"


def _host(host: str) -> dict[str, str]:
    return {"host": host}


def _get(client: TestClient, host: str = "shalik.localhost") -> Any:
    return client.get(_MENU, headers=_host(host))


def _seed_category(
    engine: Engine,
    business_id: uuid.UUID,
    *,
    name: str = "Curries",
    position: int = 0,
    is_visible: bool = True,
    description: str | None = None,
) -> uuid.UUID:
    category_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO menu_categories (id, business_id, name, description,"
                " position, is_visible) VALUES (:id, :bid, :name, :description,"
                " :position, :is_visible)"
            ),
            {
                "id": category_id,
                "bid": business_id,
                "name": name,
                "description": description,
                "position": position,
                "is_visible": is_visible,
            },
        )
    return category_id


def _seed_item(
    engine: Engine,
    business_id: uuid.UUID,
    category_id: uuid.UUID,
    *,
    name: str = "Samosa",
    price_minor: int = 350,
    position: int = 0,
    is_available: bool = True,
    is_hidden: bool = False,
    is_featured: bool = False,
    description: str | None = None,
    tags: tuple[str, ...] = (),
) -> uuid.UUID:
    item_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO menu_items (id, business_id, category_id, name, description,"
                " price_minor, position, is_available, is_hidden, is_featured)"
                " VALUES (:id, :bid, :cid, :name, :description, :price, :position,"
                " :is_available, :is_hidden, :is_featured)"
            ),
            {
                "id": item_id,
                "bid": business_id,
                "cid": category_id,
                "name": name,
                "description": description,
                "price": price_minor,
                "position": position,
                "is_available": is_available,
                "is_hidden": is_hidden,
                "is_featured": is_featured,
            },
        )
        for tag in tags:
            connection.execute(
                text(
                    "INSERT INTO menu_item_dietary_tags (id, business_id, item_id, tag)"
                    " VALUES (:id, :bid, :iid, :tag)"
                ),
                {"id": uuid.uuid4(), "bid": business_id, "iid": item_id, "tag": tag},
            )
    return item_id


def _seed_group(
    engine: Engine,
    business_id: uuid.UUID,
    item_id: uuid.UUID,
    *,
    name: str = "Spice level",
    min_select: int = 0,
    max_select: int | None = None,
    position: int = 0,
    options: tuple[tuple[str, int, bool], ...] = (),
) -> uuid.UUID:
    """Seed a group plus ``(name, price_delta_minor, is_available)`` options."""
    group_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO modifier_groups (id, business_id, item_id, name,"
                " min_select, max_select, position) VALUES (:id, :bid, :iid, :name,"
                " :min_select, :max_select, :position)"
            ),
            {
                "id": group_id,
                "bid": business_id,
                "iid": item_id,
                "name": name,
                "min_select": min_select,
                "max_select": max_select,
                "position": position,
            },
        )
        for index, (option_name, delta, available) in enumerate(options):
            connection.execute(
                text(
                    "INSERT INTO modifier_options (id, business_id, group_id, name,"
                    " price_delta_minor, is_available, position) VALUES (:id, :bid,"
                    " :gid, :name, :delta, :available, :position)"
                ),
                {
                    "id": uuid.uuid4(),
                    "bid": business_id,
                    "gid": group_id,
                    "name": option_name,
                    "delta": delta,
                    "available": available,
                    "position": index,
                },
            )
    return group_id


def _seed_media(
    engine: Engine,
    business_id: uuid.UUID,
    *,
    status: str = "active",
    variant_sizes: dict[str, int] | None = None,
) -> uuid.UUID:
    """Seed a media asset row plus variant rows (no stored objects needed).

    The projection describes images from the database inventory alone, so
    these tests need no bytes on disk — delivery of the bytes is covered by
    the public media suite.
    """
    asset_id = uuid.uuid4()
    sizes = variant_sizes if variant_sizes is not None else {"w320": 900, "w640": 2400}
    widths = {"w320": 320, "w640": 640, "w1280": 1280}
    expiry = "now() + interval '48 hours'" if status == "pending" else "NULL"
    with engine.begin() as connection:
        connection.execute(
            text(
                # S608: expiry is one of two test-internal literals.
                "INSERT INTO media_assets (id, business_id, kind, status,"  # noqa: S608
                " pending_expires_at, original_filename, declared_content_type,"
                " source_format, width, height, byte_size, checksum_sha256)"
                f" VALUES (:id, :bid, 'image', :status, {expiry}, 'dish.jpg',"
                " 'image/jpeg', 'jpeg', 1200, 800, 40000, :sha)"
            ),
            {"id": asset_id, "bid": business_id, "status": status, "sha": "a" * 64},
        )
        for variant, byte_size in sizes.items():
            connection.execute(
                text(
                    "INSERT INTO media_asset_variants (id, business_id, asset_id,"
                    " variant, width, height, byte_size, checksum_sha256) VALUES"
                    " (:id, :bid, :aid, :variant, :width, :height, :bytes, :sha)"
                ),
                {
                    "id": uuid.uuid4(),
                    "bid": business_id,
                    "aid": asset_id,
                    "variant": variant,
                    "width": widths[variant],
                    "height": int(widths[variant] * 2 / 3),
                    "bytes": byte_size,
                    "sha": "b" * 64,
                },
            )
    return asset_id


def _attach_image(
    engine: Engine, item_id: uuid.UUID, asset_id: uuid.UUID, *, alt: str | None = None
) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE menu_items SET image_media_id = :aid, image_alt_text = :alt WHERE id = :iid"
            ),
            {"aid": asset_id, "alt": alt, "iid": item_id},
        )


def _active(create_business: CreateBusiness, slug: str = "shalik") -> uuid.UUID:
    return create_business(slug=slug, name="Shalik", status="active")


class TestPublicMenuShape:
    def test_active_business_returns_its_menu(
        self, client: TestClient, create_business: CreateBusiness, migrated_engine: Engine
    ) -> None:
        business_id = _active(create_business)
        category_id = _seed_category(migrated_engine, business_id, description="Slow cooked")
        item_id = _seed_item(
            migrated_engine,
            business_id,
            category_id,
            description="Crisp pastry",
            tags=("halal", "vegan"),
        )

        response = _get(client)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["business"] == {
            "name": "Shalik",
            "slug": "shalik",
            "timezone": "America/New_York",
            "currency": "USD",
        }
        assert body["featured_item_ids"] == []
        (category,) = body["categories"]
        assert category["id"] == str(category_id)
        assert category["name"] == "Curries"
        assert category["description"] == "Slow cooked"
        (item,) = category["items"]
        assert item == {
            "id": str(item_id),
            "name": "Samosa",
            "description": "Crisp pastry",
            "price_minor": 350,
            "is_available": True,
            "is_orderable": True,
            "dietary_tags": ["halal", "vegan"],
            "image": None,
            "modifier_groups": [],
        }

    def test_currency_comes_only_from_the_business(
        self, client: TestClient, create_business: CreateBusiness, migrated_engine: Engine
    ) -> None:
        business_id = create_business(slug="shalik", status="active", currency="GBP")
        category_id = _seed_category(migrated_engine, business_id)
        _seed_item(migrated_engine, business_id, category_id)

        body = _get(client).json()
        assert body["business"]["currency"] == "GBP"
        assert "currency" not in body
        assert "currency" not in body["categories"][0]["items"][0]

    def test_empty_menu_is_an_empty_list_not_a_404(
        self, client: TestClient, create_business: CreateBusiness
    ) -> None:
        _active(create_business)
        response = _get(client)
        assert response.status_code == 200
        assert response.json()["categories"] == []
        assert response.json()["featured_item_ids"] == []

    def test_menu_response_is_never_cacheable(
        self, client: TestClient, create_business: CreateBusiness
    ) -> None:
        _active(create_business)
        assert _get(client).headers["cache-control"] == "no-store"


class TestPublicMenuResolutionAndIsolation:
    def _assert_neutral_404(self, response: Any) -> None:
        assert response.status_code == 404
        body = response.json()
        assert set(body) == {"error"}
        assert body["error"]["code"] == "not_found"
        assert body["error"]["message"] == "Not found."
        assert body["error"]["field_errors"] == []
        assert body["error"]["details"] is None
        assert response.headers["cache-control"] == "no-store"

    def test_unknown_host_is_neutral_404(self, client: TestClient) -> None:
        self._assert_neutral_404(_get(client, "nope.localhost"))

    def test_non_active_states_are_neutral_404(
        self, client: TestClient, create_business: CreateBusiness, migrated_engine: Engine
    ) -> None:
        # Negative control for the active-status predicate: a full menu
        # exists behind each of these and must stay invisible.
        for state in ("provisioning", "suspended", "closed"):
            business_id = create_business(slug=f"biz-{state}", status=state)
            category_id = _seed_category(migrated_engine, business_id)
            _seed_item(migrated_engine, business_id, category_id)
            self._assert_neutral_404(_get(client, f"biz-{state}.localhost"))

    def test_malformed_reserved_apex_and_ip_hosts_are_neutral_404(
        self, client: TestClient, create_business: CreateBusiness
    ) -> None:
        _active(create_business)
        for host in ("bad_host", "api.localhost", "localhost", "a.shalik.localhost", "127.0.0.1"):
            self._assert_neutral_404(_get(client, host))

    def test_each_host_returns_only_its_own_menu(
        self, client: TestClient, create_business: CreateBusiness, migrated_engine: Engine
    ) -> None:
        alpha = create_business(slug="alpha", name="Alpha", status="active")
        bravo = create_business(slug="bravo", name="Bravo", status="active")
        alpha_category = _seed_category(migrated_engine, alpha, name="Alpha Section")
        bravo_category = _seed_category(migrated_engine, bravo, name="Bravo Section")
        _seed_item(migrated_engine, alpha, alpha_category, name="Alpha Dish")
        _seed_item(migrated_engine, bravo, bravo_category, name="Bravo Dish")

        alpha_body = _get(client, "alpha.localhost").json()
        bravo_body = _get(client, "bravo.localhost").json()
        assert [c["name"] for c in alpha_body["categories"]] == ["Alpha Section"]
        assert [c["name"] for c in bravo_body["categories"]] == ["Bravo Section"]
        assert alpha_body["categories"][0]["items"][0]["name"] == "Alpha Dish"
        assert bravo_body["categories"][0]["items"][0]["name"] == "Bravo Dish"

    def test_no_authentication_session_or_csrf_is_required(
        self, client: TestClient, create_business: CreateBusiness
    ) -> None:
        _active(create_business)
        # No cookie, no CSRF token, no Origin header.
        assert _get(client).status_code == 200

    def test_unsafe_methods_are_not_allowed(
        self, client: TestClient, create_business: CreateBusiness
    ) -> None:
        _active(create_business)
        for request in (client.post, client.put, client.patch, client.delete):
            response = request(_MENU, headers=_host("shalik.localhost"))
            assert response.status_code == 405, request.__name__


class TestPublicMenuVisibility:
    def test_hidden_items_are_excluded(
        self, client: TestClient, create_business: CreateBusiness, migrated_engine: Engine
    ) -> None:
        business_id = _active(create_business)
        category_id = _seed_category(migrated_engine, business_id)
        _seed_item(migrated_engine, business_id, category_id, name="Shown", position=0)
        _seed_item(
            migrated_engine, business_id, category_id, name="Hidden", position=1, is_hidden=True
        )

        (category,) = _get(client).json()["categories"]
        assert [item["name"] for item in category["items"]] == ["Shown"]

    def test_invisible_category_hides_its_visible_items(
        self, client: TestClient, create_business: CreateBusiness, migrated_engine: Engine
    ) -> None:
        business_id = _active(create_business)
        hidden_category = _seed_category(
            migrated_engine, business_id, name="Secret", position=0, is_visible=False
        )
        visible_category = _seed_category(migrated_engine, business_id, name="Public", position=1)
        _seed_item(migrated_engine, business_id, hidden_category, name="Secret Dish")
        _seed_item(migrated_engine, business_id, visible_category, name="Public Dish")

        categories = _get(client).json()["categories"]
        assert [c["name"] for c in categories] == ["Public"]
        assert [i["name"] for i in categories[0]["items"]] == ["Public Dish"]

    def test_category_with_no_publicly_visible_item_is_suppressed(
        self, client: TestClient, create_business: CreateBusiness, migrated_engine: Engine
    ) -> None:
        business_id = _active(create_business)
        empty = _seed_category(migrated_engine, business_id, name="Empty", position=0)
        all_hidden = _seed_category(migrated_engine, business_id, name="All Hidden", position=1)
        stocked = _seed_category(migrated_engine, business_id, name="Stocked", position=2)
        _seed_item(migrated_engine, business_id, all_hidden, name="Nope", is_hidden=True)
        _seed_item(migrated_engine, business_id, stocked, name="Yes")
        assert empty  # seeded and deliberately left without items

        categories = _get(client).json()["categories"]
        assert [c["name"] for c in categories] == ["Stocked"]

    def test_sold_out_item_stays_listed_and_is_not_orderable(
        self, client: TestClient, create_business: CreateBusiness, migrated_engine: Engine
    ) -> None:
        business_id = _active(create_business)
        category_id = _seed_category(migrated_engine, business_id)
        _seed_item(migrated_engine, business_id, category_id, name="Sold Out", is_available=False)

        (item,) = _get(client).json()["categories"][0]["items"]
        assert item["name"] == "Sold Out"
        assert item["is_available"] is False
        assert item["is_orderable"] is False

    def test_unregistered_stored_dietary_tag_is_never_surfaced(
        self, client: TestClient, create_business: CreateBusiness, migrated_engine: Engine
    ) -> None:
        business_id = _active(create_business)
        category_id = _seed_category(migrated_engine, business_id)
        _seed_item(migrated_engine, business_id, category_id, tags=("halal", "gluten-free"))

        (item,) = _get(client).json()["categories"][0]["items"]
        assert item["dietary_tags"] == ["halal"]


class TestPublicMenuModifiers:
    def test_only_available_options_are_projected(
        self, client: TestClient, create_business: CreateBusiness, migrated_engine: Engine
    ) -> None:
        business_id = _active(create_business)
        category_id = _seed_category(migrated_engine, business_id)
        item_id = _seed_item(migrated_engine, business_id, category_id)
        _seed_group(
            migrated_engine,
            business_id,
            item_id,
            options=(("Mild", 0, True), ("Out Of Stock", 50, False), ("Hot", 75, True)),
        )

        (item,) = _get(client).json()["categories"][0]["items"]
        (group,) = item["modifier_groups"]
        assert [option["name"] for option in group["options"]] == ["Mild", "Hot"]
        assert [option["price_delta_minor"] for option in group["options"]] == [0, 75]
        assert set(group) == {"id", "name", "min_select", "max_select", "options"}
        assert item["is_orderable"] is True

    def test_unsatisfiable_optional_group_is_omitted_without_blocking_ordering(
        self, client: TestClient, create_business: CreateBusiness, migrated_engine: Engine
    ) -> None:
        business_id = _active(create_business)
        category_id = _seed_category(migrated_engine, business_id)
        item_id = _seed_item(migrated_engine, business_id, category_id)
        _seed_group(
            migrated_engine,
            business_id,
            item_id,
            name="Extras",
            min_select=0,
            options=(("Sold Out Extra", 100, False),),
        )

        (item,) = _get(client).json()["categories"][0]["items"]
        assert item["modifier_groups"] == []
        assert item["is_orderable"] is True

    def test_unsatisfiable_required_group_makes_the_item_unorderable(
        self, client: TestClient, create_business: CreateBusiness, migrated_engine: Engine
    ) -> None:
        business_id = _active(create_business)
        category_id = _seed_category(migrated_engine, business_id)
        item_id = _seed_item(migrated_engine, business_id, category_id)
        _seed_group(
            migrated_engine,
            business_id,
            item_id,
            name="Choose a base",
            min_select=1,
            max_select=1,
            options=(("Only Option", 0, False),),
        )

        (item,) = _get(client).json()["categories"][0]["items"]
        assert item["modifier_groups"] == []
        assert item["is_available"] is True
        assert item["is_orderable"] is False

    def test_unlimited_maximum_is_projected_as_null(
        self, client: TestClient, create_business: CreateBusiness, migrated_engine: Engine
    ) -> None:
        business_id = _active(create_business)
        category_id = _seed_category(migrated_engine, business_id)
        item_id = _seed_item(migrated_engine, business_id, category_id)
        _seed_group(
            migrated_engine, business_id, item_id, min_select=0, options=(("Mild", 0, True),)
        )

        (group,) = _get(client).json()["categories"][0]["items"][0]["modifier_groups"]
        assert group["max_select"] is None
        assert group["min_select"] == 0

    def test_hidden_item_modifier_data_never_reaches_the_response(
        self, client: TestClient, create_business: CreateBusiness, migrated_engine: Engine
    ) -> None:
        business_id = _active(create_business)
        category_id = _seed_category(migrated_engine, business_id)
        shown = _seed_item(migrated_engine, business_id, category_id, name="Shown", position=0)
        hidden = _seed_item(
            migrated_engine, business_id, category_id, name="Hidden", position=1, is_hidden=True
        )
        _seed_group(
            migrated_engine, business_id, shown, name="Visible Group", options=(("A", 0, True),)
        )
        _seed_group(
            migrated_engine, business_id, hidden, name="Secret Group", options=(("B", 0, True),)
        )

        payload = _get(client).text
        assert "Visible Group" in payload
        assert "Secret Group" not in payload


class TestPublicMenuOrdering:
    def test_collections_follow_administrative_display_order(
        self, client: TestClient, create_business: CreateBusiness, migrated_engine: Engine
    ) -> None:
        business_id = _active(create_business)
        second = _seed_category(migrated_engine, business_id, name="Second", position=1)
        first = _seed_category(migrated_engine, business_id, name="First", position=0)
        _seed_item(migrated_engine, business_id, first, name="B Item", position=1)
        item_a = _seed_item(
            migrated_engine,
            business_id,
            first,
            name="A Item",
            position=0,
            tags=("vegan", "halal"),
        )
        _seed_item(migrated_engine, business_id, second, name="C Item", position=0)
        _seed_group(
            migrated_engine,
            business_id,
            item_a,
            name="Second Group",
            position=1,
            options=(("Z", 0, True),),
        )
        _seed_group(
            migrated_engine,
            business_id,
            item_a,
            name="First Group",
            position=0,
            options=(("Y", 0, True), ("X", 0, True)),
        )

        body = _get(client).json()
        assert [c["name"] for c in body["categories"]] == ["First", "Second"]
        assert [i["name"] for i in body["categories"][0]["items"]] == ["A Item", "B Item"]
        item = body["categories"][0]["items"][0]
        # Dietary tags are tag-ascending regardless of insertion order.
        assert item["dietary_tags"] == ["halal", "vegan"]
        assert [g["name"] for g in item["modifier_groups"]] == ["First Group", "Second Group"]
        # Options keep their stored positions, not alphabetical order.
        assert [o["name"] for o in item["modifier_groups"][0]["options"]] == ["Y", "X"]

    def test_repeated_requests_are_byte_stable(
        self, client: TestClient, create_business: CreateBusiness, migrated_engine: Engine
    ) -> None:
        business_id = _active(create_business)
        category_id = _seed_category(migrated_engine, business_id)
        for index in range(5):
            _seed_item(
                migrated_engine, business_id, category_id, name=f"Item {index}", position=index
            )

        first = _get(client).text
        assert all(_get(client).text == first for _ in range(3))


class TestPublicMenuImages:
    def test_attached_active_image_is_described_by_relative_urls(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        tmp_path: Path,
    ) -> None:
        business_id = _active(create_business)
        category_id = _seed_category(migrated_engine, business_id)
        item_id = _seed_item(migrated_engine, business_id, category_id)
        asset_id = _seed_media(migrated_engine, business_id)
        _attach_image(migrated_engine, item_id, asset_id, alt="Golden samosa")
        assert tmp_path  # the app's media root; objects are not needed to project

        (item,) = _get(client).json()["categories"][0]["items"]
        image = item["image"]
        assert image["alt_text"] == "Golden samosa"
        assert image["width"] == 1200
        assert image["height"] == 800
        assert image["url"] == f"/api/v1/public/media/{asset_id}/canonical"
        assert [variant["variant"] for variant in image["variants"]] == ["w320", "w640"]
        assert [variant["url"] for variant in image["variants"]] == [
            f"/api/v1/public/media/{asset_id}/w320",
            f"/api/v1/public/media/{asset_id}/w640",
        ]
        # No asset id, key, path, or checksum field on the image itself.
        assert set(image) == {"alt_text", "width", "height", "url", "variants"}

    def test_variants_are_width_ascending(
        self, client: TestClient, create_business: CreateBusiness, migrated_engine: Engine
    ) -> None:
        business_id = _active(create_business)
        category_id = _seed_category(migrated_engine, business_id)
        item_id = _seed_item(migrated_engine, business_id, category_id)
        # Seeded with a larger byte size on the smaller width, so a
        # byte-size ordering would produce the wrong srcset order.
        asset_id = _seed_media(migrated_engine, business_id, variant_sizes={"w640": 10, "w320": 99})
        _attach_image(migrated_engine, item_id, asset_id)

        image = _get(client).json()["categories"][0]["items"][0]["image"]
        assert [variant["width"] for variant in image["variants"]] == [320, 640]

    def test_item_without_an_image_projects_null(
        self, client: TestClient, create_business: CreateBusiness, migrated_engine: Engine
    ) -> None:
        business_id = _active(create_business)
        category_id = _seed_category(migrated_engine, business_id)
        _seed_item(migrated_engine, business_id, category_id)
        assert _get(client).json()["categories"][0]["items"][0]["image"] is None

    def test_alt_text_is_null_when_none_was_set(
        self, client: TestClient, create_business: CreateBusiness, migrated_engine: Engine
    ) -> None:
        business_id = _active(create_business)
        category_id = _seed_category(migrated_engine, business_id)
        item_id = _seed_item(migrated_engine, business_id, category_id)
        _attach_image(migrated_engine, item_id, _seed_media(migrated_engine, business_id))
        assert _get(client).json()["categories"][0]["items"][0]["image"]["alt_text"] is None

    def test_pending_asset_is_never_advertised(
        self, client: TestClient, create_business: CreateBusiness, migrated_engine: Engine
    ) -> None:
        # An item may reference a pending asset only through direct SQL, but
        # the projection must still refuse to publish a URL that would 404.
        business_id = _active(create_business)
        category_id = _seed_category(migrated_engine, business_id)
        item_id = _seed_item(migrated_engine, business_id, category_id)
        pending = _seed_media(migrated_engine, business_id, status="pending")
        _attach_image(migrated_engine, item_id, pending, alt="Should not appear")

        body = _get(client).json()
        assert body["categories"][0]["items"][0]["image"] is None
        assert str(pending) not in _get(client).text

    def test_hidden_items_images_are_not_described(
        self, client: TestClient, create_business: CreateBusiness, migrated_engine: Engine
    ) -> None:
        business_id = _active(create_business)
        category_id = _seed_category(migrated_engine, business_id)
        shown = _seed_item(migrated_engine, business_id, category_id, name="Shown", position=0)
        hidden = _seed_item(
            migrated_engine, business_id, category_id, name="Hidden", position=1, is_hidden=True
        )
        shown_asset = _seed_media(migrated_engine, business_id)
        hidden_asset = _seed_media(migrated_engine, business_id)
        _attach_image(migrated_engine, shown, shown_asset)
        _attach_image(migrated_engine, hidden, hidden_asset)

        payload = _get(client).text
        assert str(shown_asset) in payload
        assert str(hidden_asset) not in payload


class TestPublicMenuFeatured:
    def test_featured_ids_reference_items_in_the_tree_without_duplication(
        self, client: TestClient, create_business: CreateBusiness, migrated_engine: Engine
    ) -> None:
        business_id = _active(create_business)
        category_id = _seed_category(migrated_engine, business_id)
        featured = _seed_item(
            migrated_engine, business_id, category_id, name="Featured", position=0, is_featured=True
        )
        _seed_item(migrated_engine, business_id, category_id, name="Plain", position=1)

        body = _get(client).json()
        assert body["featured_item_ids"] == [str(featured)]
        # Ids only: the item appears exactly once, in the category tree.
        assert body["categories"][0]["items"][0]["id"] == str(featured)
        assert [key for key in body if key == "featured"] == []
        item_ids = [item["id"] for c in body["categories"] for item in c["items"]]
        assert len(item_ids) == len(set(item_ids))
        assert set(body["featured_item_ids"]) <= set(item_ids)

    def test_featured_order_follows_category_then_item_position(
        self, client: TestClient, create_business: CreateBusiness, migrated_engine: Engine
    ) -> None:
        business_id = _active(create_business)
        second = _seed_category(migrated_engine, business_id, name="Second", position=1)
        first = _seed_category(migrated_engine, business_id, name="First", position=0)
        in_second = _seed_item(
            migrated_engine, business_id, second, name="C", position=0, is_featured=True
        )
        first_b = _seed_item(
            migrated_engine, business_id, first, name="B", position=1, is_featured=True
        )
        first_a = _seed_item(
            migrated_engine, business_id, first, name="A", position=0, is_featured=True
        )

        assert _get(client).json()["featured_item_ids"] == [
            str(first_a),
            str(first_b),
            str(in_second),
        ]

    def test_hidden_and_invisible_category_featured_items_are_excluded(
        self, client: TestClient, create_business: CreateBusiness, migrated_engine: Engine
    ) -> None:
        business_id = _active(create_business)
        visible = _seed_category(migrated_engine, business_id, name="Visible", position=0)
        invisible = _seed_category(
            migrated_engine, business_id, name="Invisible", position=1, is_visible=False
        )
        shown = _seed_item(
            migrated_engine, business_id, visible, name="Shown", position=0, is_featured=True
        )
        _seed_item(
            migrated_engine,
            business_id,
            visible,
            name="Hidden",
            position=1,
            is_hidden=True,
            is_featured=True,
        )
        _seed_item(
            migrated_engine, business_id, invisible, name="Secret", position=0, is_featured=True
        )

        assert _get(client).json()["featured_item_ids"] == [str(shown)]

    def test_sold_out_featured_item_stays_featured(
        self, client: TestClient, create_business: CreateBusiness, migrated_engine: Engine
    ) -> None:
        business_id = _active(create_business)
        category_id = _seed_category(migrated_engine, business_id)
        sold_out = _seed_item(
            migrated_engine,
            business_id,
            category_id,
            is_available=False,
            is_featured=True,
        )
        assert _get(client).json()["featured_item_ids"] == [str(sold_out)]


class TestBoundedQueries:
    """The projection must not issue work per parent (M3D, R10).

    Child collections load only for the parents that survived visibility,
    so an empty menu genuinely costs fewer statements than a stocked one.
    The invariant is therefore not a fixed number but *independence from
    size*: two menus of the same shape and very different magnitude must
    cost exactly the same number of statements.
    """

    @staticmethod
    @contextmanager
    def _statements(app: FastAPI) -> Iterator[list[str]]:
        recorded: list[str] = []

        def _before(_conn: Any, _cursor: Any, statement: str, *_rest: Any, **_kwargs: Any) -> None:
            recorded.append(statement)

        event.listen(app.state.engine, "before_cursor_execute", _before)
        try:
            yield recorded
        finally:
            event.remove(app.state.engine, "before_cursor_execute", _before)

    def _stock(
        self,
        engine: Engine,
        business_id: uuid.UUID,
        *,
        categories: int,
        items_per_category: int,
        options_per_group: int,
    ) -> None:
        for category_index in range(categories):
            category_id = _seed_category(
                engine, business_id, name=f"Cat {category_index}", position=category_index
            )
            for item_index in range(items_per_category):
                item_id = _seed_item(
                    engine,
                    business_id,
                    category_id,
                    name=f"Item {category_index}-{item_index}",
                    position=item_index,
                    tags=("halal",),
                )
                _seed_group(
                    engine,
                    business_id,
                    item_id,
                    options=tuple(
                        (f"Opt {index}", index, True) for index in range(options_per_group)
                    ),
                )
                _attach_image(engine, item_id, _seed_media(engine, business_id))

    def test_statement_count_does_not_grow_with_the_menu(
        self,
        client: TestClient,
        app: FastAPI,
        create_business: CreateBusiness,
        migrated_engine: Engine,
    ) -> None:
        small = create_business(slug="small", status="active")
        large = create_business(slug="large", status="active")
        self._stock(migrated_engine, small, categories=1, items_per_category=1, options_per_group=1)
        self._stock(migrated_engine, large, categories=3, items_per_category=4, options_per_group=5)

        with self._statements(app) as recorded:
            assert _get(client, "small.localhost").status_code == 200
            small_count = len(recorded)
        with self._statements(app) as recorded:
            body = _get(client, "large.localhost").json()
            large_count = len(recorded)

        assert sum(len(category["items"]) for category in body["categories"]) == 12
        assert small_count == large_count
        # Host resolution plus categories, items, tags, groups, options,
        # media assets, and media variants: a fixed, bounded plan.
        assert small_count == 8

    def test_child_statements_are_skipped_when_nothing_is_publicly_visible(
        self,
        client: TestClient,
        app: FastAPI,
        create_business: CreateBusiness,
        migrated_engine: Engine,
    ) -> None:
        business_id = _active(create_business)
        # Hidden items in a visible category: the category read runs, the
        # item read runs, and every child read is skipped.
        category_id = _seed_category(migrated_engine, business_id)
        _seed_item(migrated_engine, business_id, category_id, is_hidden=True)

        with self._statements(app) as recorded:
            assert _get(client).json()["categories"] == []
        assert len(recorded) == 3

    def test_hidden_item_children_are_never_queried(
        self,
        client: TestClient,
        app: FastAPI,
        create_business: CreateBusiness,
        migrated_engine: Engine,
    ) -> None:
        business_id = _active(create_business)
        category_id = _seed_category(migrated_engine, business_id)
        shown = _seed_item(migrated_engine, business_id, category_id, name="Shown", position=0)
        hidden = _seed_item(
            migrated_engine, business_id, category_id, name="Hidden", position=1, is_hidden=True
        )
        _seed_group(migrated_engine, business_id, hidden, options=(("Secret", 0, True),))

        with self._statements(app) as recorded:
            assert _get(client).status_code == 200
        # The hidden item's id must not appear in any statement parameter
        # binding path: it is filtered in SQL, never fetched then dropped.
        assert not any(str(hidden) in statement for statement in recorded)
        assert shown


class TestPublicMenuHead:
    def test_head_returns_no_body_with_the_get_status_and_headers(
        self, client: TestClient, create_business: CreateBusiness, migrated_engine: Engine
    ) -> None:
        business_id = _active(create_business)
        category_id = _seed_category(migrated_engine, business_id)
        _seed_item(migrated_engine, business_id, category_id)

        head = client.head(_MENU, headers=_host("shalik.localhost"))
        get = _get(client)
        assert head.status_code == 200
        assert head.content == b""
        assert head.headers["cache-control"] == "no-store"
        assert head.headers["content-type"] == get.headers["content-type"]

    def test_head_failures_stay_neutral(self, client: TestClient) -> None:
        head = client.head(_MENU, headers=_host("nope.localhost"))
        assert head.status_code == 404
        assert head.headers["cache-control"] == "no-store"
