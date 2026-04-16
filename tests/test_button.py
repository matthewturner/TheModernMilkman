"""Tests for The Modern Milkman button entities."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.themodernmilkman.button import (
    TMMSkipProductButton,
    TMMRefreshButton,
    async_setup_entry,
)
from custom_components.themodernmilkman.const import (
    CONF_COORDINATOR,
    CONF_ITEMS,
    CONF_NEXT_DELIVERY,
    DOMAIN,
)


def _make_setup_mocks(initial_items):
    """Return (hass, coordinator, add_calls, listener_getter) for setup tests."""
    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.data = {
        CONF_NEXT_DELIVERY: {
            "deliveryDate": "2026-04-16",
            CONF_ITEMS: list(initial_items),
        }
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

    hass = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: {CONF_COORDINATOR: coordinator}}}

    add_calls = []

    def mock_add_entities(entities, update_before_add=False):
        add_calls.append(list(entities))

    asyncio.run(async_setup_entry(hass, entry, mock_add_entities))

    return hass, coordinator, add_calls, lambda: registered_listener


def test_async_setup_entry_adds_refresh_and_skip_buttons():
    """Setup adds a refresh button and one skip button per product item."""
    items = [
        {"productName": "Milk", "subscriptionItemId": 9320404},
        {"productName": "Bread", "subscriptionItemId": 9320405},
    ]
    _, _, add_calls, _ = _make_setup_mocks(items)

    assert len(add_calls) == 1
    assert sum(isinstance(entity, TMMRefreshButton) for entity in add_calls[0]) == 1
    assert sum(isinstance(entity, TMMSkipProductButton) for entity in add_calls[0]) == 2


def test_async_setup_entry_listener_adds_new_skip_button():
    """Listener adds skip buttons for newly added products."""
    initial_items = [{"productName": "Milk", "subscriptionItemId": 9320404}]
    _, coordinator, add_calls, get_listener = _make_setup_mocks(initial_items)

    coordinator.data[CONF_NEXT_DELIVERY][CONF_ITEMS] = [
        {"productName": "Milk", "subscriptionItemId": 9320404},
        {"productName": "Bread", "subscriptionItemId": 9320405},
    ]
    get_listener()()

    assert len(add_calls) == 2
    assert len(add_calls[1]) == 1
    assert isinstance(add_calls[1][0], TMMSkipProductButton)


def test_skip_button_press_calls_skip_api_with_subscription_item_id():
    """Pressing a skip button calls coordinator skip with the product item ID."""
    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.async_skip_subscription_item = AsyncMock()
    coordinator.data = {
        CONF_NEXT_DELIVERY: {
            CONF_ITEMS: [{"productName": "Milk", "subscriptionItemId": 9320404}]
        }
    }
    button = TMMSkipProductButton(
        coordinator,
        "Test",
        1,
        {"productName": "Milk", "subscriptionItemId": 9320404},
    )

    asyncio.run(button.async_press())

    coordinator.async_skip_subscription_item.assert_awaited_once_with(9320404)
