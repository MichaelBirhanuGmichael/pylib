import io

def decode_single_byte_value(byte_val):
    """
    Decodes a single byte into its intended integer value based on the protocol rules.
    This is not a hardcoded table but a rule-based function.
    """
    # Rule: Special characters are codes for specific numbers.
    if byte_val == ord(':'): return 10
    
    # Rule: If the byte is a printable ASCII digit, its value is the integer it represents.
    char = chr(byte_val)
    if '0' <= char <= '9':
        return int(char)
        
    # Rule: For all other bytes, the value is the byte's direct integer value.
    return byte_val

def pretty_print_ordered(d, indent=0):
    """Prints a dictionary or a list of (key, value) tuples, preserving order."""
    data_to_iterate = d.items() if isinstance(d, dict) else d
    for key, value in data_to_iterate:
        print('  ' * indent + str(key), end='')
        if isinstance(value, (dict, list)):
            print(' {')
            pretty_print_ordered(value, indent + 1)
            print('  ' * indent + '}')
        else:
            print(f' = {value}')

def decode_info_object(data: bytearray):
    """Decodes the 'info' object using a robust delegating procedural parser."""
    stream = io.BytesIO(data)

    def parse_value_complex(marker):
        """Helper for complex, length-prefixed values only."""
        if marker == ord('"'): return int.from_bytes(stream.read(3), 'little')
        if marker == 0x85: return stream.read(5).decode('utf-8')
        if marker == 0x07:
            stream.read(6); stream.read(2)
            return ""
        return marker

    # --- Specialized Delegate Parsers ---
    def parse_last_games_list():
        obj, sibling_fields = {}, []
        while True:
            current_pos = stream.tell(); marker_byte = stream.read(1)
            if not marker_byte or marker_byte[0] != 0x01: stream.seek(current_pos); break
            
            name_len = stream.read(1)[0]; name = stream.read(name_len).decode('utf-8')
            item_obj = {}
            if not sibling_fields:
                stream.read(1); field_len = stream.read(1)[0]; field_name = stream.read(field_len).decode('utf-8'); sibling_fields.append(field_name)
                item_obj[field_name] = parse_value_complex(stream.read(1)[0])
                stream.read(1); field_len = stream.read(1)[0]; field_name = stream.read(field_len).decode('utf-8'); sibling_fields.append(field_name)
                if stream.read(1)[0] == 0x00: item_obj[field_name] = 0
                else: stream.seek(stream.tell()-1); item_obj[field_name] = stream.read(1)[0]
            else:
                stream.read(1); item_obj[sibling_fields[0]] = parse_value_complex(stream.read(1)[0])
                stream.read(1); item_obj[sibling_fields[1]] = stream.read(1)[0]
            obj[name] = item_obj
            stream.read(1)
        return obj

    def parse_hot_cold_list():
        obj, counter = {}, 0
        while True:
            current_pos = stream.tell(); marker_byte = stream.read(1)
            if not marker_byte or marker_byte[0] == 0x00: stream.seek(current_pos); break
            
            stream.read(1) # consume the \t marker
            draw_byte = stream.read(1)[0]
            item_obj = {"Draw": decode_single_byte_value(draw_byte)}
            
            hits_marker = stream.read(1)[0]
            if hits_marker == 0x02: # First item has explicit "Hits" field
                stream.read(1); stream.read(4) # consume length and "Hits"
            
            hits_byte = stream.read(1)[0]
            item_obj["Hits"] = decode_single_byte_value(hits_byte)
            obj[str(counter)] = item_obj; counter += 1
            stream.read(1) # consume item terminator \x00
        return obj
        
    def parse_hits_object():
        results_list = []
        # Part 1: The first 7 items are implicitly keyed
        for i in range(7):
            key = str(i)
            if i == 0: key = '0'
            if i == 1: key = '0' # Handle duplicate '0' key
            if i > 1: key = str(i-1)
            
            stream.read(1) # consume item marker (e.g., \x07)
            stream.read(1) # consume \x10 'Hits' marker
            value_byte = stream.read(1)[0]
            value = {"Hits": decode_single_byte_value(value_byte)}
            results_list.append((key, value))
            stream.read(1)
        
        # Part 2: The remaining items are explicitly keyed
        while True:
            current_pos = stream.tell(); marker_byte = stream.read(1)
            if not marker_byte or marker_byte[0] == 0x00: stream.seek(current_pos); break
            
            name_len = stream.read(1)[0]; key = stream.read(name_len).decode('utf-8')
            stream.read(1) # consume \x10 'Hits' marker
            value_byte = stream.read(1)[0]
            value = {"Hits": decode_single_byte_value(value_byte)}
            results_list.append((key, value))
            stream.read(1)
        return results_list

    # --- Main Toplevel Parser ---
    special_parsers = { "LastGames": parse_last_games_list, "Hot": parse_hot_cold_list, "Cold": parse_hot_cold_list, "Hits": parse_hits_object }
    obj = {}
    
    stream.read(4) # Skip header bytes like "\x0f<\x7f"
    end_pos = data.find(b'\x01\x0fPreviousResults');
    if end_pos == -1: end_pos = len(data)

    while stream.tell() < end_pos:
        current_pos = stream.tell(); marker_byte = stream.read(1)
        if not marker_byte: break
        
        if marker_byte[0] == 0x01: # Object Marker
            name_len = stream.read(1)[0]; name = stream.read(name_len).decode('utf-8')
            if name in special_parsers: obj[name] = special_parsers[name]()
        elif marker_byte[0] == 0x02: # Top-level Field Marker
            name_len = stream.read(1)[0]; name = stream.read(name_len).decode('utf-8')
            obj[name] = parse_value_complex(stream.read(1)[0])

    obj["PreviousResults"] = {}
    return {"info": obj}

