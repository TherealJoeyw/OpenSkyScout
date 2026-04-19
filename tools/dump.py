"""
OpenSkyScount - Firmware Dump Tool
====================================
Dumps the SkyScout NAND flash contents over USB using getFlashCmd (0x16).

Protocol reverse engineered from SkyScout.dll (Celestron SkyScout CD, 2006).

getFlashCmd payload (4 bytes):
  byte 0: page_address low byte
  byte 1: page_address high byte
  byte 2: page_number low byte
  byte 3: page_number high byte

Response: 14 bytes (10-byte header + 4 bytes data? TBC)

NAND: Samsung K9F5608U0D - 32MB, 512-byte pages, 32 pages per block

IMPORTANT: Power cycle the SkyScout before running this.
The device only accepts one USB session per power cycle.

Usage:
  python dump.py                        - dump first 64KB to skyscout_dump.bin
  python dump.py <outfile>              - dump to specified file
  python dump.py <outfile> <pages>      - dump N pages (512 bytes each)
  python dump.py <outfile> <pages> <start_page>  - start from page N
"""

import usb.core, usb.util, struct, zlib, sys, time

VENDOR_ID  = 0x19B4
PRODUCT_ID = 0x0002
EP_OUT     = 0x03
EP_IN      = 0x81
TIMEOUT_MS = 5000

NAND_PAGE_SIZE  = 512         # Samsung K9F5608U0D page size
NAND_TOTAL_PAGES = 65536      # 32MB / 512 = 65536 pages

_seq = 0
def next_seq():
    global _seq
    s = _seq & 0xFF
    _seq += 1
    return s

def open_device():
    dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
    if dev is None:
        print("ERROR: SkyScout not found.")
        print("  - Check USB connection")
        print("  - Windows: install libusb-win32 via Zadig for VID=19B4 PID=0002")
        print("  - Linux: check udev rules or run as root")
        sys.exit(1)
    try:
        if dev.is_kernel_driver_active(0): dev.detach_kernel_driver(0)
    except: pass
    try: dev.set_configuration()
    except: pass
    return dev

def make_packet(cmd, payload=b''):
    hdr = bytearray(20)
    hdr[0]  = 0x00   # ProtocolID
    hdr[1]  = 0x01   # ProtocolVersion
    struct.pack_into('<I', hdr, 4, len(payload))
    hdr[8]  = next_seq()
    hdr[9]  = 0      # request
    hdr[10] = cmd
    hdr[11] = 0
    crc = zlib.crc32(bytes(hdr[:16])) & 0xFFFFFFFF
    struct.pack_into('<I', hdr, 16, crc)
    return bytes(hdr) + payload

def send_recv(dev, cmd, payload=b'', read_size=64, timeout=TIMEOUT_MS):
    dev.write(EP_OUT, make_packet(cmd, payload), timeout)
    try:
        return bytes(dev.read(EP_IN, read_size, timeout))
    except usb.core.USBError as e:
        if 'timeout' in str(e).lower():
            return None
        raise

def verify_connection(dev):
    """Send versionCmd and verify device responds"""
    resp = send_recv(dev, 0x01)
    if resp and len(resp) >= 6 and resp[5] == 0x0a:
        print(f"  Device responding (version response: {resp.hex()})")
        return True
    print(f"  WARNING: unexpected version response: {resp.hex() if resp else 'none'}")
    return False

def read_page(dev, page_addr, page_num):
    """
    Read a single NAND page using getFlashCmd (0x16).
    
    Payload format (4 bytes, from SkyScout.dll disassembly):
      byte 0-1: page_addr as LE uint16
      byte 2-3: page_num  as LE uint16
    
    Response: 14 bytes expected (SetLength(0xe) in DLL)
    """
    payload = struct.pack('<HH', page_addr & 0xFFFF, page_num & 0xFFFF)
    resp = send_recv(dev, 0x16, payload, read_size=256)
    return resp

def dump(dev, outfile, num_pages, start_page=0):
    print(f"\nDumping {num_pages} pages ({num_pages * NAND_PAGE_SIZE} bytes)")
    print(f"  Start page: {start_page}")
    print(f"  Output: {outfile}\n")

    dumped = 0
    errors = 0

    with open(outfile, 'wb') as f:
        for i in range(num_pages):
            page_num = start_page + i
            resp = read_page(dev, page_num, page_num)

            if resp is None:
                print(f"\n  WARNING: no response for page {page_num}, writing zeros")
                f.write(b'\x00' * NAND_PAGE_SIZE)
                errors += 1
            else:
                # Response is 14 bytes per DLL - first 10 are header, last 4 are data?
                # Or entire response is data? Log everything until format is confirmed.
                f.write(resp)
                dumped += len(resp)

            # Progress bar
            pct = (i + 1) * 100 // num_pages
            bar = '#' * (pct // 2) + '.' * (50 - pct // 2)
            print(f"\r  [{bar}] {pct}% page {page_num} ({dumped} bytes)", end='', flush=True)

            time.sleep(0.02)  # don't hammer the device

    print(f"\n\nDone. {dumped} bytes written, {errors} errors.")
    if errors:
        print(f"  {errors} pages returned no response and were filled with zeros.")
    print(f"\nNOTE: Response format not fully confirmed.")
    print(f"  Expected 14 bytes per page per DLL (SetLength=0xe).")
    print(f"  Actual page data may be a subset of the response.")
    print(f"  Check the hex dump and compare boot strings against known boot log.")


def main():
    outfile    = sys.argv[1] if len(sys.argv) > 1 else 'skyscout_dump.bin'
    num_pages  = int(sys.argv[2]) if len(sys.argv) > 2 else 128   # 64KB default
    start_page = int(sys.argv[3]) if len(sys.argv) > 3 else 0

    if num_pages > NAND_TOTAL_PAGES:
        print(f"Max pages: {NAND_TOTAL_PAGES} ({NAND_TOTAL_PAGES * NAND_PAGE_SIZE // 1024 // 1024}MB)")
        sys.exit(1)

    print("OpenSkyScount Firmware Dump Tool")
    print("=================================")
    print("Connecting to SkyScout...")

    dev = open_device()
    print(f"Connected: Celestron SkyScout (VID={VENDOR_ID:04x} PID={PRODUCT_ID:04x})")

    print("Verifying connection...")
    verify_connection(dev)

    dump(dev, outfile, num_pages, start_page)

    usb.util.dispose_resources(dev)


if __name__ == '__main__':
    main()
