"""Health binary sensors for Netatmo Public Weather."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import NetatmoPublicConfigEntry, NetatmoPublicCoordinator
from .entity import NetatmoPublicEntity, ViewTarget, view_targets


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NetatmoPublicConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up health sensors for stations and the primary view."""
    coordinator = entry.runtime_data
    async_add_entities(
        HealthySensor(coordinator, target)
        for target in view_targets(coordinator)
        if target.kind in ("station", "primary")
    )


class HealthySensor(NetatmoPublicEntity, BinarySensorEntity):
    """On while the station (or any station for primary) delivers fresh data."""

    _attr_translation_key = "healthy"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: NetatmoPublicCoordinator, target: ViewTarget) -> None:
        """Initialize."""
        super().__init__(coordinator, target, "healthy")

    @property
    def available(self) -> bool:
        """Always available, so automations see an outage as 'off'."""
        return True

    @property
    def is_on(self) -> bool:
        """Return True if the last poll succeeded and delivered fresh data."""
        data = self.coordinator.data
        if data is None or not self.coordinator.last_update_success:
            return False
        if self.target.kind == "primary":
            return data.active_station is not None
        assert self.target.station is not None
        return data.healthy.get(self.target.station.id, False)
