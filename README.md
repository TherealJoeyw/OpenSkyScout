# OpenSkyScount

An open source revival project for the Celestron SkyScout Personal Planetarium.

The SkyScout was a handheld GPS star identifier released in 2006 — point it at anything in the sky and it tells you what you're looking at, with audio descriptions, pointing arrows, and a database of 50,000+ celestial objects. It was genuinely ahead of its time, predating phone astronomy apps by years.

Celestron abandoned the platform on 1 January 2016. A GPS week number rollover bug in April 2019 finished it off completely — every unit now thinks it's September 2006, the pointing system outputs all-zeros, and the device is effectively a paperweight.

This project aims to fix that, and go further: a full open source firmware replacement that preserves the original experience while updating the database, fixing the date problem permanently, and adding new capabilities.

---

## Current Status

**Quick fix found and implemented.** The year selector in manual date entry mode is hardcoded to 2005-2015. The fix is a simple binary patch to the firmware. The CEL file format has been reverse engineered, the firmware extracted, and a patched version produced. `SkyScout_013022EN_patched.cel` in `firmware/` updates the year range to 2024-2034. **Needs testing on hardware before flashing your main device.**

**Firmware fully extracted and analysed.** All three hardware revision firmware files recovered from Celestron's server. CEL archive format documented and parser written. CODE_RO.bin disassembled in Ghidra — 996 functions identified, key addresses documented, original source file names recovered from the binary.

**USB protocol reverse engineered.** Full command set documented from SkyScout.dll (2006 CD). Device communicates over USB bulk transfer with a persistent response queue that survives power cycles.

**GPS protocol documented.** The GPS chip uses a proprietary Motorola OnCore binary protocol at non-standard 19560 baud. Week rollover bug causes it to report September 2006. An ESP32 intercept approach to correct the week number has been partially validated.

---

## The Problem in Detail

There are two separate issues:

**1. Manual date entry** — The year spinner only goes up to 2015. This is a hardcoded string array in the firmware at `0x300af890`. A simple binary patch fixes it. Once the correct date is set manually, the device works correctly for star and constellation identification — the Julian date math library in the firmware has no such limit.

**2. GPS date** — The GPS chip has a week number rollover bug and reports September 2006 when it gets a lock. This prevents automatic GPS-based operation. The fix requires either an ESP32 intercept on the GPS UART (correcting the week number in-flight) or replacing the GPS module entirely.

Both issues are solvable. The patched firmware addresses issue 1 immediately.

---

## Hardware

From joshumax's teardown (Cloudy Nights SkyHack thread, 2014):

| Component | Part | Notes |
|-----------|------|-------|
| CPU | Samsung S3C2410AL-20 | ARM920T, 135MHz |
| NAND Flash | Samsung K9F5608U0D | 32MB |
| RAM | Samsung K4S641632N | 64MB |
| GPS | SkyLab SKG13C | SIRF chipset, Motorola OnCore binary protocol |
| OS | ucOS II | Built with ARM Developer Suite |

**Three hardware revisions exist** (1.x, 2.x, 3.x). Firmware is not cross-compatible between revisions. Check Settings → About for the version string.

**Debug UART** — Three test points near the CPU give access to a full debug shell:

| Pin | Function |
|-----|----------|
| TP16 | GND |
| TP17 | TXD (device transmits) |
| TP18 | RXD (device receives) |

Settings: 9600 baud, 8N1. Connect with any USB-UART adapter (CP2102, CH340, FTDI).

**Hidden debug menu** — Press the GPS button from the main screen to see live sensor readings: GPS coordinates, elevation, UTC time, altitude, azimuth, RA, declination, temperature.

