# MusicLab v0.6.3

Änderungen:
- Album-Browser links gruppiert jetzt nach Albumtitel und zeigt gleiche Albennamen nicht mehr mehrfach pro Interpret an.
- Bei Alben mit mehreren Interpreten steht links „Verschiedene Interpreten“.
- Klick auf ein Album im Album-Modus öffnet das Album global, also über alle enthaltenen Interpreten hinweg.
- Analyse/Normalisierung funktioniert im Album-Modus albumweit.
- Version auf v0.6.3 aktualisiert.

Installation:
1. Inhalt des ZIP nach `/volume1/docker/musiclab` kopieren.
2. Projekt stoppen/starten oder neu erstellen.
3. Browser hart neu laden (`Cmd + Shift + R`).


## v0.6.3
- Album-Auswahl robuster gemacht: keine Inline-onclick-Strings mehr.
- Albumnamen mit Apostrophen, Anführungszeichen oder Sonderzeichen öffnen jetzt zuverlässig.
- Globale Albumansicht öffnet eindeutige Alben direkt beim passenden Interpreten, Sampler weiterhin global.
