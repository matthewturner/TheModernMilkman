"""The Modern Milkman button platform."""

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_COORDINATOR, DOMAIN
from .coordinator import TMMCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up The Modern Milkman button from a config entry."""
    coordinator: TMMCoordinator = hass.data[DOMAIN][entry.entry_id][CONF_COORDINATOR]
    async_add_entities([TMMRefreshButton(coordinator, entry.title)])


class TMMRefreshButton(CoordinatorEntity[TMMCoordinator], ButtonEntity):
    """Button to manually refresh data from The Modern Milkman API."""

    def __init__(self, coordinator: TMMCoordinator, name: str) -> None:
        """Initialize the refresh button."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{DOMAIN}")},
            manufacturer="The Modern Milkman",
            model="Milkround",
            name=name,
            configuration_url="https://github.com/jampez77/TheModernMilkman/",
        )
        self._attr_unique_id = f"{DOMAIN}-{name}-refresh".lower()
        self.entity_id = f"button.{DOMAIN}_refresh"
        self.entity_description = ButtonEntityDescription(
            key="themodernmilkman_refresh",
            name="Refresh",
            icon="mdi:refresh",
        )

    async def async_press(self) -> None:
        """Refresh data from The Modern Milkman API."""
        await self.coordinator.async_request_refresh()
