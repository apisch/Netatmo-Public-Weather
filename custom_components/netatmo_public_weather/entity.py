"""Base entity for Netatmo Public Weather."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, VIEW_AVERAGE, VIEW_PRIMARY, station_view
from .coordinator import NetatmoPublicCoordinator, StationConfig
from .model import WeatherValues


class ViewTarget:
    """Which view an entity shows and the device it belongs to."""

    def __init__(
        self, coordinator: NetatmoPublicCoordinator, kind: str, station: StationConfig | None = None
    ) -> None:
        """Initialize; kind is 'station', 'primary' or 'average'."""
        entry = coordinator.config_entry
        self.kind = kind
        self.station = station
        if kind == "station" and station is not None:
            self.view_key = station_view(station.id)
            self.device_id = f"{entry.entry_id}_{station.id.replace(':', '')}"
            self.device_name = f"Netatmo {station.name}"
            self.modules = station.modules
            model = "Public station"
        else:
            self.view_key = VIEW_PRIMARY if kind == "primary" else VIEW_AVERAGE
            self.device_id = f"{entry.entry_id}_{kind}"
            self.device_name = f"{entry.title} {'Primary' if kind == 'primary' else 'Average'}"
            self.modules = frozenset().union(*(s.modules for s in coordinator.stations))
            model = "Primary with fallback" if kind == "primary" else "Average of stations"
        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, self.device_id)},
            name=self.device_name,
            manufacturer="Netatmo (public data)",
            model=model,
            entry_type=DeviceEntryType.SERVICE,
        )


def view_targets(coordinator: NetatmoPublicCoordinator) -> list[ViewTarget]:
    """Return all devices of an entry: stations, primary and (if >1) average."""
    targets = [ViewTarget(coordinator, "station", s) for s in coordinator.stations]
    targets.append(ViewTarget(coordinator, "primary"))
    if len(coordinator.stations) >= 2:
        targets.append(ViewTarget(coordinator, "average"))
    return targets


class NetatmoPublicEntity(CoordinatorEntity[NetatmoPublicCoordinator]):
    """An entity that shows one view of the coordinator snapshot."""

    _attr_has_entity_name = True
    _attr_attribution = "Data from public Netatmo weather stations"

    def __init__(self, coordinator: NetatmoPublicCoordinator, target: ViewTarget, key: str) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.target = target
        self._attr_unique_id = f"{target.device_id}_{key}"
        self._attr_device_info = target.device_info

    @property
    def view(self) -> WeatherValues | None:
        """Return the current values of this entity's view."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.views.get(self.target.view_key)

    @property
    def available(self) -> bool:
        """Unavailable whenever the view has no healthy data."""
        return super().available and self.view is not None
