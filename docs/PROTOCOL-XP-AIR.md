# ROCCAT Kone XP Air – USB-Protokoll

Beschreibung des Konfigurationsprotokolls der ROCCAT Kone XP Air (Kabel `1e7d:2cb2`, Dongle `1e7d:2cb6`),
ermittelt zur Herstellung von Interoperabilität (§ 69e UrhG / Art. 6 RL 2009/24/EG) durch Analyse des
Swarm-Plugins „Kone XP Air“ 1.0019 (Protokoll-Bibliothek und GUI). Dieses Dokument enthält nur eigene
Beschreibungen, keinen Herstellercode.

**Stand: an echter Hardware bestätigt:** Lesen per Kabel und Dongle (Dongle-FW 1.07), Schreiben des Profilblocks
`0x46` per Kabel. Tastenblock `0x47`, Debounce `0x43`, Profilwechsel `0x45` und Schreiben per Dongle ungeprüft.
Konfidenz bezieht sich auf den Herstellercode: **sicher** = eindeutig im Code, **wahrscheinlich** = abgeleitet,
**offen** = unbekannt, **bestätigt** = an echter Hardware gesehen.
Schreiben lässt sich mit `KONEXP_AIR_WRITE=0` abschalten.

## Überblick

Die Air legt intern **dieselben Datenformate wie die Kone XP** ab (siehe [PROTOCOL.md](PROTOCOL.md)):
Profil-Einstellungen beginnen mit `06 4e`, die Tastenbelegung mit `07 7d`, Debounce mit `11 0d`.
Anders ist die Hülle: Alle Blöcke laufen in Stücken von höchstens 25 Bytes durch einen einzigen
30-Byte-Feature-Report.

| PID | Gerät | Ziel-Byte |
|---|---|---|
| `2cb2` | Maus per Kabel | `0` |
| `2cb6` | 2,4-GHz-Dongle (Befehle gehen an die Maus) | `1`; Befehle an den Dongle selbst: `0` |
| `2cb7` | Dongle im Bootloader | wird nicht angesprochen |
| `2cb8` | vermutlich Ladestation (eigenes Protokoll, Holtek) | wird nicht angesprochen |

Konfiguriert wird über das HID-Interface mit **Usage Page `0xFF03`, Usage `0xFF00`** (Interface 2),
bei Kabel und Dongle gleich. *sicher*

## Transport

Feature-Report `0x06`, immer 30 Bytes inkl. Report-ID, SET und GET. *sicher*

| Byte | Anfrage | Antwort |
|---|---|---|
| 0 | `06` | `06` |
| 1 | Ziel (s. o.) | Ziel |
| 2 | Kommando | Kommando |
| 3 | `06` schreiben, `07` lesen | Status: `00` beschäftigt, `08` ok, sonst Fehler |
| 4 | Länge der Daten | Länge der Antwortdaten (*bestätigt*) |
| 5–29 | Daten (max. 25 B) | Antwortdaten |

- **Lesen**: 90 ms warten, SET mit Op `07`, 90 ms warten, GET; Daten ab Byte 5. Swarm prüft den Status hier nicht. *sicher*
- **Schreiben**: SET mit Op `06`, 80 ms warten. Bestätigung: Kommando `0x44` lesen, Datenbyte 0 = `01` heißt angenommen. *sicher*
- **Blöcke** (`0x46`, `0x47`): je Stück erst `[index, profil]` (2 B) schreiben, dann 25 B lesen bzw. schreiben.
  Beim Lesen ändert der Kopf nichts am Gerät; beim Schreiben bestätigt Swarm Kopf und Daten einzeln über `0x44`. *sicher*
- **Checksumme** der Blöcke: wie bei der Kone XP, u16-LE-Summe aller Bytes davor. *sicher*
- Einzelne Pakete haben keine Checksumme. *sicher*
- **Öffnen** wie Swarm: nur Dongle zuerst Link-Check (Ziel 0, Kommando 0, Op `04`, dann Op `05`; je pollen bis
  Status ≠ 0; Op `05` mit Status `08` und Byte 13 = `01` heißt Maus verbunden), dann `0x4e` = `01 00 00 ff`
  („Software aktiv“), beim Schließen `0x4e` = `00 00 00 ff`. *sicher*
- Antwort auf Op `05`: Länge `09`, Bytes 5–12 = Seriennummer der Maus (gleich `HID_UNIQ` am Kabel), Byte 13 = `01`. *bestätigt*
- Ohne diese Schritte antwortete die Air am Dongle auf jede Anfrage an Ziel 1 mit Status `0c` und leeren Daten;
  mit ihnen lesen Kabel (Ziel 0) und Dongle (Ziel 1) identische Daten. Welcher Schritt nötig ist, ist *offen*.
- Events kommen als Input-Report `0x08` (Byte 2 Typ, Byte 3 Wert; `01` = Profilwechsel). *sicher*

## Kommandos

