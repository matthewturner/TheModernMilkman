"""The Modern Milkman button platform."""

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_COORDINATOR,
    CONF_ITEMS,
    CONF_NEXT_DELIVERY,
    CONF_UNKNOWN,
    DOMAIN,
)
from .coordinator import TMMCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up The Modern Milkman button from a config entry."""
    coordinator: TMMCoordinator = hass.data[DOMAIN][entry.entry_id][CONF_COORDINATOR]
    buttons: list[ButtonEntity] = [TMMRefreshButton(coordinator, entry.title)]

    next_delivery = coordinator.data.get(CONF_NEXT_DELIVERY)
    if next_delivery and next_delivery != CONF_UNKNOWN:
        items = next_delivery.get(CONF_ITEMS, [])
        for index, item in enumerate(items, start=1):
            if item.get("subscriptionItemId") is None:
                continue
            pause_button = TMMPauseProductButton(coordinator, entry.title, index, item)
            hass.data[DOMAIN][pause_button.unique_id] = pause_button
            buttons.append(pause_button)

    async_add_entities(buttons)

    @callback
    def _async_add_new_pause_buttons() -> None:
        """Add pause buttons for any new products in the coordinator data."""
        next_del = coordinator.data.get(CONF_NEXT_DELIVERY)
        if not next_del or next_del == CONF_UNKNOWN:
            return

        items = next_del.get(CONF_ITEMS, [])
        new_buttons = []
        for index, item in enumerate(items, start=1):
            if item.get("subscriptionItemId") is None:
                continue
            unique_id = f"{DOMAIN}-{entry.title}-product_{index}_pause".lower()
            if unique_id not in hass.data[DOMAIN]:
                pause_button = TMMPauseProductButton(coordinator, entry.title, index, item)
                hass.data[DOMAIN][pause_button.unique_id] = pause_button
                new_buttons.append(pause_button)

        if new_buttons:
            async_add_entities(new_buttons)

    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_pause_buttons))


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


class TMMPauseProductButton(CoordinatorEntity[TMMCoordinator], ButtonEntity):
    """Button to pause a specific product from the next delivery."""

    def __init__(
        self, coordinator: TMMCoordinator, name: str, index: int, item: dict
    ) -> None:
        """Initialize the pause button."""
        super().__init__(coordinator)
        self._index = index
        self._item = item
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{DOMAIN}")},
            manufacturer="The Modern Milkman",
            model="Milkround",
            name=name,
            configuration_url="https://github.com/jampez77/TheModernMilkman/",
        )
        self._attr_unique_id = f"{DOMAIN}-{name}-product_{index}_pause".lower()
        self.entity_id = f"button.{DOMAIN}_product_{index}_pause"
        self.entity_description = ButtonEntityDescription(
            key=f"themodernmilkman_product_{index}_pause",
            name=f"Pause Product {index}",
            icon="mdi:pause-circle",
        )

    @property
    def available(self) -> bool:
        """Return if the entity is available."""
        return (
            self.coordinator.last_update_success
            and self._item is not None
            and self._item.get("subscriptionItemId") is not None
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        next_delivery = self.coordinator.data.get(CONF_NEXT_DELIVERY)
        if next_delivery and next_delivery != CONF_UNKNOWN:
            items = next_delivery.get(CONF_ITEMS, [])
            if len(items) >= self._index:
                self._item = items[self._index - 1]
            else:
                self._item = None
        else:
            self._item = None
        self.async_write_ha_state()

    async def async_press(self) -> None:
        """Pause product for next delivery."""
        if not self._item or self._item.get("subscriptionItemId") is None:
            raise HomeAssistantError("No subscription item available to pause")

        await self.coordinator.async_skip_subscription_item(
            self._item["subscriptionItemId"]
        )
