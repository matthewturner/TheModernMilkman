"""Tests for The Modern Milkman sensor entities."""

import asyncio
from datetime import date
from unittest.mock import MagicMock

from custom_components.themodernmilkman.sensor import (
    TMMNextDeliverySensor,
    TMMProductSensor,
    TMMWastageSensor,
    async_setup_entry,
)
from custom_components.themodernmilkman.const import (
    CONF_COORDINATOR,
    CONF_ITEMS,
    CONF_NEXT_DELIVERY,
    CONF_UNKNOWN,
    CONF_WASTAGE,
    DOMAIN,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_coordinator(next_delivery_data, wastage_data=None):
    """Return a minimal coordinator mock with the given data."""
    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.data = {}
    if next_delivery_data is not None:
        coordinator.data[CONF_NEXT_DELIVERY] = next_delivery_data
    if wastage_data is not None:
        coordinator.data[CONF_WASTAGE] = wastage_data
    return coordinator


# ---------------------------------------------------------------------------
# TMMNextDeliverySensor tests
# ---------------------------------------------------------------------------


def test_next_delivery_sensor_initial_state():
    """Sensor state is set correctly from initial coordinator data."""
    delivery_data = {"deliveryDate": "2026-04-01", "items": []}
    coordinator = _make_coordinator(delivery_data)

    sensor = TMMNextDeliverySensor(coordinator, "Test")

    assert sensor.native_value == date(2026, 4, 1)


def test_next_delivery_sensor_update_from_coordinator_reflects_new_date():
    """After coordinator data changes, update_from_coordinator reflects the new delivery date.

    This covers the session-expiry scenario: the coordinator re-fetches data
    after re-authentication, and the entity must pick up the updated date.
    """
    initial_data = {"deliveryDate": "2026-04-01", "items": []}
    coordinator = _make_coordinator(initial_data)
    sensor = TMMNextDeliverySensor(coordinator, "Test")

    assert sensor.native_value == date(2026, 4, 1)

    # Simulate coordinator re-fetching data after session expiry + re-auth
    updated_data = {"deliveryDate": "2026-04-08", "items": []}
    coordinator.data[CONF_NEXT_DELIVERY] = updated_data
    sensor.update_from_coordinator()

    assert sensor.native_value == date(2026, 4, 8)


def test_next_delivery_sensor_update_from_coordinator_when_no_delivery_scheduled():
    """After coordinator returns no delivery, the entity state becomes CONF_UNKNOWN."""
    initial_data = {"deliveryDate": "2026-04-01", "items": []}
    coordinator = _make_coordinator(initial_data)
    sensor = TMMNextDeliverySensor(coordinator, "Test")

    # Coordinator now reports no delivery scheduled
    coordinator.data[CONF_NEXT_DELIVERY] = CONF_UNKNOWN
    sensor.update_from_coordinator()

    assert sensor.native_value == CONF_UNKNOWN


def test_next_delivery_sensor_update_from_coordinator_populates_attributes():
    """update_from_coordinator stores extra fields as entity attributes."""
    delivery_data = {
        "deliveryDate": "2026-04-01",
        "orderId": "ABC123",
        "items": [],
    }
    coordinator = _make_coordinator(delivery_data)
    sensor = TMMNextDeliverySensor(coordinator, "Test")

    updated_data = {
        "deliveryDate": "2026-04-08",
        "orderId": "DEF456",
        "items": [],
    }
    coordinator.data[CONF_NEXT_DELIVERY] = updated_data
    sensor.update_from_coordinator()

    assert sensor.extra_state_attributes.get("orderId") == "DEF456"


# ---------------------------------------------------------------------------
# TMMWastageSensor tests
# ---------------------------------------------------------------------------


def test_wastage_sensor_update_from_coordinator_reflects_new_value():
    """After coordinator data changes, update_from_coordinator reflects the new wastage value."""
    initial_wastage = {"bottlesSaved": 5}
    coordinator = _make_coordinator(
        next_delivery_data={"deliveryDate": "2026-04-01", "items": []},
        wastage_data=initial_wastage,
    )
    sensor = TMMWastageSensor(coordinator, "Test")

    assert sensor.native_value == 5

    # Simulate coordinator re-fetching data after session expiry + re-auth
    coordinator.data[CONF_WASTAGE] = {"bottlesSaved": 10}
    sensor.update_from_coordinator()

    assert sensor.native_value == 10


# ---------------------------------------------------------------------------
# TMMProductSensor tests
# ---------------------------------------------------------------------------


def test_product_sensor_initial_state():
    """Product sensor state is set from the item passed at construction time."""
    item = {"productName": "Milk", "quantity": 2}
    coordinator = _make_coordinator(
        {"deliveryDate": "2026-04-01", CONF_ITEMS: [item]}
    )
    sensor = TMMProductSensor(coordinator, "Test", 1, item)

    assert sensor.native_value == "Milk"


def test_product_sensor_update_from_coordinator_reflects_new_product():
    """update_from_coordinator refreshes the product name from coordinator data."""
    initial_item = {"productName": "Milk"}
    coordinator = _make_coordinator(
        {"deliveryDate": "2026-04-01", CONF_ITEMS: [initial_item]}
    )
    sensor = TMMProductSensor(coordinator, "Test", 1, initial_item)

    assert sensor.native_value == "Milk"

    updated_item = {"productName": "Whole Milk"}
    coordinator.data[CONF_NEXT_DELIVERY][CONF_ITEMS] = [updated_item]
    sensor.update_from_coordinator()

    assert sensor.native_value == "Whole Milk"


def test_product_sensor_becomes_unavailable_when_product_removed():
    """When products decrease, sensors beyond the new count become unavailable."""
    items = [{"productName": "Milk"}, {"productName": "Yogurt"}]
    coordinator = _make_coordinator(
        {"deliveryDate": "2026-04-01", CONF_ITEMS: items}
    )
    sensor = TMMProductSensor(coordinator, "Test", 2, items[1])

    assert sensor.native_value == "Yogurt"
    assert sensor.available

    # Product list shrinks to one item — sensor 2 should become unavailable
    coordinator.data[CONF_NEXT_DELIVERY][CONF_ITEMS] = [{"productName": "Milk"}]
    sensor.update_from_coordinator()

    assert sensor.native_value is None
    assert not sensor.available


def test_product_sensor_becomes_unavailable_when_no_delivery():
    """When no delivery is scheduled, product sensors become unavailable."""
    item = {"productName": "Milk"}
    coordinator = _make_coordinator(
        {"deliveryDate": "2026-04-01", CONF_ITEMS: [item]}
    )
    sensor = TMMProductSensor(coordinator, "Test", 1, item)

    assert sensor.available

    coordinator.data[CONF_NEXT_DELIVERY] = CONF_UNKNOWN
    sensor.update_from_coordinator()

    assert sensor.native_value is None
    assert not sensor.available


# ---------------------------------------------------------------------------
# async_setup_entry dynamic product sensor tests
# ---------------------------------------------------------------------------


def _make_setup_mocks(initial_items):
    """Return (hass, entry, coordinator, add_calls) ready for async_setup_entry."""
    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.data = {
        CONF_NEXT_DELIVERY: {
            "deliveryDate": "2026-04-01",
            CONF_ITEMS: list(initial_items),
        },
        CONF_WASTAGE: {"bottlesSaved": 5},
    }

    registered_listener = None

    def capture_listener(listener):
        nonlocal registered_listener
        registered_listener = listener
        return MagicMock()

    coordinator.async_add_listener = capture_listener

    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.title = "Test"
    entry.options = {}
    entry.data = {"username": "test"}

    domain_data = {entry.entry_id: {CONF_COORDINATOR: coordinator}}
    hass = MagicMock()
    hass.data = {DOMAIN: domain_data}

    add_calls = []

    def mock_add_entities(entities, update_before_add=False):
        add_calls.append(list(entities))

    asyncio.run(async_setup_entry(hass, entry, mock_add_entities))

    return hass, entry, coordinator, add_calls, lambda: registered_listener


def test_async_setup_entry_registers_all_initial_product_sensors():
    """async_setup_entry creates one sensor per product (no arbitrary cap)."""
    items = [{"productName": f"Product {i}"} for i in range(1, 7)]
    _, _, _, add_calls, _ = _make_setup_mocks(items)

    # wastage + next_delivery + 6 product sensors
    assert len(add_calls) == 1
    assert len(add_calls[0]) == 8


def test_async_setup_entry_listener_adds_new_product_sensors_when_count_increases():
    """When coordinator updates with more products, new sensors are registered."""
    initial_items = [{"productName": "Milk"}, {"productName": "Yogurt"}]
    hass, entry, coordinator, add_calls, get_listener = _make_setup_mocks(
        initial_items
    )

    # Initial setup: wastage + next_delivery + 2 products
    assert len(add_calls) == 1
    assert len(add_calls[0]) == 4

    # Coordinator now returns 2 additional products
    coordinator.data[CONF_NEXT_DELIVERY][CONF_ITEMS] = [
        {"productName": "Milk"},
        {"productName": "Yogurt"},
        {"productName": "Butter"},
        {"productName": "Cheese"},
    ]

    get_listener()()  # invoke the registered coordinator listener

    assert len(add_calls) == 2
    new_names = [s.native_value for s in add_calls[1]]
    assert new_names == ["Butter", "Cheese"]


def test_async_setup_entry_listener_does_not_duplicate_existing_sensors():
    """Calling the listener when no new products exist adds nothing."""
    initial_items = [{"productName": "Milk"}, {"productName": "Yogurt"}]
    _, _, _, add_calls, get_listener = _make_setup_mocks(initial_items)

    get_listener()()  # invoke listener without changing coordinator data

    assert len(add_calls) == 1  # no second call to async_add_entities
