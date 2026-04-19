"""
SkyScout one-shot v2 - flush between commands, focus on getFlashCmd
Power cycle before running
"""
import usb.core, usb.util, struct, zlib, sys, time

VENDOR_ID  = 0x19B4
PRODUCT_ID = 0x0002
EP_OUT     = 0x03
EP_IN      = 0x81

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

def flush(dev):
    """Drain any pending responses"""
    while True:
        try:
            dev.read(EP_IN, 256, 200)
        except:
            break

def make_packet(cmd, seq, payload=b''):
    hdr = bytearray(20)
    hdr[0]  = 0x00
    hdr[1]  = 0x01
    struct.pack_into('<I', hdr, 4, len(payload))
    hdr[8]  = seq & 0xFF
    hdr[9]  = 0
    hdr[10] = cmd
    hdr[11] = 0
    crc = zlib.crc32(bytes(hdr[:16])) & 0xFFFFFFFF
    struct.pack_into('<I', hdr, 16, crc)
    return bytes(hdr) + payload

def send_recv(dev, cmd, seq, payload=b'', label='', timeout=3000):
    flush(dev)
    try:
        dev.write(EP_OUT, make_packet(cmd, seq, payload), timeout)
        resp = bytes(dev.read(EP_IN, 4096, timeout))
        status = f"{len(resp)}b: {resp.hex()}"
        if len(resp) > 10:
            status += " *** DATA ***"
            with open(f'flash_{label.replace(" ","_")}.bin', 'wb') as f:
                f.write(resp)
            print(f"  SAVED flash_{label}.bin")
    except usb.core.USBError as e:
        resp = None
        status = 'timeout' if 'timeout' in str(e).lower() else str(e)
    print(f"  seq={seq} {label}: {status}")
    return resp

dev = open_device()
print("Connected\n")

seq = 0

# verify first
print("=== Verify ===")
send_recv(dev, 0x01, seq, label='version'); seq += 1

# now focus entirely on getFlashCmd with clean sequence
print("\n=== getFlashCmd experiments ===")

# the DLL disassembly showed getFlashCmd takes:
# payload[0..1] = addr low word (little endian split into bytes)  
# payload[2..3] = addr high word
# the disasm showed it splitting a 32-bit value into bytes manually
# let's try address as 4 separate bytes + length as 4 bytes

addr_len_formats = [
    # (payload, description)
    (struct.pack('<HH', 0, 0),              'addr=0(16b) len=0(16b)'),
    (struct.pack('<HH', 0, 128),            'addr=0(16b) len=128(16b)'),
    (struct.pack('<HH', 0, 512),            'addr=0(16b) len=512(16b)'),
    (struct.pack('<HH', 0, 1024),           'addr=0(16b) len=1024(16b)'),
    (struct.pack('<BBBB', 0,0,0,0),         '4 zero bytes'),
    (struct.pack('<BBBBHH', 0,0,0,0,0,256),'4b addr + 2b 0 + 2b len=256'),
    (struct.pack('<IH', 0, 256),            'addr=0(32b) len=256(16b)'),
    (struct.pack('<IH', 0, 128),            'addr=0(32b) len=128(16b)'),
    (struct.pack('<IHH', 0, 0, 256),        'addr=0 pad=0 len=256'),
    # try page-based addressing (NAND page = 512 or 2048 bytes)
    (struct.pack('<II', 0, 1),              'page=0 count=1'),
    (struct.pack('<II', 0, 512),            'LE offset=0 size=512'),
    # try with nonzero addresses
    (struct.pack('<II', 0x30010000, 256),   'RAM addr len=256'),
    (struct.pack('<II', 0x30010000, 128),   'RAM addr len=128'),
]

for payload, label in addr_len_formats:
    send_recv(dev, 0x16, seq, payload, label)
    seq += 1
    time.sleep(0.05)

print("\nDone")
usb.util.dispose_resources(dev)
