"""Tests for The Modern Milkman calendar entities."""

import asyncio
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.themodernmilkman.calendar import (
    TMMCalendarSensor,
    add_to_calendar,
    async_setup_entry,
    generate_uuid_from_json,
    get_event_uid,
)
from custom_components.themodernmilkman.const import (
    CONF_CALENDARS,
    CONF_COORDINATOR,
    CONF_DELIVERYDATE,
    CONF_NEXT_DELIVERY,
    CONF_UNKNOWN,
    DOMAIN,
)
from homeassistant.components.calendar import CalendarEvent
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_coordinator(delivery_date: str | None = "2099-12-31"):
    """Return a minimal coordinator mock with the given delivery data."""
    coordinator = MagicMock()
    coordinator.last_update_success = True
    if delivery_date is None:
        coordinator.data = {CONF_NEXT_DELIVERY: CONF_UNKNOWN}
    else:
        coordinator.data = {
            CONF_NEXT_DELIVERY: {CONF_DELIVERYDATE: delivery_date}
        }
    return coordinator


def _make_sensor(delivery_date: str | None = "2099-12-31") -> TMMCalendarSensor:
    """Return a TMMCalendarSensor with mocked coordinator."""
    coordinator = _make_coordinator(delivery_date)
    return TMMCalendarSensor(coordinator, "Test")


# ---------------------------------------------------------------------------
# TMMCalendarSensor – initialisation
# ---------------------------------------------------------------------------


def test_calendar_sensor_unique_id():
    """Sensor unique ID is set to '<domain>-calendar'."""
    sensor = _make_sensor()
    assert sensor._attr_unique_id == f"{DOMAIN}-calendar"


def test_calendar_sensor_name():
    """Sensor name is 'Deliveries'."""
    sensor = _make_sensor()
    assert sensor._attr_name == "Deliveries"


# ---------------------------------------------------------------------------
# TMMCalendarSensor – available property
# ---------------------------------------------------------------------------


def test_calendar_sensor_available_with_valid_data():
    """`available` returns True when coordinator has delivery data."""
    sensor = _make_sensor("2099-12-31")
    assert sensor.available is True


def test_calendar_sensor_not_available_when_unknown():
    """`available` returns False when delivery data is CONF_UNKNOWN."""
    sensor = _make_sensor(None)
    assert sensor.available is False


def test_calendar_sensor_not_available_when_coordinator_data_empty():
    """`available` returns False when coordinator has no data at all."""
    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.data = {}
    sensor = TMMCalendarSensor(coordinator, "Test")
    assert sensor.available is False


# ---------------------------------------------------------------------------
# TMMCalendarSensor – get_event
# ---------------------------------------------------------------------------


def test_get_event_returns_calendar_event_for_future_delivery():
    """`get_event` returns a CalendarEvent when delivery is today or in the future."""
    sensor = _make_sensor("2099-12-31")
    event = sensor.get_event(datetime(2099, 12, 1))
    assert event is not None
    assert event.start == date(2099, 12, 31)
    assert event.summary == "Milkround"


def test_get_event_returns_calendar_event_for_today():
    """`get_event` returns a CalendarEvent when delivery is today."""
    today = datetime.today()
    sensor = _make_sensor(today.strftime("%Y-%m-%d"))
    event = sensor.get_event(today)
    assert event is not None
    assert event.start == today.date()


def test_get_event_returns_none_for_past_delivery():
    """`get_event` returns None when the delivery date is in the past."""
    sensor = _make_sensor("2000-01-01")
    event = sensor.get_event(datetime(2026, 1, 1))
    assert event is None


def test_get_event_returns_none_when_unknown():
    """`get_event` returns None when delivery data is CONF_UNKNOWN."""
    sensor = _make_sensor(None)
    event = sensor.get_event(datetime.today())
    assert event is None


# ---------------------------------------------------------------------------
# TMMCalendarSensor – event property
# ---------------------------------------------------------------------------


def test_event_property_returns_next_upcoming_event():
    """`event` property returns the next delivery CalendarEvent."""
    sensor = _make_sensor("2099-12-31")
    assert sensor.event is not None
    assert sensor.event.summary == "Milkround"


def test_event_property_returns_none_when_no_delivery():
    """`event` property returns None when no future delivery is scheduled."""
    sensor = _make_sensor("2000-01-01")
    assert sensor.event is None


# ---------------------------------------------------------------------------
# TMMCalendarSensor – async_get_events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_get_events_returns_event_within_range():
    """`async_get_events` returns the event when it falls within the range."""
    sensor = _make_sensor("2099-06-15")
    hass = MagicMock()
    events = await sensor.async_get_events(
        hass, datetime(2099, 6, 1), datetime(2099, 6, 30)
    )
    assert len(events) == 1
    assert events[0].start == date(2099, 6, 15)


@pytest.mark.asyncio
async def test_async_get_events_returns_empty_when_event_beyond_range():
    """`async_get_events` returns empty list when event is after the end_date."""
    sensor = _make_sensor("2099-12-31")
    hass = MagicMock()
    events = await sensor.async_get_events(
        hass, datetime(2099, 1, 1), datetime(2099, 6, 30)
    )
    assert events == []