| Cmd | Richtung | Länge | Inhalt | Konfidenz |
|---|---|---|---|---|
| `0x45` | lesen/schreiben | 2 | `[aktives Profil 0–4, Anzahl Profile 1–5]` | sicher |
| `0x46` | Block | 78 je Profil | Profil-Einstellungen (Format Report `0x06`, s. u.) | sicher |
| `0x47` | Block | 125 je Profil | Tastenbelegung, identisch zu Report `0x07` der Kone XP | sicher |
| `0x48` | Block | 1043 je Profil × Taste | Makro (Format wie Report `0x08`); von konexp nicht genutzt | sicher |
| `0x43` | lesen/schreiben | 19 | Debounce, s. u. | sicher |
| `0x4f` | lesen/schreiben | 2 | Lift-off (DCU) `[modus 0–2, x]`; Kalibrierung `[02, ff/00/01]` | sicher |
| `0x44` | lesen | 17 | Status: Byte 0 Ack, Byte 2 Akkustand in % (gesehen: `5a` = 90), Byte 1 = 0 am Kabel/Laden, 1 per Funk | sicher / Byte 1 bestätigt |
| `0x35` | lesen | 13 | Firmware der Maus: BCD-Bytes 5, 7, 6, 9 → `((b5·10+b7)·10+b6)·10+b9`; echte Maus ergibt 501, Plugin liefert `FW_V0.051` | sicher / Bedeutung offen |
| `0x13` | lesen, Ziel 0 | 2 | Firmware des Dongles | sicher |
| `0x25` | lesen, Ziel 0 | 4 | Signalstärke (Byte 2), nur Dongle | sicher |
| `0x4c`, `0x4d`, `0x4e` | schreiben | | LED-Vorschau, direkte LED-Steuerung, Software-Modus an/aus | wahrscheinlich |
| `0x4a` | lesen/schreiben | 14 | Easy-Shift/Easy-Aim-Laufzeitzustand | wahrscheinlich |

**Nie senden** (konexp sperrt sie): `0x49` (Subkommando `01` = Werksreset; weitere Systemfunktionen),
`0x01` (Pairing), `0x12` (Wechsel in den Bootloader), `0x31`–`0x34` (Firmware-Update),
Schreiben auf `0x4b` (Geräte-IDs und Schreibzähler).

## `0x46` – Profil-Einstellungen (78 B)

Bis Offset `0x23` wie Report `0x06` der Kone XP, mit einer Ausnahme: **DPI-Werte stehen direkt als u16**
(`0x0190` = 400), nicht in 50er-Einheiten.

| Offset | Größe | Feld | Konfidenz |
|---|---|---|---|
| `0x00`–`0x02` | 3 | `06 4e <profil>` | sicher |
| `0x03`, `0x04` | 1+1 | unbekannt (Werk `06 06`) | offen |
| `0x05` | 1 | DPI-Stufen aktiv (Bitmaske) | sicher |
| `0x06` | 1 | aktive DPI-Stufe 0–4 | sicher |
| `0x07` / `0x11` | 5×u16 LE | DPI X / Y je Stufe, 50–19000 | sicher |
| `0x1b` | 1 | Angle Snapping | sicher |
| `0x1c` | 1 | unbekannt | offen |
| `0x1d` | 1 | Polling-Rate 0–3 = 125/250/500/1000 Hz | sicher |
| `0x1e`–`0x22` | 5 | Effekt, Geschwindigkeit 1–11, Helligkeit, LED-Timeout, Effekt nach Timeout | sicher |
| `0x23` | 1 | unbekannt | offen |
| `0x24` | 7×5 | LED-Zonen `[z0, alpha, r, g, b]`; z0 unklar (Werk `14` bzw. `01`) | Farbe wahrscheinlich |
| `0x47` | 5 | Profilfarbe `[01, 64, r, g, b]` | wahrscheinlich |
| `0x4c` | 2 | Checksumme | sicher |

Swarm koppelt X und Y: Setzen einer Achse schreibt beide. *sicher*

## `0x47` – Tastenbelegung (125 B)

Byte für Byte wie Report `0x07` der Kone XP (30 Einträge à 4 B, Funktionscodes identisch), aber die Tasten
liegen in anderer Reihenfolge. *sicher* (Umrechnung im GUI-Plugin, gegen die Werksdatei geprüft)

| Index | Taste | Index | Taste |
|---|---|---|---|
| 0 | links | 8 | Taste „−“ links neben der linken Haupttaste (hinten) |
| 1 | rechts | 9 | Daumen T3 |
| 2 | Radklick | 10 | Daumen T4 |
| 3 | Rad hoch | 11 | Rad-Tilt links |
| 4 | Rad runter | 12 | Rad-Tilt rechts |
| 5 | Daumen T1 | 13 | untere Seitentaste (Easy-Shift) |
| 6 | Daumen T2 | 14 | Taste hinter dem Rad |
| 7 | Taste „+“ links neben der linken Haupttaste (vorn) | 15–29 | dieselben Tasten, Easy-Shift-Ebene |

## LED-Zonen

| Zone | Lage | Konfidenz |
|---|---|---|
| 0 | von Swarm nicht genutzt | offen |
| 1 | Mausrad | sicher |
| 2 / 3 | Leiste links / rechts, vorn | sicher |
| 4 / 5 | Leiste links / rechts, hinten | sicher |
| 6 | von Swarm nicht genutzt | offen |

Lichteffekte (`0x1e`) wie bei der Kone XP, zusätzlich `0x13` = Battery Indication. *sicher*

## `0x43` – Debounce (19 B)

`11 0d <aktiv> <wert> <wert> <12 weitere Werte> <checksumme>`. Swarm setzt beim Ändern Byte 2 = `01`,
Byte 3 und 4 = Debounce 0–10 ms und die 12 weiteren Werte auf `0a`. Werkszustand: `11 0d 00 0a 0a 05…05 6e 00`.
Die Checksumme (u16-LE-Summe der Bytes 0–16) passt zum Werkszustand; Swarm berechnet sie fehlerhaft über
einen verschobenen Bereich, die Firmware prüft sie vermutlich nicht. *Layout sicher, Checksumme offen*

## Werkszustand

Die Werksdatei des Plugins enthält nacheinander `0x45`, `0x4f`, `0x43`, `0x4b` und je fünfmal `0x46` und `0x47`.
Die Werte stehen in `konexp/defaults.py` (`air_settings`, `air_buttons`, `AIR_ADVANCED_HEX`); alle zehn
Checksummen stimmen.
