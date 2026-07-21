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
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

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
