"""The Modern Milkman calendar platform."""

from datetime import date, datetime
import hashlib
import json
import uuid

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import TMMCoordinator
from .const import (
    CONF_COORDINATOR,
    DOMAIN,
    CONF_CALENDARS,
    CONF_NEXT_DELIVERY,
    CONF_DELIVERYDATE,
    CONF_UNKNOWN,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry created in the integrations UI."""
    config = hass.data[DOMAIN][entry.entry_id]
    # Update our config to include new repos and remove those that have been removed.
    if entry.options:
        config.update(entry.options)

    calendars = entry.data[CONF_CALENDARS]

    coordinator = hass.data[DOMAIN][entry.entry_id][CONF_COORDINATOR]

    sensors = [TMMCalendarSensor(coordinator, entry.title)]

    for calendar in calendars:
        if calendar != "None":
            for sensor in sensors:
                next_event = sensor.get_event(datetime.today())
                if next_event is not None:
                    await add_to_calendar(hass, calendar, next_event, entry)

    if "None" in calendars:
        async_add_entities(sensors, update_before_add=True)


async def create_event(hass: HomeAssistant, service_data):
    """Create calendar event."""
    try:
        await hass.services.async_call(
            "calendar",
            "create_event",
            service_data,
            blocking=True,
            return_response=True,
        )
    except (ServiceValidationError, HomeAssistantError):
        await hass.services.async_call(
            "calendar",
            "create_event",
            service_data,
            blocking=True,
        )


class DateTimeEncoder(json.JSONEncoder):
    """Encode date time object."""

    def default(self, o):
        """Encode date time object."""
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        return super().default(o)


def generate_uuid_from_json(json_obj):
    """Generate a UUID from a JSON object."""

    json_string = json.dumps(json_obj, cls=DateTimeEncoder, sort_keys=True)

    sha1_hash = hashlib.sha1(json_string.encode("utf-8")).digest()

    return str(uuid.UUID(bytes=sha1_hash[:16]))


async def get_event_uid(hass: HomeAssistant, service_data) -> str | None:
    """Fetch the created event by matching with details in service_data."""
    entity_id = service_data.get("entity_id")
    start_time = service_data.get("start_date")
    end_time = service_data.get("end_date")

    try:
        events = await hass.services.async_call(
            "calendar",
            "get_events",
            {
                "entity_id": entity_id,
                "start_date_time": f"{start_time}T00:00:00+0000",
                "end_date_time": f"{end_time}T00:00:00+0000",
            },
            return_response=True,
            blocking=True,
        )
    except (ServiceValidationError, HomeAssistantError):
        events = None

    if events is not None and entity_id in events:
        for event in events[entity_id].get("events"):
            event_desc = str(event.get("description"))
            event_loc = str(event.get("location"))
            if (
                event["summary"] == service_data["summary"]
                and event_desc == str(service_data["description"])
                and event_loc == str(service_data["location"])
            ):
                return generate_uuid_from_json(service_data)
                return generate_uuid_from_json(service_data)

    return None


async def add_to_calendar(
    hass: HomeAssistant, calendar: str, event: CalendarEvent, entry: ConfigEntry
):
    """Add an event to the calendar."""

    service_data = {
        "entity_id": calendar,
        "start_date": event.start,
        "end_date": event.end,
        "summary": event.summary,
        "description": f"{event.description}",
        "location": f"{event.location}",
    }

    uid = await get_event_uid(hass, service_data)

    uids = entry.data.get("uids", [])

    if uid not in uids:
        await create_event(hass, service_data)

        created_event_uid = await get_event_uid(hass, service_data)

        if created_event_uid is not None and created_event_uid not in uids:
            uids.append(created_event_uid)

    if uids != entry.data.get("uids", []):
        updated_data = entry.data.copy()
        updated_data["uids"] = uids
        hass.config_entries.async_update_entry(entry, data=updated_data)


class TMMCalendarSensor(CoordinatorEntity[TMMCoordinator], CalendarEntity):
    """Define The Modern Milkman sensor."""

    def __init__(
        self,
        coordinator: TMMCoordinator,
        name: str,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.data = coordinator.data.get(CONF_NEXT_DELIVERY)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{DOMAIN}")},
            manufacturer="The Modern Milkman",
            model="Milkround",
            name=name,
            configuration_url="https://github.com/jampez77/TheModernMilkman/",
        )
        self._attr_unique_id = f"{DOMAIN}-calendar".lower()
        self._attr_name = "Deliveries"

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return bool(self.coordinator.data) and (self.data != CONF_UNKNOWN)

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event."""
        return self.get_event(datetime.today())

    def get_event(self, start_date: datetime) -> CalendarEvent | None:
        """Return calendar event."""

        if self.data == CONF_UNKNOWN:
            return None

        value = datetime.fromisoformat(self.data[CONF_DELIVERYDATE]).date()
        if value >= start_date.date():
            return CalendarEvent(value, value, "Milkround")

        return None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        event = self.get_event(start_date)
        if event is not None and event.start <= end_date.date():
            return [event]

        return []
