# Netatmo Public Weather Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A HACS-installable Home Assistant custom integration that turns 1 to 3 public Netatmo stations near the user into the following entities:
- weather entities and sensors per station;
- a primary-with-fallback set;
- an average set;
- optionally, condition and forecast taken from an existing weather entity.

**Architecture:** The code has three layers.
- **Pure-Python core:** parsing, geometry, health, failover and aggregation. It has no HA imports and is unit tested in isolation.
- **Coordinator:** one per config entry. It makes the OAuth `getpublicdata` calls and builds an immutable snapshot of "views" (`station:<id>`, `primary`, `average`).
- **Entities:** they only read a view.

The config flow uses HA's `application_credentials` and `AbstractOAuth2FlowHandler`.

**Tech Stack:**
- Python 3.14, Home Assistant ≥ 2025.1;
- `aiohttp` through `config_entry_oauth2_flow.OAuth2Session`;
- tests with `pytest-homeassistant-custom-component==0.13.375` in the Docker image `npw-test` (`.devcontainer-test/Dockerfile`).

**Spec:** `docs/superpowers/specs/2026-11-08-netatmo-public-weather-design.md`

Run tests with:
```
docker run --rm -v /root/homelab/netatmo-public-weather:/work npw-test pytest -q
```

## Global Constraints

- Domain `netatmo_public_weather`, name "Netatmo Public Weather", license MIT, `"homeassistant": "2025.1.0"` in hacs.json.
- Netatmo endpoints:
  - authorize `https://api.netatmo.com/oauth2/authorize`;
  - token `https://api.netatmo.com/oauth2/token`;
  - data `https://api.netatmo.com/api/getpublicdata`.
- Scope `read_station`.
- No third-party requirements in manifest.json (`"requirements": []`).
- 1 to 3 stations per entry, with priority order.
- Defaults: radius 3 km (0.5 to 20), update interval 10 min (5 to 60), stale threshold 30 min (15 to 120), station list capped at 20.
- On a rate limit the interval grows by exponential backoff, capped at 60 min.
- Failback to a higher-priority station needs 2 consecutive healthy polls.
- Average entity:
  - temperature, humidity and pressure use the mean;
  - wind, gust, rain_live, rain_60min and rain_24h use the maximum;
  - the angles come from the station with the maximum gust. If no station reports gust, they come from the station with the maximum wind.
- Weather entity without a source:
  - `rainy` if rain_live > 0;
  - else `windy` if wind ≥ 39 km/h or gust ≥ 50 km/h;
  - else `None`.
- Weather entity with a source:
  - the condition comes from the source;
  - if rain_live > 0 and the source condition is not in {rainy, pouring, lightning-rainy, snowy, snowy-rainy}, the condition becomes `rainy`.
- Native units: °C, %, hPa, km/h, mm, mm/h. HA converts them to the user's unit system.
- Unhealthy data is shown as `unavailable`, never as stale values.
- Generic code: no hard-coded locations or providers. All UI strings go through `strings.json`, with `translations/en.json` and `translations/de.json`.
- Docs are English. The README carries a prominent "not a storm guard" warning.
- Repair issue `station_gone_<id>` when a station has been absent for 7 days.

## Review Focus

1. **A station in the response without one of its modules** (for example the wind module disappears) → the station is unhealthy, primary fails over. Covered by a test in Task 3.
2. **A clock or timestamp in the future, or a missing `res`** → it must not crash. A future timestamp counts as fresh, a missing `res` counts as stale. Test in Task 2.
3. **The source weather entity is deleted, unavailable, or does not support forecasts** → the weather entity stays available without a forecast, and `async_forecast_daily` returns `None`. Test in Task 7.
4. **Netatmo returns `{"error": {...}}` with HTTP 200 or 403** (token revoked) → ConfigEntryAuthFailed starts reauth. Test in Task 4.
5. **An empty search result in the config flow** → the form shows the error `no_stations` and lets the user enlarge the radius. Test in Task 6.

---

### Task 1: Scaffolding, geometry and CI skeleton

**Files:**
- Create:
  - `custom_components/netatmo_public_weather/{__init__.py,manifest.json,const.py,geo.py}`;
  - `hacs.json`, `LICENSE`, `.gitignore`, `pyproject.toml` (pytest config: `asyncio_mode = "auto"`, `testpaths = ["tests"]`);
  - `tests/__init__.py`, `tests/conftest.py` (fixture `auto_enable_custom_integrations` autouse).
