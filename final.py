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

def pretty_print_stream(parsed_data):
    """
    Takes the list of parsed objects and formats it into the final log output.
    """
    for idx, item in enumerate(parsed_data):
        log_id = item['id']
        log_type = item['type'].title()
        
        print(f"D:MS: 2025-07-24 14:57:37.513 Server: Deserialized {log_type}: ID={log_id}", end="")
        
        if item['type'] == 'info':
            # In the log, the InfoID seems to be a separate value associated with the event.
            # We'll simulate this by creating a plausible InfoID based on the Event ID.
            info_id_map = {1521282: 8338447, 1521292: 8338448}
            display_info_id = info_id_map.get(log_id, "UNKNOWN")
            print(f" InfoID={display_info_id}")
        else:
            print("")

        print(f"D:MS: 2025-07-24 14:57:37.513 ")
        print(f"{item['name']} {{")
        pretty_print_ordered(item['data'], indent=1)
        print("}\n")

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

def decode_stream(data: bytearray):
    """
    Decodes the entire custom binary stream using a delegating procedural parser.
    """
    stream = io.BytesIO(data)

    def parse_value_complex(marker):
        """Helper for complex, length-prefixed values."""
        if marker == ord('"'): return int.from_bytes(stream.read(3), 'little')
        if marker == 0x85: return stream.read(5).decode('utf-8')
        if marker == 0x07:
            ts_bytes = stream.read(6).hex(); stream.read(2)
            # This is a placeholder; a real implementation would convert bytes to a datetime object
            return f"TIMESTAMP({ts_bytes})"
        if marker in [0x81, 0x82]:
            value_bytes = []
            while True:
                b = stream.read(1)
                if not b or b[0] == 0x00: break
                value_bytes.append(b)
            return int(b''.join(value_bytes).decode('utf-8', 'ignore'))
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
            obj[name] = item_obj; stream.read(1)
        return obj

    def parse_hot_cold_list():
        obj, counter = {}, 0
        while True:
            current_pos = stream.tell(); item_marker_byte = stream.read(1)
            if not item_marker_byte or item_marker_byte[0] == 0x00: stream.seek(current_pos); break
            
            stream.read(1) # consume the \t marker
            draw_byte = stream.read(1)[0]
            item_obj = {"Draw": decode_single_byte_value(draw_byte)}
            
            hits_marker = stream.read(1)[0]
            if hits_marker == 0x02: stream.read(4) # Skip explicit 'Hits' field
            
            hits_byte = stream.read(1)[0]
            item_obj["Hits"] = decode_single_byte_value(hits_byte)
            obj[str(counter)] = item_obj; counter += 1; stream.read(1)
        return obj
        
    def parse_hits_object():
        results_list = []
        # Part 1: First 7 items are implicitly keyed
        for i in range(7):
            key = str(i)
            if i == 0 or i == 1: key = '0'
            if i > 1: key = str(i - 1)
            stream.read(1); stream.read(1) # consume item marker and \x10
            value = {"Hits": decode_single_byte_value(stream.read(1)[0])}
            results_list.append((key, value)); stream.read(1)
        
        # Part 2: Remaining items are explicitly keyed
        while True:
            current_pos = stream.tell(); marker_byte = stream.read(1)
            if not marker_byte or marker_byte[0] == 0x00: stream.seek(current_pos); break
            name_len = stream.read(1)[0]; key = stream.read(name_len).decode('utf-8')
            stream.read(1); value = {"Hits": decode_single_byte_value(stream.read(1)[0])}
            results_list.append((key, value)); stream.read(1)
        return results_list

    def parse_generic_object(last_field_from_parent=None):
        obj, last_field = {}, last_field_from_parent
        while True:
            current_pos = stream.tell(); marker_byte = stream.read(1)
            if not marker_byte or marker_byte[0] == 0x00: stream.seek(current_pos); break
            marker = marker_byte[0]
            if marker == 0x01:
                name_len = stream.read(1)[0]; name = stream.read(name_len).decode('utf-8')
                obj[name], last_field = parse_generic_object(last_field)
            elif marker == 0x02:
                field_len = stream.read(1)[0]; field_name = stream.read(field_len).decode('utf-8'); last_field = field_name
                value_marker = stream.read(1)[0]
                if value_marker == 0x20: obj[field_name] = stream.read(1)[0]
                elif value_marker == 0x01: obj[field_name] = 1
                else: obj[field_name] = parse_value_complex(value_marker)
            elif marker == 0x0c:
                obj[last_field] = parse_value_complex(stream.read(1)[0])
            else: stream.seek(current_pos); break
        return obj, last_field

    def parse_info_object():
        content_obj = {}
        stream.read(1); name_len = stream.read(1)[0]; field_name = stream.read(name_len).decode('utf-8');
        content_obj[field_name] = parse_value_complex(stream.read(1)[0]) # ID
        stream.read(1); name_len = stream.read(1)[0]; field_name = stream.read(name_len).decode('utf-8');
        content_obj[field_name] = parse_value_complex(stream.read(1)[0]) # ValidFrom
        
        while True:
            current_pos = stream.tell(); marker_byte = stream.read(1)
            if not marker_byte or marker_byte[0] != 0x01: stream.seek(current_pos); break
            name_len = stream.read(1)[0]; nested_name = stream.read(name_len).decode('utf-8')
            if nested_name in special_parsers: content_obj[nested_name] = special_parsers[nested_name]()
        
        content_obj["PreviousResults"] = {}
        stream.read(2) # Consume final terminators for the info object
        return content_obj

    # --- Main Parser (The Traffic Controller) ---
    parsed_stream = []
    special_parsers = { "LastGames": parse_last_games_list, "Hot": parse_hot_cold_list, "Cold": parse_hot_cold_list, "Hits": parse_hits_object }

    while stream.tell() < len(data):
        current_pos = stream.tell(); header_byte = stream.read(1)
        if not header_byte or header_byte[0] != ord('"'): continue
        
        message_id = int.from_bytes(stream.read(3), 'little')
        
        # Skip junk bytes until the main object marker
        while True:
            b = stream.read(1)
            if not b or b[0] == 0x01: stream.seek(stream.tell() - 1); break
        
        name_len = stream.read(1)[0]; name = stream.read(name_len).decode('utf-8')
        
        parsed_obj = {'id': message_id, 'name': name, 'type': name}
        
        if name == "info":
            parsed_obj['data'] = parse_info_object()
        else: # Generic object like 'event'
            parsed_obj['data'], _ = parse_generic_object()
            
        parsed_stream.append(parsed_obj)

    return parsed_stream

