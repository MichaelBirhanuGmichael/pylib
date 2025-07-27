import io

def pretty_print_ordered(d, indent=0):
    """
    A helper function to print the decoded dictionary in a readable, nested format,
    preserving the original insertion order of keys.
    """
    for key, value in d.items():
        print('  ' * indent + str(key), end='')
        if isinstance(value, dict):
            print(' {')
            pretty_print_ordered(value, indent + 1)
            print('  ' * indent + '}')
        else:
            print(f' = {value}')

def decode_custom_binary(data: bytearray):
    """Decodes the custom binary format from a bytearray into a Python dictionary."""
    stream = io.BytesIO(data)

    def parse_value():
        """Reads and decodes a value based on its type marker."""
        marker = stream.read(1)[0]

        if marker == ord('"'):
            return int.from_bytes(stream.read(3), 'little')
        
        elif marker in [0x8a, 0x85]:
            value_bytes = []
            while True:
                current_pos = stream.tell()
                b = stream.read(1)
                if not b or b[0] in [0x00, 0x01, 0x02, 0x0c]:
                    stream.seek(current_pos)
                    break
                value_bytes.append(b)
            return b''.join(value_bytes).decode('utf-8', 'ignore')

        elif marker in [0x81, 0x82]:
            value_bytes = []
            while True:
                current_pos = stream.tell()
                b = stream.read(1)
                # IMPORTANT FIX: This value type is terminated by the parent object's
                # null terminator. We must peek at the byte but not consume it.
                if not b or b[0] == 0x00:
                    stream.seek(current_pos) # Rewind so the parent can see the terminator.
                    break
                value_bytes.append(b)
            return int(b''.join(value_bytes).decode('utf-8', 'ignore'))
        
        elif marker == 0x20:
            return int.from_bytes(stream.read(1), 'big')
            
        elif marker == 0x07:
            ts_bytes = stream.read(6)
            stream.read(2) # Consume the two trailing nulls specific to this type
            return f"TIMESTAMP(0x{ts_bytes.hex()})"

        else:
            return marker

    def parse_level(last_field_from_parent=None):
        """
        Parses one level of nesting. It can receive the last-seen field name from
        its parent to correctly handle the repetitive field marker (\x0c).
        It returns the parsed dictionary and the last field name it found.
        """
        obj = {}
        last_field_in_scope = last_field_from_parent
        
        while True:
            current_pos = stream.tell()
            marker_byte = stream.read(1)
            # A null terminator or end-of-stream marks the end of this object.
            if not marker_byte or marker_byte[0] == 0x00:
                break
            
            stream.seek(current_pos) # Rewind to process the marker
            marker = stream.read(1)[0]

            if marker == 0x01:  # A nested object (e.g., Win, Red)
                name_len = stream.read(1)[0]
                name = stream.read(name_len).decode('utf-8')
                # Recursively parse the child, passing down the last known field name.
                inner_obj, last_field_from_inner = parse_level(last_field_in_scope)
                obj[name] = inner_obj
                # If the child defined a new field, that becomes our new last_field_in_scope.
                if last_field_from_inner:
                    last_field_in_scope = last_field_from_inner
            
            elif marker == 0x02:  # A new field definition (e.g., Odds)
                field_len = stream.read(1)[0]
                field_name = stream.read(field_len).decode('utf-8')
                last_field_in_scope = field_name # This is now the last known field.
                obj[field_name] = parse_value()

            elif marker == 0x0c:  # A repetitive field
                if last_field_in_scope:
                    obj[last_field_in_scope] = parse_value()

        return obj, last_field_in_scope

    # --- Main execution starts here ---
    # Skip the initial header
    if stream.read(1) == b'"':
        stream.read(3)

    # Begin parsing from the top level. We only need the final object.
    final_obj, _ = parse_level()
    return final_obj

# --- Execution ---
your_byte_array = bytearray(b'"\xaa6\x17\x01\x05event\x02\x02ID"\xaa6\x17\x02\x04Type\x8aSpinAndWin\x02\x04Time\x07`\xdaC}`\xc1\x00\x00\x02\x06Number\x8589308\x02\x08Duration \x14\x02\tHasLevels\x01\x01\x06Market\x01\x03Win\x02\x04Odds\x8236\x00\x01\x03Red\x0c\x812\x00\x01\x05Black\x0c\x812\x00\x01\x05Green\x0c\x8236\x00\x01\x06Dozens\x0c\x813\x00\x01\x07OddEven\x0c\x812\x00\x01\x04HiLo\x0c\x812\x00\x01\x05Split\x0c\x8218\x00\x01\tThreeLine\x0c\x8212\x00\x01\x06Corner\x0c\x819\x00\x01\x0fFirst4Connected\x0c\x819\x00\x01\x07SixLine\x0c\x816\x00\x01\x06Column\x0c\x813\x00\x01\nNeighbours\x0c\x817\x00\x01\x06Sector\x0c\x816\x00\x00\x000"')
decoded_data = decode_custom_binary(your_byte_array)

print("--- Decoded Data ---")
pretty_print_ordered(decoded_data)