- Test: `tests/test_geo.py`

**Interfaces:**
- Produces in `geo.py`:
  - `haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float`
  - `BBox = NamedTuple("BBox", lat_ne, lon_ne, lat_sw, lon_sw)`
  - `bbox_from_radius(lat: float, lon: float, radius_km: float) -> BBox`
  - `bbox_around(points: list[tuple[float, float]], margin_km: float = 0.3) -> BBox`
- Produces in `const.py`: `DOMAIN`, `CONF_STATIONS` (an ordered list of dicts `{id, lat, lon, name, modules}`), `CONF_SOURCE_ENTITY`, `CONF_UPDATE_INTERVAL`, `CONF_STALE_MINUTES`, `CONF_RADIUS_KM`, and the defaults listed above.

Steps:
- [ ] Write the tests:
  - `haversine_km(52.28, 7.44, 52.29, 7.44)` ≈ 1.11 (abs 0.01);
  - `bbox_from_radius(52.0, 7.0, 3)` contains points 2.9 km north, south, east and west, and excludes points at 3.5 km;
  - `bbox_around([(52.0, 7.0), (52.01, 7.02)], 0.3)` has `lat_ne > 52.01` and `lon_sw < 7.0`.
- [ ] Run them and see them fail. Implement. Run them and see them pass.
- [ ] Commit `chore: scaffold integration and geo helpers`.

### Task 2: Parsing the Netatmo response

