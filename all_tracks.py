import os
import glob

# --- Configuration ---
INPUT_DIR = "track_dumps"
OUTPUT_C_FILE = "all_tracks.c"
ARRAY_NAME = "all_track_data"
# This will be a huge file, so we'll store pointers to the start of each track
# and their known widths for easy access in your C code.
METADATA_ARRAY_NAME = "track_metadata"

# The widths we've identified so far (0 if unknown)
# You can fill this out as you identify more tracks.
# Based on our last conversation:
# track_00 & 01 are likely not valid tracks
# track_02 is 104
# track_03 is 112
# track_04 is 98 (the secret track)
TRACK_WIDTHS = [
    0, # Track 00
    0, # Track 01
    104, # Track 02
    112, # Track 03
    98, # Track 04
    0, 0, 0, 0, 0, # Tracks 05-09
    0, 0, 0, 0, 0, # Tracks 10-14
    0, 0, 0, 0, 0, # Tracks 15-19
    0, 0, 0, 0, 0, # Tracks 20-24
    0 # Track 25
]

def create_c_source_file():
    """
    Finds all.bin files in the input directory, concatenates them into
    a single byte array in a C source file, and adds a metadata struct.
    """
    # Find all.bin files and sort them numerically
    bin_files = sorted(glob.glob(os.path.join(INPUT_DIR, "track_*.bin")))

    if not bin_files:
        print(f"Error: No.bin files found in '{INPUT_DIR}'.")
        print("Please make sure you've run the extraction script first.")
        return

    print(f"Found {len(bin_files)} track files to process.")
    
    # Store metadata for the header
    track_offsets = []
    current_offset = 0

    with open(OUTPUT_C_FILE, "w") as f:
        print(f"Creating C source file: {OUTPUT_C_FILE}")

        # 1. Write the main data array
        f.write(f"// Combined data for all {len(bin_files)} tracks.\n")
        f.write(f"unsigned char {ARRAY_NAME}[] = {{\n ")
        
        total_bytes = 0
        for i, bin_file in enumerate(bin_files):
            track_offsets.append(current_offset)
            with open(bin_file, "rb") as bf:
                data = bf.read()
                file_size = len(data)
                
                # Write file header comment
                f.write(f"\n // --- Track {i:02d} ({os.path.basename(bin_file)}, {file_size} bytes) --- \n ")

                for byte_index, byte in enumerate(data):
                    f.write(f"0x{byte:02X}, ")
                    if (byte_index + 1) % 16 == 0:
                        f.write("\n ")
                
                total_bytes += file_size
                current_offset += file_size
        
        f.write("\n};\n\n")
        print(f"Wrote {total_bytes} bytes to '{ARRAY_NAME}'.")

        # 2. Write the metadata struct for easy access
        f.write("// --- Metadata for easy access in C code ---\n")
        f.write("typedef struct {\n")
        f.write(" unsigned int offset; // Byte offset into the all_track_data array\n")
        f.write(" unsigned int size; // Size of the track data in bytes\n")
        f.write(" unsigned int width; // The correct width for rendering\n")
        f.write("} TrackMetadata;\n\n")

        f.write(f"TrackMetadata {METADATA_ARRAY_NAME}[{len(bin_files)}] = {{\n")
        for i, offset in enumerate(track_offsets):
            size = (track_offsets[i+1] - offset) if i + 1 < len(track_offsets) else (total_bytes - offset)
            width = TRACK_WIDTHS[i] if i < len(TRACK_WIDTHS) else 0
            f.write(f" {{ {offset}, {size}, {width} }}, // Track {i:02d}\n")
        f.write("};\n")
        print("Wrote track metadata struct.")

    print("\nConcatenation complete!")

if __name__ == "__main__":
    create_c_source_file()