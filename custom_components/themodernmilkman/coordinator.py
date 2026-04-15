import json
import logging
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    TMM_LOGIN_URL,
    TMM_NEXT_DELIVERY_URL,
    TMM_SKIP_SUBSCRIPTION_URL,
    TMM_USER_WASTEAGE_URL,
    CONF_PASSWORD,
    CONF_USERNAME,
    TMM_USER_STATE_URL,
    REQUEST_HEADER,
    CONF_WASTAGE,
    CONF_NEXT_DELIVERY,
    CONF_DELIVERYDATE,
    CONF_UNKNOWN,
)

_LOGGER = logging.getLogger(__name__)


def handle_status_code(status_code):
    """Raise an appropriate exception for non-successful HTTP status codes.

    Raises InvalidAuth for 401 responses and APIRatelimitExceeded for 429 responses.
    """
    if status_code == 401:
        raise InvalidAuth("Invalid authentication credentials")
    if status_code == 429:
        raise APIRatelimitExceeded("API rate limit exceeded.")


class TMMCoordinator(DataUpdateCoordinator):
    """The Modern Milkman coordinator."""

    def __init__(self, hass: HomeAssistant, session, data) -> None:
        """Initialize coordinator."""

        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="The Modern Milkman",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(days=1),
        )

        self.session = session
        self.body = {
            CONF_USERNAME: data[CONF_USERNAME],
            CONF_PASSWORD: data[CONF_PASSWORD],
        }

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        body = {}
        try:
            login_resp = await self.session.request(
                method="POST",
                url=TMM_LOGIN_URL,
                json=self.body,
                headers=REQUEST_HEADER,
            )

            handle_status_code(login_resp.status)

            wastageResp = await self.session.request(
                method="GET", url=TMM_USER_WASTEAGE_URL
            )

            handle_status_code(wastageResp.status)

            wastage = await wastageResp.text()

            body[CONF_WASTAGE] = json.loads(wastage)

            nextDeliveryResp = await self.session.request(
                method="GET", url=TMM_NEXT_DELIVERY_URL
            )

            handle_status_code(nextDeliveryResp.status)

            if nextDeliveryResp.status == 200:
                nextDelivery = await nextDeliveryResp.text()
                body[CONF_NEXT_DELIVERY] = json.loads(nextDelivery)
            else:
                body[CONF_NEXT_DELIVERY] = CONF_UNKNOWN

        except InvalidAuth as err:
            raise ConfigEntryAuthFailed from err
        except TMMError as err:
            raise UpdateFailed(str(err)) from err
        except ValueError as err:
            _LOGGER.error("Value error occurred: %s", err)
            raise UpdateFailed(f"Unexpected response: {err}") from err
        except Exception as err:
            _LOGGER.error("Unexpected exception: %s", err)
            raise UnknownError from err
        else:
            return body

    async def async_skip_subscription_item(self, subscription_item_id: int) -> None:
        """Pause a subscription item on the next delivery date."""
        next_delivery = self.data.get(CONF_NEXT_DELIVERY)
        if not next_delivery or next_delivery == CONF_UNKNOWN:
            raise UpdateFailed("No next delivery available to pause")

        skip_date_raw = next_delivery.get(CONF_DELIVERYDATE)
        if not skip_date_raw:
            raise UpdateFailed("Missing next delivery date")

        skip_date = self._normalise_skip_date(skip_date_raw)

        payload = {
            "skipDate": skip_date,
            "pauseReasonId": 5,
            "subscriptionItemIds": [subscription_item_id],
        }

        response = await self.session.request(
            method="POST",
            url=TMM_SKIP_SUBSCRIPTION_URL,
            json=payload,
            headers=REQUEST_HEADER,
        )

        handle_status_code(response.status)
        if response.status not in (200, 201, 204):
            raise UpdateFailed(f"Unable to pause subscription item: {response.status}")

        await self.async_request_refresh()

    @staticmethod
    def _normalise_skip_date(raw_value: str) -> str:
        """Convert API date values to YYYY-MM-DD."""
        try:
            return datetime.fromisoformat(raw_value.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            return raw_value.split("T")[0]


class TMMLoginCoordinator(DataUpdateCoordinator):
    """Login coordinator."""

    def __init__(self, hass: HomeAssistant, session, data: dict) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="The Modern Milkman",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=None,
        )
        self.session = session
        self.data = dict(data)

        self.body = {
            CONF_USERNAME: data[CONF_USERNAME],
            CONF_PASSWORD: data[CONF_PASSWORD],
        }

    async def _async_update_data(self):
        """Fetch data from API endpoint."""

        try:
            if self.body is not None:
                resp = await self._make_request()

                handle_status_code(resp.status)

                user_resp = await self._make_request_user_state()

                handle_status_code(user_resp.status)

                body = await user_resp.text()

        except InvalidAuth as err:
            raise ConfigEntryAuthFailed from err
        except TMMError as err:
            raise UpdateFailed(str(err)) from err
        except ConfigEntryAuthFailed as err:
            raise ConfigEntryAuthFailed(f"Config Entry failed: {err}") from err
        except ValueError as err:
            _LOGGER.error("Value error occurred: %s", err)
            raise UpdateFailed(f"Unexpected response: {err}") from err
        except Exception as err:
            _LOGGER.error("Unexpected exception: %s", err)
            raise UnknownError from err
        else:
            return json.loads(body)

    async def _make_request(self):
        """Make the API request."""
        return await self.session.request(
            method="POST", url=TMM_LOGIN_URL, json=self.body, headers=REQUEST_HEADER
        )

    async def _make_request_user_state(self):
        """Make the API request."""
        return await self.session.request(method="GET", url=TMM_USER_STATE_URL)

    async def refresh_tokens(self):
        """Public method to refresh tokens."""
        return await self._async_update_data()


class TMMError(HomeAssistantError):
    """Base error."""


class InvalidAuth(TMMError):
    """Raised when invalid authentication credentials are provided."""


class APIRatelimitExceeded(TMMError):
    """Raised when the API rate limit is exceeded."""


class NotFoundError(TMMError):
    """Raised when the API rate limit is exceeded."""


class UnknownError(TMMError):
    """Raised when an unknown error occurs."""
