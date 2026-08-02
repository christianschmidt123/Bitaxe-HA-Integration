from __future__ import annotations

from typing import Any
import logging

from awesomeversion import AwesomeVersion, AwesomeVersionCompareException
from homeassistant.components.update import UpdateDeviceClass, UpdateEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from .const import DOMAIN, FIRMWARE_ASSET_NAME, WEB_UI_ASSET_NAME

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Bitaxe update entities from a config entry."""
    device_data = hass.data[DOMAIN][entry.unique_id]
    coordinator = device_data["coordinator"]
    release_coordinator = device_data["release_coordinator"]

    async_add_entities(
        [
            BitaxeUpdateEntity(
                coordinator,
                release_coordinator,
                entry,
                "firmware_update",
                FIRMWARE_ASSET_NAME,
                "version",
                UpdateDeviceClass.FIRMWARE,
            ),
            BitaxeUpdateEntity(
                coordinator,
                release_coordinator,
                entry,
                "web_ui_update",
                WEB_UI_ASSET_NAME,
                "axeOSVersion",
            ),
        ],
        True,
    )


class BitaxeUpdateEntity(CoordinatorEntity, UpdateEntity):
    """Representation of an available Bitaxe update."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        release_coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
        translation_key: str,
        asset_name: str,
        installed_version_key: str,
        device_class: UpdateDeviceClass | None = None,
    ) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self.release_coordinator = release_coordinator
        self.asset_name = asset_name
        self.installed_version_key = installed_version_key
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{entry.entry_id}_{translation_key}"
        self._attr_device_class = device_class
        self._attr_icon = "mdi:update"

    async def async_added_to_hass(self) -> None:
        """Listen to both device and release coordinator updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.release_coordinator.async_add_listener(self.async_write_ha_state)
        )

    @property
    def available(self) -> bool:
        """Return if the entity is available."""
        return bool(self.coordinator.data)

    @property
    def device_info(self) -> dict[str, Any]:
        """Group update entities under the same Bitaxe device."""
        return {
            "identifiers": {(DOMAIN, self.entry.entry_id)},
            "name": self.entry.data.get("device_name", "BitAxe Miner"),
            "manufacturer": "Open Source Hardware",
            "model": "BitAxe Miner",
            "via_device": None,
        }

    @property
    def installed_version(self) -> str | None:
        """Return the currently installed version."""
        data = self.coordinator.data or {}
        version = data.get(self.installed_version_key)
        return _normalize_version(version)

    @property
    def latest_version(self) -> str | None:
        """Return the latest version relevant for this asset."""
        release = self.release_coordinator.data or {}
        if self.asset_name not in _release_assets(release):
            return self.installed_version

        latest = _normalize_version(release.get("tag_name"))
        installed = self.installed_version
        is_newer = _is_newer_version(installed, latest)

        if is_newer is True:
            return latest
        if installed is not None:
            return installed
        return None

    @property
    def release_url(self) -> str | None:
        """Return the release page URL."""
        release = self.release_coordinator.data or {}
        if self.asset_name not in _release_assets(release):
            return None
        return release.get("html_url")

    @property
    def release_summary(self) -> str | None:
        """Return the release notes."""
        release = self.release_coordinator.data or {}
        if self.asset_name not in _release_assets(release):
            return None
        return release.get("body")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose related release metadata."""
        release = self.release_coordinator.data or {}
        asset = _release_assets(release).get(self.asset_name, {})
        return {
            "asset_name": self.asset_name,
            "asset_url": asset.get("browser_download_url"),
            "board_version": (self.coordinator.data or {}).get("boardVersion"),
        }


def _normalize_version(value: Any) -> str | None:
    """Normalize a version-like value."""
    if value is None:
        return None

    version = str(value).strip()
    return version or None


def _release_assets(release: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return release assets keyed by name."""
    assets = release.get("assets", [])
    return {
        asset.get("name"): asset
        for asset in assets
        if asset.get("name") and asset.get("browser_download_url")
    }


def _is_newer_version(installed: str | None, latest: str | None) -> bool | None:
    """Compare installed and latest versions."""
    if not installed or not latest:
        return None

    try:
        return AwesomeVersion(latest) > AwesomeVersion(installed)
    except AwesomeVersionCompareException:
        if latest.lstrip("vV") == installed.lstrip("vV"):
            return False
        _LOGGER.debug("Unable to compare Bitaxe versions: installed=%s latest=%s", installed, latest)
        return None
