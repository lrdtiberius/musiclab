# MusicLab v1.9.1

Redesign-/Workbench-Version auf Basis von v1.8.28.

## Neu / geändert

- UI-Redesign Richtung dunkles Studio-Dashboard.
- Größere Album-Kacheln und klarere Auswahlzustände.
- Der Tab **Duplikate** heißt jetzt **Wartung**.
- Auf der Wartungsseite wird die linke Suche weiterhin ausgeblendet, damit die komplette Breite genutzt wird.
- Fix für die Auswahlmarkierung:
  - Es kann optisch nur noch ein Interpret aktiv sein.
  - Es kann optisch nur noch ein Album aktiv sein.
  - Beim Wechsel werden alte Markierungen sofort entfernt.
  - Schnelle Klickwechsel und verspätete Ladeantworten markieren keine alten Alben mehr erneut.
- Cache-Buster auf `1.9.1` gesetzt.

## Start

```bash
docker compose down
docker compose up -d --build
```

Danach Browser hart neu laden.

## Credits

Idea & Umsetzung by Lrd.Tiberius.
