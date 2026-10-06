# ROCCAT Kone XP – USB-Protokoll

Beschreibung des Konfigurationsprotokolls der ROCCAT Kone XP (USB `1e7d:2c8b`, Firmware 1.09),
ermittelt zur Herstellung von Interoperabilität (§ 69e UrhG / Art. 6 RL 2009/24/EG) durch Analyse von
ROCCAT Swarm 1.9482 samt Kone-XP-Plugin 1.0006 und durch Messungen an einer echten Maus.
Dieses Dokument enthält nur eigene Beschreibungen, keinen Herstellercode.

Konfidenz: **sicher** = im Herstellercode belegt und/oder an der Maus bestätigt,
**wahrscheinlich** = im Code belegt, an der Maus noch nicht geprüft, **offen** = unbekannt.

## Überblick

Die Maus meldet vier HID-Interfaces. Konfiguriert wird ausschließlich über **Interface 3**
(Vendor-Page `0xFF01`) mit **Feature-Reports**. Unter Linux: `HIDIOCGFEATURE` / `HIDIOCSFEATURE`
auf dem passenden `/dev/hidrawN` (`HID_PHYS` endet auf `/input3`).

| ID | Länge* | Zweck | Lesen | Schreiben |
|---|---|---|---|---|
| `0x04` | 4 | Select (vor GET) und Ack-Status | ja | ja (Select) |
| `0x05` | 4 | aktives Profil | ja | ja |
| `0x06` | 174 | Profil-Einstellungen (DPI, Sensor, Licht) | ja | ja |
| `0x07` | 125 | Tastenbelegung eines Profils | ja | ja |
| `0x08` | 1043 | Makro eines Tasten-Slots | ja | ja |
| `0x09` | 9 | Firmware-Info; **Schreiben = Werksreset** | ja | **nein** |
| `0x0d` | 122 | AIMO-Frames (Software-Beleuchtung) | – | nicht nötig |
| `0x0e` | 6 | Umschaltung Hardware-/Software-Beleuchtung | – | ja |
| `0x0f` | 6 | Lift-off (DCU) und Kalibrierung | ja | ja |
| `0x11` | 20 | Debounce | ja | ja |
| `0x0a`, `0x10`, `0x12`, `0x13` | – | von Swarm nicht genutzt | – | **nein** |

\* inklusive Report-ID-Byte.

`konexp` schreibt nur `0x04`, `0x05`, `0x06`, `0x07`, `0x08`, `0x0e`, `0x0f`, `0x11`.

## Transport

**Checksumme** (`0x06`, `0x07`, `0x08`, `0x11`): Summe aller Bytes außer den letzten zwei,
`& 0xffff`, als u16 Little-Endian in die letzten zwei Bytes. *sicher*

**Ack nach jedem SET**: 150 ms warten, dann `GET 0x04`; Byte 1 ist der Status:
`01` ok, `02` Fehler, `03` busy (erneut warten, Swarm versucht bis zu 100-mal). *sicher*

**Select vor GET**: Profilbezogene Reports liefern den zuletzt ausgewählten Datensatz.
Vor dem Lesen `SET 04 <profil> <req> 00` senden (inkl. Ack):

| req | danach lesbar |
|---|---|
| `0x80` | `0x06` des Profils |
| `0x90` | `0x07` des Profils |
| `0..29` | `0x08` für diesen Tasten-Slot |

Beim Schreiben ist kein Select nötig: Profil bzw. Slot stehen im Report selbst. *sicher*

**Speicherreihenfolge in Swarm**: `0x07` → `0x06` → Makros (`0x08`, danach je 400 ms Pause) → `0x0f` →
`0x11` → `0x0e`, jeweils nur bei Änderung.

## `0x05` – aktives Profil

`05 04 <profil 0..4> 05`. GET liefert dasselbe Format, SET mit demselben Format wechselt das Profil. *sicher*

## `0x06` – Profil-Einstellungen (174 B)

