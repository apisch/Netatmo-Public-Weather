"""Sensors for Netatmo Public Weather."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    DEGREE,
    PERCENTAGE,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfVolumetricFlux,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import MODULE_BASE, MODULE_RAIN, MODULE_WIND
from .coordinator import NetatmoPublicConfigEntry, NetatmoPublicCoordinator
from .entity import NetatmoPublicEntity, ViewTarget, view_targets
from .model import WeatherValues

# Added in recent HA versions; fall back gracefully on older ones.
_WIND_DIRECTION = getattr(SensorDeviceClass, "WIND_DIRECTION", None)
_ANGLE_STATE = getattr(SensorStateClass, "MEASUREMENT_ANGLE", None)


@dataclass(frozen=True, kw_only=True)
class NetatmoSensorDescription(SensorEntityDescription):
    """Describes a measured sensor."""

    module: str
    value_fn: Callable[[WeatherValues], float | None]


def _angle(key: str, attr: str) -> NetatmoSensorDescription:
    return NetatmoSensorDescription(
        key=key,
        translation_key=key,
        module=MODULE_WIND,
        device_class=_WIND_DIRECTION,
        state_class=_ANGLE_STATE,
        native_unit_of_measurement=DEGREE,
        value_fn=lambda v: getattr(v, attr),
    )


SENSORS: tuple[NetatmoSensorDescription, ...] = (
    NetatmoSensorDescription(
        key="temperature",
        module=MODULE_BASE,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda v: v.temperature,
    ),
    NetatmoSensorDescription(
        key="humidity",
        module=MODULE_BASE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda v: v.humidity,
    ),
    NetatmoSensorDescription(
        key="pressure",
        module=MODULE_BASE,
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPressure.HPA,
        value_fn=lambda v: v.pressure,
    ),
    NetatmoSensorDescription(
        key="rain_live",
        translation_key="rain_live",
        module=MODULE_RAIN,
        device_class=SensorDeviceClass.PRECIPITATION_INTENSITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR,
        value_fn=lambda v: v.rain_live,
    ),
    NetatmoSensorDescription(
        key="rain_60min",
        translation_key="rain_60min",
        module=MODULE_RAIN,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        value_fn=lambda v: v.rain_60min,
    ),
    NetatmoSensorDescription(
        key="rain_24h",
        translation_key="rain_24h",
        module=MODULE_RAIN,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        value_fn=lambda v: v.rain_24h,
    ),
    NetatmoSensorDescription(
        key="wind_strength",
        translation_key="wind_strength",
        module=MODULE_WIND,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        value_fn=lambda v: v.wind_strength,
    ),
    _angle("wind_angle", "wind_angle"),
    NetatmoSensorDescription(
        key="gust_strength",
        translation_key="gust_strength",
        module=MODULE_WIND,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        value_fn=lambda v: v.gust_strength,
    ),
    _angle("gust_angle", "gust_angle"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NetatmoPublicConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = []
    for target in view_targets(coordinator):
        entities.extend(
            NetatmoMeasureSensor(coordinator, target, d)
            for d in SENSORS
            if d.module in target.modules
        )
        if target.kind == "primary":
            entities.append(ActiveStationSensor(coordinator, target))
        elif target.kind == "average":
            entities.append(StationsUsedSensor(coordinator, target))
    async_add_entities(entities)


class NetatmoMeasureSensor(NetatmoPublicEntity, SensorEntity):
    """One measured value of a view."""

    entity_description: NetatmoSensorDescription

    def __init__(
        self,
        coordinator: NetatmoPublicCoordinator,
        target: ViewTarget,
        description: NetatmoSensorDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, target, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        """Return the measured value."""
        view = self.view
        return self.entity_description.value_fn(view) if view else None


class ActiveStationSensor(NetatmoPublicEntity, SensorEntity):
    """Which station currently feeds the primary view."""

    _attr_translation_key = "active_station"

    def __init__(self, coordinator: NetatmoPublicCoordinator, target: ViewTarget) -> None:
        """Initialize."""
        super().__init__(coordinator, target, "active_station")

    def _active(self) -> tuple[int, Any] | None:
        data = self.coordinator.data
        if data is None or data.active_station is None:
            return None
        for index, station in enumerate(self.coordinator.stations):
            if station.id == data.active_station:
                return index, station
        return None

    @property
    def native_value(self) -> str | None:
        """Return the active station's name."""
        active = self._active()
        return active[1].name if active else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return station id and priority (1 = primary)."""
        active = self._active()
        if not active:
            return None
        return {"station_id": active[1].id, "priority": active[0] + 1}


class StationsUsedSensor(NetatmoPublicEntity, SensorEntity):
    """How many healthy stations feed the average view."""

    _attr_translation_key = "stations_used"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: NetatmoPublicCoordinator, target: ViewTarget) -> None:
        """Initialize."""
        super().__init__(coordinator, target, "stations_used")

    @property
    def available(self) -> bool:
        """Zero healthy stations is a valid value, not an outage."""
        return self.coordinator.last_update_success and self.coordinator.data is not None

    @property
    def native_value(self) -> int | None:
        """Return the number of healthy stations."""
        data = self.coordinator.data
        return len(data.used_stations) if data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the names of the stations in use."""
        data = self.coordinator.data
        if data is None:
            return None
        names = {s.id: s.name for s in self.coordinator.stations}
        return {"stations": [names[s] for s in data.used_stations]}
