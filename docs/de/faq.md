# FAQ und Fehlersuche

[English](../faq.md) | **Deutsch**

### Die Stationsliste ist leer

Im Suchbereich gibt es keine öffentlichen Stationen, oder Netatmo hat keine geliefert. Geh zurück und nimm einen größeren Radius. Auf dem Land liegen öffentliche Stationen oft mehrere Kilometer auseinander. Wie gut die Abdeckung ist, siehst du auf der Netatmo-Wetterkarte: <https://weathermap.netatmo.com>.

### Favoriten oder Suche: Was soll ich nehmen?

Beides führt zum selben Ergebnis. Mit **Favoriten** wählst du die Stationen vorher auf der Karte aus und siehst dabei genaue Lage und Verlauf. Mit der **Suche** bekommst du eine Liste aller Stationen rund um einen Ort. Favoriten werden einmalig übernommen. Änderst du deine Sterne später, öffne **Konfigurieren** an der Integration und wähle erneut *Meine Netatmo-Favoriten*.

### Meine Favoriten werden nicht gefunden

Die Integration listet nur Stationen, die du mit **demselben Netatmo-Konto** markiert hast, mit dem du dich in Home Assistant angemeldet hast. Deine eigenen Netatmo-Stationen erscheinen nicht. Sie sind womöglich privat und würden dann keine öffentlichen Daten liefern. Netatmo erlaubt höchstens 5 Favoriten.

### Ich kenne eine Station, die nicht aufgelistet ist

Netatmo lässt manchmal Stationen weg, besonders bei großen Suchbereichen. Trage ihre ID im Feld *Stations-IDs* ein: die MAC-Adresse der Basisstation, etwa `70:ee:50:12:34:56`. Die Integration sucht diese ID dann in einem Bereich mit dreifachem Radius (höchstens 50 km).

### Die Anmeldung scheitert mit „redirect_uri“ oder „invalid client“

Die Redirect-URI deiner Netatmo-App muss genau `https://my.home-assistant.io/redirect/oauth` lauten. Prüfe außerdem Client-ID und Secret unter **Einstellungen → Geräte & Dienste → ⋮ → Anwendungs-Anmeldedaten (Application credentials)**. Siehe [netatmo-app.md](netatmo-app.md).

### Home Assistant will, dass ich mich neu anmelde

Netatmo hat die gespeicherte Anmeldung abgelehnt. Häufige Ursachen:
- die Netatmo-App wurde gelöscht oder ihr Secret geändert;
- dieselbe Netatmo-App wird auch von einem anderen Tool genutzt (siehe nächste Frage).

Klicke an der Integration auf **Neu konfigurieren** oder **Erneut authentifizieren** und melde dich an.

### Kann ich die Zugangsdaten der offiziellen Netatmo-Integration mitnutzen?

Nein. Netatmo erneuert den Refresh-Token bei jeder Nutzung. Teilen sich zwei Tools eine App und ein Konto, machen sie sich gegenseitig die Anmeldung ungültig. Lege für diese Integration eine eigene App an, das kostet nichts.

### „Netatmo rate limit reached“ im Log

Netatmo erlaubt 500 Abrufe pro Stunde und Konto. Diese Integration braucht etwa 6 pro Stunde und Eintrag, aber andere Tools mit demselben Netatmo-Konto zählen mit. Die Integration wartet von selbst länger, bis zu einem Abruf pro Stunde, und erholt sich automatisch. Passiert das oft, erhöhe das Abrufintervall in den Optionen oder prüfe, welche anderen Tools dein Konto nutzen.

### Eine Reparaturmeldung sagt, eine Station sei verschwunden

Die Station wurde 7 Tage lang nicht gesehen. Sie wurde vermutlich abgeschaltet oder auf privat gestellt. Öffne **Konfigurieren** an der Integration und wähle eine andere Station.

### Warum ist der Primary-Wetter-Eintrag nicht verfügbar?

Keine deiner Stationen ist gesund. Jede hat entweder aufgehört zu senden oder mindestens ein stummes Messgerät. Sieh dir die Sensoren *Daten aktuell* der Stations-Geräte an. Ist ein Messgerät (oft der Windmesser) an einer Station dauerhaft ausgefallen, wähle eine andere Station oder stelle sie in der Reihenfolge nach hinten.

### Warum Höchstwert statt Mittelwert bei Wind und Regen?

Für Entscheidungen wie „Markise einfahren“ oder „nicht bewässern“ zählt der ungünstigste Fall in deiner Nähe mehr als ein Mittelwert, der ihn versteckt. Siehe [failover.md](failover.md).

### Meine Vorhersage fehlt

Die Wetter-Einträge reichen nur die Vorhersage des Quell-Eintrags durch. Stelle unter **Konfigurieren → Quelle für Zustand und Vorhersage** einen ein und achte darauf, dass dieser Eintrag selbst Vorhersagen kann.

### Umstieg vom Add-on `nfws`

Beide können parallel laufen. Richte diese Integration mit denselben Stationen ein, vergleiche die Werte ein paar Tage und stelle dann deine Automationen und Dashboards auf die neuen Entitäts-IDs um. Danach entfernst du das Add-on. Liest nfws schon deine Netatmo-Favoriten, wähle bei der Einrichtung *Meine Netatmo-Favoriten*, dann bekommst du dieselben Stationen. Diese Integration legt keine Kompass-Text- oder Pfeil-Sensoren an; Home Assistant zeigt Windrichtungen selbst an.

### Diagnose

**Einstellungen → Geräte & Dienste → Netatmo Public Weather → ⋮ → Diagnosedaten herunterladen (Download diagnostics).** Die Datei enthält die Konfiguration (ohne Tokens), die letzte Auswertung und die rohen Stationsdaten, die ohnehin öffentlich sind. Häng sie an Fehlermeldungen an.