@pytest.mark.asyncio
async def test_async_get_events_returns_empty_when_no_event():
    """`async_get_events` returns empty list when `get_event` returns None."""
    sensor = _make_sensor(None)
    hass = MagicMock()
    events = await sensor.async_get_events(
        hass, datetime(2026, 1, 1), datetime(2026, 12, 31)
    )
    assert events == []


@pytest.mark.asyncio
async def test_async_get_events_returns_empty_for_past_delivery():
    """`async_get_events` returns empty list when the delivery is in the past."""
    sensor = _make_sensor("2000-01-01")
    hass = MagicMock()
    events = await sensor.async_get_events(
        hass, datetime(2026, 1, 1), datetime(2026, 12, 31)
    )
    assert events == []


# ---------------------------------------------------------------------------
# generate_uuid_from_json
# ---------------------------------------------------------------------------


def test_generate_uuid_from_json_is_deterministic():
    """Same input must always produce the same UUID."""
    data = {"summary": "Milkround", "start_date": "2099-01-01"}
    uid1 = generate_uuid_from_json(data)
    uid2 = generate_uuid_from_json(data)
    assert uid1 == uid2


def test_generate_uuid_from_json_differs_for_different_input():
    """Different inputs must produce different UUIDs."""
    uid1 = generate_uuid_from_json({"key": "value1"})
    uid2 = generate_uuid_from_json({"key": "value2"})
    assert uid1 != uid2


def test_generate_uuid_from_json_handles_dates():
    """generate_uuid_from_json should not raise for date/datetime values."""
    data = {"start_date": date(2099, 1, 1), "created_at": datetime(2099, 1, 1, 12, 0)}
    uid = generate_uuid_from_json(data)
    assert uid is not None


# ---------------------------------------------------------------------------
# get_event_uid
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_event_uid_returns_none_on_service_validation_error():
    """`get_event_uid` returns None when the calendar service raises ServiceValidationError."""
    hass = MagicMock()
    hass.services.async_call = AsyncMock(side_effect=ServiceValidationError("err"))

    service_data = {
        "entity_id": "calendar.test",
        "start_date": date(2099, 1, 1),
        "end_date": date(2099, 1, 2),
        "summary": "Milkround",
        "description": "desc",
        "location": "loc",
    }
    result = await get_event_uid(hass, service_data)
    assert result is None


@pytest.mark.asyncio
async def test_get_event_uid_returns_none_on_home_assistant_error():
    """`get_event_uid` returns None when the calendar service raises HomeAssistantError."""
    hass = MagicMock()
    hass.services.async_call = AsyncMock(side_effect=HomeAssistantError("err"))

    service_data = {
        "entity_id": "calendar.test",
        "start_date": date(2099, 1, 1),
        "end_date": date(2099, 1, 2),
        "summary": "Milkround",
        "description": "desc",
        "location": "loc",
    }
    result = await get_event_uid(hass, service_data)
    assert result is None


@pytest.mark.asyncio
async def test_get_event_uid_returns_none_when_event_not_found():
    """`get_event_uid` returns None when the matching event is not in the results."""
    hass = MagicMock()
    hass.services.async_call = AsyncMock(
        return_value={
            "calendar.test": {
                "events": [
                    {
                        "summary": "Other Event",
                        "description": "desc",
                        "location": "loc",
                    }
                ]
            }
        }
    )
    service_data = {
        "entity_id": "calendar.test",
        "start_date": date(2099, 1, 1),
        "end_date": date(2099, 1, 2),
        "summary": "Milkround",
        "description": "desc",
        "location": "loc",
    }
    result = await get_event_uid(hass, service_data)
    assert result is None


