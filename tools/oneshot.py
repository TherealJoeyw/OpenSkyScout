"""
SkyScout one-shot flash dump attempt
Sends everything in one connection after fresh boot
Power cycle device before running this
"""
import usb.core, usb.util, struct, zlib, sys, time

VENDOR_ID  = 0x19B4
PRODUCT_ID = 0x0002
EP_OUT     = 0x03
EP_IN      = 0x81
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
    return dev

_seq = 0
def make_packet(cmd, payload=b''):
    global _seq
    hdr = bytearray(20)
    hdr[0]  = 0x00
    hdr[1]  = 0x01
    struct.pack_into('<I', hdr, 4, len(payload))
    hdr[8]  = _seq & 0xFF
    hdr[9]  = 0
    hdr[10] = cmd
    hdr[11] = 0
    crc = zlib.crc32(bytes(hdr[:16])) & 0xFFFFFFFF
    struct.pack_into('<I', hdr, 16, crc)
    _seq += 1
    return bytes(hdr) + payload

def send_recv(dev, cmd, payload=b'', label=''):
    try:
        dev.write(EP_OUT, make_packet(cmd, payload), TIMEOUT_MS)
        resp = bytes(dev.read(EP_IN, 4096, TIMEOUT_MS))
        print(f"  {label}: {len(resp)} bytes: {resp.hex()}")
        return resp
    except usb.core.USBError as e:
        if 'timeout' in str(e).lower():
            print(f"  {label}: no response")
        else:
            print(f"  {label}: ERROR {e}")
        return None

dev = open_device()
print("Connected — running one-shot sequence\n")

# Step 1: verify comms
print("=== Step 1: verify ===")
send_recv(dev, 0x01, label='versionCmd')
send_recv(dev, 0x34, label='battery')

# Step 2: try getFlashCmd (0x16) with every payload format
print("\n=== Step 2: getFlashCmd payload formats ===")
payloads = [
    (b'',                                   'no payload'),
    (struct.pack('<II', 0, 256),            'LE addr=0 len=256'),
    (struct.pack('<II', 0, 4096),           'LE addr=0 len=4096'),
    (struct.pack('<II', 0, 65536),          'LE addr=0 len=65536'),
    (struct.pack('>II', 0, 256),            'BE addr=0 len=256'),
    (struct.pack('>II', 0, 4096),           'BE addr=0 len=4096'),
    (struct.pack('<I',  0),                 'LE addr=0 only'),
    (struct.pack('<I',  256),               'LE len=256 only'),
    (struct.pack('<HH', 0, 256),            'LE uint16 addr=0 len=256'),
    (b'\x00' * 8,                           '8 zero bytes'),
    (b'\x00' * 4,                           '4 zero bytes'),
    (struct.pack('<II', 0x30010000, 4096),  'LE addr=RAM_BASE len=4096'),
    (struct.pack('<II', 0x00000000, 0x1000),'LE addr=0 len=0x1000'),
]

for payload, label in payloads:
    resp = send_recv(dev, 0x16, payload, f'getFlashCmd {label}')
    if resp and len(resp) > 10:
        print(f"  *** GOT DATA: {len(resp)} bytes ***")
        # save it
        with open('flash_chunk.bin', 'wb') as f:
            f.write(resp)
        print(f"  Saved to flash_chunk.bin")
    time.sleep(0.05)

# Step 3: try getSensorVectors (0x37) same way
print("\n=== Step 3: getSensorVectors payload formats ===")
for payload, label in payloads[:6]:
    send_recv(dev, 0x37, payload, f'getSensorVectors {label}')
    time.sleep(0.05)

# Step 4: try getTemperature (0x35)
print("\n=== Step 4: getTemperature ===")
for payload, label in payloads[:4]:
    send_recv(dev, 0x35, payload, f'getTemperature {label}')
    time.sleep(0.05)

# Step 5: orientation for reference
print("\n=== Step 5: orientation ===")
send_recv(dev, 0x38, label='getOrientation')

print("\nDone")
usb.util.dispose_resources(dev)
