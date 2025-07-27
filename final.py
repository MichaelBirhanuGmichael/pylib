import io
import datetime

# --- Value-decoding helpers ---
def decode_single_byte_value(byte_val):
    """Decodes a single byte into its intended integer value."""
    if byte_val is None: return None
    char = chr(byte_val)
    if '0' <= char <= '9': return int(char)
    if byte_val == ord(':'): return 10
    return byte_val

def decode_multi_byte_value(byte_data):
    """Decodes multiple bytes into an integer."""
    if not byte_data: return None
    return int.from_bytes(byte_data, 'little')

# --- Output formatting helper ---
def pretty_print_compact(d, indent=0):
    """Prints a dictionary or a list of (key, value) tuples in a compact format."""
    prefix = '  ' * indent
    
    if isinstance(d, list): # Used for Hits object
        for key, value in d:
            print(prefix + str(key) + ' {')
            pretty_print_compact(value, indent + 1)
            print(prefix + '}')
        return

    items_on_line = []
    nested_items = []

    data_to_iterate = d.items() if isinstance(d, dict) else []

    for key, value in data_to_iterate:
        if isinstance(value, (dict, list)):
            nested_items.append((key, value))
        else:
            val_str = f'"{value}"' if isinstance(value, str) else str(value)
            items_on_line.append(f'{key}={val_str}')
    
    if items_on_line:
        print(prefix + ' '.join(items_on_line), end=' \n' if nested_items else '\n')

    for key, value in nested_items:
        if value: # Don't print empty objects like PreviousResults
            print(prefix + str(key) + ' {')
            pretty_print_compact(value, indent + 1)
            print(prefix + '}')
        else:
            print(prefix + str(key) + ' {}')