| Offset | Größe | Feld | Werte | Werk | Konfidenz |
|---|---|---|---|---|---|
| `0x00` | 1 | Report-ID | `06` | | sicher |
| `0x01` | 1 | Länge | `ae` | | sicher |
| `0x02` | 1 | Profil | 0–4 | | sicher |
| `0x03`, `0x04` | 1+1 | unbekannt | | `06 06` | offen |
| `0x05` | 1 | DPI-Stufen aktiv | Bit *i* = Stufe *i* | `1f` | sicher |
| `0x06` | 1 | aktive DPI-Stufe | 0–4 | `01` | sicher |
| `0x07` | 5×u16 LE | DPI X je Stufe | DPI/50, 50–19000 in 50er-Schritten | 400/800/1200/1600/3200 | sicher |
| `0x11` | 5×u16 LE | DPI Y je Stufe | wie X; Swarm schreibt Y nie | wie X | Offset wahrscheinlich, Wirkung offen |
| `0x1b` | 1 | Angle Snapping | Bit 0 | `00` | sicher |
| `0x1c` | 1 | unbekannt | | `00` | offen |
| `0x1d` | 1 | Polling-Rate | 0/1/2/3 = 125/250/500/1000 Hz | `03` | Offset sicher, Kodierung wahrscheinlich |
| `0x1e` | 1 | Lichteffekt | siehe unten | `0a` | sicher |
| `0x1f` | 1 | Effekt-Geschwindigkeit | 1–11 | `06` | sicher |
| `0x20` | 1 | Helligkeit | 0–255 | `ff` | sicher |
| `0x21` | 1 | LED-Timeout | 0 = aus, sonst Zeit (Einheit offen, vermutlich Minuten) | `0f` | Feld sicher |
| `0x22` | 1 | Effekt nach Timeout | 0 aus, 1–4, 9 wie Lichteffekt | `00` | sicher |
| `0x23` | 1 | Flag, wird bei Änderung von `0x21`/`0x22` auf 0 gesetzt | | `00` | offen |
| `0x24` | 20×6 | LEDs (siehe unten) | | | sicher |
| `0x9c` | 1 | Profilfarbe aktiv | 0/1 | `01` | wahrscheinlich |
| `0x9d` | 1 | unbekannt | | `64` | offen |
| `0x9e` | 4 | Profilfarbe A, R, G, B | | je Profil | sicher |
| `0xa2` | 1 | Tasten-Preset-Index | 0 = Basic | `00` | wahrscheinlich |
| `0xa3` | 1 | AIMO-Parameter | Bit 0–6 Farbthema, Bit 7 Flag | `00` | Kodierung sicher |
| `0xa4` | 1 | Flag je DPI-Stufe | Bit *i* | `00` | offen |
| `0xa5`–`0xab` | 7 | unbekannt / reserviert | | `00` | offen |
| `0xac` | u16 LE | Checksumme | | | sicher |

**Lichteffekte** (`0x1e`): 1 Fully Lit, 2 Blinking, 3 Breathing, 4 Heartbeat, 5 Photon FX, 9 AIMO,
10 Colorwave. AIMO wird unter Windows von Software berechnet (Umschaltung über `0x0e`,
Frames über `0x0d`); alle anderen laufen in der Firmware.

**LEDs**: 20 Blöcke à 6 Byte ab `0x24`: `+0` unbekannt (Werk `14`), `+1` Alpha, `+2..+4` R, G, B,
`+5` unbekannt (Werk `64`). LED 18 = Mausrad, LED 19 = DPI-Anzeige, LED 0–17 = die beiden Leuchtleisten.
Die genaue Zuordnung 0–17 zu links/rechts ist noch nicht an der Maus bestätigt.

## `0x07` – Tastenbelegung (125 B)

`07 7d <profil>`, dann 30 Einträge à 4 Byte, dann Checksumme an `0x7b`.
Einträge 0–14 sind die normale Ebene, 15–29 die Easy-Shift-Ebene (gleiche Tastenreihenfolge). *sicher*

| Index | Taste |
|---|---|
| 0–2 | links, rechts, Radklick |
| 3, 4 | Rad-Tilt links/rechts |
| 5, 6 | Rad hoch/runter |
| 7, 8 | Seitentasten links neben der linken Haupttaste (vorn/hinten) |
| 9–12 | Daumen-Cluster |
| 13 | Easy-Shift |
| 14 | Taste hinter dem Rad |

Eintrag `[b0, b1, b2, typ]`:

