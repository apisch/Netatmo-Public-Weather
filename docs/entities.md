# Entities

Every integration entry creates the following devices:

| Device | Created when | Contains |
|---|---|---|
| **Netatmo ‹station›**, one per station | always | weather entity, measurement sensors, *Data fresh* |
| **‹entry› Primary** | always | weather entity, measurement sensors, *Active station*, *Data fresh* |
| **‹entry› Average** | 2 or more stations | weather entity, measurement sensors, *Stations used* |

Station names come from what Netatmo reports. Usually that is only the town, so the end of the station ID is added to keep names distinct, for example `Rheine 48:8c`. If Netatmo also reports a street, the name is `street, town`. You can rename devices and entities in Home Assistant as usual; the unique IDs do not change. On a station's device page, **Visit** opens that station on the Netatmo Weathermap, with its history graphs.

## Measurement sensors

Measurement sensors are only created when the data exists. A station without a wind module has no wind sensors. Primary and Average get a sensor as soon as any configured station has the module.

| Sensor | Unit (native) | Notes |
|---|---|---|
| Temperature | °C | outdoor module |
| Humidity | % | outdoor module |
| Pressure | hPa | from the indoor base station |
| Rain intensity | mm/h | latest value from the rain gauge |
| Rain last hour | mm | |
| Rain last 24 hours | mm | |
| Wind speed | km/h | |
| Wind direction | ° | |
| Gust speed | km/h | strongest gust in the last measurement interval |
| Gust direction | ° | |

Home Assistant converts all values to your unit system. All sensors have a state class, so they appear in long-term statistics and history graphs.

## Weather entities

Each device has one weather entity with:

- temperature, humidity, pressure, wind speed, gust speed and wind bearing from Netatmo;
- the dew point, calculated from temperature and humidity;
- if a **source entity** is configured:
  - the condition, with measured rain taking precedence;
  - forecasts (daily, hourly and twice daily, whatever the source supports);
  - UV index, cloud coverage, apparent temperature, visibility and ozone, where the source provides them.

Without a source entity, the condition is derived from the measurements:

- `rainy` while rain is measured;
- otherwise `windy` at 39 km/h or more wind (Beaufort 6), or 50 km/h or more gusts;
- otherwise unknown.

There is no forecast in that case.

## Status entities

| Entity | Device | Meaning |
|---|---|---|
| **Data fresh** (binary sensor) | each station | `on` while this station delivers fresh data for all its modules. |
| **Data fresh** (binary sensor) | Primary | `on` while at least one station is healthy, so Primary has data. |
| **Active station** (sensor) | Primary | Name of the station currently feeding Primary. Attributes: `station_id`, `priority` (1 = your primary station). |
| **Stations used** (sensor) | Average | Number of healthy stations in the average. Attribute: `stations` (names). |

*Data fresh* is never `unavailable`. During an outage it is `off`, so you can trigger automations on it.

## When is an entity unavailable?

Measurement sensors and weather entities become **unavailable** instead of showing old values:

- **Station entities:** when the station is not healthy. See [failover.md](failover.md).
- **Primary entities:** when no configured station is healthy.
- **Average entities:** when no station is healthy, or when no healthy station measures that value.
- **All entities:** when Home Assistant cannot reach Netatmo (network problem, Netatmo outage, rate limit). Each failed update makes them unavailable until the next successful one.