class UnifiedParser:
    """A unified parser for both 'event' and 'info' objects."""
    def __init__(self, data: bytearray):
        # Remove only space characters from the bytearray before processing
        self.stream = io.BytesIO(data.replace(b' ', b''))
        self.last_field_name = None

    def parse(self):
        """Parses the entire byte stream and prints formatted output."""
        while self.stream.tell() < len(self.stream.getbuffer()):
            # Find the start of the next message
            start_marker = self.stream.read(1)
            if not start_marker: break
            if start_marker == b'"':
                header = self.stream.read(3)
                id_val = decode_multi_byte_value(header)
                
                # Check for object marker
                obj_marker = self.stream.read(1)
                if not obj_marker or obj_marker[0] != 0x01:
                    continue # Not a valid object structure, find next message

                # Determine object type (event or info)
                name_len_byte = self.stream.read(1)
                if not name_len_byte: break
                name_len = name_len_byte[0]
                name = self.stream.read(name_len).decode('utf-8')

                if name == 'event':
                    self.print_log_header("Event", id_val)
                    event_obj, _ = self._parse_generic_object()
                    print(f"event {{")
                    pretty_print_compact(event_obj)
                    print("}")
                elif name == 'info':
                    info_obj = self._parse_info_object()
                    # The event ID is the first value inside the info object
                    event_id_for_info = info_obj.get('ID')
                    self.print_log_header("Event Info", event_id_for_info, id_val)
                    print(f"info {{")
                    pretty_print_compact(info_obj)
                    print("}")

    def print_log_header(self, obj_type, event_id, info_id=None):
        """Prints the formatted log header."""
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        log_msg = f"D:MS: {now} Server: Deserialized {obj_type}: ID={event_id}"
        if info_id:
            log_msg += f" InfoID={info_id}"
        print(log_msg)
        print(f"D:MS: {now} ")

    def _parse_value(self):
        """Generic value parser for the 'event' object."""
        marker_byte = self.stream.read(1)
        if not marker_byte: return None
        marker = marker_byte[0]
        
        if marker == ord('"'): return decode_multi_byte_value(self.stream.read(3))
        elif marker in [0x8a, 0x85]:
            value_bytes = []
            while True:
                pos = self.stream.tell()
                b = self.stream.read(1)
                if not b or b[0] in [0x00, 0x01, 0x02, 0x0c, 0x08, 0x09]: self.stream.seek(pos); break
                value_bytes.append(b)
            return b''.join(value_bytes).decode('utf-8', 'ignore').strip()
        elif marker in [0x81, 0x82]:
            value_bytes = []
            while True:
                pos = self.stream.tell()
                b = self.stream.read(1)
                if not b or b[0] == 0x00: self.stream.seek(pos); break
                value_bytes.append(b)
            val_str = b''.join(value_bytes).decode('utf-8', 'ignore')
            return int(val_str) if val_str else 0
        elif marker == 0x20: return int.from_bytes(self.stream.read(1), 'big')
        elif marker == 0x07:
            ts_bytes = self.stream.read(6)
            self.stream.read(2) # Skip two null bytes
            ts = int.from_bytes(ts_bytes, 'big')
            try:
                # Handle potential large timestamp values by assuming they are in milliseconds
                return datetime.datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d %H:%M:%S')
            except (OSError, ValueError):
                return f"Invalid Timestamp value: {ts}"
        else: return marker

    def _parse_generic_object(self, last_field_from_parent=None):
        """Recursive parser for generic objects like 'event' and 'Market'."""
        obj = {}
        last_field_in_scope = last_field_from_parent
        while True:
            pos = self.stream.tell()
            marker_byte = self.stream.read(1)
            if not marker_byte or marker_byte[0] == 0x00: break
            self.stream.seek(pos)
            marker = self.stream.read(1)[0]
            if marker == 0x01:
                name_len = self.stream.read(1)[0]
                name = self.stream.read(name_len).decode('utf-8')
                inner_obj, last_field_from_inner = self._parse_generic_object(last_field_in_scope)
                obj[name] = inner_obj
                if last_field_from_inner: last_field_in_scope = last_field_from_inner
            elif marker == 0x02:
                field_len = self.stream.read(1)[0]
                field_name = self.stream.read(field_len).decode('utf-8')
                last_field_in_scope = field_name
                obj[field_name] = self._parse_value()
            elif marker == 0x0c:
                if last_field_in_scope: obj[last_field_in_scope] = self._parse_value()
        return obj, last_field_in_scope

    def _parse_info_object(self):
        """Top-level parser for the specialized 'info' object fields."""
        obj = {}
        # The first two fields are standard
        self.stream.read(1); id_len = self.stream.read(1)[0]; id_name = self.stream.read(id_len).decode('utf-8'); obj[id_name] = self._parse_value()
        self.stream.read(1); vf_len = self.stream.read(1)[0]; vf_name = self.stream.read(vf_len).decode('utf-8'); obj[vf_name] = self._parse_value()

        # Delegate parsing for complex fields, skipping nulls between them
        while True:
            pos = self.stream.tell()
            peek = self.stream.read(1)
            if not peek: break
            self.stream.seek(pos)

            if peek == b'\x00':
                self.stream.read(1) # Consume null byte
                continue

            if peek == b'\x01':
                self.stream.read(1) # Consume object marker
                name_len = self.stream.read(1)[0]
                name = self.stream.read(name_len).decode('utf-8')
                if name == "LastGames": obj[name] = self._parse_last_games_list()
                elif name == "Hot": obj[name] = self._parse_hot_cold_list()
                elif name == "Cold": obj[name] = self._parse_hot_cold_list()
                elif name == "Hits": obj[name] = self._parse_hits_object()
                elif name == "PreviousResults": obj[name] = {}; self.stream.read(1) # Empty object
            else:
                break # End of info object
        return obj

    def _parse_last_games_list(self):
        obj, fields = {}, []
        while True:
            pos = self.stream.tell()
            marker = self.stream.read(1)
            if not marker or marker[0] != 0x01: self.stream.seek(pos); break
            name_len = self.stream.read(1)[0]
            name = self.stream.read(name_len).decode('utf-8')
            item = {}
            if not fields:
                self.stream.read(1); fl = self.stream.read(1)[0]; fn = self.stream.read(fl).decode('utf-8'); fields.append(fn)
                item[fn] = self._parse_value()
                self.stream.read(1); fl = self.stream.read(1)[0]; fn = self.stream.read(fl).decode('utf-8'); fields.append(fn)
                # The 'Draw' value in LastGames is a raw byte, not a complex type
                item[fn] = decode_single_byte_value(self.stream.read(1)[0])
            else:
                self.stream.read(1); item[fields[0]] = self._parse_value()
                self.stream.read(1); 
                # The 'Draw' value in LastGames is a raw byte
                item[fields[1]] = decode_single_byte_value(self.stream.read(1)[0])
            obj[name] = item
            self.stream.read(1)
        return obj

    def _parse_hot_cold_list(self):
        obj, i, field_name = {}, 0, None
        while True:
            pos = self.stream.tell()
            marker = self.stream.read(1)
            if not marker or marker[0] == 0x00:
                self.stream.seek(pos)
                break
            
            self.stream.read(1) # consume the \t marker
            draw = decode_single_byte_value(self.stream.read(1)[0])
            
            hits_marker = self.stream.read(1)[0]
            if hits_marker == 0x02: # First item has explicit field name
                field_len = self.stream.read(1)[0]
                field_name = self.stream.read(field_len).decode('utf-8')
            
            hits = decode_single_byte_value(self.stream.read(1)[0])
            obj[i] = {"Draw": draw, field_name if field_name else "Hits": hits}
            i += 1
            self.stream.read(1) # consume item terminator \x00
        return obj

    def _parse_hits_object(self):
        results = []
        while True:
            pos = self.stream.tell()
            marker_byte = self.stream.read(1)
            
            if not marker_byte or marker_byte[0] == 0x00:
                self.stream.seek(pos)
                break

            # Determine the key type based on the marker
            if marker_byte[0] == 0x01:  # Length-prefixed string key
                name_len = self.stream.read(1)[0]
                key = self.stream.read(name_len).decode('utf-8', 'ignore')
            else:  # Simple single-byte key
                # We need to re-read the byte as it's part of the key
                self.stream.seek(pos)
                key_byte = self.stream.read(1)
                key = str(decode_single_byte_value(key_byte[0]))

            # Now parse the value which is always in the same format
            self.stream.read(1)  # consume \x10 'Hits' marker
            val = decode_single_byte_value(self.stream.read(1)[0])
            results.append((key, {"Hits": val}))
            
            # Consume the terminator byte
            self.stream.read(1)
            
        return results