@pytest.mark.asyncio
async def test_get_event_uid_returns_uuid_when_event_matches():
    """`get_event_uid` returns a UUID string when the event details match."""
    service_data = {
        "entity_id": "calendar.test",
        "start_date": date(2099, 1, 1),
        "end_date": date(2099, 1, 2),
        "summary": "Milkround",
        "description": "desc",
        "location": "loc",
    }
    hass = MagicMock()
    hass.services.async_call = AsyncMock(
        return_value={
            "calendar.test": {
                "events": [
                    {
                        "summary": "Milkround",
                        "description": "desc",
                        "location": "loc",
                    }
                ]
            }
        }
    )
    result = await get_event_uid(hass, service_data)
    assert result is not None
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# add_to_calendar
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_to_calendar_creates_event_when_not_already_present():
    """`add_to_calendar` calls create_event when uid is not in entry.data."""
    hass = MagicMock()
    expected_uid = generate_uuid_from_json(
        {
            "entity_id": "calendar.test",
            "start_date": date(2099, 1, 1),
            "end_date": date(2099, 1, 1),
            "summary": "Milkround",
            "description": "None",
            "location": "None",
        }
    )

    call_count = 0

    async def mock_get_event_uid_side_effect(h, sd):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return None  # event doesn't exist yet
        return expected_uid  # after creation

    hass.services.async_call = AsyncMock(return_value=None)

    entry = MagicMock()
    entry.data = {"uids": []}

    event = CalendarEvent(date(2099, 1, 1), date(2099, 1, 1), "Milkround")

    with patch(
        "custom_components.themodernmilkman.calendar.get_event_uid",
        side_effect=mock_get_event_uid_side_effect,
    ), patch(
        "custom_components.themodernmilkman.calendar.create_event",
        new_callable=AsyncMock,
    ) as mock_create:
        await add_to_calendar(hass, "calendar.test", event, entry)

    mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_add_to_calendar_skips_creation_when_uid_already_present():
    """`add_to_calendar` does not call create_event when uid is already tracked."""
    event = CalendarEvent(date(2099, 1, 1), date(2099, 1, 1), "Milkround")
    service_data = {
        "entity_id": "calendar.test",
        "start_date": date(2099, 1, 1),
        "end_date": date(2099, 1, 1),
        "summary": "Milkround",
        "description": "None",
        "location": "None",
    }
    existing_uid = generate_uuid_from_json(service_data)

    entry = MagicMock()
    entry.data = {"uids": [existing_uid]}

    hass = MagicMock()

    with patch(
        "custom_components.themodernmilkman.calendar.get_event_uid",
        new_callable=AsyncMock,
        return_value=existing_uid,
    ), patch(
        "custom_components.themodernmilkman.calendar.create_event",
        new_callable=AsyncMock,
    ) as mock_create:
        await add_to_calendar(hass, "calendar.test", event, entry)

    mock_create.assert_not_called()


# ---------------------------------------------------------------------------
# async_setup_entry
# ---------------------------------------------------------------------------


def _make_setup_mocks(calendars, delivery_date="2099-12-31"):
    """Return (hass, entry, coordinator) ready for async_setup_entry."""
    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.data = {
        CONF_NEXT_DELIVERY: {CONF_DELIVERYDATE: delivery_date}
    }

    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.title = "Test"
    entry.options = {}
    entry.data = {CONF_CALENDARS: calendars, "uids": []}

    domain_data = {entry.entry_id: {CONF_COORDINATOR: coordinator}}
    hass = MagicMock()
    hass.data = {DOMAIN: domain_data}

    return hass, entry, coordinator


def test_async_setup_entry_adds_entities_for_none_calendar():
    """async_setup_entry registers entities when 'None' is in the calendars list."""
    hass, entry, _ = _make_setup_mocks(["None"])
    add_calls = []

    def mock_add_entities(entities, update_before_add=False):
        add_calls.append(list(entities))

    asyncio.run(async_setup_entry(hass, entry, mock_add_entities))

    assert len(add_calls) == 1
    assert len(add_calls[0]) == 1
    assert isinstance(add_calls[0][0], TMMCalendarSensor)


def test_async_setup_entry_does_not_add_entities_for_external_calendar():
    """async_setup_entry does not register HA entities for external calendars."""
    hass, entry, _ = _make_setup_mocks(["calendar.google"])
    add_calls = []

    def mock_add_entities(entities, update_before_add=False):
        add_calls.append(list(entities))

    with patch(
        "custom_components.themodernmilkman.calendar.add_to_calendar",
        new_callable=AsyncMock,
    ):
        asyncio.run(async_setup_entry(hass, entry, mock_add_entities))

    assert len(add_calls) == 0


def test_async_setup_entry_calls_add_to_calendar_when_event_exists():
    """async_setup_entry calls add_to_calendar for each external calendar when an event exists."""
    hass, entry, _ = _make_setup_mocks(["calendar.google"])

    with patch(
        "custom_components.themodernmilkman.calendar.add_to_calendar",
        new_callable=AsyncMock,
    ) as mock_add:
        asyncio.run(async_setup_entry(hass, entry, MagicMock()))

    mock_add.assert_called_once()
    call_args = mock_add.call_args
    assert call_args[0][1] == "calendar.google"
    assert isinstance(call_args[0][2], CalendarEvent)


def test_async_setup_entry_skips_add_to_calendar_when_no_event():
    """async_setup_entry skips add_to_calendar when there is no upcoming delivery."""
    hass, entry, _ = _make_setup_mocks(["calendar.google"], delivery_date="2000-01-01")

    with patch(
        "custom_components.themodernmilkman.calendar.add_to_calendar",
        new_callable=AsyncMock,
    ) as mock_add:
        asyncio.run(async_setup_entry(hass, entry, MagicMock()))

    mock_add.assert_not_called()


def test_async_setup_entry_handles_both_none_and_external_calendars():
    """async_setup_entry registers entities AND delegates to external calendars."""
    hass, entry, _ = _make_setup_mocks(["None", "calendar.google"])
    add_calls = []

    def mock_add_entities(entities, update_before_add=False):
        add_calls.append(list(entities))

    with patch(
        "custom_components.themodernmilkman.calendar.add_to_calendar",
        new_callable=AsyncMock,
    ) as mock_add:
        asyncio.run(async_setup_entry(hass, entry, mock_add_entities))

    assert len(add_calls) == 1  # HA entity registered
    mock_add.assert_called_once()  # external calendar populated
