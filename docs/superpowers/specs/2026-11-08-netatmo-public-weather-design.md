# Netatmo Public Weather – Design

Date: 2026-11-08
Status: draft, awaiting approval

## 1. Intent

Andreas has no weather station of his own. He wants local weather in Home Assistant from public Netatmo stations in his neighbourhood. He uses it for two things:

1. To know the current local weather (dashboard).
2. To drive the awning (Markise) automations: wind, gusts, rain.

Today he uses the add-on `nfws` (GiZMoSK1221/hass-addons). It reads Netatmo favourites and creates plain sensors. He wants a native Home Assistant custom integration instead. It must be simple to set up and well documented. The documentation is in English so other people can use it.

Because the awning depends on it, **wrong or stale values are worse than no values**. A dead station must never look alive.

## 2. Goals

- G1: The integration is installable through HACS from a GitHub repository. The GitHub repository is a mirror of the Gitea repository.
- G2: Setup happens in the UI only, without YAML. It has three parts:
  - the Netatmo OAuth login;
  - a list of public stations near the HA home location, with distance, available modules and last-seen time;
  - picking 1 to 3 stations in priority order.
- G3: Every selected station gets its own **weather entity** and its own sensors (requirement b).
- G4: The **primary-with-fallback** weather entity shows the values of the first healthy station in priority order. If the primary station is unhealthy, **all** values come from the next healthy station, never mixed per value (requirement a).
- G5: The **aggregated** weather entity combines all healthy stations (requirement c):
  - temperature, humidity and pressure are averaged;
  - for wind, gusts and rain the maximum is used (see 6.4).
- G6: Optionally, a weather entity that already exists in HA (for example Met.no or DWD) is chosen as the **source for missing data**. From that source the integration takes condition, forecasts and the attributes Netatmo cannot measure.
- G7: Polling stays far below the Netatmo rate limits. The default interval is 10 minutes, configurable from 5 to 60 minutes.
- G8: The English documentation covers the following:
  - creating the Netatmo developer app, step by step;
  - installation and configuration;
  - what each entity means;
  - how failover works;
  - limitations: this is not a storm guard;
  - troubleshooting.

## 3. Non-goals

- Netatmo favourites (the `get_favorites` API) are not used. Stations are picked in the integration.
- A user's own Netatmo hardware is out of scope; the core `netatmo` integration covers it.
- The integration creates no forecasts of its own and does no weather modelling.
- Migration of nfws entities, automations or dashboards is not part of this repository. It is done separately in Andreas' HA afterwards.
- No more than 3 stations per configuration entry. Several configuration entries are allowed.

## 4. Anti-goals

These would count as failure even if the code otherwise works.

- A station that stopped reporting keeps showing its last values as if they were current.
- The fallback entity mixes values from two stations.
- The integration triggers Netatmo `429` errors or a token lockout for the user's account.
- Setup requires editing YAML or copying tokens by hand.
- The documentation suggests the integration is a safe storm protection for awnings.

## 5. Constraints

- **Netatmo API.**
  - It uses OAuth2 with authorization code. The access token lives about 3 h, and the refresh token **rotates on every refresh**.
  - Rate limits per user: 50 requests per 10 s and 500 per hour. Per app with fewer than 100 users: 2000 per hour.
  - Public station data comes from `GET/POST https://api.netatmo.com/api/getpublicdata` with the parameters `lat_ne`, `lon_ne`, `lat_sw`, `lon_sw`, optionally `required_data` and `filter`.
  - The scope needed is `read_station`. The builder must verify this against the live API.