if __name__ == "__main__":
    full_byte_array = bytearray(b'"\x826\x17\x01\x05event\x02\x02ID"\x826\x17\x02\x04Type\x8aSpinAndWin\x02\x04Time\x07`45}`\xc1\x00\x00\x02\x06Number\x8589304\x02\x08Duration \x14\x02\tHasLevels\x01\x01\x06Market\x01\x03Win\x02\x04Odds\x8236\x00\x01\x03Red\x0c\x812\x00\x01\x05Black\x0c\x812\x00\x01\x05Green\x0c\x8236\x00\x01\x06Dozens\x0c\x813\x00\x01\x07OddEven\x0c\x812\x00\x01\x04HiLo\x0c\x812\x00\x01\x05Split\x0c\x8218\x00\x01\tThreeLine\x0c\x8212\x00\x01\x06Corner\x0c\x819\x00\x01\x0fFirst4Connected\x0c\x819\x00\x01\x07SixLine\x0c\x816\x00\x01\x06Column\x0c\x813\x00\x01\nNeighbours\x0c\x817\x00\x01\x06Sector\x0c\x816\x00\x00\x00"\x0f<\x7f\x01\x04info\x02\x02ID"\x826\x17\x02\tValidFrom\x07\x00\xd91}`\xc1\x00\x00\x01\tLastGames\x01\x010\x02\x06Number\x8589303\x02\x04Draw0\x00\x01\x011\x08\x8589302\t !\x00\x01\x012\x08\x8589301\t3\x00\x01\x013\x08\x8589300\t \x18\x00\x01\x014\x08\x8589299\t7\x00\x01\x015\x08\x8589298\t2\x00\x00\x01\x03Hot\x07\t \x1a\x02\x04Hits:\x00\n\t \x11\x10:\x00\x0b\t0\x10:\x00\x0c\t !\x109\x00\r\t6\x109\x00\x00\x01\x04Cold\x07\t #\x102\x00\n\t "\x102\x00\x0b\t \x1f\x102\x00\x0c\t8\x102\x00\r\t \x1b\x101\x00\x00\x01\x04Hits\x07\x10:\x00\x07\x10:\x00\n\x105\x00\x0b\x109\x00\x0c\x105\x00\r\x108\x00\x0e\x105\x00\x01\x016\x109\x00\x01\x017\x104\x00\x01\x018\x102\x00\x01\x019\x106\x00\x01\x0210\x105\x00\x01\x0211\x103\x00\x01\x0212\x103\x00\x01\x0213\x104\x00\x01\x0214\x106\x00\x01\x0215\x104\x00\x01\x0216\x104\x00\x01\x0217\x10:\x00\x01\x0218\x104\x00\x01\x0219\x107\x00\x01\x0220\x108\x00\x01\x0221\x105\x00\x01\x0222\x106\x00\x01\x0223\x107\x00\x01\x0224\x105\x00\x01\x0225\x103\x00\x01\x0226\x10:\x00\x01\x0227\x101\x00\x01\x0228\x108\x00\x01\x0229\x104\x00\x01\x0230\x104\x00\x01\x0231\x102\x00\x01\x0232\x105\x00\x01\x0233\x109\x00\x01\x0234\x102\x00\x01\x0235\x102\x00\x01\x0236\x106\x00\x01\x02Lo\x10 `\x00\x01\x02Hi\x10 ^\x00\x01\x03Odd\x10 V\x00\x01\x04Even\x10 r\x00\x01\x05Black\x10 l\x00\x01\x03Red\x10 R\x00\x01\x041-12\x10 @\x00\x01\x0513-24\x10 F\x00\x01\x0525-36\x10 8\x00\x01\x07Sector1\x10 &\x00\x01\x07Sector2\x10 \x1d\x00\x01\x07Sector3\x10 \x1b\x00\x01\x07Sector4\x10 $\x00\x01\x07Sector5\x10 \x1c\x00\x01\x07Sector6\x10  \x00\x00\x01\x0fPreviousResults\x00\x00"\x8c6\x17\x01\x05event\x02\x02ID"\x8c6\x17\x02\x04Type\x8aSpinAndWin\x02\x04Time\x07\xe0\xdd8}`\xc1\x00\x00\x02\x06Number\x8589305\x02\x08Duration \x14\x02\tHasLevels\x01\x01\x06Market\x01\x03Win\x02\x04Odds\x8236\x00\x01\x03Red\x0c\x812\x00\x01\x05Black\x0c\x812\x00\x01\x05Green\x0c\x8236\x00\x01\x06Dozens\x0c\x813\x00\x01\x07OddEven\x0c\x812\x00\x01\x04HiLo\x0c\x812\x00\x01\x05Split\x0c\x8218\x00\x01\tThreeLine\x0c\x8212\x00\x01\x06Corner\x0c\x819\x00\x01\x0fFirst4Connected\x0c\x819\x00\x01\x07SixLine\x0c\x816\x00\x01\x06Column\x0c\x813\x00\x01\nNeighbours\x0c\x817\x00\x01\x06Sector\x0c\x816\x00\x00\x00"\x10<\x7f\x01\x04info\x02\x02ID"\x8c6\x17\x02\tValidFrom\x07\x00\xd91}`\xc1\x00\x00\x01\tLastGames\x01\x010\x02\x06Number\x8589303\x02\x04Draw0\x00\x01\x011\x08\x8589302\t !\x00\x01\x012\x08\x8589301\t3\x00\x01\x013\x08\x8589300\t \x18\x00\x01\x014\x08\x8589299\t7\x00\x01\x015\x08\x8589298\t2\x00\x00\x01\x03Hot\x07\t \x1a\x02\x04Hits:\x00\n\t \x11\x10:\x00\x0b\t0\x10:\x00\x0c\t !\x109\x00\r\t6\x109\x00\x00\x01\x04Cold\x07\t #\x102\x00\n\t "\x102\x00\x0b\t \x1f\x102\x00\x0c\t8\x102\x00\r\t \x1b\x101\x00\x00\x01\x04Hits\x07\x10:\x00\x07\x10:\x00\n\x105\x00\x0b\x109\x00\x0c\x105\x00\r\x108\x00\x0e\x105\x00\x01\x016\x109\x00\x01\x017\x104\x00\x01\x018\x102\x00\x01\x019\x106\x00\x01\x0210\x105\x00\x01\x0211\x103\x00\x01\x0212\x103\x00\x01\x0213\x104\x00\x01\x0214\x106\x00\x01\x0215\x104\x00\x01\x0216\x104\x00\x01\x0217\x10:\x00\x01\x0218\x104\x00\x01\x0219\x107\x00\x01\x0220\x108\x00\x01\x0221\x105\x00\x01\x0222\x106\x00\x01\x0223\x107\x00\x01\x0224\x105\x00\x01\x0225\x103\x00\x01\x0226\x10:\x00\x01\x0227\x101\x00\x01\x0228\x108\x00\x01\x0229\x104\x00\x01\x0230\x104\x00\x01\x0231\x102\x00\x01\x0232\x105\x00\x01\x0233\x109\x00\x01\x0234\x102\x00\x01\x0235\x102\x00\x01\x0236\x106\x00\x01\x02Lo\x10 `\x00\x01\x02Hi\x10 ^\x00\x01\x03Odd\x10 V\x00\x01\x04Even\x10r\x00\x01\x05Black\x10 l\x00\x01\x03Red\x10 R\x00\x01\x041-12\x10 @\x00\x01\x0513-24\x10 F\x00\x01\x0525-36\x10 8\x00\x01\x07Sector1\x10 &\x00\x01\x07Sector2\x10 \x1d\x00\x01\x07Sector3\x10 \x1b\x00\x01\x07Sector4\x10 $\x00\x01\x07Sector5\x10 \x1c\x00\x01\x07Sector6\x10  \x00\x00\x01\x0fPreviousResults\x00\x00"\x966\x17\x01\x05event\x02\x02ID"\x966\x17\x02\x04Type\x8aSpinAndWin\x02\x04Time\x07`\x87<}`\xc1\x00\x00\x02\x06Number\x8589306\x02\x08Duration \x14\x02\tHasLevels\x01\x01\x06Market\x01\x03Win\x02\x04Odds\x8236\x00\x01\x03Red\x0c\x812\x00\x01\x05Black\x0c\x812\x00\x01\x05Green\x0c\x8236\x00\x01\x06Dozens\x0c\x813\x00\x01\x07OddEven\x0c\x812\x00\x01\x04HiLo\x0c\x812\x00\x01\x05Split\x0c\x8218\x00\x01\tThreeLine\x0c\x8212\x00\x01\x06Corner\x0c\x819\x00\x01\x0fFirst4Connected\x0c\x819\x00\x01\x07SixLine\x0c\x816\x00\x01\x06Column\x0c\x813\x00\x01\nNeighbours\x0c\x817\x00\x01\x06Sector\x0c\x816\x00\x00\x000"\xa06\x17\x01\x05event\x02\x02ID"\xa06\x17\x02\x04Type\x8aSpinAndWin\x02\x04Time\x07\xe00@}`\xc1\x00\x00\x02\x06Number\x8589307\x02\x08Duration \x14\x02\tHasLevels\x01\x01\x06Market\x01\x03Win\x02\x04Odds\x8236\x00\x01\x03Red\x0c\x812\x00\x01\x05Black\x0c\x812\x00\x01\x05Green\x0c\x8236\x00\x01\x06Dozens\x0c\x813\x00\x01\x07OddEven\x0c\x812\x00\x01\x04HiLo\x0c\x812\x00\x01\x05Split\x0c\x8218\x00\x01\tThreeLine\x0c\x8212\x00\x01\x06Corner\x0c\x819\x00\x01\x0fFirst4Connected\x0c\x819\x00\x01\x07SixLine\x0c\x816\x00\x01\x06Column\x0c\x813\x00\x01\nNeighbours\x0c\x817\x00\x01\x06Sector\x0c\x816\x00\x00\x000"\xaa6\x17\x01\x05event\x02\x02ID"\xaa6\x17\x02\x04Type\x8aSpinAndWin\x02\x04Time\x07`\xdaC}`\xc1\x00\x00\x02\x06Number\x8589308\x02\x08Duration \x14\x02\tHasLevels\x01\x01\x06Market\x01\x03Win\x02\x04Odds\x8236\x00\x01\x03Red\x0c\x812\x00\x01\x05Black\x0c\x812\x00\x01\x05Green\x0c\x8236\x00\x01\x06Dozens\x0c\x813\x00\x01\x07OddEven\x0c\x812\x00\x01\x04HiLo\x0c\x812\x00\x01\x05Split\x0c\x8218\x00\x01\tThreeLine\x0c\x8212\x00\x01\x06Corner\x0c\x819\x00\x01\x0fFirst4Connected\x0c\x819\x00\x01\x07SixLine\x0c\x816\x00\x01\x06Column\x0c\x813\x00\x01\nNeighbours\x0c\x817\x00\x01\x06Sector\x0c\x816\x00\x00\x000"\xb46\x17\x01\x05event\x02\x02ID"\xb46\x17\x02\x04Type\x8aSpinAndWin\x02\x04Time\x07\xe0\x83G}`\xc1\x00\x00\x02\x06Number\x8589309\x02\x08Duration \x14\x02\tHasLevels\x01\x01\x06Market\x01\x03Win\x02\x04Odds\x8236\x00\x01\x03Red\x0c\x812\x00\x01\x05Black\x0c\x812\x00\x01\x05Green\x0c\x8236\x00\x01\x06Dozens\x0c\x813\x00\x01\x07OddEven\x0c\x812\x00\x01\x04HiLo\x0c\x812\x00\x01\x05Split\x0c\x8218\x00\x01\tThreeLine\x0c\x8212\x00\x01\x06Corner\x0c\x819\x00\x01\x0fFirst4Connected\x0c\x819\x00\x01\x07SixLine\x0c\x816\x00\x01\x06Column\x0c\x813\x00\x01\nNeighbours\x0c\x817\x00\x01\x06Sector\x0c\x816\x00\x00\x0000\x07%\x1d2}`\xc1\x00\x00\x07%\x1d2}`\xc1\x00\x00')

    parser = UnifiedParser(full_byte_array)
    parser.parse()