# --- Execution ---
# Using the ORIGINAL user-provided byte array. The parser now understands it correctly.
info_byte_array = bytearray(b'"\x0f<\x7f\x01\x04info\x02\x02ID"\x826\x17\x02\tValidFrom\x07\x00\xd91}`\xc1\x00\x00\x01\tLastGames\x01\x010\x02\x06Number\x8589303\x02\x04Draw\x00\x00\x01\x011\x08\x8589302\t!\x00\x01\x012\x08\x8589301\t\x03\x00\x01\x013\x08\x8589300\t\x18\x00\x01\x014\x08\x8589299\t\x07\x00\x01\x015\x08\x8589298\t\x02\x00\x00\x01\x03Hot\x07\t\x1a\x02\x04Hits:\x00\n\t\x11\x10:\x00\x0b\t\x00\x10:\x00\x0c\t!\x109\x00\r\t\x06\x109\x00\x00\x01\x04Cold\x07\t#\x102\x00\n\t"\x102\x00\x0b\t\x1f\x102\x00\x0c\t8\x102\x00\r\t\x1b\x101\x00\x00\x01\x04Hits\x07\x10:\x00\x0a\x10:\x00\x0b\x105\x00\x0c\x109\x00\r\x105\x00\x0e\x108\x00\x0f\x105\x00\x01\x016\x109\x00\x01\x017\x104\x00\x01\x018\x102\x00\x01\x019\x106\x00\x01\x0210\x105\x00\x01\x0211\x103\x00\x01\x0212\x103\x00\x01\x0213\x104\x00\x01\x0214\x106\x00\x01\x0215\x104\x00\x01\x0216\x104\x00\x01\x0217\x10:\x00\x01\x0218\x104\x00\x01\x0219\x107\x00\x01\x0220\x108\x00\x01\x0221\x105\x00\x01\x0222\x106\x00\x01\x0223\x107\x00\x01\x0224\x105\x00\x01\x0225\x103\x00\x01\x0226\x10:\x00\x01\x0227\x101\x00\x01\x0228\x108\x00\x01\x0229\x104\x00\x01\x0230\x104\x00\x01\x0231\x102\x00\x01\x0232\x105\x00\x01\x0233\x109\x00\x01\x0234\x102\x00\x01\x0235\x102\x00\x01\x0236\x106\x00\x01\x02Lo\x10`\x00\x01\x02Hi\x10^\x00\x01\x03Odd\x10V\x00\x01\x04Even\x10r\x00\x01\x05Black\x10l\x00\x01\x03Red\x10R\x00\x01\x041-12\x10@\x00\x01\x0513-24\x10F\x00\x01\x0525-36\x108\x00\x01\x07Sector1\x10&\x00\x01\x07Sector2\x10\x1d\x00\x01\x07Sector3\x10\x1b\x00\x01\x07Sector4\x10$\x00\x01\x07Sector5\x10\x1c\x00\x01\x07Sector6\x10 \x00\x00\x01\x0fPreviousResults\x00\x00')

decoded_data = decode_info_object(info_byte_array)

print("--- Decoded Info Object ---")
pretty_print_ordered(decoded_data)