# Entitäten

[English](../entities.md) | **Deutsch**

Jeder Integrationseintrag legt diese Geräte an:

| Gerät | Wann | Enthält |
|---|---|---|
| **Netatmo ‹Station›**, eins pro Station | immer | Wetter-Eintrag, Messwert-Sensoren, *Daten aktuell* |
| **‹Eintrag› Primary** | immer | Wetter-Eintrag, Messwert-Sensoren, *Aktive Station*, *Daten aktuell* |
| **‹Eintrag› Average** | ab 2 Stationen | Wetter-Eintrag, Messwert-Sensoren, *Genutzte Stationen* |

Die Stationsnamen stammen aus dem, was Netatmo meldet. Meist ist das nur der Ort, deshalb wird das Ende der Stations-ID angehängt, damit die Namen eindeutig bleiben, zum Beispiel `Rheine 48:8c`. Meldet Netatmo auch eine Straße, lautet der Name `Straße, Ort`. Du kannst Geräte und Entitäten in Home Assistant wie gewohnt umbenennen; die internen IDs ändern sich dabei nicht. Auf der Geräteseite einer Station öffnet **Besuchen** die Station auf der Netatmo-Wetterkarte, mit ihren Verlaufskurven.

## Messwert-Sensoren

Sensoren werden nur angelegt, wenn es die Daten gibt. Eine Station ohne Windmesser bekommt keine Wind-Sensoren. Primary und Average bekommen einen Sensor, sobald irgendeine der gewählten Stationen das Messgerät hat.

| Sensor | Einheit (nativ) | Hinweis |
|---|---|---|
| Temperatur | °C | Außenmodul |
| Luftfeuchtigkeit | % | Außenmodul |
| Luftdruck | hPa | von der Innen-Basisstation |
| Regenintensität | mm/h | letzter Wert des Regenmessers |
| Regen letzte Stunde | mm | |
| Regen letzte 24 Stunden | mm | |
| Windgeschwindigkeit | km/h | |
| Windrichtung | ° | |
| Böengeschwindigkeit | km/h | stärkste Böe im letzten Messintervall |
| Böenrichtung | ° | |

Home Assistant rechnet alle Werte in dein Einheitensystem um. Alle Sensoren haben eine Zustandsklasse, sie erscheinen also in den Langzeitstatistiken und Verlaufsdiagrammen.

## Wetter-Einträge

Jedes Gerät hat einen Wetter-Eintrag mit:

- Temperatur, Luftfeuchte, Luftdruck, Windgeschwindigkeit, Böengeschwindigkeit und Windrichtung von Netatmo;
- dem Taupunkt, berechnet aus Temperatur und Luftfeuchte;
- wenn ein **Quell-Wetter-Eintrag** eingestellt ist:
  - dem Zustand, wobei gemessener Regen Vorrang hat;
  - Vorhersagen (täglich, stündlich und zweimal täglich, je nachdem, was die Quelle kann);
  - UV-Index, Bewölkung, gefühlter Temperatur, Sichtweite und Ozon, soweit die Quelle sie liefert.

Ohne Quell-Eintrag wird der Zustand aus den Messwerten abgeleitet:

- `rainy`, solange Regen gemessen wird;
- sonst `windy` ab 39 km/h Wind (Beaufort 6) oder ab 50 km/h Böen;
- sonst unbekannt.

Eine Vorhersage gibt es dann nicht.

## Status-Entitäten

| Entität | Gerät | Bedeutung |
|---|---|---|
| **Daten aktuell** (Binärsensor) | jede Station | `an`, solange diese Station für alle ihre Messgeräte frische Daten liefert. |
| **Daten aktuell** (Binärsensor) | Primary | `an`, solange mindestens eine Station gesund ist, Primary also Daten hat. |
| **Aktive Station** (Sensor) | Primary | Name der Station, die Primary gerade speist. Attribute: `station_id`, `priority` (1 = deine Hauptstation). |
| **Genutzte Stationen** (Sensor) | Average | Anzahl der gesunden Stationen im Mittelwert. Attribut: `stations` (Namen). |

*Daten aktuell* ist nie `nicht verfügbar`. Bei einem Ausfall ist der Sensor `aus`, so kannst du Automationen darauf auslösen.

## Wann ist eine Entität nicht verfügbar?

Messwert-Sensoren und Wetter-Einträge werden **nicht verfügbar**, statt alte Werte zu zeigen:

- **Stations-Entitäten:** wenn die Station nicht gesund ist. Siehe [failover.md](failover.md).
- **Primary-Entitäten:** wenn keine der gewählten Stationen gesund ist.
- **Average-Entitäten:** wenn keine Station gesund ist oder keine gesunde Station diesen Wert misst.
- **Alle Entitäten:** wenn Home Assistant Netatmo nicht erreicht (Netzwerkproblem, Netatmo-Störung, Rate-Limit). Jeder fehlgeschlagene Abruf macht sie bis zum nächsten erfolgreichen nicht verfügbar.