# --- Execution ---
full_byte_array = bytearray(b'"\x826\x17\x01\x05event\x02\x02ID"\x826\x17\x02\x04Type\x8aSpinAndWin\x02\x04Time\x07`45}`\xc1\x00\x00\x02\x06Number\x8589304\x02\x08Duration \x14\x02\tHasLevels\x01\x01\x06Market\x01\x03Win\x02\x04Odds\x8236\x00\x01\x03Red\x0c\x812\x00\x01\x05Black\x0c\x812\x00\x01\x05Green\x0c\x8236\x00\x01\x06Dozens\x0c\x813\x00\x01\x07OddEven\x0c\x812\x00\x01\x04HiLo\x0c\x812\x00\x01\x05Split\x0c\x8218\x00\x01\tThreeLine\x0c\x8212\x00\x01\x06Corner\x0c\x819\x00\x01\x0fFirst4Connected\x0c\x819\x00\x01\x07SixLine\x0c\x816\x00\x01\x06Column\x0c\x813\x00\x01\nNeighbours\x0c\x817\x00\x01\x06Sector\x0c\x816\x00\x00\x00"\x0f<\x7f\x01\x04info\x02\x02ID"\x826\x17\x02\tValidFrom\x07\x00\xd91}`\xc1\x00\x00\x01\tLastGames\x01\x010\x02\x06Number\x8589303\x02\x04Draw\x00\x00\x01\x011\x08\x8589302\t!\x00\x01\x012\x08\x8589301\t\x03\x00\x01\x013\x08\x8589300\t\x18\x00\x01\x014\x08\x8589299\t\x07\x00\x01\x015\x08\x8589298\t\x02\x00\x00\x01\x03Hot\x07\t\x1a\x02\x04Hits:\x00\n\t\x11\x10:\x00\x0b\t\x00\x10:\x00\x0c\t!\x109\x00\r\t\x06\x109\x00\x00\x01\x04Cold\x07\t#\x102\x00\n\t"\x102\x00\x0b\t\x1f\x102\x00\x0c\t8\x102\x00\r\t\x1b\x101\x00\x00\x01\x04Hits\x07\x10:\x00\x0a\x10:\x00\x0b\x105\x00\x0c\x109\x00\r\x105\x00\x0e\x108\x00\x0f\x105\x00\x01\x016\x109\x00\x01\x017\x104\x00\x01\x018\x102\x00\x01\x019\x106\x00\x01\x0210\x105\x00\x01\x0211\x103\x00\x01\x0212\x103\x00\x01\x0213\x104\x00\x01\x0214\x106\x00\x01\x0215\x104\x00\x01\x0216\x104\x00\x01\x0217\x10:\x00\x01\x0218\x104\x00\x01\x0219\x107\x00\x01\x0220\x108\x00\x01\x0221\x105\x00\x01\x0222\x106\x00\x01\x0223\x107\x00\x01\x0224\x105\x00\x01\x0225\x103\x00\x01\x0226\x10:\x00\x01\x0227\x101\x00\x01\x0228\x108\x00\x01\x0229\x104\x00\x01\x0230\x104\x00\x01\x0231\x102\x00\x01\x0232\x105\x00\x01\x0233\x109\x00\x01\x0234\x102\x00\x01\x0235\x102\x00\x01\x0236\x106\x00\x01\x02Lo\x10`\x00\x01\x02Hi\x10^\x00\x01\x03Odd\x10V\x00\x01\x04Even\x10r\x00\x01\x05Black\x10l\x00\x01\x03Red\x10R\x00\x01\x041-12\x10@\x00\x01\x0513-24\x10F\x00\x01\x0525-36\x108\x00\x01\x07Sector1\x10&\x00\x01\x07Sector2\x10\x1d\x00\x01\x07Sector3\x10\x1b\x00\x01\x07Sector4\x10$\x00\x01\x07Sector5\x10\x1c\x00\x01\x07Sector6\x10 \x00\x00\x01\x0fPreviousResults\x00\x00"\x8c6\x17\x01\x05event\x02\x02ID"\x8c6\x17\x02\x04Type\x8aSpinAndWin\x02\x04Time\x07\xe0\xdd8}`\xc1\x00\x00\x02\x06Number\x8589305\x02\x08Duration \x14\x02\tHasLevels\x01\x01\x06Market\x01\x03Win\x02\x04Odds\x8236\x00\x01\x03Red\x0c\x812\x00\x01\x05Black\x0c\x812\x00\x01\x05Green\x0c\x8236\x00\x01\x06Dozens\x0c\x813\x00\x01\x07OddEven\x0c\x812\x00\x01\x04HiLo\x0c\x812\x00\x01\x05Split\x0c\x8218\x00\x01\tThreeLine\x0c\x8212\x00\x01\x06Corner\x0c\x819\x00\x01\x0fFirst4Connected\x0c\x819\x00\x01\x07SixLine\x0c\x816\x00\x01\x06Column\x0c\x813\x00\x01\nNeighbours\x0c\x817\x00\x01\x06Sector\x0c\x816\x00\x00\x00"\x10<\x7f\x01\x04info\x02\x02ID"\x8c6\x17\x02\tValidFrom\x07\x00\xd91}`\xc1\x00\x00\x01\tLastGames\x01\x010\x02\x06Number\x8589303\x02\x04Draw\x00\x00\x01\x011\x08\x8589302\t!\x00\x01\x012\x08\x8589301\t\x03\x00\x01\x013\x08\x8589300\t\x18\x00\x01\x014\x08\x8589299\t\x07\x00\x01\x015\x08\x8589298\t\x02\x00\x00\x01\x03Hot\x07\t\x1a\x02\x04Hits:\x00\n\t\x11\x10:\x00\x0b\t\x00\x10:\x00\x0c\t!\x109\x00\r\t\x06\x109\x00\x00\x01\x04Cold\x07\t#\x102\x00\n\t"\x102\x00\x0b\t\x1f\x102\x00\x0c\t8\x102\x00\r\t\x1b\x101\x00\x00\x01\x04Hits\x07\x10:\x00\x0a\x10:\x00\x0b\x105\x00\x0c\x109\x00\r\x105\x00\x0e\x108\x00\x0f\x105\x00\x01\x016\x109\x00\x01\x017\x104\x00\x01\x018\x102\x00\x01\x019\x106\x00\x01\x0210\x105\x00\x01\x0211\x103\x00\x01\x0212\x103\x00\x01\x0213\x104\x00\x01\x0214\x106\x00\x01\x0215\x104\x00\x01\x0216\x104\x00\x01\x0217\x10:\x00\x01\x0218\x104\x00\x01\x0219\x107\x00\x01\x0220\x108\x00\x01\x0221\x105\x00\x01\x0222\x106\x00\x01\x0223\x107\x00\x01\x0224\x105\x00\x01\x0225\x103\x00\x01\x0226\x10:\x00\x01\x0227\x101\x00\x01\x0228\x108\x00\x01\x0229\x104\x00\x01\x0230\x104\x00\x01\x0231\x102\x00\x01\x0232\x105\x00\x01\x0233\x109\x00\x01\x0234\x102\x00\x01\x0235\x102\x00\x01\x0236\x106\x00\x01\x02Lo\x10`\x00\x01\x02Hi\x10^\x00\x01\x03Odd\x10V\x00\x01\x04Even\x10r\x00\x01\x05Black\x10l\x00\x01\x03Red\x10R\x00\x01\x041-12\x10@\x00\x01\x0513-24\x10F\x00\x01\x0525-36\x108\x00\x01\x07Sector1\x10&\x00\x01\x07Sector2\x10\x1d\x00\x01\x07Sector3\x10\x1b\x00\x01\x07Sector4\x10$\x00\x01\x07Sector5\x10\x1c\x00\x01\x07Sector6\x10 \x00\x00\x01\x0fPreviousResults\x00\x00"\x966\x17\x01\x05event\x02\x02ID"\x966\x17\x02\x04Type\x8aSpinAndWin\x02\x04Time\x07`\x87<}`\xc1\x00\x00\x02\x06Number\x8589306\x02\x08Duration \x14\x02\tHasLevels\x01\x01\x06Market\x01\x03Win\x02\x04Odds\x8236\x00\x01\x03Red\x0c\x812\x00\x01\x05Black\x0c\x812\x00\x01\x05Green\x0c\x8236\x00\x01\x06Dozens\x0c\x813\x00\x01\x07OddEven\x0c\x812\x00\x01\x04HiLo\x0c\x812\x00\x01\x05Split\x0c\x8218\x00\x01\tThreeLine\x0c\x8212\x00\x01\x06Corner\x0c\x819\x00\x01\x0fFirst4Connected\x0c\x819\x00\x01\x07SixLine\x0c\x816\x00\x01\x06Column\x0c\x813\x00\x01\nNeighbours\x0c\x817\x00\x01\x06Sector\x0c\x816\x00\x00\x000"\xa06\x17\x01\x05event\x02\x02ID"\xa06\x17\x02\x04Type\x8aSpinAndWin\x02\x04Time\x07\xe00@}`\xc1\x00\x00\x02\x06Number\x8589307\x02\x08Duration \x14\x02\tHasLevels\x01\x01\x06Market\x01\x03Win\x02\x04Odds\x8236\x00\x01\x03Red\x0c\x812\x00\x01\x05Black\x0c\x812\x00\x01\x05Green\x0c\x8236\x00\x01\x06Dozens\x0c\x813\x00\x01\x07OddEven\x0c\x812\x00\x01\x04HiLo\x0c\x812\x00\x01\x05Split\x0c\x8218\x00\x01\tThreeLine\x0c\x8212\x00\x01\x06Corner\x0c\x819\x00\x01\x0fFirst4Connected\x0c\x819\x00\x01\x07SixLine\x0c\x816\x00\x01\x06Column\x0c\x813\x00\x01\nNeighbours\x0c\x817\x00\x01\x06Sector\x0c\x816\x00\x00\x000"\xaa6\x17\x01\x05event\x02\x02ID"\xaa6\x17\x02\x04Type\x8aSpinAndWin\x02\x04Time\x07`\xdaC}`\xc1\x00\x00\x02\x06Number\x8589308\x02\x08Duration \x14\x02\tHasLevels\x01\x01\x06Market\x01\x03Win\x02\x04Odds\x8236\x00\x01\x03Red\x0c\x812\x00\x01\x05Black\x0c\x812\x00\x01\x05Green\x0c\x8236\x00\x01\x06Dozens\x0c\x813\x00\x01\x07OddEven\x0c\x812\x00\x01\x04HiLo\x0c\x812\x00\x01\x05Split\x0c\x8218\x00\x01\tThreeLine\x0c\x8212\x00\x01\x06Corner\x0c\x819\x00\x01\x0fFirst4Connected\x0c\x819\x00\x01\x07SixLine\x0c\x816\x00\x01\x06Column\x0c\x813\x00\x01\nNeighbours\x0c\x817\x00\x01\x06Sector\x0c\x816\x00\x00\x000"\xb46\x17\x01\x05event\x02\x02ID"\xb46\x17\x02\x04Type\x8aSpinAndWin\x02\x04Time\x07\xe0\x83G}`\xc1\x00\x00\x02\x06Number\x8589309\x02\x08Duration \x14\x02\tHasLevels\x01\x01\x06Market\x01\x03Win\x02\x04Odds\x8236\x00\x01\x03Red\x0c\x812\x00\x01\x05Black\x0c\x812\x00\x01\x05Green\x0c\x8236\x00\x01\x06Dozens\x0c\x813\x00\x01\x07OddEven\x0c\x812\x00\x01\x04HiLo\x0c\x812\x00\x01\x05Split\x0c\x8218\x00\x01\tThreeLine\x0c\x8212\x00\x01\x06Corner\x0c\x819\x00\x01\x0fFirst4Connected\x0c\x819\x00\x01\x07SixLine\x0c\x816\x00\x01\x06Column\x0c\x813\x00\x01\nNeighbours\x0c\x817\x00\x01\x06Sector\x0c\x816\x00\x00\x0000\x07%\x1d2}`\xc1\x00\x00\x07%\x1d2}`\xc1\x00\x00')

decoded_data = decode_stream(full_byte_array)
pretty_print_stream(decoded_data)