**Files:** Create `custom_components/netatmo_public_weather/model.py`. Test: `tests/test_model.py` with `tests/fixtures/getpublicdata.json`. The fixture is pyatmo's fixture, trimmed to 3 stations: one with base and rain, one with base and wind, one with all three. Add `place.city` and `place.street` to one station.

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class WeatherValues:
      temperature: float|None; humidity: float|None; pressure: float|None
      rain_live: float|None; rain_60min: float|None; rain_24h: float|None
      wind_strength: float|None; wind_angle: float|None
      gust_strength: float|None; gust_angle: float|None
  @dataclass(frozen=True)
  class StationData:
      station_id: str; lat: float; lon: float; altitude: int|None
      city: str|None; street: str|None
      modules: frozenset[str]            # subset of {"base","rain","wind"}
      timestamps: dict[str, datetime]    # module -> newest measurement (UTC)
      values: WeatherValues
  def parse_public_data(body: list[dict]) -> dict[str, StationData]
  def station_label(s: StationData, home: tuple[float,float]|None) -> str
  ```
- Parsing rules:
  - base temperature and humidity come from the measure whose `type` contains "temperature";
  - pressure comes from the one whose `type` contains "pressure";
  - the newest key in `res` is used, and the base timestamp is the newer of the two;
  - rain comes from the keys `rain_*`, with the timestamp from `rain_timeutc`;
  - wind comes from `wind_*` and `gust_*`, with the timestamp from `wind_timeutc`.
- `station_label` returns `"<street>, <city> · 0.8 km"`, and falls back to `"Station <last 8 chars of id>"` without a place.

Steps:
- [ ] Write the tests:
  - all 3 fixture stations are parsed with the correct `modules` sets;
  - the station with all modules has `values.gust_strength == 31` and `timestamps["wind"] == datetime.fromtimestamp(1560248190, UTC)`;
  - a station whose temperature measure has an empty `res` gets temperature `None` and no `"base"` timestamp, while its modules still include `"base"`, so it will be stale (Review Focus 2);
  - an unknown measure layout is skipped without raising;
  - `station_label` covers both forms.
- [ ] Fail, implement, pass, commit `feat: parse getpublicdata response`.

### Task 3: Health, failover and aggregation (pure core)

**Files:** Create `custom_components/netatmo_public_weather/logic.py`. Test: `tests/test_logic.py`.

**Interfaces:**
- Consumes: `StationData` and `WeatherValues` (Task 2).
- Produces:
  ```python
  def is_healthy(data: StationData|None, expected_modules: frozenset[str], now: datetime, stale_after: timedelta) -> bool
  class FailoverSelector:
      def __init__(self, count: int, failback_polls: int = 2) -> None
      def update(self, healthy: list[bool]) -> int|None   # index of active station or None
      active: int|None
  def aggregate(values: list[WeatherValues]) -> WeatherValues
  def derive_condition(v: WeatherValues, source_condition: str|None) -> str|None
  def dew_point(temp_c: float|None, humidity: float|None) -> float|None   # Magnus a=17.62 b=243.12
  ```
- Health rule: the data is present, every module in `expected_modules` is present, and each one has a timestamp with `now - ts <= stale_after`. A future timestamp counts as fresh.
- `FailoverSelector` rules:
  - If the active station is unhealthy, switch immediately to the first healthy station by index.
  - Move to a better (lower) index only after it has been healthy for `failback_polls` consecutive updates.
  - The first update picks the first healthy station immediately.
  - If no station is healthy, return `None`.

Steps:
- [ ] Write the tests:
  - `is_healthy`: fresh → True; one module older than 30 min → False; an expected module missing in the data (Review Focus 1) → False; `None` → False; a future timestamp → True.
  - `FailoverSelector(3)`:
    - `[T,T,T]` → 0;
    - then `[F,T,T]` → 1;
    - then `[T,T,T]` → 1 (first good poll);
    - then `[T,T,T]` → 0;
    - `[F,F,F]` → None;
    - `[F,F,T]` from None → 2.
  - `aggregate`:
    - temperatures 10, 12, None → 11.0;
    - wind 10, 30 with gusts 20, 45 → wind 30, gust 45, angles from the gust-45 station;
    - rain_24h 0.2, 1.4 → 1.4;
    - all None → None;
    - empty list → all None.
  - `derive_condition`:
    - rain 0.3 with source "sunny" → "rainy";
    - rain 0.3 with source "pouring" → "pouring";
    - rain 0 with source "cloudy" → "cloudy";
    - no source: wind 40 → "windy"; gust 50 → "windy"; calm → None; rain 0.1 → "rainy".
  - `dew_point(20, 50)` ≈ 9.3 (abs 0.1).
- [ ] Fail, implement, pass, commit `feat: health, failover and aggregation logic`.

### Task 4: API client and coordinator

**Files:** Create `custom_components/netatmo_public_weather/{api.py,coordinator.py}`. Test: `tests/test_coordinator.py` (uses `aioclient_mock`).

**Interfaces:**
- `api.py`:
  ```python
  class NetatmoAuthError(Exception); class NetatmoRateLimitError(Exception); class NetatmoApiError(Exception)
  class NetatmoPublicClient:
      def __init__(self, session: OAuth2Session) -> None
      async def async_get_public_data(self, bbox: BBox) -> list[dict]
  ```
  - It sends a POST with form params, `filter=false`, and `Authorization: Bearer` from `await session.async_ensure_token_valid()` and `session.token["access_token"]`.
  - Error mapping:
    - HTTP 401/403, or an error code in {2, 3, 13, 26} → `NetatmoAuthError`;
    - HTTP 429, or error code 26 with "rate" in the message, or error code 20 → `NetatmoRateLimitError`;
    - anything else that is not ok → `NetatmoApiError`.
  - The body is in `body`.
- `coordinator.py`:
  ```python
  @dataclass(frozen=True)
  class Snapshot:
      stations: dict[str, StationData|None]   # keyed by configured id, ordered by priority
      healthy: dict[str, bool]
      views: dict[str, WeatherValues|None]    # "station:<id>", "primary", "average"
      active_station: str|None
      used_stations: list[str]
      fetched_at: datetime
  class NetatmoPublicCoordinator(DataUpdateCoordinator[Snapshot]):
      def __init__(self, hass, entry, client: NetatmoPublicClient) -> None
  ```
- Coordinator behaviour:
  - Each update makes one call with `bbox_around` the configured stations. For each configured station that is missing from the result, it makes one more call with `bbox_around([that station], 0.2)`.
  - `expected_modules` comes from the stored `modules` of each configured station.
  - On a rate limit it raises `UpdateFailed` and sets `self.update_interval` to `min(current*2, 60 min)`. After a successful update it resets the interval to the configured one.
  - `NetatmoAuthError` → `ConfigEntryAuthFailed`.
  - It tracks `last_seen` per station in `entry` runtime data. When a station has been absent for 7 days or more, it creates the repair issue `station_gone_<id>` (via `ir.async_create_issue`, not fixable, severity warning). The issue is deleted when the station is seen again.
  - The `average` view is computed only from healthy stations, and only when there are 2 or more configured stations.

Steps:
- [ ] Write the tests:
  - 3 configured stations all present → `views["primary"] == views["station:<first>"]`, `used_stations` has 3 entries;
  - the first station's wind timestamp older than 30 min → `active_station` is the second, and `views["station:<first>"] is None`;
  - a station missing from the bbox call triggers exactly one extra request with a small bbox;
  - HTTP 429 → `UpdateFailed` and `update_interval == 20 min` (from 10);
  - a 403 body `{"error":{"code":3,"message":"Access token expired"}}` → `ConfigEntryAuthFailed` (Review Focus 4);
  - absent ≥ 7 days → the issue exists.
- [ ] Fail, implement, pass, commit `feat: api client and coordinator`.

### Task 5: Entities (sensor, binary_sensor, weather) and setup

**Files:** Create `custom_components/netatmo_public_weather/{entity.py,sensor.py,binary_sensor.py,weather.py,diagnostics.py}`. Modify `__init__.py` (`async_setup_entry`, `async_unload_entry`, update listener → reload). Test: `tests/test_entities.py` and `tests/test_weather.py`.

**Interfaces:**
- Consumes: `Snapshot` and `NetatmoPublicCoordinator` (Task 4); `derive_condition` and `dew_point` (Task 3).
- `entity.py`: `NetatmoPublicEntity(CoordinatorEntity)` with `view_key: str`.
  - Device identifiers: `(DOMAIN, "<station_id>")` for station views, `(DOMAIN, f"{entry_id}_primary")` and `(DOMAIN, f"{entry_id}_average")`.
  - `available` = the coordinator is ok and `views[view_key] is not None`.
  - `has_entity_name = True`, unique_id `f"{device_id}_{key}"`. Unique ids are based on the station MAC, so they stay stable across option changes.
- `sensor.py` keys: `temperature, humidity, pressure, rain_live, rain_60min, rain_24h, wind_strength, wind_angle, gust_strength, gust_angle`.
  - A sensor is created only when its module exists. For primary and average it is created when any configured station has the module.
  - Device classes: `temperature`, `humidity`, `atmospheric_pressure`, `precipitation_intensity` (rain_live, mm/h), `precipitation` (rain_60min and rain_24h, mm), `wind_speed` (km/h), `wind_direction` (°, state_class `measurement_angle` if HA has it, else `None`).
  - Extra sensors: `active_station` on primary (attributes `station_id`, `priority`) and `stations_used` on average (attribute `stations`).
- `binary_sensor.py`: `healthy` (device class `connectivity`) on the station devices and on primary. This entity stays available when the data is not.
- `weather.py`: `NetatmoPublicWeather(NetatmoPublicEntity, WeatherEntity)`.
  - It sets the native values from the view, plus `native_dew_point`.
  - If `CONF_SOURCE_ENTITY` is set, it tracks the source with `async_track_state_change_event`. On each change it writes the state, and if the source's `supported_features` changed, it calls `async_update_listeners(None)`.
  - `supported_features` = the source state's `supported_features & (FORECAST_DAILY|FORECAST_HOURLY|FORECAST_TWICE_DAILY)`, or 0.
  - `async_forecast_daily`, `async_forecast_hourly` and `async_forecast_twice_daily` call `weather.get_forecasts` with `return_response=True` on the source. They return the list, or `None` on any error or a missing source.
  - `condition` = `derive_condition(view, source_state or None)`.
  - `uv_index`, `cloud_coverage`, `native_apparent_temperature`, `native_visibility` and `ozone` come from the source attributes when present. The source attributes are in the source's units; the source's unit attributes are passed through as the native units.
- `diagnostics.py`: entry options, snapshot (dataclasses asdict), last raw body. `async_redact_data` redacts `token`, `access_token`, `refresh_token`.

Steps:
- [ ] Write the tests:
  - setting up an entry with 2 stations (mocked client) creates `weather.*` for station 1, station 2, primary and average, and `sensor.*_gust_strength` only where wind exists;
  - after failover the primary temperature equals station 2;
  - a stale station's entities are `unavailable` and its `healthy` binary sensor is `off`;
  - weather with source `weather.src` (a template or demo-like state with `supported_features=1`): the condition follows the source; `weather.get_forecasts` on our entity returns the source's forecast;
  - the source is removed → the entity stays available and the forecast response is empty or `None` (Review Focus 3);
  - diagnostics contain no `access_token`.
- [ ] Fail, implement, pass, commit `feat: weather, sensor and binary sensor entities`.

### Task 6: Config flow, options flow, application credentials, translations

**Files:** Create `custom_components/netatmo_public_weather/{application_credentials.py,config_flow.py,strings.json,translations/en.json,translations/de.json}`. Test: `tests/test_config_flow.py`.

**Interfaces:**
- `application_credentials.py`: `async_get_authorization_server(hass) -> AuthorizationServer` with the URLs from Global Constraints.
- `config_flow.py`: `OAuth2FlowHandler(AbstractOAuth2FlowHandler, domain=DOMAIN)`.
  - `extra_authorize_data = {"scope": "read_station"}`.
  - Steps after OAuth:
    - `async_oauth_create_entry` → step `area`: location selector (default HA home) and radius number (default 3).
    - Step `stations`: a multi-select of up to 20 labels sorted by distance, plus an optional text field `manual_ids` (comma-separated MACs). It validates 1 to 3 selections. An empty result → error `no_stations` back on `area` (Review Focus 5).
    - Step `order`, only when 2 or more stations: selects `primary`, `fallback_1` and `fallback_2` from the chosen ones, all distinct. It shows the description placeholder warning `primary_missing_modules` when the primary lacks rain or wind.
    - Step `options`: entity selector for the source (domain weather, optional), interval, stale threshold.
    - The entry is created with `data` = token plus `CONF_STATIONS`, and `options` = the source, interval and stale threshold. Title: `f"Netatmo {label of primary without distance}"`.
  - The flow client needs a temporary `OAuth2Session`-like token holder. It uses `self.flow_impl` and the token from `data["token"]` directly as the bearer, because the token is fresh.
  - Reauth: `async_step_reauth` → `reauth_confirm` → OAuth, then `async_update_reload_and_abort`.
  - `OptionsFlow`: the same `area` → `stations` → `order` → `options` sequence. It stores stations in `options[CONF_STATIONS]`, and the coordinator prefers options over data.
  - Unique id: none. Several entries are allowed.
- Translations: English is the source, German is complete. Error keys: `no_stations`, `too_many`, `too_few`, `duplicate_order`, `invalid_id`.

Steps:
- [ ] Write the tests:
  - full flow: credentials → OAuth callback (standard `hass_client_no_auth` pattern from the HA OAuth tests) → area → stations (2 picked) → order → options → entry created with 2 stations in order;
  - 0 stations returned → `errors == {"base": "no_stations"}`;
  - 4 picked → `too_many`;
  - options flow swaps the order → entry reloaded and primary changed;
  - reauth updates the token.
- [ ] Fail, implement, pass, commit `feat: config, options and reauth flow`.

### Task 7: Documentation, CI and release

**Files:** Create:
- `README.md`;
- `docs/netatmo-app.md`, `docs/entities.md`, `docs/failover.md` (with a Mermaid diagram), `docs/faq.md`;
- `.github/workflows/validate.yml` (hassfest, `hacs/action` with category integration) and `.github/workflows/tests.yml` (Python 3.14, `pip install -r requirements_test.txt`, `pytest`).

Remove `.devcontainer-test` from the published tree only if it confuses HACS; it does not, so keep it and document it in CONTRIBUTING notes in the README.

- [ ] Write the README:
  - what the integration does and why (neutral, not tied to any location);
  - feature list;
  - the "⚠️ Not a storm guard" block;
  - installation through HACS (custom repository) and manually;
  - quick start in 5 steps;
  - links to the docs.
- [ ] Write `netatmo-app.md`:
  - dev.netatmo.com → My apps → Create;
  - which fields to fill: name, description, data protection officer name and email (required by Netatmo);
  - redirect URI `https://my.home-assistant.io/redirect/oauth`;
  - where to copy the client ID and secret;
  - where to enter them in HA (Settings → Devices & services → Add integration, or Application credentials).
- [ ] Write `entities.md` (the table of devices and entities, units, when an entity is unavailable), `failover.md` (health rule, failover and failback rule, average rules, condition rules) and `faq.md` (no stations found, 429, reauth, a station removed, renaming entities, migrating from nfws).
- [ ] Run hassfest locally:
  ```
  docker run --rm -v $PWD:/github/workspace ghcr.io/home-assistant/hassfest
  ```
  Expected: no errors.
- [ ] Run the full test suite. Expected: all pass.
- [ ] Commit `docs: user documentation and CI`. Tag `v0.1.0`. Push to Gitea. The GitHub mirror is set up once Andreas names the repository.
