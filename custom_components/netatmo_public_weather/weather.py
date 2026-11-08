"""Weather entities for Netatmo Public Weather."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.weather import (
    ATTR_FORECAST_APPARENT_TEMP,
    ATTR_FORECAST_DEW_POINT,
    ATTR_FORECAST_NATIVE_APPARENT_TEMP,
    ATTR_FORECAST_NATIVE_DEW_POINT,
    ATTR_FORECAST_NATIVE_PRECIPITATION,
    ATTR_FORECAST_NATIVE_PRESSURE,
    ATTR_FORECAST_NATIVE_TEMP,
    ATTR_FORECAST_NATIVE_TEMP_LOW,
    ATTR_FORECAST_NATIVE_WIND_GUST_SPEED,
    ATTR_FORECAST_NATIVE_WIND_SPEED,
    ATTR_FORECAST_PRECIPITATION,
    ATTR_FORECAST_PRESSURE,
    ATTR_FORECAST_TEMP,
    ATTR_FORECAST_TEMP_LOW,
    ATTR_FORECAST_WIND_GUST_SPEED,
    ATTR_FORECAST_WIND_SPEED,
    ATTR_WEATHER_APPARENT_TEMPERATURE,
    ATTR_WEATHER_CLOUD_COVERAGE,
    ATTR_WEATHER_OZONE,
    ATTR_WEATHER_PRECIPITATION_UNIT,
    ATTR_WEATHER_PRESSURE_UNIT,
    ATTR_WEATHER_TEMPERATURE_UNIT,
    ATTR_WEATHER_UV_INDEX,
    ATTR_WEATHER_VISIBILITY,
    ATTR_WEATHER_VISIBILITY_UNIT,
    ATTR_WEATHER_WIND_SPEED_UNIT,
    DOMAIN as WEATHER_DOMAIN,
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.const import (
    ATTR_SUPPORTED_FEATURES,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfLength,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util.unit_conversion import (
    DistanceConverter,
    PressureConverter,
    SpeedConverter,
    TemperatureConverter,
)

from .const import CONF_SOURCE_ENTITY
from .coordinator import NetatmoPublicConfigEntry, NetatmoPublicCoordinator
from .entity import NetatmoPublicEntity, ViewTarget, view_targets
from .logic import derive_condition, dew_point

_LOGGER = logging.getLogger(__name__)

FORECAST_FEATURES = (
    WeatherEntityFeature.FORECAST_DAILY
    | WeatherEntityFeature.FORECAST_HOURLY
    | WeatherEntityFeature.FORECAST_TWICE_DAILY
)
NATIVE_TEMP = UnitOfTemperature.CELSIUS
NATIVE_PRESSURE = UnitOfPressure.HPA
NATIVE_WIND = UnitOfSpeed.KILOMETERS_PER_HOUR
NATIVE_PRECIP = UnitOfPrecipitationDepth.MILLIMETERS
NATIVE_VISIBILITY = UnitOfLength.KILOMETERS

# Forecast keys as HA returns them (display units) -> (native key, converter, unit attr, native unit)
_FORECAST_UNITS: dict[str, tuple[str, Any, str, str]] = {
    ATTR_FORECAST_TEMP: (ATTR_FORECAST_NATIVE_TEMP, TemperatureConverter, ATTR_WEATHER_TEMPERATURE_UNIT, NATIVE_TEMP),
    ATTR_FORECAST_TEMP_LOW: (ATTR_FORECAST_NATIVE_TEMP_LOW, TemperatureConverter, ATTR_WEATHER_TEMPERATURE_UNIT, NATIVE_TEMP),
    ATTR_FORECAST_APPARENT_TEMP: (ATTR_FORECAST_NATIVE_APPARENT_TEMP, TemperatureConverter, ATTR_WEATHER_TEMPERATURE_UNIT, NATIVE_TEMP),
    ATTR_FORECAST_DEW_POINT: (ATTR_FORECAST_NATIVE_DEW_POINT, TemperatureConverter, ATTR_WEATHER_TEMPERATURE_UNIT, NATIVE_TEMP),
    ATTR_FORECAST_PRESSURE: (ATTR_FORECAST_NATIVE_PRESSURE, PressureConverter, ATTR_WEATHER_PRESSURE_UNIT, NATIVE_PRESSURE),
    ATTR_FORECAST_WIND_SPEED: (ATTR_FORECAST_NATIVE_WIND_SPEED, SpeedConverter, ATTR_WEATHER_WIND_SPEED_UNIT, NATIVE_WIND),
    ATTR_FORECAST_WIND_GUST_SPEED: (ATTR_FORECAST_NATIVE_WIND_GUST_SPEED, SpeedConverter, ATTR_WEATHER_WIND_SPEED_UNIT, NATIVE_WIND),
    ATTR_FORECAST_PRECIPITATION: (ATTR_FORECAST_NATIVE_PRECIPITATION, DistanceConverter, ATTR_WEATHER_PRECIPITATION_UNIT, NATIVE_PRECIP),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NetatmoPublicConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one weather entity per view."""
    coordinator = entry.runtime_data
    source = entry.options.get(CONF_SOURCE_ENTITY) or None
    async_add_entities(
        NetatmoPublicWeather(coordinator, target, source) for target in view_targets(coordinator)
    )


def _convert(value: Any, converter: Any, from_unit: str | None, to_unit: str) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    if not from_unit or from_unit == to_unit:
        return value
    try:
        return round(converter.convert(value, from_unit, to_unit), 2)
    except (ValueError, HomeAssistantError):
        return None


