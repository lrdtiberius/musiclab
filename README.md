# MusicLab v0.5.3

Neu in v0.5.3:

- Referenzalbum festlegen
- Referenzalbum dauerhaft in der Datenbank speichern
- Referenzalbum oben in der Oberfläche anzeigen
- Referenzalbum in der Albumliste mit ⭐ markieren
- Ziel-LUFS kann direkt aus der Referenz übernommen werden
- Beim Setzen einer Referenz wird Ziel-LUFS automatisch auf den Albumdurchschnitt gesetzt

Wichtig:

- Ein Album muss zuerst analysiert sein, bevor es als Referenz gesetzt werden kann.
- TP und LRA bleiben als Sicherheits-/Normalisierungsparameter erhalten und werden nicht automatisch überschrieben.
- Frontend und Backend werden per Volume gemountet; kleine Änderungen greifen nach Browser-Reload bzw. Backend-Neustart.

Installation:

1. ZIP entpacken.
2. Inhalt nach `/volume1/docker/musiclab` kopieren.
3. Projekt im Container Manager stoppen.
4. Bereinigen / neu erstellen.
5. Browser hart neu laden: `Cmd + Shift + R`.


## v0.5.3
- Zeigt unter jedem Titel zusätzlich den relativen Dateipfad an.


## v0.5.3
- Albumliste hat jetzt einen eigenen Scrollbereich, damit die Titelliste und Navigation bei Interpreten mit vielen Alben stabil bleiben.


## v0.5.3
- Referenzalbum-Box passt nun auch bei langen Namen sauber in den Bereich.
- Dateiname unter dem Titel entfernt, da der Pfad bereits angezeigt wird.
