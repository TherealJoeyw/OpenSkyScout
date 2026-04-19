# OpenSkyScount

An open source revival project for the Celestron SkyScout Personal Planetarium.

The SkyScout was a handheld GPS-enabled star identifier released in 2006. Celestron abandoned the platform on 1 January 2016, and a GPS week number rollover in 2019 rendered all units non-functional for GPS-based operation. This project aims to reverse engineer the hardware and firmware, and ultimately produce a fully open source replacement firmware that restores and extends the original functionality.

---

## The Problem

- Celestron ended all support and updates on 1 January 2016
- A GPS week number rollover bug in April 2019 caused the GPS chip to report incorrect dates (currently reports ~September 2006)
- With the wrong date, the pointing/targeting system produces all-zeros and the device cannot identify or locate objects
- The star/object database is frozen at 2007 knowledge (e.g. Andromeda's size is listed as half the Milky Way — it's now known to be 1.5x larger)
- The year selector in manual entry mode only goes up to 2015/2016

---

## Hardware

From joshumax's teardown (Cloudy Nights SkyHack thread, 2014):

| Component | Part |
|-----------|------|
| CPU | Samsung S3C2410AL-20 ARM920T |
| NAND Flash | Samsung K9F5608U0D (32MB) |
| RAM | Samsung K4S641632N (64MB) |
| GPS | SkyLab SKG13C (SIRF chipset, Motorola OnCore binary protocol) |
| OS | ucOS II |

**Debug UART** (read-only, safe):
- TP16 = GND
- TP17 = TXD (device transmits)
- TP18 = RXD (device receives)
- Settings: 9600 baud, 8N1

**USB**: VID `19B4`, PID `0002`. Custom bulk transfer protocol. Endpoints: EP_OUT `0x03`, EP_IN `0x81`.

**Hardware revisions**: Three distinct board revisions exist (1.x, 2.x, 3.x). Firmware is not cross-compatible between revisions. Check Settings → About for your version.

---

## GPS Week Rollover

The GPS chip uses a proprietary variant of the Motorola OnCore binary protocol (not NMEA). Protocol details reverse engineered by DM2NT (Cloudy Nights / Astrotreff, February 2026):

- UART: **19560 baud** (non-standard), 3.3V, 8N1
- Packet format: `@@ ID1 ID2 [payload] [XOR checksum] CR LF`
- GPS→SkyScout: `@@Pb` (position/time, lat/lon in milliarcseconds), `@@Ou` (satellite data)
- SkyScout→GPS: `@@Oi` (heartbeat), `@@Ot` (config), `@@Oa` (start/stop)
- **Week rollover bug**: chip outputs week 358 instead of 2406, causing the device to display ~September 2006

Confirmed via the hidden debug menu (press GPS button): current reported date is **September 3rd 2006**.

---

## USB Protocol

Reverse engineered from `SkyScout.dll` (Celestron SkyScout CD, 2006, archived at archive.org).

### Packet format (sent by host, 20 bytes)

| Offset | Size | Field | Notes |
|--------|------|-------|-------|
| 0x00 | 1 | ProtocolID | Always 0x00 |
| 0x01 | 1 | ProtocolVersion | Always 0x01 |
| 0x02 | 2 | padding | |
| 0x04 | 4 | PayloadLength | uint32 LE |
| 0x08 | 1 | Sequence | Incrementing counter |
| 0x09 | 1 | Type | 0=request |
| 0x0a | 1 | Command | See table below |
| 0x0b | 1 | StatusCode | 0=OK |
| 0x0c | 4 | (unused) | |
| 0x10 | 4 | CRC32 | CRC32 of first 16 bytes |

### Response format (device → host, 10 bytes)

| Offset | Size | Field |
|--------|------|-------|
| 0x00 | 2 | word0 (varies by command) |
| 0x02 | 2 | word1 |
| 0x04 | 1 | unknown (0x00) |
| 0x05 | 1 | marker (always 0x0a) |
| 0x06 | 2 | data0 |
| 0x08 | 2 | data1 |

