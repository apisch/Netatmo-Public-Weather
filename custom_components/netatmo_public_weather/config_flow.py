"""Config and options flow for Netatmo Public Weather."""

from __future__ import annotations

from collections.abc import Mapping
import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigEntry,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    LocationSelector,
    LocationSelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)
from homeassistant.util import dt as dt_util

from .api import NetatmoApiError, NetatmoPublicClient
from .const import (
    CONF_RADIUS_KM,
    CONF_SOURCE_ENTITY,
    CONF_STALE_MINUTES,
    CONF_STATIONS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_RADIUS_KM,
    DEFAULT_STALE_MINUTES,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_LISTED_STATIONS,
    MAX_RADIUS_KM,
    MAX_STALE_MINUTES,
    MAX_STATIONS,
    MAX_UPDATE_INTERVAL,
    MIN_RADIUS_KM,
    MIN_STALE_MINUTES,
    MIN_STATIONS,
    MIN_UPDATE_INTERVAL,
    MODULE_RAIN,
    MODULE_WIND,
    SCOPE,
)
from .geo import bbox_from_radius, haversine_km
from .model import StationData, parse_public_data, place_name, station_label

_LOGGER = logging.getLogger(__name__)

CONF_LOCATION = "location"
CONF_MANUAL_IDS = "manual_ids"
ORDER_FIELDS = ("primary", "fallback_1", "fallback_2")
MAC_RE = re.compile(r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$")
MANUAL_SEARCH_FACTOR = 3
MANUAL_SEARCH_MAX_KM = 50.0


def _picker_label(station: StationData, home: tuple[float, float]) -> str:
    """Return e.g. 'Main St, Town · 0.8 km · 🌡 🌧 💨 · 4 min'."""
    icons = "🌡"
    if MODULE_RAIN in station.modules:
        icons += " 🌧"
    if MODULE_WIND in station.modules:
        icons += " 💨"
    label = f"{station_label(station, home)} · {icons}"
    if station.timestamps:
        age = dt_util.utcnow() - max(station.timestamps.values())
        label += f" · {max(int(age.total_seconds() // 60), 0)} min"
    return label


def _station_dict(station: StationData) -> dict[str, Any]:
    return {
        "id": station.station_id,
        "lat": station.lat,
        "lon": station.lon,
        "name": place_name(station),
        "modules": sorted(station.modules),
    }


class StationPickerMixin:
    """Steps shared by the config flow and the options flow."""

    hass: HomeAssistant
    _client: NetatmoPublicClient
    _home: tuple[float, float]
    _radius: float
    _found: dict[str, StationData]
    _chosen: list[str]
    _order_warned: bool = False

    # Hooks the flow classes provide.
    def _defaults(self) -> dict[str, Any]:
        raise NotImplementedError

    async def _async_finish(
        self, stations: list[dict[str, Any]], settings: dict[str, Any]
    ) -> ConfigFlowResult:
        raise NotImplementedError

    async def async_step_area(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask where to search."""
        errors: dict[str, str] = {}
        if user_input is not None:
            loc = user_input[CONF_LOCATION]
            self._home = (float(loc["latitude"]), float(loc["longitude"]))
            self._radius = float(user_input[CONF_RADIUS_KM])
            try:
                self._found = await self._async_search(self._home, self._radius)
            except NetatmoApiError as err:
                _LOGGER.warning("Station search failed: %s", err)
                errors["base"] = "cannot_connect"
            else:
                if self._found:
                    return await self.async_step_stations()
                errors["base"] = "no_stations"

        home = getattr(self, "_home", (self.hass.config.latitude, self.hass.config.longitude))
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_LOCATION, default={"latitude": home[0], "longitude": home[1]}
                ): LocationSelector(LocationSelectorConfig(radius=False)),
                vol.Required(
                    CONF_RADIUS_KM, default=getattr(self, "_radius", DEFAULT_RADIUS_KM)
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_RADIUS_KM, max=MAX_RADIUS_KM, step=0.5, mode=NumberSelectorMode.BOX,
                        unit_of_measurement="km",
                    )
                ),
            }
        )
        return self.async_show_form(step_id="area", data_schema=schema, errors=errors)  # type: ignore[attr-defined]

    async def _async_search(
        self, home: tuple[float, float], radius: float
    ) -> dict[str, StationData]:
        body = await self._client.async_get_public_data(bbox_from_radius(*home, radius))
        stations = [
            s
            for s in parse_public_data(body).values()
            if haversine_km(home[0], home[1], s.lat, s.lon) <= radius
        ]
        stations.sort(key=lambda s: haversine_km(home[0], home[1], s.lat, s.lon))
        return {s.station_id: s for s in stations[:MAX_LISTED_STATIONS]}

    async def async_step_stations(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick 1 to 3 stations."""
        errors: dict[str, str] = {}
        if user_input is not None:
            chosen: list[str] = list(user_input.get(CONF_STATIONS, []))
            manual = [
                x.strip().lower()
                for x in (user_input.get(CONF_MANUAL_IDS) or "").split(",")
                if x.strip()
            ]
            if manual:
                errors.update(await self._async_add_manual(manual, chosen))
            if not errors:
                if len(chosen) < MIN_STATIONS:
                    errors["base"] = "too_few"
                elif len(chosen) > MAX_STATIONS:
                    errors["base"] = "too_many"
                else:
                    self._chosen = chosen
                    self._order_warned = False
                    if len(chosen) == 1:
                        return await self.async_step_settings()
                    return await self.async_step_order()

        options = [
            SelectOptionDict(value=sid, label=_picker_label(s, self._home))
            for sid, s in self._found.items()
        ]
        current = [sid for sid in self._defaults().get(CONF_STATIONS, []) if sid in self._found]
        schema = vol.Schema(
            {
                vol.Optional(CONF_STATIONS, default=current): SelectSelector(
                    SelectSelectorConfig(
                        options=options, multiple=True, mode=SelectSelectorMode.LIST
                    )
                ),
                vol.Optional(CONF_MANUAL_IDS): TextSelector(),
            }
        )
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id="stations",
            data_schema=schema,
            errors=errors,
            description_placeholders={"count": str(len(self._found))},
        )

    async def _async_add_manual(self, manual: list[str], chosen: list[str]) -> dict[str, str]:
        if any(not MAC_RE.match(m) for m in manual):
            return {CONF_MANUAL_IDS: "invalid_id"}
        missing = [m for m in manual if m not in self._found]
        if missing:
            radius = min(self._radius * MANUAL_SEARCH_FACTOR, MANUAL_SEARCH_MAX_KM)
            try:
                body = await self._client.async_get_public_data(
                    bbox_from_radius(*self._home, radius)
                )
            except NetatmoApiError:
                return {"base": "cannot_connect"}
            wide = parse_public_data(body)
            for m in missing:
                if m not in wide:
                    return {CONF_MANUAL_IDS: "invalid_id"}
                self._found[m] = wide[m]
        for m in manual:
            if m not in chosen:
                chosen.append(m)
        return {}

    async def async_step_order(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Let the user set the priority of 2 or 3 stations."""
        fields = ORDER_FIELDS[: len(self._chosen)]
        errors: dict[str, str] = {}
        defaults = dict(zip(fields, self._chosen, strict=False))
        if user_input is not None:
            ordered = [user_input[f] for f in fields]
            defaults = dict(zip(fields, ordered, strict=False))
            primary = self._found[ordered[0]]
            if len(set(ordered)) != len(ordered):
                errors["base"] = "duplicate_order"
            elif not self._order_warned and not {MODULE_RAIN, MODULE_WIND} <= primary.modules:
                self._order_warned = True
                errors["base"] = "primary_missing_modules"
            else:
                self._chosen = ordered
                return await self.async_step_settings()

        options = [
            SelectOptionDict(value=sid, label=_picker_label(self._found[sid], self._home))
            for sid in self._chosen
        ]
        selector = SelectSelector(
            SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
        )
        schema = vol.Schema({vol.Required(f, default=defaults[f]): selector for f in fields})
        return self.async_show_form(step_id="order", data_schema=schema, errors=errors)  # type: ignore[attr-defined]

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the optional source entity and timing."""
        if user_input is not None:
            settings: dict[str, Any] = {
                CONF_UPDATE_INTERVAL: int(user_input[CONF_UPDATE_INTERVAL]),
                CONF_STALE_MINUTES: int(user_input[CONF_STALE_MINUTES]),
                CONF_RADIUS_KM: self._radius,
            }
            if user_input.get(CONF_SOURCE_ENTITY):
                settings[CONF_SOURCE_ENTITY] = user_input[CONF_SOURCE_ENTITY]
            stations = [_station_dict(self._found[sid]) for sid in self._chosen]
            return await self._async_finish(stations, settings)

        defaults = self._defaults()
        source_key = (
            vol.Optional(CONF_SOURCE_ENTITY, default=defaults[CONF_SOURCE_ENTITY])
            if defaults.get(CONF_SOURCE_ENTITY)
            else vol.Optional(CONF_SOURCE_ENTITY)
        )
        schema = vol.Schema(
            {
                source_key: EntitySelector(EntitySelectorConfig(domain="weather")),
                vol.Required(
                    CONF_UPDATE_INTERVAL,
                    default=defaults.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_UPDATE_INTERVAL, max=MAX_UPDATE_INTERVAL, step=1,
                        mode=NumberSelectorMode.BOX, unit_of_measurement="min",
                    )
                ),
                vol.Required(
                    CONF_STALE_MINUTES,
                    default=defaults.get(CONF_STALE_MINUTES, DEFAULT_STALE_MINUTES),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_STALE_MINUTES, max=MAX_STALE_MINUTES, step=1,
                        mode=NumberSelectorMode.BOX, unit_of_measurement="min",
                    )
                ),
            }
        )
        return self.async_show_form(step_id="settings", data_schema=schema)  # type: ignore[attr-defined]


