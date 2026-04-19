"""
SkyScout USB Tool v2
====================
Corrected protocol based on actual device responses.

Real header format (10 bytes):
  Offset  Size  Field
  0x00    2     Value/counter (varies, often echoes something from request)
  0x02    2     padding (00 00)
  0x04    1     unknown (00)
  0x05    1     marker (always 0x0a)
  0x06    2     data word 1
  0x08    2     data word 2

Request format (20 bytes as sent):
  0x00    1     ProtocolID (0x00)
  0x01    1     ProtocolVersion (0x01)
  0x02    2     padding
  0x04    4     payload length
  0x08    1     sequence
  0x09    1     type (0=request)
  0x0a    1     command
  0x0b    1     status
  0x0c    4     (unused)
  0x10    4     CRC32

Commands that respond:
  0x01  versionCmd         -> 00 01 00 00 00 0a 00 01 00 02
  0x34  getBatteryLevel    -> 01 00 00 00 00 0a 18 01 1c 03  (bytes 6-9 = ADC values)
  0x38  getOrientation     -> XX XX 00 00 00 0a YY ZZ WW VV  (pointing data)
  0x36  enableAutoShutdown -> 00 01 00 00 00 0a 00 01 00 02  (ack)
  0x3a  setLED             -> 00 01 00 00 00 0a 00 01 00 02  (ack)
  0x6f  getDACOffset       -> 37 00 00 00 00 0a a8 01 3f 02  (DAC values)

Commands that don't respond (need payload or wrong cmd byte):
  0x16  getFlashCmd  - needs address+length payload
  0x35  getTemperature
  0x37  getSensorVectors
  0x39  enableLCD
  0x6e  sensorCmd
  0x70  setDACOffset

Usage:
  python skyscout2.py version
  python skyscout2.py battery
  python skyscout2.py orientation
  python skyscout2.py monitor        (continuous orientation readout)
  python skyscout2.py dump <outfile> (attempt flash dump)
  python skyscout2.py raw <cmd_hex>  (send raw command byte, e.g. raw 35)
"""

import usb.core, usb.util, struct, zlib, sys, time

VENDOR_ID  = 0x19B4
PRODUCT_ID = 0x0002
EP_OUT     = 0x03
EP_IN      = 0x81
TIMEOUT_MS = 3000

_seq = 0
def next_seq():
    global _seq
    s = _seq & 0xFF
    _seq += 1
    return s

def open_device():
    dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
    if dev is None:
        print("SkyScout not found"); sys.exit(1)
    try:
        if dev.is_kernel_driver_active(0): dev.detach_kernel_driver(0)
    except: pass
    try: dev.set_configuration()
    except: pass
    return dev

def make_packet(cmd, payload=b''):
    hdr = bytearray(20)
    hdr[0] = 0x00
    hdr[1] = 0x01
    struct.pack_into('<I', hdr, 4, len(payload))
    hdr[8]  = next_seq()
    hdr[9]  = 0
    hdr[10] = cmd
    hdr[11] = 0
    crc = zlib.crc32(bytes(hdr[:16])) & 0xFFFFFFFF
    struct.pack_into('<I', hdr, 16, crc)
    return bytes(hdr) + payload

def send_recv(dev, cmd, payload=b'', timeout=TIMEOUT_MS):
    dev.write(EP_OUT, make_packet(cmd, payload), timeout)
    try:
        return bytes(dev.read(EP_IN, 256, timeout))
    except usb.core.USBError:
        return None

def parse_response(resp):
    """Parse 10-byte response into named fields"""
    if resp is None or len(resp) < 10:
        return None
    return {
        'word0':  struct.unpack_from('<H', resp, 0)[0],
        'word1':  struct.unpack_from('<H', resp, 2)[0],
        'unk':    resp[4],
        'marker': resp[5],
        'data0':  struct.unpack_from('<H', resp, 6)[0],
        'data1':  struct.unpack_from('<H', resp, 8)[0],
        'raw':    resp.hex(),
    }

# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_version(dev):
    resp = send_recv(dev, 0x01)
    p = parse_response(resp)
    if not p:
        print("No response"); return
    print(f"Raw: {p['raw']}")
    print(f"Protocol: {p['word0'] & 0xff}.{(p['word0'] >> 8) & 0xff}")
    print(f"Data: {p['data0']:04x} {p['data1']:04x}")

def cmd_battery(dev):
    resp = send_recv(dev, 0x34)
    p = parse_response(resp)
    if not p:
        print("No response"); return
    print(f"Raw: {p['raw']}")
    # From probe: 01 00 00 00 00 0a 18 01 1c 03
    # data0=0x0118=280, data1=0x031c=796
    # Likely two ADC readings - voltage divider values
    adc0 = p['data0']
    adc1 = p['data1']
    print(f"ADC0: {adc0} (0x{adc0:04x})")
    print(f"ADC1: {adc1} (0x{adc1:04x})")
    # Rough voltage estimate - SkyScout runs on 2x AA = ~3V
    # ADC is likely 10-bit (0-1023) or 12-bit (0-4095)
    if adc0 < 1024:
        volts = (adc0 / 1023.0) * 3.3
        print(f"Estimated voltage: {volts:.2f}V (if 10-bit 3.3V ref)")