| typ | Bedeutung | Parameter |
|---|---|---|
| `00` | deaktiviert | |
| `01` | Maus | b2: 1 links, 2 rechts, 3 Mitte, 4 Doppelklick, 5/6 Browser vor/zurück, 7/8 Tilt, 9/10 Scroll |
| `02` | DPI | b2: 1 Cycle, 2 Up, 3 Down, 7–11 Easy-Aim auf Stufe 1–5, 12 Easy-Aim mit eigenem Wert (DPI/50 als u16 **Big-Endian** in b0:b1), 13 Easy-Aim 200 DPI |
| `03` | Multimedia | b2: 2 zurück, 3 vor, 4 Play/Pause, 5 Stop, 6 Stumm, 7/8 lauter/leiser, 11–18 Browser/Apps |
| `04` | Navigation | b2: 3 Pos1, 4 Ende, 5/6 Bild hoch/runter, 7 Strg, 8 Shift, 9 Alt |
| `05` | System | b2: 1 Herunterfahren, 2 Ruhezustand, 3 Aufwachen |
| `06` | Taste | b1 = HID-Usage (Page 0x07), b2 = Modifier (Bit 0 Strg, 1 Shift, 2 Alt, 3 Win) |
| `07` | Makro | b1 = 1, b2 = Modus (1 solange gedrückt, 2 bei Druck); Inhalt in `0x08` |
| `08` | Profile | b2: 1 Cycle, 2 nächstes, 3 voriges, 4–8 Profil 1–5, 11 Helligkeit umschalten |
| `09` | Easy-Wheel | b2: 3 DPI, 4 Lautstärke, 5 Alt-Tab, 6 Task View |
| `0a` | Easy-Shift | b2 = 1 |
| `0b` | Host-Funktion | Maus sendet nur ein Event; ausgeführt von Swarm unter Windows (Programme, Ordner, Timer, Mikrofon stumm …) |

## `0x08` – Makros (1043 B)

| Offset | Größe | Inhalt |
|---|---|---|
| `0x000` | 3 | `08 13 04` |
| `0x003` | 1 | Profil |
| `0x004` | 1 | Slot (Eintragsindex aus `0x07`, 0–29) |
| `0x005` | 40 | Gruppenname, UTF-8, NUL-terminiert |
| `0x02d` | 32 | Makroname, NUL-terminiert |
| `0x04d` | u16 LE | 1 bei „solange gedrückt“/„endlos“, sonst 0 |
| `0x04f` | u16 LE | Wiederholungen (Modus „bei Druck“) |
| `0x051` | 960 | Events, Ende bei `00 00` |
| `0x411` | u16 LE | Checksumme |

Tasten-Event, 2 Byte `[d, key]`: Bit 7 von `d` = loslassen, `d & 0x7f` = Pause davor in ms (1–127),
`key` = HID-Usage. Längere Pausen: 4-Byte-Block `00 <einheit> <u16 LE>` mit Einheit 1/2/3 = 20/50/100 ms.
Maximal 480 Tasten-Events. Jede Taste/Ebene hat ihre eigene Makrokopie. *Kodierung sicher, an der Maus ungeprüft.*

## `0x0e`, `0x0f`, `0x11`

- `0x0e` = `0e 06 <a> <b> 00 ff`: `b = 1` Beleuchtung durch Host (AIMO), `0` durch Firmware.
  Beim Beenden sendet Swarm `0e 06 00 00 00 ff`. *wahrscheinlich*
- `0x0f` = `0f 06 <modus> <cmd> <nonce> 00`: Lift-off-Modus 0 Very Low, 1 Low, 2 kalibriert.
  Kalibrierung: `0f 06 02 ff 00 00`, Ergebnis als Input-Event `0x30`, dann `…02 01…` übernehmen
  oder `…02 00…` verwerfen. *wahrscheinlich*
- `0x11` = `11 14 <debounce ms 0–10> …`, Checksumme an `0x12`. Werk: 10 ms. *sicher*

## Events

Die Maus meldet Änderungen aktiv (Format `[id, ?, typ, wert, …]`): `0x20` Profilwechsel (1-basiert),
`0xb0` DPI-Stufe (1-basiert), `0xd0` Polling-Rate, `0xee` Tasten-Bitmaske, `0xf0`/`0xf1` Host-Funktionen.
Über welches Interface sie kommen, ist noch nicht an der Maus geprüft. *wahrscheinlich*

## Werkszustand

`konexp/defaults.py` enthält die rekonstruierten Werksprofile (Reports `0x06`, `0x07`, `0x11`).
Profile 1–4 unterscheiden sich von Profil 0 nur im Index, der Profilfarbe und der Checksumme.
Swarm setzt für einen Werksreset `09 08 01 …` ab; `konexp` schreibt stattdessen die Werksdaten über die
normalen Reports.
