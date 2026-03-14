import os
import struct

# --- Configuration ---
ROM_FILE = "Mickey's Speedway USA (USA, Europe) (En,Fr,De,Es).gbc"
OUTPUT_DIR = "track_dumps"
POINTER_TABLE_OFFSET = 0x0182E0 # The start of the track definition table we found
NUM_TRACKS = 26
POINTER_ENTRY_SIZE = 3
BANK_SIZE = 0x4000
EXTRACT_SIZE = 8192 # <--- CORRECTED: Use a fixed size (8KB) for every track

def extract_all_tracks_fixed_size():
    """
    Reads the master track pointer table and dumps a fixed-size block
    for each track's collision map.
    """
    print(f"Opening ROM file: {ROM_FILE}...")
    try:
        with open(ROM_FILE, 'rb') as f:
            rom_data = f.read()
    except FileNotFoundError:
        print(f"ERROR: ROM file not found. Make sure '{ROM_FILE}' is in the same directory.")
        return

    if not os.path.exists(OUTPUT_DIR):
        print(f"Creating output directory: {OUTPUT_DIR}")
        os.makedirs(OUTPUT_DIR)

    print("Reading master track pointer table and extracting tracks...")
    for i in range(NUM_TRACKS):
        entry_offset = POINTER_TABLE_OFFSET + (i * POINTER_ENTRY_SIZE)
        
        bank_num = rom_data[entry_offset]
        pointer_bytes = rom_data[entry_offset + 1 : entry_offset + 3]
        local_addr = struct.unpack('<H', pointer_bytes)[0]
        
        # Calculate the absolute starting offset
        if local_addr < BANK_SIZE:
            absolute_start_offset = (bank_num * BANK_SIZE) + local_addr
        else:
            absolute_start_offset = (bank_num * BANK_SIZE) + (local_addr - BANK_SIZE)

        # Extract the fixed-size data slice
        track_data = rom_data[absolute_start_offset : absolute_start_offset + EXTRACT_SIZE]

        # Write to a file
        output_filename = os.path.join(OUTPUT_DIR, f"track_{i:02d}.bin")
        with open(output_filename, 'wb') as f:
            f.write(track_data)
        
        print(f" -> Saved Track {i:02d} (Bank 0x{bank_num:02X}, Offset 0x{absolute_start_offset:06X}) to '{output_filename}' ({len(track_data)} bytes)")

    print("\nExtraction complete! All 26 tracks saved.")

if __name__ == "__main__":
    extract_all_tracks_fixed_size()