def cmd_orientation(dev):
    resp = send_recv(dev, 0x38)
    p = parse_response(resp)
    if not p:
        print("No response"); return
    print(f"Raw: {p['raw']}")
    # From probe: 34 00 00 00 00 0a 06 01 ab 02
    # word0=0x0034=52 (could be azimuth tenths of degree?)
    # data0=0x0106=262, data1=0x02ab=683
    print(f"Word0: {p['word0']} (0x{p['word0']:04x})")
    print(f"Data0: {p['data0']} (0x{p['data0']:04x})")
    print(f"Data1: {p['data1']} (0x{p['data1']:04x})")

def cmd_monitor(dev):
    """Continuously read orientation and display - move the device to calibrate"""
    print("Monitoring orientation (Ctrl+C to stop)...")
    print("Move the SkyScout around to understand the data fields\n")
    prev = None
    while True:
        resp = send_recv(dev, 0x38, timeout=1000)
        if resp and len(resp) >= 10:
            if resp != prev:
                w0 = struct.unpack_from('<H', resp, 0)[0]
                w1 = struct.unpack_from('<H', resp, 2)[0]
                d0 = struct.unpack_from('<H', resp, 6)[0]
                d1 = struct.unpack_from('<H', resp, 8)[0]
                print(f"w0={w0:5d}  w1={w1:5d}  d0={d0:5d}  d1={d1:5d}  raw={resp.hex()}")
                prev = resp
        time.sleep(0.1)

def cmd_dac(dev):
    resp = send_recv(dev, 0x6f)
    p = parse_response(resp)
    if not p:
        print("No response"); return
    print(f"Raw: {p['raw']}")
    print(f"DAC0: {p['data0']} (0x{p['data0']:04x})")
    print(f"DAC1: {p['data1']} (0x{p['data1']:04x})")

def cmd_raw(dev, cmd_byte):
    """Send a raw command byte and show response"""
    print(f"Sending command 0x{cmd_byte:02x}...")
    resp = send_recv(dev, cmd_byte)
    if resp:
        print(f"Response ({len(resp)} bytes): {resp.hex()}")
        # Also try with a dummy payload
        resp2 = send_recv(dev, cmd_byte, b'\x00\x00\x00\x00\x00\x00\x00\x00')
        if resp2:
            print(f"With payload ({len(resp2)} bytes): {resp2.hex()}")
    else:
        print("No response")
        # Try with payload
        resp2 = send_recv(dev, cmd_byte, b'\x00\x00\x00\x00')
        if resp2:
            print(f"With 4-byte payload ({len(resp2)} bytes): {resp2.hex()}")

def cmd_dump(dev, outfile):
    """
    Attempt flash dump using getFlashCmd (0x16).
    Since no-payload gives no response, try with address+length payload.
    The NAND is 32MB (Samsung K9F5608U0D).
    """
    print(f"Attempting flash dump -> {outfile}")
    
    # Try different payload formats for getFlashCmd
    test_payloads = [
        (b'\x00\x00\x00\x00\x00\x00\x10\x00', "addr=0 len=0x1000"),
        (b'\x00\x00\x00\x00\x00\x10\x00\x00', "addr=0 len=0x1000 BE"),
        (struct.pack('<II', 0, 256), "addr=0 len=256 LE uint32"),
        (struct.pack('>II', 0, 256), "addr=0 len=256 BE uint32"),
        (struct.pack('<I', 0), "just addr=0"),
        (struct.pack('<I', 256), "just len=256"),
    ]
    
    print("\nTrying payload formats for getFlashCmd (0x16):")
    for payload, desc in test_payloads:
        resp = send_recv(dev, 0x16, payload)
        if resp:
            print(f"  {desc}: {len(resp)} bytes: {resp.hex()}")
        else:
            print(f"  {desc}: no response")
        time.sleep(0.1)
    
    # Also try getSensorVectors (0x37) with payloads since it didn't respond bare
    print("\nTrying getSensorVectors (0x37) with payloads:")
    for payload, desc in test_payloads[:3]:
        resp = send_recv(dev, 0x37, payload)
        if resp:
            print(f"  {desc}: {len(resp)} bytes: {resp.hex()}")
        time.sleep(0.1)

def usage():
    print(__doc__); sys.exit(1)

def main():
    if len(sys.argv) < 2: usage()
    
    dev = open_device()
    print(f"Connected: Celestron SkyScout\n")
    
    cmd = sys.argv[1].lower()
    if   cmd == 'version':     cmd_version(dev)
    elif cmd == 'battery':     cmd_battery(dev)
    elif cmd == 'orientation': cmd_orientation(dev)
    elif cmd == 'monitor':     cmd_monitor(dev)
    elif cmd == 'dac':         cmd_dac(dev)
    elif cmd == 'dump':
        out = sys.argv[2] if len(sys.argv) > 2 else 'skyscout_flash.bin'
        cmd_dump(dev, out)
    elif cmd == 'raw':
        if len(sys.argv) < 3: print("Usage: raw <hex_byte>"); sys.exit(1)
        cmd_raw(dev, int(sys.argv[2], 16))
    else:
        print(f"Unknown: {cmd}"); usage()
    
    usb.util.dispose_resources(dev)

if __name__ == '__main__':
    main()