### Command bytes

| Byte | Name | Responds |
|------|------|---------|
| 0x01 | versionCmd | yes |
| 0x15 | flashCmd (write) | **DO NOT USE** |
| 0x16 | getFlashCmd (read) | partial — payload format TBD |
| 0x18 | burnPageCmd | **DO NOT USE** |
| 0x32 | resetCmd | **DO NOT USE** |
| 0x33 | powerdownCmd | **DO NOT USE** |
| 0x34 | getBatteryLevel | yes |
| 0x35 | getTemperature | no response yet |
| 0x36 | enableAutoShutdown | yes (ack) |
| 0x37 | getSensorVectors | no response yet |
| 0x38 | getOrientation | yes |
| 0x39 | enableLCD | no response yet |
| 0x3a | setLED | yes (ack) |
| 0x6e | sensorCmd | no response yet |
| 0x6f | getDACOffset | yes |
| 0x70 | setDACOffset | no response yet |

### Notes on USB behaviour

- The device accepts **one USB session per power cycle**. Reconnecting after the first session causes firmware crashes.
- The device **pushes unsolicited data** on EP_IN after connecting (battery level sent without being requested).
- `getFlashCmd` (0x16) returns a 10-byte ack for some payload formats but has not yet yielded actual flash data. Payload format is still being determined.
- Commands that cause crashes: anything sent after the device has already responded to one session.

---

## Debug Menu

A hidden debug menu is accessible by pressing the **GPS button** on the main screen. It displays:

- GPS coordinates (lat/lon)
- Elevation
- UTC time and date
- Altitude and Azimuth
- RA and Declination
- Temperature (internal sensor)

This is useful for verifying GPS lock status and confirming the week rollover date (~September 2006 when GPS-locked).

---

## Proposed Fix (Short Term)

An ESP32 acting as a man-in-the-middle on the GPS UART:

1. Desolder or cut the TX trace from the GPS chip to the CPU
2. Wire GPS TX → ESP32 RX
3. Wire ESP32 TX → CPU RX
4. ESP32 receives `@@Pb` packets, corrects the GPS week number, recalculates XOR checksum, forwards to CPU
5. CPU sees correct date, targeting works

Tested approach by Tino/DM2NT (Astrotreff, February 2026): writing corrected date to the internal RTC via debug UART works, but the GPS chip overwrites it every few minutes. The ESP32 intercept approach solves this permanently.

---

## Proposed Fix (Long Term)

Full open source firmware replacement targeting the original ARM920T hardware:

- **Boot**: manual date/time/location entry screen (no GPS dependency for date)
- **GPS**: optional, used for location only, NMEA from modern module via ESP32 translator
- **Sensors**: reuse existing magnetometer and accelerometer via same I2C/SPI interface
- **Star database**: Hipparcos catalogue (public domain, already used by original firmware per the About screen)
- **Planet ephemeris**: JPL DE421 or similar
- **Object descriptions**: updated text from current sources
- **SD card**: database stored on SD, updateable via PC tool or phone app
- **USB**: database sync tool, compatible with original connector
- **Telescope interface**: NexStar serial protocol (already supported in hardware)

### Toolchain

The CPU is an ARM920T. GCC cross-compiler (`arm-none-eabi-gcc`) with `-mcpu=arm920t` targets this directly. The original firmware used ARM Developer Suite (ADS) and ucOS II — a free RTOS replacement (FreeRTOS) is a viable alternative.

---

## Tools

See [`tools/`](tools/) for all reverse engineering and communication scripts.

| Script | Purpose |
|--------|---------|
| `skyscout.py` | Original USB tool (v1, header size bug) |
| `skyscout2.py` | Corrected USB tool with proper 10-byte response parsing |
| `probe.py` | Probes all known command bytes, logs raw responses |
| `safe_probe.py` | Single-command probe, only safe known-good commands |
| `oneshot.py` | One-session flash dump attempt |
| `oneshot2.py` | Improved one-session attempt with flush between commands |
| `twophase.py` | Two-phase read attempt for getFlashCmd |
| `listen.py` | Pure listener — connects and logs all unsolicited device output |
| `poke.py` | Packet format experiments (size, layout variants) |
| `dump.py` | Firmware dump tool — reads NAND flash via getFlashCmd (0x16) |

