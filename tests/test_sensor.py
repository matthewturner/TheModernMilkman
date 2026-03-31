"""Tests for The Modern Milkman sensor entities."""

from datetime import date
from unittest.mock import MagicMock

from custom_components.themodernmilkman.sensor import (
    TMMNextDeliverySensor,
    TMMWastageSensor,
)
from custom_components.themodernmilkman.const import (
    CONF_NEXT_DELIVERY,
    CONF_UNKNOWN,
    CONF_WASTAGE,
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
