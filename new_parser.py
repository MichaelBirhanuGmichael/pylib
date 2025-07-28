import io

def decode_value(stream):
    """
    Decodes a value from the stream based on the next byte marker.
    This handles single-byte, multi-byte, and character-encoded values.
    """
    marker = stream.read(1)
    if not marker:
        return None
    
    marker = marker[0]

    # Multi-byte integer (e.g., ID)
    if marker == ord('"'):
        return int.from_bytes(stream.read(3), 'little')
    
    # Character-encoded integers for N and L fields
    if ord('0') <= marker <= ord('9'):
        return marker - ord('0')
    if ord(':') <= marker <= ord('?'):
        return marker - ord(':') + 10
    
    # For values >= 16, it seems to be a two-byte sequence where
    # the first byte is a space (32) and the second is the value.
    if marker == 32: # Space character
        return stream.read(1)[0]

    # Default case for any other single-byte value
    return marker

def pretty_print_data(data):
    """Prints the parsed data in the specified format."""
    print("data {")
    if 'ID' in data:
        print(f"  ID={data['ID']}")
    # The key is now 'Numbers' not 'Number'
    for number_entry in data.get("Numbers", []):
        print("  Number {")
        print(f"    N={number_entry['N']} L={number_entry['L']}")
        print("  }")
    print("}")

class LevelsParser:
    def __init__(self, data: bytearray):
        self.stream = io.BytesIO(data)

    def parse(self):
        # Find the start of the main data object.
        temp_buffer = self.stream.read()
        data_start_marker = b'\x01\x04data'
        marker_pos = temp_buffer.find(data_start_marker)
        if marker_pos == -1:
            raise ValueError("Could not find the data start marker in the byte stream.")

        # Reset stream to the beginning of the found data object.
        self.stream = io.BytesIO(temp_buffer[marker_pos:])
        
        # --- Start Parsing Data Object ---
        obj = {}
        obj["Numbers"] = []

        # Consume the object marker and name for 'data'
        self.stream.read(1) # consume object marker \x01
        name_len = self.stream.read(1)[0]
        self.stream.read(name_len) # consume 'data' name

        while True:
            pos = self.stream.tell()
            marker_byte = self.stream.read(1)
            if not marker_byte or marker_byte == b'\x00':
                break # End of object

            marker = marker_byte[0]
            
            # Nested Object (First Number)
            if marker == 0x01:
                name_len = self.stream.read(1)[0]
                name = self.stream.read(name_len).decode('utf-8')
                if name == 'Number':
                    # Verbose Number format
                    self.stream.read(1); self.stream.read(1); self.stream.read(1) # skip \x02, \x01, 'N'
                    n_val = decode_value(self.stream)
                    self.stream.read(1); self.stream.read(1); self.stream.read(1) # skip \x02, \x01, 'L'
                    l_val = decode_value(self.stream)
                    obj["Numbers"].append({'N': n_val, 'L': l_val})
                    self.stream.read(1) # Read terminator \x00

            # Key-Value Field (ID)
            elif marker == 0x02:
                name_len = self.stream.read(1)[0]
                name = self.stream.read(name_len).decode('utf-8')
                if name == 'ID':
                    obj[name] = decode_value(self.stream)
            
            # Compact Number object
            elif marker == 0x05:
                self.stream.read(1) # skip field marker 0x06
                n_val = decode_value(self.stream)
                self.stream.read(1) # skip field marker 0x07
                l_val = decode_value(self.stream)
                obj["Numbers"].append({'N': n_val, 'L': l_val})
                self.stream.read(1) # Read terminator
            
            else:
                # Unknown marker, so we are done with this object
                self.stream.seek(pos)
                break
        return obj

if __name__ == "__main__":
    # You can switch between these two to test both formats.
    byte_data = bytearray(b'\x8aS&W_Levels \xbc\x01\x04data\x02\x02ID"n\\\x17\x01\x06Number\x02\x01N0\x02\x01L:\x00\x05\x061\x078\x00\x05\x062\x079\x00\x05\x063\x077\x00\x05\x064\x076\x00\x05\x065\x077\x00\x05\x066\x077\x00\x05\x067\x076\x00\x05\x068\x078\x00\x05\x069\x075\x00\x05\x06:\x077\x00\x05\x06;\x077\x00\x05\x06<\x077\x00\x05\x06=\x078\x00\x05\x06>\x076\x00\x05\x06?\x079\x00\x05\x06 \x10\x079\x00\x05\x06 \x11\x078\x00\x05\x06 \x12\x076\x00\x05\x06 \x13\x077\x00\x05\x06 \x14\x077\x00\x05\x06 \x15\x077\x00\x05\x06 \x16\x078\x00\x05\x06 \x17\x078\x00\x05\x06 \x18\x078\x00\x05\x06 \x19\x074\x00\x05\x06 \x1a\x076\x00\x05\x06 \x1b\x075\x00\x05\x06 \x1c\x076\x00\x05\x06 \x1d\x076\x00\x05\x06 \x1e\x077\x00\x05\x06 \x1f\x077\x00\x05\x06  \x075\x00\x05\x06 !\x077\x00\x05\x06 "\x078\x00\x05\x06 #\x077\x00\x05\x06 $\x076\x00\x00\x10')
    # byte_data = bytearray(b'\x8aS&W_Levels!\x04\x04\x01\x04data\x02\x02ID"\x14+\x17\x01\x06Number\x02\x01N0\x02\x01L:\x00\x05\x061\x079\x00\x05\x062\x075\x00\x05\x063\x078\x00\x05\x064\x078\x00\x05\x065\x076\x00\x05\x066\x075\x00\x05\x067\x075\x00\x05\x068\x07:\x00\x05\x069\x079\x00\x05\x06:\x076\x00\x05\x06;\x079\x00\x05\x06<\x079\x00\x05\x06=\x078\x00\x05\x06>\x077\x00\x05\x06?\x077\x00\x05\x06 \x10\x079\x00\x05\x06 \x11\x078\x00\x05\x06 \x12\x077\x00\x05\x06 \x13\x077\x00\x05\x06 \x14\x079\x00\x05\x06 \x15\x077\x00\x05\x06 \x16\x07:\x00\x05\x06 \x17\x077\x00\x05\x06 \x18\x077\x00\x05\x06 \x19\x079\x00\x05\x06 \x1a\x076\x00\x05\x06 \x1b\x076\x00\x05\x06 \x1c\x077\x00\x05\x06 \x1d\x074\x00\x05\x06 \x1e\x078\x00\x05\x06 \x1f\x079\x00\x05\x06  \x077\x00\x05\x06 !\x079\x00\x05\x06 "\x077\x00\x05\x06 #\x07:\x00\x05\x06 $\x078\x00\x00\x10')
    
    parser = LevelsParser(byte_data)
    parsed_data = parser.parse()
    pretty_print_data(parsed_data)