class OAuth2FlowHandler(
    StationPickerMixin, config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Handle the Netatmo OAuth2 login and the station selection."""

    DOMAIN = DOMAIN
    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        super().__init__()
        self._oauth_data: dict[str, Any] = {}

    @property
    def logger(self) -> logging.Logger:
        """Return the logger."""
        return _LOGGER

    @property
    def extra_authorize_data(self) -> dict[str, Any]:
        """Request the weather station scope."""
        return {"scope": SCOPE}

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Start re-authentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm re-authentication."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        return await self.async_step_user()

    async def async_oauth_create_entry(self, data: dict[str, Any]) -> ConfigFlowResult:
        """Continue after a successful login."""
        if self.source == SOURCE_REAUTH:
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(), data_updates=data
            )
        self._oauth_data = data
        token = data["token"]["access_token"]

        async def _token() -> str:
            return token

        self._client = NetatmoPublicClient(async_get_clientsession(self.hass), _token)
        return await self.async_step_area()

    def _defaults(self) -> dict[str, Any]:
        return {}

    async def _async_finish(
        self, stations: list[dict[str, Any]], settings: dict[str, Any]
    ) -> ConfigFlowResult:
        return self.async_create_entry(
            title=f"Netatmo {stations[0]['name']}",
            data={**self._oauth_data, CONF_STATIONS: stations},
            options=settings,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return NetatmoPublicOptionsFlow()


class NetatmoPublicOptionsFlow(StationPickerMixin, OptionsFlow):
    """Change stations, order, source and timing without re-adding."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Start with the search area."""
        coordinator = getattr(self.config_entry, "runtime_data", None)
        if coordinator is None:
            return self.async_abort(reason="not_loaded")
        self._client = coordinator.client
        stations = coordinator.stations
        if stations:
            self._home = (
                sum(s.lat for s in stations) / len(stations),
                sum(s.lon for s in stations) / len(stations),
            )
        self._radius = float(self.config_entry.options.get(CONF_RADIUS_KM, DEFAULT_RADIUS_KM))
        return await self.async_step_area()

    def _defaults(self) -> dict[str, Any]:
        opts = dict(self.config_entry.options)
        opts[CONF_STATIONS] = [s.id for s in self.config_entry.runtime_data.stations]
        return opts

    async def _async_finish(
        self, stations: list[dict[str, Any]], settings: dict[str, Any]
    ) -> ConfigFlowResult:
        return self.async_create_entry(data={**settings, CONF_STATIONS: stations})
