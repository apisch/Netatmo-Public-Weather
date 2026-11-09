# Netatmo-App anlegen

[English](../netatmo-app.md) | **Deutsch**

Netatmo gibt API-Zugang nur an registrierte Apps. Du legst dafür einmalig eine eigene kleine „App“ an. Sie muss nur existieren, du baust oder veröffentlichst nichts. Das dauert etwa drei Minuten.

## 1. Im Entwicklerportal anmelden

Öffne <https://dev.netatmo.com/apps/> und melde dich mit deinem normalen Netatmo-Konto an. Hast du keines, lege kostenlos eines an. Ein Netatmo-Gerät brauchst du nicht.

## 2. App anlegen

Klicke auf **Create** und fülle das Formular aus:

| Feld | Eintrag |
|---|---|
| App name | beliebig, z. B. `Home Assistant Public Weather` |
| Description | beliebig, z. B. `Public weather data for my Home Assistant` |
| Data protection officer name | dein eigener Name |
| Data protection officer email | deine eigene E-Mail-Adresse |
| Redirect URI | `https://my.home-assistant.io/redirect/oauth` |
| Webhook URI | leer lassen |

Akzeptiere die Bedingungen und klicke auf **Save**.

> [!IMPORTANT]
> Die Redirect-URI muss genau `https://my.home-assistant.io/redirect/oauth` lauten. Weicht sie ab, endet die Anmeldung mit einem Fehler von Netatmo. Die Adresse funktioniert auch, wenn dein Home Assistant nicht aus dem Internet erreichbar ist. Es ist eine Weiterleitungsseite des Home-Assistant-Projekts, die die Anmeldung an deine eigene Instanz zurückgibt.

## 3. Client-ID und Client-Secret kopieren

Nach dem Speichern zeigt die App-Seite die **Client-ID** und das **Client-Secret**. Beides brauchst du im nächsten Schritt. Behandle das Secret wie ein Passwort.

## 4. In Home Assistant eintragen

Home Assistant fragt nach den Zugangsdaten, wenn du **Netatmo Public Weather** zum ersten Mal hinzufügst. Du kannst sie auch vorab eintragen: **Einstellungen → Geräte & Dienste → ⋮ → Anwendungs-Anmeldedaten (Application credentials) → hinzufügen**. Wähle dort *Netatmo Public Weather* und füge Client-ID und Secret ein.

Danach geht die Einrichtung weiter: Home Assistant öffnet die Netatmo-Anmeldung, du erlaubst den Zugriff und kehrst zu Home Assistant zurück, um deine Stationen auszuwählen.

## Hinweise

- Die Integration fragt nur das Recht `read_station` an. Sie kann in deinem Netatmo-Konto nichts verändern.
- Eine App reicht für mehrere Integrationseinträge, etwa für Zuhause und Ferienhaus, und für mehrere Home-Assistant-Benutzer.
- Verwende **nicht** die Zugangsdaten der offiziellen Netatmo-Integration oder eines anderen Tools. Jedes Tool erneuert die Anmelde-Tokens, und wenn sich Tools eine App teilen, melden sie sich gegenseitig ab.
- Löschst du die App auf dev.netatmo.com, fordert Home Assistant dich zur erneuten Anmeldung auf. Lege dann eine neue App an und ersetze die Zugangsdaten unter **Anwendungs-Anmeldedaten (Application credentials)**.
