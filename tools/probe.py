"""
SkyScout protocol probe - tries all known commands and dumps raw responses
"""
import usb.core, usb.util, struct, zlib, sys, time

VENDOR_ID  = 0x19B4
PRODUCT_ID = 0x0002
EP_OUT = 0x03
EP_IN  = 0x81
TIMEOUT_MS = 3000

def open_device():
    dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
    if dev is None:
        print("SkyScout not found"); sys.exit(1)
    try:
        if dev.is_kernel_driver_active(0): dev.detach_kernel_driver(0)
    except: pass
    try: dev.set_configuration()
    except: pass
    print(f"Connected: SkyScout")
    return dev

def try_raw(dev, data):
    """Send raw bytes and read back whatever comes"""
    try:
        dev.write(EP_OUT, data, TIMEOUT_MS)
    except Exception as e:
        return None, f"write error: {e}"
    try:
        resp = bytes(dev.read(EP_IN, 256, TIMEOUT_MS))
        return resp, None
    except Exception as e:
        return None, f"read error: {e}"

def make_packet(cmd, seq=0, payload=b''):
    hdr = bytearray(20)
    hdr[0] = 0x00   # protocol id
    hdr[1] = 0x01   # protocol version
    struct.pack_into('<I', hdr, 4, len(payload))
    hdr[8] = seq
    hdr[9] = 0      # request
    hdr[10] = cmd
    hdr[11] = 0
    crc = zlib.crc32(bytes(hdr[:16])) & 0xFFFFFFFF
    struct.pack_into('<I', hdr, 16, crc)
    return bytes(hdr) + payload

dev = open_device()

# Try all known command bytes
commands = {
    0x01: 'versionCmd',
    0x15: 'flashCmd(write)',
    0x16: 'getFlashCmd(read)',
    0x18: 'burnPageCmd',
    0x32: 'resetCmd',
    0x33: 'powerdownCmd',
    0x34: 'getBatteryLevel',
    0x35: 'getTemperature',
    0x36: 'enableAutoShutdown',
    0x37: 'getSensorVectors',
    0x38: 'getOrientation',
    0x39: 'enableLCD',
    0x3a: 'setLED',
    0x6e: 'sensorCmd',
    0x6f: 'getDACOffset',
    0x70: 'setDACOffset',
}

# Skip destructive ones
skip = {0x15, 0x18, 0x32, 0x33}

print("\n=== Probing all commands ===\n")
for cmd_byte, name in sorted(commands.items()):
    if cmd_byte in skip:
        print(f"  0x{cmd_byte:02x} {name}: SKIPPED")
        continue
    
    pkt = make_packet(cmd_byte)
    resp, err = try_raw(dev, pkt)
    
    if err:
        print(f"  0x{cmd_byte:02x} {name}: {err}")
    elif resp is None or len(resp) == 0:
        print(f"  0x{cmd_byte:02x} {name}: no response")
    else:
        print(f"  0x{cmd_byte:02x} {name}: {len(resp)} bytes: {resp.hex()}")
    
    time.sleep(0.1)

# Also try some random command bytes to see what happens
print("\n=== Probing unknown command bytes ===\n")
for cmd_byte in [0x00, 0x02, 0x03, 0x10, 0x20, 0x30, 0x31, 0x40, 0x50, 0xff]:
    pkt = make_packet(cmd_byte)
    resp, err = try_raw(dev, pkt)
    if resp and len(resp) > 0:
        print(f"  0x{cmd_byte:02x}: {len(resp)} bytes: {resp.hex()}")
    time.sleep(0.1)

# Also try sending just a few bytes with no proper header
print("\n=== Probing minimal packets ===\n")
for test in [b'\x00', b'\x01', b'\x00\x01', bytes(20), b'\x00'*4 + b'\x01']:
    resp, err = try_raw(dev, test)
    if resp and len(resp) > 0:
        print(f"  sent {test.hex()}: got {resp.hex()}")
    time.sleep(0.1)

usb.util.dispose_resources(dev)