class NetatmoPublicWeather(NetatmoPublicEntity, WeatherEntity):
    """Measured weather from Netatmo, optionally completed by a source entity."""

    _attr_name = None
    _attr_native_temperature_unit = NATIVE_TEMP
    _attr_native_pressure_unit = NATIVE_PRESSURE
    _attr_native_wind_speed_unit = NATIVE_WIND
    _attr_native_precipitation_unit = NATIVE_PRECIP
    _attr_native_visibility_unit = NATIVE_VISIBILITY

    def __init__(
        self, coordinator: NetatmoPublicCoordinator, target: ViewTarget, source: str | None
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, target, "weather")
        self._source = source
        self._source_features = 0

    async def async_added_to_hass(self) -> None:
        """Follow the source entity."""
        await super().async_added_to_hass()
        if self._source:
            self._source_features = self._features_of(self._source_state())
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, [self._source], self._async_source_changed
                )
            )

    @callback
    def _async_source_changed(self, event: Event[EventStateChangedData]) -> None:
        features = self._features_of(event.data["new_state"])
        self._source_features = features
        self.async_write_ha_state()
        if features:
            self.hass.async_create_task(self.async_update_listeners(None))

    @staticmethod
    def _features_of(state: State | None) -> int:
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return 0
        return int(state.attributes.get(ATTR_SUPPORTED_FEATURES, 0)) & FORECAST_FEATURES

    def _source_state(self) -> State | None:
        if not self._source or self.hass is None:
            return None
        state = self.hass.states.get(self._source)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        return state

    def _source_attr(self, attr: str, converter: Any = None, unit_attr: str = "", native: str = "") -> Any:
        state = self._source_state()
        if state is None:
            return None
        value = state.attributes.get(attr)
        if converter is None:
            return value if isinstance(value, (int, float)) else None
        return _convert(value, converter, state.attributes.get(unit_attr), native)

    @property
    def supported_features(self) -> WeatherEntityFeature:
        """Mirror the forecast features of the source."""
        return WeatherEntityFeature(self._source_features)

    @property
    def condition(self) -> str | None:
        """Return the condition; measured rain beats the source."""
        view = self.view
        if view is None:
            return None
        state = self._source_state()
        return derive_condition(view, state.state if state else None)

    @property
    def native_temperature(self) -> float | None:
        """Return the temperature."""
        return self.view.temperature if self.view else None

    @property
    def humidity(self) -> float | None:
        """Return the humidity."""
        return self.view.humidity if self.view else None

    @property
    def native_pressure(self) -> float | None:
        """Return the pressure."""
        return self.view.pressure if self.view else None

    @property
    def native_wind_speed(self) -> float | None:
        """Return the wind speed."""
        return self.view.wind_strength if self.view else None

    @property
    def native_wind_gust_speed(self) -> float | None:
        """Return the gust speed."""
        return self.view.gust_strength if self.view else None

    @property
    def wind_bearing(self) -> float | None:
        """Return the wind bearing."""
        return self.view.wind_angle if self.view else None

    @property
    def native_dew_point(self) -> float | None:
        """Return the dew point calculated from temperature and humidity."""
        view = self.view
        return dew_point(view.temperature, view.humidity) if view else None

    @property
    def native_apparent_temperature(self) -> float | None:
        """Return the apparent temperature from the source."""
        return self._source_attr(
            ATTR_WEATHER_APPARENT_TEMPERATURE, TemperatureConverter, ATTR_WEATHER_TEMPERATURE_UNIT, NATIVE_TEMP
        )

    @property
    def native_visibility(self) -> float | None:
        """Return the visibility from the source."""
        return self._source_attr(
            ATTR_WEATHER_VISIBILITY, DistanceConverter, ATTR_WEATHER_VISIBILITY_UNIT, NATIVE_VISIBILITY
        )

    @property
    def uv_index(self) -> float | None:
        """Return the UV index from the source."""
        return self._source_attr(ATTR_WEATHER_UV_INDEX)

    @property
    def cloud_coverage(self) -> float | None:
        """Return the cloud coverage from the source."""
        return self._source_attr(ATTR_WEATHER_CLOUD_COVERAGE)

    @property
    def ozone(self) -> float | None:
        """Return the ozone level from the source."""
        return self._source_attr(ATTR_WEATHER_OZONE)

    async def _async_source_forecast(self, kind: str) -> list[Forecast] | None:
        state = self._source_state()
        if state is None:
            return None
        try:
            response = await self.hass.services.async_call(
                WEATHER_DOMAIN,
                "get_forecasts",
                {"entity_id": self._source, "type": kind},
                blocking=True,
                return_response=True,
            )
        except HomeAssistantError as err:
            _LOGGER.debug("Forecast from %s failed: %s", self._source, err)
            return None
        items = ((response or {}).get(self._source) or {}).get("forecast")
        if not isinstance(items, list):
            return None
        return [self._to_native(item, state) for item in items if isinstance(item, dict)]

    @staticmethod
    def _to_native(item: dict[str, Any], state: State) -> Forecast:
        """Convert a forecast in the source's display units back to native units."""
        out: dict[str, Any] = {}
        for key, value in item.items():
            mapping = _FORECAST_UNITS.get(key)
            if mapping is None:
                out[key] = value
                continue
            native_key, converter, unit_attr, native_unit = mapping
            out[native_key] = _convert(value, converter, state.attributes.get(unit_attr), native_unit)
        return Forecast(**out)  # type: ignore[typeddict-item]

    async def async_forecast_daily(self) -> list[Forecast] | None:
        """Return the daily forecast of the source."""
        return await self._async_source_forecast("daily")

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        """Return the hourly forecast of the source."""
        return await self._async_source_forecast("hourly")

    async def async_forecast_twice_daily(self) -> list[Forecast] | None:
        """Return the twice-daily forecast of the source."""
        return await self._async_source_forecast("twice_daily")
