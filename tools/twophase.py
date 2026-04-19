"""
SkyScout two-phase read attempt
Send getFlashCmd, then try reading again without sending anything
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

def read_all(dev, label=''):
    """Keep reading until timeout"""
    chunks = []
    while True:
        try:
            chunk = bytes(dev.read(EP_IN, 4096, 500))
            chunks.append(chunk)
            print(f"  {label} chunk {len(chunks)}: {len(chunk)}b {chunk.hex()}")
        except:
            break
    return b''.join(chunks)

dev = open_device()
print("Connected\n")

seq = 0

# Send version, read response normally
print("=== version ===")
dev.write(EP_OUT, make_packet(0x01, seq), 3000)
seq += 1
r = read_all(dev, 'version')

# Now send getFlashCmd with the payload that got an ack
print("\n=== getFlashCmd addr=0 len=128 then multi-read ===")
payload = struct.pack('<HH', 0, 128)
dev.write(EP_OUT, make_packet(0x16, seq), 3000)
seq += 1
r = read_all(dev, 'getFlashCmd(no payload)')

print("\n=== getFlashCmd with payload, then multi-read ===")
dev.write(EP_OUT, make_packet(0x16, seq, payload), 3000)
seq += 1
r = read_all(dev, 'getFlashCmd(with payload)')
if len(r) > 10:
    print(f"*** GOT {len(r)} bytes of data ***")
    with open('flash_data.bin', 'wb') as f:
        f.write(r)

# Try sending an empty packet after the ack to trigger data send
print("\n=== getFlashCmd then empty write then read ===")
dev.write(EP_OUT, make_packet(0x16, seq, struct.pack('<HH', 0, 128)), 3000)
seq += 1
try:
    ack = bytes(dev.read(EP_IN, 256, 1000))
    print(f"  ack: {ack.hex()}")
    # now send empty/ack back
    dev.write(EP_OUT, bytes(4), 1000)
    r = read_all(dev, 'after empty ack')
    if len(r) > 10:
        print(f"*** DATA: {len(r)} bytes ***")
        with open('flash_data2.bin', 'wb') as f:
            f.write(r)
except Exception as e:
    print(f"  error: {e}")

print("\nDone")
usb.util.dispose_resources(dev)