- **Home Assistant.**
  - The integration uses `application_credentials` and `config_entry_oauth2_flow`, so HA stores and rotates the tokens.
  - A reauth flow covers revoked tokens.
  - The minimum HA version is 2025.1 (builder's call, see 9.)
  - The integration must pass `hassfest` and the HACS validation action.
- **Domain name.** The domain must not collide with core `netatmo`. Domain: `netatmo_public_weather`. Display name: "Netatmo Public Weather".
- **Redirect URI.** The Netatmo app must allow `https://my.home-assistant.io/redirect/oauth`. This is the standard HA flow.
- **The integration is generic.** It is meant for anyone, not only for Andreas' setup. Concretely:
  - Nothing in the code or the defaults refers to a country, a city or a specific weather provider.
  - The source entity is any `weather` entity the user has, or none.
  - The integration reports native metric units. HA converts them to the user's unit system, so imperial users see °F and mph without extra code.
  - Each config entry is one independent "neighbourhood". Several entries can share one Netatmo login, for example for a home and a holiday house.
  - All UI text goes through translations. English and German ship, and other languages can be added by pull request.
  - The docs never assume Andreas' environment; any examples use neutral placeholders.
- **Andreas' environment (for the rollout only, see 8):** HA OS 2026.11, with the home location in Rheine, Germany. Possible source entities are `weather.home` (Met.no), `weather.rheine_bentlage` (DWD) and `weather.wetter_alemannenallee`.

## 6. Behaviour

### 6.1 Setup flow

1. **Application credentials.** If none exist yet, HA asks for Client ID and Client Secret. The docs link to dev.netatmo.com and show exactly which fields to fill in.
2. **OAuth login** at Netatmo, then the return to HA.
3. **Search area.**
   - The centre defaults to the HA home zone, and the user can change it with a location selector.
   - The radius defaults to 3 km (range 0.5 to 20 km).
4. **Station list.**
   - The integration converts the radius into a bounding box and calls `getpublicdata`.
   - It shows up to 20 stations, sorted by distance. Each entry gives the place (street and city from `place`), the distance in km, icons for the modules (temperature/humidity/pressure always; rain; wind) and the last-seen age. Example: `Rheine, Musterstraße · 0.8 km · rain ✓ wind ✓ · 4 min ago`.
   - The user selects 1 to 3 stations.
   - If no stations are found, the flow suggests a larger radius.
5. **Priority order.** The user picks the primary station, fallback 1 and fallback 2 from the selected ones. If the primary station has no wind or rain module, a warning appears, but it is not blocking.
6. **Options in the same step, also changeable later:**
   - the optional source weather entity (entity selector, domain `weather`);
   - the update interval (default 10 min);
   - the stale threshold (default 30 min, range 15 to 120).
7. **Entry title.** The title is the primary station's place name, for example "Netatmo Rheine Musterstraße".

The **options flow** lets the user change all of the above later, including swapping stations, without removing the entry. Changing stations reloads the entry, and the entity IDs of stations that remain stay stable.

A manual fallback lets the user enter station IDs (MAC addresses) directly, for stations outside the search or for power users.

### 6.2 Polling

- One `DataUpdateCoordinator` exists per config entry.
- Each poll makes one `getpublicdata` call. The bounding box is the smallest box that contains all selected stations, plus a margin of about 300 m.
- If a selected station is missing from that response, the integration makes one extra call per missing station with a tiny box around its known coordinates. This guards against Netatmo leaving stations out of larger boxes.
- With 3 stations this means 6 to 24 requests per hour.
- On HTTP 429 or a Netatmo rate-limit error, the next poll waits with exponential backoff, up to 60 min. The integration logs the backoff once and does not spam the log.
- On an auth failure it starts reauth.

### 6.3 Station health

A station is **healthy** only if both conditions hold:

- it appears in the latest response; and
- for every module it reported at selection time (base, rain, wind), the newest measurement timestamp is younger than the stale threshold.

Otherwise the station is **unhealthy**. Its own entities then become `unavailable`. They do not keep showing stale values.

This matches Andreas' rule "alle Werte" (all values): if any module that is normally present goes stale, the whole station counts as down.

### 6.4 Entities

The device and entity layout is:

| Device | Entities |
|---|---|
| One per station: "Netatmo ‹place›" | `weather.*` plus sensors (see below) |
| "Netatmo ‹entry› Primary" | `weather.*`, sensors, plus `sensor.*_active_station` |
| "Netatmo ‹entry› Average" (only when 2 or more stations) | `weather.*`, sensors, plus `sensor.*_stations_used` |

Sensors per device, created only where the data exists:
- temperature °C, humidity %, pressure hPa;
- rain current mm/h, rain last 1 h mm, rain last 24 h mm;
- wind speed km/h, wind direction °, gust speed km/h, gust direction °;
- a binary sensor `*_healthy` (device class `connectivity`), on the station devices and on Primary.

Each sensor has the correct `device_class`, `state_class` and native unit, so long-term statistics work. Compass text and arrow sensors as in nfws are not created; the HA unit and direction display covers them.

**Primary with fallback**
- It takes all values from the first healthy station in priority order.
- Switching back to a station higher in the order needs **two consecutive healthy polls** (hysteresis), so the source does not flap.
- `sensor.*_active_station` shows the place name of the active station. Its attributes are the station ID and the priority index.
- If no station is healthy, all entities of this device become unavailable.

**Average**
- Temperature, humidity and pressure are the arithmetic mean of the healthy stations.
- Wind speed, gust speed, rain current, rain 1 h and rain 24 h use the **maximum** across healthy stations. The worst case is safer for the awning.
- Wind and gust direction come from the station that has the maximum gust, so the direction matches the reported strength.
- A value is unavailable only when no healthy station delivers it.
- `sensor.*_stations_used` holds the number of healthy stations. Its attribute lists which ones.

### 6.5 Weather entities and the source entity

Every weather entity (per station, Primary, Average) fills these values from Netatmo:
- `native_temperature`, `humidity`, `native_pressure`;
- `native_wind_speed`, `wind_bearing`, `native_wind_gust_speed`;
- `native_dew_point`, calculated with the Magnus formula from temperature and humidity.

When a **source entity** is configured:
- `condition` comes from the source, with one override. If Netatmo measures current rain above 0 and the source says neither `rainy`, `pouring`, `lightning-rainy`, `snowy` nor `snowy-rainy`, the condition becomes `rainy`. Measured rain beats a model.
- `native_apparent_temperature`, `uv_index`, `cloud_coverage`, `native_visibility` and `ozone` come from the source if it provides them.
- The forecasts (daily, hourly, twice_daily) are proxied:
  - `supported_features` mirror the source;
  - `async_forecast_*` calls `weather.get_forecasts` on the source;
  - when the source's state changes, `async_update_listeners` runs so that forecast subscriptions refresh.

Without a source entity:
- the condition is `rainy` while rain is above 0;
- otherwise `windy` when wind speed is at least 39 km/h (Beaufort 6) or gust speed at least 50 km/h;
- otherwise the condition is `None`, which shows as unknown;
- there is no forecast.

If the source entity is unavailable, the weather entity behaves as if no source were configured. It stays available.

### 6.6 Diagnostics and repairs

- The diagnostics download contains the selected stations, the last raw response and the health state, with the tokens redacted. Station coordinates stay in because they are public data.
- A repair issue appears when a selected station has been absent from every response for 7 days. It suggests that the station was removed.

## 7. Repository, distribution and documentation

- **Gitea is the source of truth:** `git.d0ner.de/d0ner/netatmo-public-weather`. A push mirror sends it to the GitHub repository that Andreas provides. HACS installs from GitHub.
- **Layout:**
  ```
  custom_components/netatmo_public_weather/
    __init__.py
    manifest.json
    application_credentials.py
    config_flow.py
    api.py
    coordinator.py
    health.py
    aggregate.py
    entity.py
    weather.py
    sensor.py
    binary_sensor.py
    diagnostics.py
    repairs.py (if needed)
    const.py
    strings.json
    translations/en.json
    translations/de.json
  tests/
  docs/
  README.md
  hacs.json
  LICENSE (MIT)
  .github/workflows/ (hassfest, hacs, pytest)
  ```
- **No pyatmo dependency.** The API surface is two endpoints. A small async client on HA's `aiohttp` session keeps the dependency list empty and avoids pyatmo's model layer. This is the builder's call.
- **Tests** use `pytest-homeassistant-custom-component`:
  - the config flow including OAuth;
  - the station list parsing;
  - health and staleness;
  - the failover order and hysteresis;
  - aggregation;
  - the condition override;
  - forecast proxying;
  - 429 backoff.
- **Docs, in English:**
  - README with quick start;
  - `docs/netatmo-app.md`: creating the developer app, with the exact field values and the redirect URI;
  - `docs/entities.md`;
  - `docs/failover.md`, with a diagram of the health and failover logic;
  - `docs/faq.md`.
  - A prominent warning in README and failover.md: data is 10 to 20 minutes old and comes from a station that is not at your house. Use a local wind sensor for storm protection.
  - The German UI translation ships, but the documentation is English only.
- **Versioning:** SemVer, with Git tags and GitHub releases, so HACS can offer updates.

## 8. Rollout in Andreas' HA

These steps are not part of the repository deliverable, but they are part of done.

1. Install through HACS as a custom repository, next to nfws.
2. Choose the same Rheine station(s) nfws uses, plus 1 or 2 nearby stations.
3. Compare the values with nfws for a few days.
4. Afterwards, as a separate task with Andreas' approval, switch the awning automation and dashboards over and remove nfws.

## 9. Decisions made by Claude, not by Andreas

- The domain and name are `netatmo_public_weather` / "Netatmo Public Weather".
- The Average entity uses the maximum for wind, gust and rain, and the direction of the strongest gust. Andreas had no objection, but it is still a proposal.
- The stale threshold defaults to 30 min.
- Switching back to a higher station needs 2 healthy polls.
- The search radius defaults to 3 km, and the list shows at most 20 stations.
- Without a source, the condition uses the rain and wind thresholds from 6.5.
- The condition override "measured rain beats source" applies.
- There is a dew point calculation.
- Compass text and arrow sensors are not created.
- There is no pyatmo; the integration has its own small client.
- The minimum HA version is 2025.1.
- The license is MIT.
- A repair issue appears for a station missing for 7 days.

## 10. Open for the builder

- Verify against the live API:
  - the required scope;
  - whether `getpublicdata` returns `place.street`;
  - the exact timestamp fields per module (`res` keyed by time for the base module, `wind_timeutc`, `rain_timeutc`);
  - the behaviour for very small bounding boxes.
- Choose the exact entity ID scheme. It must be stable across option changes and be based on the station MAC.
