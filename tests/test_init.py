"""Tests for The Modern Milkman __init__.py.

These tests prove that iterating over hass.data[DOMAIN].items() while a
coordinator refresh can simultaneously add new product-sensor entries to that
same dict caused a RuntimeError, and that the fix (wrapping .items() in
list()) eliminates that error.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.themodernmilkman import async_setup_entry
from custom_components.themodernmilkman.const import CONF_COORDINATOR, DOMAIN


# ---------------------------------------------------------------------------
# Pure unit tests: dict-mutation bug and its fix
# ---------------------------------------------------------------------------


def test_iterating_dict_items_while_dict_grows_raises_runtime_error():
    """Iterating dict.items() while adding entries raises RuntimeError.

    This demonstrates the root cause of the bug: when coordinator.async_request_refresh
    fired _async_add_new_product_sensors (which adds a new key to hass.data[DOMAIN]),
    the live .items() iterator detected the size change and raised RuntimeError.
    """
    # Simulates hass.data[DOMAIN] containing the config-entry dict plus an
    # already-registered product-sensor key.
    d = {
        "config_entry_id": {"coordinator": "mock_coord"},
        "themodernmilkman-home-product_1": MagicMock(),
    }

    with pytest.raises(RuntimeError, match="dictionary changed size during iteration"):
        for _key, _val in d.items():
            # Simulates _async_add_new_product_sensors adding a new sensor
            d["themodernmilkman-home-product_2"] = MagicMock()


def test_iterating_list_snapshot_of_dict_items_does_not_raise():
    """Wrapping .items() in list() snapshots the keys so growth does not raise.

    This proves the one-line fix: changing
        for entry_id, entry_data in hass.data[DOMAIN].items():
    to
        for entry_id, entry_data in list(hass.data[DOMAIN].items()):
    prevents RuntimeError even when the dict grows during the loop body.
    """
    d = {
        "config_entry_id": {"coordinator": "mock_coord"},
        "themodernmilkman-home-product_1": MagicMock(),
    }

    # Must not raise
    for _key, _val in list(d.items()):
        d["themodernmilkman-home-product_2"] = MagicMock()

    assert "themodernmilkman-home-product_2" in d


# ---------------------------------------------------------------------------
# Integration tests: the actual _async_refresh_data handler
# ---------------------------------------------------------------------------


def _setup_hass_and_entry():
    """Build minimal hass and entry mocks for async_setup_entry."""
    entry_id = "test_entry_id"

    hass = MagicMock()
    hass.data = {DOMAIN: {}}
    hass.services.has_service.return_value = False
    hass.config_entries.async_forward_entry_setups = AsyncMock()

    entry = MagicMock()
    entry.entry_id = entry_id
    entry.data = {"username": "user@example.com", "password": "secret"}
    entry.add_update_listener.return_value = MagicMock()

    return hass, entry


@pytest.mark.asyncio
async def test_refresh_service_handler_does_not_raise_when_product_count_increases():
    """The registered refresh-data service handler must not raise RuntimeError.

    When coordinator.async_request_refresh() resolves, _async_add_new_product_sensors
    may add new keys to hass.data[DOMAIN].  With the fix in place (list() snapshot)
    the service handler must complete without error and the new key must be present.
    """
    hass, entry = _setup_hass_and_entry()

    # Capture the registered service handler
    captured = {}

    def capture_register(domain, service, handler):
        captured["fn"] = handler

    hass.services.async_register.side_effect = capture_register

    coordinator = AsyncMock()

    with (
        patch("custom_components.themodernmilkman.async_get_clientsession"),
        patch(
            "custom_components.themodernmilkman.TMMCoordinator",
            return_value=coordinator,
        ),
    ):
        await async_setup_entry(hass, entry)

    # After setup, hass.data[DOMAIN] has one dict entry (the config-entry data)
    # plus simulate an already-registered product-sensor key so that there are
    # multiple entries — matching the real-world scenario that triggers the bug.
    existing_sensor_key = f"{DOMAIN}-home-product_1"
    hass.data[DOMAIN][existing_sensor_key] = MagicMock()

    # When the coordinator refreshes it triggers _async_add_new_product_sensors,
    # which adds a new product-sensor entry to hass.data[DOMAIN].
    new_sensor_key = f"{DOMAIN}-home-product_2"

    async def add_new_sensor():
        hass.data[DOMAIN][new_sensor_key] = MagicMock()

    coordinator.async_request_refresh.side_effect = add_new_sensor

    handler = captured["fn"]

    # The handler must complete without RuntimeError
    await handler(None)

    # Confirm the new sensor key was added (side-effect ran)
    assert new_sensor_key in hass.data[DOMAIN]


@pytest.mark.asyncio
async def test_refresh_service_handler_refreshes_all_coordinators():
    """The refresh-data handler calls async_request_refresh on every coordinator."""
    hass, entry = _setup_hass_and_entry()

    captured = {}

    def capture_register(domain, service, handler):
        captured["fn"] = handler

    hass.services.async_register.side_effect = capture_register

    coordinator = AsyncMock()

    with (
        patch("custom_components.themodernmilkman.async_get_clientsession"),
        patch(
            "custom_components.themodernmilkman.TMMCoordinator",
            return_value=coordinator,
        ),
    ):
        await async_setup_entry(hass, entry)

    coordinator.async_request_refresh.reset_mock()

    handler = captured["fn"]
    await handler(None)

    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_refresh_service_handler_skips_non_dict_entries():
    """The refresh-data handler ignores non-dict values in hass.data[DOMAIN].

    Product-sensor objects registered under hass.data[DOMAIN] are not dicts;
    the handler must skip them without error.
    """
    hass, entry = _setup_hass_and_entry()

    captured = {}

    def capture_register(domain, service, handler):
        captured["fn"] = handler

    hass.services.async_register.side_effect = capture_register

    coordinator = AsyncMock()

    with (
        patch("custom_components.themodernmilkman.async_get_clientsession"),
        patch(
            "custom_components.themodernmilkman.TMMCoordinator",
            return_value=coordinator,
        ),
    ):
        await async_setup_entry(hass, entry)

    # Add sensor-object entries (non-dict) — these must be skipped
    hass.data[DOMAIN]["sensor_uid_1"] = MagicMock()
    hass.data[DOMAIN]["sensor_uid_2"] = MagicMock()

    coordinator.async_request_refresh.reset_mock()

    handler = captured["fn"]
    await handler(None)

    # Only the real coordinator (inside the dict entry) should be refreshed
    coordinator.async_request_refresh.assert_awaited_once()
