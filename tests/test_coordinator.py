"""Tests for The Modern Milkman coordinator."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.themodernmilkman.coordinator import (
    APIRatelimitExceeded,
    InvalidAuth,
    TMMCoordinator,
    handle_status_code,
)
from custom_components.themodernmilkman.const import (
    CONF_DELIVERYDATE,
    CONF_NEXT_DELIVERY,
    CONF_UNKNOWN,
    CONF_WASTAGE,
)


# ---------------------------------------------------------------------------
# handle_status_code unit tests
# ---------------------------------------------------------------------------


def test_handle_status_code_401_raises_invalid_auth():
    """A 401 status code must raise InvalidAuth."""
    with pytest.raises(InvalidAuth):
        handle_status_code(401)


def test_handle_status_code_429_raises_api_ratelimit_exceeded():
    """A 429 status code must raise APIRatelimitExceeded."""
    with pytest.raises(APIRatelimitExceeded):
        handle_status_code(429)


def test_handle_status_code_200_does_not_raise():
    """A 200 status code must not raise."""
    handle_status_code(200)  # should not raise


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(status: int, body: str = "{}"):
    """Return a mock aiohttp response."""
    resp = MagicMock()
    resp.status = status
    resp.text = AsyncMock(return_value=body)
    return resp


def _make_coordinator(hass):
    """Return a TMMCoordinator with fake credentials."""
    session = AsyncMock()
    data = {"username": "user@example.com", "password": "secret"}
    return TMMCoordinator(hass, session, data)


# ---------------------------------------------------------------------------
# TMMCoordinator._async_update_data tests
# ---------------------------------------------------------------------------


@pytest.fixture
def hass(event_loop):
    """Minimal HomeAssistant-like object for coordinator tests."""
    hass = MagicMock()
    hass.loop = event_loop
    hass.async_add_executor_job = AsyncMock()
    return hass


@pytest.mark.asyncio
async def test_update_data_success(hass):
    """Successful update returns wastage and next-delivery data."""
    wastage_data = {"bottlesSaved": 5}
    delivery_data = {"deliveryDate": "2026-04-01"}

    coordinator = _make_coordinator(hass)
    coordinator.session.request = AsyncMock(
        side_effect=[
            _make_response(200),  # login
            _make_response(200, json.dumps(wastage_data)),  # wastage
            _make_response(200, json.dumps(delivery_data)),  # next delivery
        ]
    )

    result = await coordinator._async_update_data()

    assert result[CONF_WASTAGE] == wastage_data
    assert result[CONF_NEXT_DELIVERY] == delivery_data


@pytest.mark.asyncio
async def test_update_data_no_next_delivery(hass):
    """A non-200 next-delivery response sets next_delivery to CONF_UNKNOWN."""
    wastage_data = {"bottlesSaved": 3}

    coordinator = _make_coordinator(hass)
    coordinator.session.request = AsyncMock(
        side_effect=[
            _make_response(200),  # login
            _make_response(200, json.dumps(wastage_data)),  # wastage
            _make_response(404),  # next delivery – nothing scheduled
        ]
    )

    result = await coordinator._async_update_data()

    assert result[CONF_WASTAGE] == wastage_data
    assert result[CONF_NEXT_DELIVERY] == CONF_UNKNOWN


@pytest.mark.asyncio
async def test_update_data_login_401_raises_config_entry_auth_failed(hass):
    """A 401 on login must raise ConfigEntryAuthFailed."""
    coordinator = _make_coordinator(hass)
    coordinator.session.request = AsyncMock(
        return_value=_make_response(401)  # login fails
    )

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_update_data_wastage_401_raises_config_entry_auth_failed(hass):
    """A 401 on the wastage call (session expired) must raise ConfigEntryAuthFailed."""
    coordinator = _make_coordinator(hass)
    coordinator.session.request = AsyncMock(
        side_effect=[
            _make_response(200),  # login succeeds
            _make_response(401),  # wastage – session expired
        ]
    )

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_update_data_next_delivery_401_raises_config_entry_auth_failed(hass):
    """A 401 on the next-delivery call (session expired) must raise ConfigEntryAuthFailed."""
    wastage_data = {"bottlesSaved": 1}

    coordinator = _make_coordinator(hass)
    coordinator.session.request = AsyncMock(
        side_effect=[
            _make_response(200),  # login succeeds
            _make_response(200, json.dumps(wastage_data)),  # wastage succeeds
            _make_response(401),  # next delivery – session expired
        ]
    )

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_update_data_login_429_raises_update_failed(hass):
    """A 429 on login must raise UpdateFailed (rate-limit, not auth failure)."""
    coordinator = _make_coordinator(hass)
    coordinator.session.request = AsyncMock(
        return_value=_make_response(429)  # rate limited
    )

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_update_data_wastage_429_raises_update_failed(hass):
    """A 429 on the wastage call must raise UpdateFailed."""
    coordinator = _make_coordinator(hass)
    coordinator.session.request = AsyncMock(
        side_effect=[
            _make_response(200),  # login
            _make_response(429),  # wastage rate-limited
        ]
    )

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_skip_subscription_item_posts_expected_payload(hass):
    """Skip request posts next delivery date, reason, and subscription item ID."""
    coordinator = _make_coordinator(hass)
    coordinator.data = {
        CONF_NEXT_DELIVERY: {
            CONF_DELIVERYDATE: "2026-04-16T00:00:00.000Z",
        }
    }
    coordinator.session.request = AsyncMock(return_value=_make_response(200))
    coordinator.async_request_refresh = AsyncMock()

    await coordinator.async_skip_subscription_item(9320404)

    coordinator.session.request.assert_awaited_once_with(
        method="POST",
        url="https://themodernmilkman.co.uk/api/subscriptions/skip",
        json={
            "skipDate": "2026-04-16",
            "pauseReasonId": 5,
            "subscriptionItemIds": [9320404],
        },
        headers={"Content-Type": "application/json"},
    )
    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_skip_subscription_item_raises_when_no_next_delivery(hass):
    """Skip request fails when there is no next delivery data."""
    coordinator = _make_coordinator(hass)
    coordinator.data = {CONF_NEXT_DELIVERY: CONF_UNKNOWN}

    with pytest.raises(UpdateFailed, match="No next delivery"):
        await coordinator.async_skip_subscription_item(9320404)
