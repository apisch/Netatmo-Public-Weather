# FAQ and troubleshooting

### The station list is empty

There are no public stations in the search area, or Netatmo returned none. Go back and use a larger radius. In rural areas, public stations may be several kilometres apart. You can check coverage on the Netatmo Weathermap: <https://weathermap.netatmo.com>.

### I know a station that is not listed

Netatmo sometimes leaves stations out, especially in large search areas. Enter its ID in the *Station IDs* field: the MAC address of the base station, like `70:ee:50:12:34:56`. The integration then searches an area three times the radius (at most 50 km) for that ID.

### Login fails with "redirect_uri" or "invalid client"

The redirect URI of your Netatmo app must be exactly `https://my.home-assistant.io/redirect/oauth`. Also check the client ID and secret under **Settings → Devices & services → ⋮ → Application credentials**. See [netatmo-app.md](netatmo-app.md).

### Home Assistant asks me to sign in again

Netatmo rejected the stored login. Common causes:
- the Netatmo app was deleted or its secret changed;
- the same Netatmo app is also used by another tool (see the next answer).

Click **Reconfigure** or **Re-authenticate** on the integration and sign in.

### Can I use the same credentials as the official Netatmo integration?

No. Netatmo rotates the refresh token on every use. If two tools share one app and one account, they keep invalidating each other's login. Create a separate app for this integration; it's free.

### "Netatmo rate limit reached" in the log

Netatmo allows 500 requests per hour per account. This integration uses about 6 per hour per entry, but other tools on the same Netatmo account count too. The integration backs off by itself, up to one update per hour, and recovers automatically. If it happens often, raise the update interval in the options, or check which other tools use your account.

### A repair says a station has disappeared

The station was not seen for 7 days. It was probably taken offline or made private. Open **Configure** on the integration and pick another station.

### Why is the Primary weather entity unavailable?

None of your stations is healthy. Every station has either stopped reporting or has at least one silent module. Check the *Data fresh* sensors of the station devices. If one module (often wind) is permanently dead at a station, pick another station, or lower its priority.

### Why maximum instead of mean for wind and rain?

For decisions like "retract the awning" or "skip irrigation", the worst case near you matters more than an average that hides it. See [failover.md](failover.md).

### My forecast is missing

The weather entities only proxy the forecast of the source entity. Configure one under **Configure → Source for condition and forecast**, and make sure that entity supports forecasts itself.

### Migrating from the `nfws` add-on

Both can run side by side. Set up this integration with the same stations, compare the values for a few days, then switch your automations and dashboards to the new entity IDs. After that, remove the add-on. This integration does not need Netatmo favourites, and it creates no compass text or arrow sensors; Home Assistant shows wind directions natively.

### Diagnostics

**Settings → Devices & services → Netatmo Public Weather → ⋮ → Download diagnostics.** The file contains the configuration (tokens removed), the last evaluation and the raw station data, which are public anyway. Attach it to bug reports.
