# Firmware Rewrite Roadmap

## Goal

A fully open source firmware replacement for the Celestron SkyScout, targeting the original ARM920T hardware. Preserves the original experience while fixing the date problem, updating the database, and adding new features.

## Toolchain

- Compiler: `arm-none-eabi-gcc` with `-mcpu=arm920t -mfloat-abi=soft`
- RTOS: FreeRTOS (replaces ucOS II)
- Debugger: OpenOCD via JTAG (JTAG pins TBD — see hardware notes)
- Flash tool: NAND writer via JTAG, or modified USB update protocol

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Application                       │
│  ┌──────────┐  ┌──────────┐  ┌────────────────────┐ │
│  │  UI/Menu │  │ Pointing │  │  Database          │ │
│  │          │  │  Engine  │  │  (SD card)         │ │
│  └──────────┘  └──────────┘  └────────────────────┘ │
├─────────────────────────────────────────────────────┤
│                    HAL / Drivers                     │
│  ┌──────┐ ┌──────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ │
│  │ LCD  │ │ Keys │ │ Mag │ │ Acc │ │ GPS │ │ USB │ │
│  └──────┘ └──────┘ └─────┘ └─────┘ └─────┘ └─────┘ │
├─────────────────────────────────────────────────────┤
│                    FreeRTOS                          │
├─────────────────────────────────────────────────────┤
│              Samsung S3C2410 ARM920T                 │
└─────────────────────────────────────────────────────┘
```

## Modules

### Boot / Date Entry
- On first boot (or if no valid date stored), show date/time/location entry screen
- Store date in hardware RTC and NVData
- No GPS required for basic operation

### GPS (optional)
- If GPS lock acquired, use for location only
- Date from GPS requires ESP32 week-number corrector on UART (see hardware notes)
- Or: ignore GPS date entirely, trust user-entered date

### Sensor Drivers
- Magnetometer: 3-axis, existing hardware — driver needs writing
- Accelerometer: 3-axis, existing hardware — driver needs writing
- Calibration routine needed (tilt compensation for compass)

### Pointing Engine
- Input: magnetometer + accelerometer → azimuth + altitude
- Input: GPS/manual location + date/time → sidereal time
- Output: RA/Dec of current pointing direction
- Output: Az/Alt for a target object
- Reference implementation: KStars, Stellarium (open source, adaptable)

### Star Database
- Source: Hipparcos catalogue (already used by original firmware)
- Format: compact binary on SD card, indexed for fast lookup
- Fields: RA, Dec, magnitude, spectral type, common name, Bayer designation
- ~118,000 stars in full catalogue, subset for display

### Planet Ephemeris
- Source: JPL DE421 or VSOP87 (compact, suitable for embedded)
- Covers: all planets + Moon + Sun
- Accuracy: arcsecond level, sufficient for naked-eye pointing

### Object Database
- Deep sky objects: NGC/IC catalogue
- Descriptions: updated text (not 2007 knowledge)
- Stored on SD card, updateable

### SD Card Update System
- Database files in open format on SD card
- PC/phone tool generates SD card contents from current sources
- Tool pulls from: Hipparcos, JPL Horizons, Simbad, Wikipedia
- User replaces SD card or updates files via USB

### USB
- Database sync: push updated database files from PC
- Sensor data export: raw sensor readings for calibration
- Firmware update: standard DFU or custom protocol

### Telescope Interface
- NexStar serial protocol (already supported in hardware per original firmware)
- Allows SkyScout to control a compatible GoTo mount

## Database Update Tool (PC/Phone)

A separate project (`openscout-updater`) that:
1. Downloads current star/planet/object data from public sources
2. Packages it into the SD card format
3. Writes to SD card or pushes via USB

Possible sources:
- Stars: [Hipparcos catalogue](https://cdsarc.cds.unistra.fr/viz-bin/cat/I/239)
- Planets: [JPL Horizons](https://ssd.jpl.nasa.gov/horizons/)
- Deep sky: [NGC/IC catalogue](https://github.com/mattiaverga/OpenNGC)
- Object descriptions: Wikipedia API

## Open Questions

- [ ] LCD controller chip identification (needed for display driver)
- [ ] Magnetometer chip identification  
- [ ] Accelerometer chip identification
- [ ] JTAG pin locations
- [ ] NVData structure (calibration values, settings)
- [ ] Hardware differences between 1.x, 2.x, 3.x revisions
- [ ] Audio system — how to preserve the object narration feature