### Requirements

```
pip install pyusb
```

Windows: use [Zadig](https://zadig.akeo.ie/) to install **libusb-win32** driver for VID=19B4 PID=0002.

Linux: `echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="19b4", ATTR{idProduct}=="0002", MODE="0666"' | sudo tee /etc/udev/rules.d/99-skyscout.rules`

---

## Known Issues / Open Questions

- [ ] `getFlashCmd` (0x16) payload confirmed: 4 bytes (page_addr LE uint16 + page_num LE uint16), response 14 bytes — dump tool written, needs testing
- [ ] `getSensorVectors` (0x37) and `getTemperature` (0x35) not responding — may need specific payload
- [ ] JTAG pins not yet located on PCB
- [ ] Hardware differences between 1.x, 2.x and 3.x board revisions not documented
- [ ] Full GPS UART protocol capture needed to verify DM2NT's week correction factor

---

## References

- [SkyHack thread — Cloudy Nights](https://www.cloudynights.com/forums/topic/471626-skyhack-things-you-shouldnt-be-doing-with-celestrons-skyscout/) — original reverse engineering by joshumax (2014), GPS protocol by DM2NT (2026)
- [Save the Celestron Skyscout — Astrotreff](https://www.astrotreff.de/forum/index.php?thread/305750-rettet-den-celestron-skyscout/) — Tino's debug UART date correction approach (February 2026)
- [SkyScout Wikipedia](https://en.wikipedia.org/wiki/SkyScout) — hardware history and support dates
- [SkyScout CD — Internet Archive](https://archive.org/details/skyscoutcdcelestron2006) — original software including SkyScout.dll used for protocol reverse engineering

---

## Contributing

This project needs:
- People with 2.x and 3.x hardware revisions to document differences
- Someone to locate and document JTAG pins on the PCB
- Firmware binary dump via JTAG or NAND reader
- ESP32 GPS intercept implementation and testing
- Astronomy/pointing math implementation

Open an issue or PR. All hardware revisions welcome.
# SkyScout USB Tool

Communicates with a Celestron SkyScout over USB to read sensors, dump firmware, and more.

Reverse engineered from `SkyScout.dll` (Celestron SkyScout CD, 2006).

## Setup

### Windows
1. Install the USB driver:
   - Option A: Use `UsbScout.inf` + `UsbScout.sys` from the original CD ISO
   - Option B (easier): Install [Zadig](https://zadig.akeo.ie/), select "Celestron SkyScout Device", install WinUSB driver
2. Install Python dependencies:
   ```
   pip install pyusb
   ```

### Linux
```bash
pip install pyusb
# Either run as root, or add udev rule:
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="19b4", ATTR{idProduct}=="0002", MODE="0666"' | sudo tee /etc/udev/rules.d/99-skyscout.rules
sudo udevadm control --reload-rules
```

## Usage

```bash
# Check firmware version
python skyscout.py version

# Read battery level
python skyscout.py battery

# Read temperature sensor
python skyscout.py temperature

# Read raw magnetometer + accelerometer vectors
python skyscout.py sensors

# Read computed orientation (azimuth/elevation)
python skyscout.py orientation

# Dump firmware to file (default: first 2MB)
python skyscout.py dump skyscout_firmware.bin

# Dump specific range (hex addresses)
python skyscout.py dump skyscout_firmware.bin 0x00000000 0x400000

# Reset device
python skyscout.py reset
```

## Protocol (reverse engineered from SkyScout.dll)

### Header (20 bytes)
| Offset | Size | Field           | Notes                        |
|--------|------|-----------------|------------------------------|
| 0x00   | 1    | ProtocolID      | Always 0x00                  |
| 0x01   | 1    | ProtocolVersion | Always 0x01                  |
| 0x02   | 2    | padding         |                              |
| 0x04   | 4    | Length          | Payload length, uint32 LE    |
| 0x08   | 1    | Sequence        | Incrementing counter         |
| 0x09   | 1    | Type            | 0=request, 1=response        |
| 0x0a   | 1    | Command         | See command table            |
| 0x0b   | 1    | StatusCode      | 0=OK in responses            |
| 0x0c   | 4    | (payload ptr)   | Not used on wire             |
| 0x10   | 4    | CRC32           | CRC32 of first 16 bytes      |

### Command Bytes
| Byte | Name              |
|------|-------------------|
| 0x01 | versionCmd        |
| 0x15 | flashCmd (write)  |
| 0x16 | getFlashCmd (read)|
| 0x18 | burnPageCmd       |
| 0x32 | resetCmd          |
| 0x33 | powerdownCmd      |
| 0x34 | getBatteryLevel   |
| 0x35 | getTemperature    |
| 0x36 | enableAutoShutdown|
| 0x37 | getSensorVectors  |
| 0x38 | getOrientation    |
| 0x39 | enableLCD         |
| 0x3a | setLED            |
| 0x6e | sensorCmd         |
| 0x6f | getDACOffset      |
| 0x70 | setDACOffset      |

### Hardware (from joshumax, Cloudy Nights SkyHack thread)
- CPU: Samsung S3C2410AL-20 ARM920T
- NAND: Samsung K9F5608U0D (32MB)
- RAM: Samsung K4S641632N (64MB)
- GPS: SkyLab SKG13C (SIRF, Motorola OnCore binary protocol)
- Debug UART: TP16=GND, TP17=TXD, TP18=RXD @ 9600 8N1

## Status

- [ ] Driver installation verified on Windows 10
- [ ] `version` command confirmed working
- [ ] `dump` command confirmed working
- [ ] Payload format for `sensors`/`orientation` needs verification

The `getFlashCmd` payload format (addr + length as uint32 LE) was inferred from
the disassembly of `getFlashCmd` in `SkyScout.dll`. If the dump returns errors,
the address/length encoding may need adjustment.

## Contributing

Part of the SkyScout open source revival project. See the original reverse 
engineering thread: https://www.cloudynights.com/forums/topic/471626-skyhack-things-you-shouldnt-be-doing-with-celestrons-skyscout/

---

## Flash Protocol (from SkyScout.dll disassembly)

### getFlashCmd (0x16) — Read flash

Payload: **4 bytes**

| Offset | Size | Field |
|--------|------|-------|
| 0x00 | 2 | page_address (uint16 LE) |
| 0x02 | 2 | page_number (uint16 LE) |

Expected response length: **14 bytes** (from `SetLength(0xe)` in DLL).

NAND page size: 512 bytes (Samsung K9F5608U0D). Total pages: 65536 (32MB).

Note: previous attempts failed because we sent 8-byte payloads and read 10-byte responses. Correct values are 4-byte payload and 14-byte response.

### flashCmd (0x15) — Initiate flash write — DO NOT USE

Takes: pointer to firmware data, total firmware size. Streams data in 1024-byte chunks. Waits 30 seconds for response. Status byte 8 = burn failure.

### burnPageCmd (0x18) — Write flash page — DO NOT USE

Payload:
| Offset | Size | Field |
|--------|------|-------|
| 0x00 | 2 | page_address (uint16 LE) |
| 0x02 | 2 | page_number (uint16 LE) |
| 0x04 | up to 512 | page data |

Max page size capped at 0x200 (512 bytes). Waits 10 seconds for response.

### Flash write sequence (for future reference, DO NOT attempt without a dump first)

1. `flashCmd` — sends total firmware size, initiates write
2. `burnPageCmd` × N — sends 512-byte pages sequentially
3. Device verifies CRC and reboots

