# Creating the Netatmo app

Netatmo only gives API access to registered apps. You create your own small "app" once. It only has to exist, so you don't build or publish anything. This takes about three minutes.

## 1. Sign in at the developer portal

Open <https://dev.netatmo.com/apps/> and sign in with your normal Netatmo account. If you don't have one, create one for free; no Netatmo device is needed.

## 2. Create the app

Click **Create** and fill in the form:

| Field | What to enter |
|---|---|
| App name | Anything, for example `Home Assistant Public Weather` |
| Description | Anything, for example `Public weather data for my Home Assistant` |
| Data protection officer name | Your own name |
| Data protection officer email | Your own email address |
| Redirect URI | `https://my.home-assistant.io/redirect/oauth` |
| Webhook URI | Leave empty |

Accept the terms and click **Save**.

> [!IMPORTANT]
> The redirect URI must be exactly `https://my.home-assistant.io/redirect/oauth`. If it is different, the login ends with an error from Netatmo. This address works even if your Home Assistant is not reachable from the internet. It is a redirect page run by the Home Assistant project, and it forwards the login back to your own instance.

## 3. Copy client ID and client secret

After saving, the app page shows the **client ID** and the **client secret**. You will need both in the next step. Treat the secret like a password.

## 4. Enter them in Home Assistant

Home Assistant asks for the credentials the first time you add **Netatmo Public Weather**. You can also enter them in advance under **Settings → Devices & services → ⋮ → Application credentials → Add application credential**. There, choose *Netatmo Public Weather* and paste the client ID and secret.

Then continue with the setup. Home Assistant opens the Netatmo login page, you allow access, and you return to Home Assistant to pick your stations.

## Notes

- The integration only asks for the `read_station` permission. It cannot change anything in your Netatmo account.
- One app is enough for several integration entries, for example home and holiday house, and for several Home Assistant users.
- Do **not** reuse the credentials of the official Netatmo integration or of any other tool. Each tool rotates the login tokens, and sharing an app between tools makes them log each other out.
- If you ever delete the app on dev.netatmo.com, Home Assistant asks you to sign in again. Create a new app, then replace the credentials under **Application credentials**.