**USB** — VID `19B4`, PID `0002`. Custom bulk transfer protocol. EP_OUT `0x03`, EP_IN `0x81`. Windows: install libusb-win32 via [Zadig](https://zadig.akeo.ie/).

**Manual date entry** — All revisions support manual coordinate entry. Press SELECT before GPS lock → ENTER TIME/LOCATION MANUALLY.

---

## Firmware Files

Original firmware files recovered from `http://software.celestron.com/updates/SkyScout/EN/`.

| File | Version | Date | Contents |
|------|---------|------|----------|
| SkyScout_013022EN.cel | 1.30.22 | 2008-06-05 | 50,000+ objects, NGC/Caldwell/Herschel400 catalogues |
| SkyScout_020210EN.cel | 2.2.10 | 2010-11-30 | Current release for v2 units |
| SkyScout_030216EN.cel | 3.2.16 | 2010-11-30 | First release for v3 units |

### CEL Archive Format

Magic bytes: `RS 01 00`, followed by 3 file entries in a 512-byte header, then file data concatenated.

Each entry: `[name][2 bytes][2 bytes][18-char date][4: unknown][4: CRC32][4: size_bytes][4: unknown]`

Files in order:
1. `DATA_RW.bin` — initialised read-write data (~4KB)
2. `CODE_RO.bin` — ARM firmware code (~676KB)
3. `NVDataBase.bin` — star/object database (~29MB)

Use `tools/parse_cel.py` to extract.

### Patched Firmware

`firmware/SkyScout_013022EN_patched.cel` — year selector updated from 2005-2015 to 2024-2034. All other firmware identical to original. **Test on a donor unit before flashing your main device.**

---

## Firmware Analysis (CODE_RO.bin v1.30.22)

Analysed with Ghidra. ARM v4, little endian, 32-bit. Load address: `0x30010000`.

996 functions identified. Original source file names embedded in binary: `SkyScout.cpp`, `visualmenu.cpp`, `SkyVector.h`.

**Key addresses:**

| Address | Description |
|---------|-------------|
| `0x300af890` | Year selector string array (`"2005"` through `"2015"`) — patch target |
| `0x300ab7a5` | Julian date library: `"Years prior to 1600 are not supported"` |
| `0x3001b4f2` | GPS initialisation |
| `0x3001b1fe` | Database initialisation |
| `0x3001b2ee` | USB initialisation |
| `0x30034fe2` | SkyDBLib deserialise entry point |
| `0x30035002` | SkyDBLib search init |
| `0x3001a5ae` | Debug shell `hwrtc` command (RTC get/set) |
| `0x30012bc2` | NAND flash read error handler |

---

## USB Protocol

Reverse engineered from `SkyScout.dll` (Celestron SkyScout CD, 2006).

### Request format (20 bytes)

| Offset | Size | Field |
|--------|------|-------|
| 0x00 | 1 | ProtocolID (0x00) |
| 0x01 | 1 | ProtocolVersion (0x01) |
| 0x02 | 2 | padding |
| 0x04 | 4 | PayloadLength (uint32 LE) |
| 0x08 | 1 | Sequence (incrementing) |
| 0x09 | 1 | Type (0=request) |
| 0x0a | 1 | Command |
| 0x0b | 1 | StatusCode (0=OK) |
| 0x0c | 4 | (unused) |
| 0x10 | 4 | CRC32 of first 16 bytes |

### Response format (10 bytes)

| Offset | Size | Field |
|--------|------|-------|
| 0x00 | 1 | Command echo |
| 0x01 | 3 | zeros |
| 0x04 | 1 | unknown (0x00) |
| 0x05 | 1 | marker (always 0x0a) |
| 0x06 | 2 | data0 (uint16 LE) |
| 0x08 | 2 | data1 (uint16 LE) |

### Commands

| Byte | Name | Notes |
|------|------|-------|
| 0x01 | versionCmd | works |
| 0x15 | flashCmd | **DO NOT USE without firmware dump first** |
| 0x16 | getFlashCmd | payload: `[page_addr uint16 LE][page_num uint16 LE]` — blocks session |
| 0x18 | burnPageCmd | **DO NOT USE without firmware dump first** |
| 0x34 | getBatteryLevel | works |
| 0x35 | getTemperature | works (queued) |
| 0x37 | getSensorVectors | works (queued) |
| 0x38 | getOrientation | works |
| 0x6f | getDACOffset | works |

### Important USB behaviour

- Commands only work during the **GPS acquiring screen** at boot
- The device has a **persistent response queue** that survives power cycles — drain stale responses before sending commands
- Each command generates **two responses**: data packet + ack packet
- `getFlashCmd` blocks all subsequent commands in the same session
- Device becomes unresponsive after the first USB session per power cycle

---

## GPS Protocol

The GPS chip uses a proprietary Motorola OnCore binary protocol. Reverse engineered by DM2NT (Cloudy Nights / Astrotreff, February 2026).

- UART: **19560 baud** (non-standard), 3.3V, 8N1
- Packet: `@@ ID1 ID2 [payload] [XOR checksum] CR LF`
- GPS→SkyScout: `@@Pb` (position/time), `@@Ou` (satellite data)
- SkyScout→GPS: `@@Oi` (heartbeat), `@@Ot` (config), `@@Oa` (start/stop)
- Rollover bug: chip outputs week 358 instead of 2406, device displays ~September 2006

**Proposed fix**: ESP32 between GPS chip and CPU. Intercept `@@Pb` packets, correct the week number, recalculate XOR checksum, forward corrected packets to CPU. Requires cutting one PCB trace and soldering three wires.

---

## Long Term: Custom Firmware

The goal is a full open source firmware replacement for the original ARM920T hardware:

- Boot from SD card — bootloader in NAND, everything else on the card, update by swapping it
- Manual date entry at boot, no GPS dependency for date
- Updated star/planet/object database on SD card
- PC/phone sync tool to pull from public astronomy databases
- NexStar telescope interface (hardware already supports it)
- USB host mode for WiFi dongle, replacement GPS, etc.

See `docs/firmware-roadmap.md` for full architecture details.

---

## Tools

| Script | Purpose |
|--------|---------|
| `parse_cel.py` | Extract firmware sections from a .cel file |
| `skyscout2.py` | USB communication tool |
| `probe.py` | Probe all USB command bytes |
| `singlecmd.py` | Send one command and read all queued responses |
| `listen.py` | Passive USB listener |
| `dump.py` | Firmware dump tool (getFlashCmd — payload TBD) |
| `flashtest.py` | Multi-command session tester |
| `safe_probe.py` | Single-command probe, known-safe commands only |
| `oneshot.py` / `oneshot2.py` | One-session flash dump attempts |
| `twophase.py` | Two-phase read experiment |
| `poke.py` | Packet format experiments |

```
pip install pyusb
```

Windows: Zadig → libusb-win32 for VID=19B4 PID=0002

Linux: `echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="19b4", ATTR{idProduct}=="0002", MODE="0666"' | sudo tee /etc/udev/rules.d/99-skyscout.rules`

---

## Open Questions

- [ ] Test patched firmware on donor unit
- [ ] `getFlashCmd` payload format — currently blocks USB session after sending
- [ ] JTAG pin locations on PCB
- [ ] LCD, magnetometer, accelerometer chip identification
- [ ] Hardware differences between 1.x, 2.x, 3.x revisions
- [ ] NVDataBase.bin format — 29MB star database structure needs documenting
- [ ] ESP32 GPS week correction — continuous loop to prevent GPS overwriting RTC

---

## Contributing

What we need: people with 2.x or 3.x units to document hardware differences; JTAG experience on ARM920T to attempt a full NAND dump; embedded ARM firmware experience for the custom firmware rewrite; astronomy/ephemeris experience for the pointing math and database format.

Open an issue or PR.

---

## References

- [SkyHack — Cloudy Nights](https://www.cloudynights.com/forums/topic/471626-skyhack-things-you-shouldnt-be-doing-with-celestrons-skyscout/) — hardware teardown (joshumax, 2014), GPS protocol (DM2NT, 2026)
- [Save the Celestron Skyscout — Astrotreff](https://www.astrotreff.de/forum/index.php?thread/305750-rettet-den-celestron-skyscout/) — debug UART date correction (Tino/DM2NT, February 2026)
- [SkyScout CD — Internet Archive](https://archive.org/details/skyscoutcdcelestron2006) — original software including SkyScout.dll
- [SkyScout — Wikipedia](https://en.wikipedia.org/wiki/SkyScout)
