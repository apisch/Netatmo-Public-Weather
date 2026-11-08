# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [0.1.3] - 2026-11-09

### Changed
- The README has badges (release, licence, issues, minimum HA version) and one-click buttons for the Home Assistant Marketplace (2026.11+) and HACS (2026.10 and older).
- The installation guide covers the Marketplace, HACS and manual installation.

## [0.1.2] - 2026-11-09

### Added
- An original logo and icon (no Netatmo trademarks). Home Assistant 2026.x shows them directly from the integration folder; the README shows them too.
- The integration categories `weather_alerts` and `sensors.temperature_humidity` in the manifest.

### Changed
- The GitHub Actions use `actions/checkout@v5` and `actions/setup-python@v6`, because Node.js 20 is deprecated.

## [0.1.1] - 2026-11-09

### Fixed
- Station names are now distinct. Netatmo usually reports only the town and no street, so all stations of a town had the same name and entity IDs ended in `_2` or `_3`. Names now get the end of the station ID, for example `Rheine 48:8c`. Entries created with 0.1.0 are renamed automatically when Home Assistant loads them. Existing entity IDs stay as they are.

## [0.1.0] - 2026-11-08

### Added
- First release.
- Setup in the UI with your own Netatmo app (OAuth2 via application credentials). The station picker lists public stations near you, sorted by distance, with icons for their modules.
- For 1 to 3 stations: one weather entity and sensors per station, a Primary set with failover (hysteresis when switching back), and an Average set (mean for temperature, humidity and pressure; maximum for wind, gusts and rain).
- An optional source weather entity for condition, forecasts and the values Netatmo cannot measure. Measured rain overrides the condition.
- *Data fresh* binary sensors. Stale stations become `unavailable` instead of showing old values.
- Backoff when Netatmo signals its rate limit, a repair issue when a station is gone for 7 days, and diagnostics with tokens redacted.
- Options flow to change stations, priority, source and timing.
- English and German UI, and English documentation.

[0.1.3]: https://github.com/apisch/Netatmo-Public-Weather/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/apisch/Netatmo-Public-Weather/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/apisch/Netatmo-Public-Weather/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/apisch/Netatmo-Public-Weather/releases/tag/v0.1.0
