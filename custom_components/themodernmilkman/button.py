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


def _skip_button_unique_id(name: str, index: int) -> str:
    """Build a stable unique ID for a product skip button."""
    return f"{DOMAIN}-{name}-product_{index}_skip".lower()


def _product_buttons(
    coordinator: TMMCoordinator, name: str, index: int, item: dict
) -> list[ButtonEntity]:
    """Build the skip and quantity buttons for one product."""
    return [
        TMMSkipProductButton(coordinator, name, index, item),
        TMMQuantityButton(coordinator, name, index, item, 1),
        TMMQuantityButton(coordinator, name, index, item, -1),
    ]


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
            product_buttons = _product_buttons(coordinator, entry.title, index, item)
            hass.data[DOMAIN][product_buttons[0].unique_id] = product_buttons[0]
            buttons.extend(product_buttons)

    async_add_entities(buttons)

    @callback
    def _async_add_new_skip_buttons() -> None:
        """Add skip buttons for any new products in the coordinator data."""
        next_del = coordinator.data.get(CONF_NEXT_DELIVERY)
        if not next_del or next_del == CONF_UNKNOWN:
            return

        items = next_del.get(CONF_ITEMS, [])
        new_buttons = []
        for index, item in enumerate(items, start=1):
            if item.get("subscriptionItemId") is None:
                continue
            unique_id = _skip_button_unique_id(entry.title, index)
            if unique_id not in hass.data[DOMAIN]:
                product_buttons = _product_buttons(
                    coordinator, entry.title, index, item
                )
                hass.data[DOMAIN][product_buttons[0].unique_id] = product_buttons[0]
                new_buttons.extend(product_buttons)

        if new_buttons:
            async_add_entities(new_buttons)

    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_skip_buttons))


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


class _TMMProductButton(CoordinatorEntity[TMMCoordinator], ButtonEntity):
    """Base for buttons tied to a product in the next delivery."""

    def __init__(
        self, coordinator: TMMCoordinator, name: str, index: int, item: dict
    ) -> None:
        """Initialize the product button."""
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


class TMMSkipProductButton(_TMMProductButton):
    """Button to skip a specific product from the next delivery."""

    def __init__(
        self, coordinator: TMMCoordinator, name: str, index: int, item: dict
    ) -> None:
        """Initialize the skip button."""
        super().__init__(coordinator, name, index, item)
        self._attr_unique_id = _skip_button_unique_id(name, index)
        self.entity_id = f"button.{DOMAIN}_product_{index}_skip"
        self.entity_description = ButtonEntityDescription(
            key=f"themodernmilkman_product_{index}_skip",
            name=f"Skip Product {index}",
            icon="mdi:skip-next-circle",
        )

    async def async_press(self) -> None:
        """Skip product for next delivery."""
        if not self._item or self._item.get("subscriptionItemId") is None:
            raise HomeAssistantError("No subscription item available to skip")

        await self.coordinator.async_skip_subscription_item(
            self._item["subscriptionItemId"]
        )


class TMMQuantityButton(_TMMProductButton):
    """Button to increase or decrease a product's quantity on the next delivery."""

    def __init__(
        self,
        coordinator: TMMCoordinator,
        name: str,
        index: int,
        item: dict,
        delta: int,
    ) -> None:
        """Initialize the quantity button."""
        super().__init__(coordinator, name, index, item)
        self._delta = delta
        action = "increase" if delta > 0 else "decrease"
        self._attr_unique_id = (
            f"{DOMAIN}-{name}-product_{index}_{action}".lower()
        )
        self.entity_id = f"button.{DOMAIN}_product_{index}_{action}"
        self.entity_description = ButtonEntityDescription(
            key=f"themodernmilkman_product_{index}_{action}",
            name=f"{action.capitalize()} Product {index}",
            icon="mdi:plus-circle" if delta > 0 else "mdi:minus-circle",
        )

    async def async_press(self) -> None:
        """Change the product quantity for the next delivery."""
        if not self._item or self._item.get("subscriptionItemId") is None:
            raise HomeAssistantError("No subscription item available to amend")

        await self.coordinator.async_adjust_item_quantity(
            self._item["subscriptionItemId"], self._delta
        )
