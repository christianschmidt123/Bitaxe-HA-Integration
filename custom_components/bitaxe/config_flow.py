import ipaddress
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import zeroconf
from homeassistant.const import CONF_IP_ADDRESS, CONF_NAME
from homeassistant.core import callback

from .api import BitAxeApiError, async_fetch_system_info, get_bitaxe_device_name, get_bitaxe_unique_id
from .const import DOMAIN

DEFAULT_DEVICE_NAME = "Bitaxe Miner"


class BitAxeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovered_entry_data: dict[str, str] | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            ip_address = user_input[CONF_IP_ADDRESS].strip()
            configured_name = user_input.get(CONF_NAME, "").strip()

            try:
                ipaddress.ip_address(ip_address)
            except ValueError:
                errors[CONF_IP_ADDRESS] = "invalid_ip"
            else:
                if self._is_ip_address_configured(ip_address):
                    return self.async_abort(reason="already_configured")

                try:
                    system_info = await async_fetch_system_info(self.hass, ip_address)
                except BitAxeApiError:
                    errors["base"] = "cannot_connect"
                else:
                    unique_id = get_bitaxe_unique_id(system_info, ip_address)
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured(updates={CONF_IP_ADDRESS: ip_address})

                    device_name = configured_name or get_bitaxe_device_name(system_info, DEFAULT_DEVICE_NAME)
                    return self.async_create_entry(
                        title=device_name,
                        data={CONF_IP_ADDRESS: ip_address, "device_name": device_name},
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=self._get_user_schema(),
            errors=errors,
        )

    async def async_step_zeroconf(self, discovery_info: zeroconf.ZeroconfServiceInfo):
        """Handle a discovered Bitaxe device."""
        ip_address = self._get_discovery_ip_address(discovery_info)
        if ip_address is None:
            return self.async_abort(reason="cannot_connect")

        if self._is_ip_address_configured(ip_address):
            return self.async_abort(reason="already_configured")

        try:
            system_info = await async_fetch_system_info(self.hass, ip_address)
        except BitAxeApiError:
            return self.async_abort(reason="cannot_connect")

        unique_id = get_bitaxe_unique_id(system_info, ip_address)
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured(updates={CONF_IP_ADDRESS: ip_address})

        device_name = get_bitaxe_device_name(system_info, discovery_info.name)
        self._discovered_entry_data = {
            CONF_IP_ADDRESS: ip_address,
            "device_name": device_name,
        }
        self.context["title_placeholders"] = {"name": device_name}

        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(self, user_input: dict[str, Any] | None = None):
        """Confirm the discovered Bitaxe before creating the entry."""
        if self._discovered_entry_data is None:
            return self.async_abort(reason="cannot_connect")

        if user_input is not None:
            return self.async_create_entry(
                title=self._discovered_entry_data["device_name"],
                data=self._discovered_entry_data,
            )

        return self.async_show_form(
            step_id="zeroconf_confirm",
            description_placeholders={
                "ip_address": self._discovered_entry_data[CONF_IP_ADDRESS],
                "device_name": self._discovered_entry_data["device_name"],
            },
            data_schema=vol.Schema({}),
        )

    def _get_user_schema(self) -> vol.Schema:
        """Return the schema for user input."""
        return vol.Schema(
            {
                vol.Required(CONF_IP_ADDRESS): str,
                vol.Optional(CONF_NAME): str,
            }
        )

    def _get_discovery_ip_address(self, discovery_info: zeroconf.ZeroconfServiceInfo) -> str | None:
        """Extract the IP address from zeroconf discovery info."""
        host = getattr(discovery_info, "host", None)
        if isinstance(host, str) and host:
            return host.rstrip(".")

        ip_address = getattr(discovery_info, "ip_address", None)
        if isinstance(ip_address, str) and ip_address:
            return ip_address

        return None

    def _is_ip_address_configured(self, ip_address: str) -> bool:
        """Check if the Bitaxe IP address is already configured."""
        return any(
            entry.data.get(CONF_IP_ADDRESS) == ip_address
            for entry in self._async_current_entries()
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return BitAxeOptionsFlowHandler(config_entry)


class BitAxeOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        return self.async_show_form(step_id="init")
