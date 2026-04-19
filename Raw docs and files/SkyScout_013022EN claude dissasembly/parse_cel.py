"""
OpenSkyScount - CEL firmware archive parser
Extracts DATA_RW.bin, CODE_RO.bin, NVDataBase.bin from a .cel file

CEL file format (reverse engineered):
  0x000: "RS" magic (2 bytes)
  0x002: format version (2 bytes, = 0x0001)
  0x004: entry 1 header [len][date][...][size_bytes][...] 
  ...entries for DATA_RW.bin, CODE_RO.bin, NVDataBase.bin...
  0x200: DATA_RW.bin data
  0x200+DATA_RW_size: CODE_RO.bin data
  0x200+DATA_RW_size+CODE_RO_size: NVDataBase.bin data

Sizes are stored as LE uint32 at specific offsets in each entry header.
Entry layout after filename: [2][2][date 18 chars][4: ?][4: CRC32][4: size_bytes][4: ?]

Usage: python parse_cel.py SkyScout_013022EN.cel [output_dir]
"""
import struct, sys, os, zlib

def parse_cel(filename, outdir='.'):
    with open(filename, 'rb') as f:
        data = f.read()
    
    if data[:2] != b'RS':
        print(f"ERROR: not a CEL file (magic={data[:2].hex()})")
        return
    
    print(f"CEL file: {filename} ({len(data)} bytes)")
    
    # Find file entries by locating .bin filenames in header
    files = []
    for name in [b'DATA_RW.bin', b'CODE_RO.bin', b'NVDataBase.bin']:
        idx = data.find(name, 0, 0x200)
        if idx < 0:
            print(f"WARNING: {name.decode()} not found in header")
            continue
        after = idx + len(name)
        # Skip: 01 00 1e 00 16 00 [18 char date] = 6+18 = 24 bytes
        size_offset = after + 24 + 4  # skip [2][2][date][4:unknown] to get to CRC
        crc  = struct.unpack_from('<I', data, size_offset)[0]
        size = struct.unpack_from('<I', data, size_offset + 4)[0]
        print(f"  {name.decode()}: size={size} bytes ({size//1024}KB), crc=0x{crc:08x}")
        files.append((name.decode(), size, crc))
    
    if not files:
        print("ERROR: no files found in header")
        return

    # Extract files sequentially starting at 0x200
    offset = 0x200
    for fname, size, expected_crc in files:
        outpath = os.path.join(outdir, fname)
        chunk = data[offset:offset+size]
        actual_crc = zlib.crc32(chunk) & 0xFFFFFFFF
        crc_ok = "OK" if actual_crc == expected_crc else f"MISMATCH (got 0x{actual_crc:08x})"
        with open(outpath, 'wb') as f:
            f.write(chunk)
        print(f"  Extracted {fname} -> {outpath} (CRC: {crc_ok})")
        offset += size
    
    print(f"\nDone. Extracted {len(files)} files.")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python parse_cel.py <file.cel> [output_dir]")
        sys.exit(1)
    outdir = sys.argv[2] if len(sys.argv) > 2 else '.'
    os.makedirs(outdir, exist_ok=True)
    parse_cel(sys.argv[1], outdir)
