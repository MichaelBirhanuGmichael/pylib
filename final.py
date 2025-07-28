import io
from datetime import datetime
import struct

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
        if value: # Recursively print non-empty nested objects
            print(prefix + str(key) + ' {')
            pretty_print_compact(value, indent + 1)
            print(prefix + '}')
        else: # Print empty objects on a single line, e.g., "PreviousResults {}"
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
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
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
                return datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d %H:%M:%S')
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
                name = self.stream.read(name_len).decode('utf-8', 'ignore')
                inner_obj, last_field_from_inner = self._parse_generic_object(last_field_in_scope)
                obj[name] = inner_obj
                if last_field_from_inner: last_field_in_scope = last_field_from_inner
            elif marker == 0x02:
                field_len = self.stream.read(1)[0]
                field_name = self.stream.read(field_len).decode('utf-8', 'ignore')
                last_field_in_scope = field_name
                obj[field_name] = self._parse_value()
            elif marker == 0x0c:
                if last_field_in_scope: obj[last_field_in_scope] = self._parse_value()
        return obj, last_field_in_scope

    def _parse_info_object(self):
        """Top-level parser for the specialized 'info' object fields."""
        obj = {}
        # The first two fields are standard
        self.stream.read(1); id_len = self.stream.read(1)[0]; id_name = self.stream.read(id_len).decode('utf-8', 'ignore'); obj[id_name] = self._parse_value()
        self.stream.read(1); vf_len = self.stream.read(1)[0]; vf_name = self.stream.read(vf_len).decode('utf-8', 'ignore'); obj[vf_name] = self._parse_value()

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
                name = self.stream.read(name_len).decode('utf-8', 'ignore')
                if name == "PreviousResults":
                    obj[name] = {}
                    self.stream.read(1) # Consume the empty object's terminator
                elif name == "LastGames": obj[name] = self._parse_last_games_list()
                elif name == "Hot": obj[name] = self._parse_hot_cold_list()
                elif name == "Cold": obj[name] = self._parse_hot_cold_list()
                elif name == "Hits": obj[name] = self._parse_hits_object()
            else:
                break # End of info object
        return obj

    def _parse_last_games_list(self):
        obj, fields = {}, []
        while True:
            pos = self.stream.tell()
            marker = self.stream.read(1)
            if not marker or marker[0] != 0x01:
                self.stream.seek(pos)
                break

            name_len = self.stream.read(1)[0]
            name = self.stream.read(name_len).decode('utf-8', 'ignore')
            item = {}
            consumed_terminator = False

            if not fields:
                # First item in the list defines the field names and has a unique structure.
                self.stream.read(1) # Consume field marker (\x02)
                fl = self.stream.read(1)[0]
                fn = self.stream.read(fl).decode('utf-8', 'ignore')
                fields.append(fn)
                item[fn] = self._parse_value()

                self.stream.read(1) # Consume field marker (\x02)
                fl = self.stream.read(1)[0]
                fn = self.stream.read(fl).decode('utf-8', 'ignore')
                fields.append(fn)
                
                # The 'Draw' value for the first item can be multi-byte and is terminated by \x00
                value_bytes = []
                while True:
                    b = self.stream.read(1)
                    if not b or b[0] == 0x00:
                        consumed_terminator = True
                        break
                    value_bytes.append(b)
                val_str = b''.join(value_bytes).decode('utf-8', 'ignore').strip()
                
                # Try to convert to int, otherwise keep as string
                try:
                    item[fn] = int(val_str)
                except (ValueError, TypeError):
                    item[fn] = val_str if val_str else 0

            else:
                # Subsequent items use a more compact structure with different markers.
                marker1 = self.stream.read(1)
                if not marker1 or marker1[0] != 0x08:
                    self.stream.seek(pos) # Not the expected structure, so we stop.
                    break
                
                item[fields[0]] = self._parse_value()

                marker2 = self.stream.read(1)
                if not marker2 or marker2[0] != 0x09: # Tab character
                    self.stream.seek(pos) # Unexpected, stop.
                    break
                
                item[fields[1]] = decode_single_byte_value(self.stream.read(1)[0])
            
            obj[name] = item
            if not consumed_terminator:
                self.stream.read(1) # Consume the item terminator byte (\x00)
        return obj

    def _parse_hot_cold_list(self):
        obj, i = {}, 0
        field_name = "Hits"  # Default field name
        while True:
            pos = self.stream.tell()
            
            # Peek ahead to see if we've reached the start of a new named object
            peek_byte = self.stream.read(1)
            if not peek_byte or peek_byte == b'\x01':
                self.stream.seek(pos) # This is the next object, so stop
                break
            
            self.stream.seek(pos) # Rewind to process the item

            # The first byte is an index/key, which we can ignore for the output dict key
            self.stream.read(1)
            
            # The second byte should be a tab separator
            tab = self.stream.read(1)
            if not tab or tab != b'\t':
                self.stream.seek(pos); break # Unexpected structure

            draw_byte = self.stream.read(1)
            if not draw_byte: break
            draw = decode_single_byte_value(draw_byte[0])

            hits = 0
            marker_byte = self.stream.read(1)
            if not marker_byte: break

            if marker_byte[0] == 0x02:  # Explicit field name
                field_len = self.stream.read(1)[0]
                field_name = self.stream.read(field_len).decode('utf-8', 'ignore')
                hits_byte = self.stream.read(1)
                if not hits_byte: break
                hits = decode_single_byte_value(hits_byte[0])
            elif marker_byte[0] == 0x10:  # Implicit 'Hits'
                hits_byte = self.stream.read(1)
                if not hits_byte: break
                hits = decode_single_byte_value(hits_byte[0])
            else:
                # This case is likely an error in parsing, let's rewind and break
                self.stream.seek(pos)
                break

            obj[i] = {"Draw": draw, field_name: hits}
            i += 1
            
            # Consume the item terminator
            term_byte = self.stream.read(1)
            if not term_byte or term_byte[0] != 0x00:
                # We didn't find a terminator, so we probably read too far.
                self.stream.seek(self.stream.tell() - 1)
                break
        return obj

    def _parse_hits_object(self):
        results = []
        i = 0
        while True:
            pos = self.stream.tell()

            peek_byte = self.stream.read(1)
            if not peek_byte or peek_byte == b'\x00':
                self.stream.seek(pos)
                break
            
            if peek_byte == b'\x01':
                name_peek_pos = self.stream.tell()
                name_len_byte = self.stream.read(1)
                if name_len_byte:
                    name_len = name_len_byte[0]
                    if len(self.stream.getbuffer()) >= self.stream.tell() + name_len:
                        name = self.stream.read(name_len).decode('utf-8', 'ignore')
                        if name == "PreviousResults":
                            self.stream.seek(pos)
                            break
                self.stream.seek(pos)

            self.stream.seek(pos)

            key_byte = self.stream.read(1)
            if not key_byte: break

            key = None
            if key_byte == b'\x01':
                key_len_byte = self.stream.read(1)
                if not key_len_byte: break
                key_len = key_len_byte[0]
                key = self.stream.read(key_len).decode('utf-8', 'ignore')
            else:
                key = str(i)

            marker_byte = self.stream.read(1)
            if not marker_byte or marker_byte != b'\x10':
                self.stream.seek(pos)
                break

            value_bytes = []
            while True:
                b = self.stream.read(1)
                if not b or b == b'\x00':
                    break
                value_bytes.append(b)
            
            val = 0
            if value_bytes:
                if len(value_bytes) == 1:
                     val = decode_single_byte_value(value_bytes[0][0])
                else:
                    val_str = b''.join(value_bytes).decode('utf-8', 'ignore')
                    try:
                        val = int(val_str)
                    except (ValueError, TypeError):
                        val = val_str
            
            results.append((key, {"Hits": val}))
            i += 1
                
        return results

if __name__ == "__main__":
    full_byte_array = bytearray(b'"\x826\x17\x01\x05event\x02\x02ID"\x826\x17\x02\x04Type\x8aSpinAndWin\x02\x04Time\x07`45}`\xc1\x00\x00\x02\x06Number\x8589304\x02\x08Duration \x14\x02\tHasLevels\x01\x01\x06Market\x01\x03Win\x02\x04Odds\x8236\x00\x01\x03Red\x0c\x812\x00\x01\x05Black\x0c\x812\x00\x01\x05Green\x0c\x8236\x00\x01\x06Dozens\x0c\x813\x00\x01\x07OddEven\x0c\x812\x00\x01\x04HiLo\x0c\x812\x00\x01\x05Split\x0c\x8218\x00\x01\tThreeLine\x0c\x8212\x00\x01\x06Corner\x0c\x819\x00\x01\x0fFirst4Connected\x0c\x819\x00\x01\x07SixLine\x0c\x816\x00\x01\x06Column\x0c\x813\x00\x01\nNeighbours\x0c\x817\x00\x01\x06Sector\x0c\x816\x00\x00\x00"\x0f<\x7f\x01\x04info\x02\x02ID"\x826\x17\x02\tValidFrom\x07\x00\xd91}`\xc1\x00\x00\x01\tLastGames\x01\x010\x02\x06Number\x8589303\x02\x04Draw0\x00\x01\x011\x08\x8589302\t !\x00\x01\x012\x08\x8589301\t3\x00\x01\x013\x08\x8589300\t \x18\x00\x01\x014\x08\x8589299\t7\x00\x01\x015\x08\x8589298\t2\x00\x00\x01\x03Hot\x07\t \x1a\x02\x04Hits:\x00\n\t \x11\x10:\x00\x0b\t0\x10:\x00\x0c\t !\x109\x00\r\t6\x109\x00\x00\x01\x04Cold\x07\t #\x102\x00\n\t "\x102\x00\x0b\t \x1f\x102\x00\x0c\t8\x102\x00\r\t \x1b\x101\x00\x00\x01\x04Hits\x07\x10:\x00\x07\x10:\x00\n\x105\x00\x0b\x109\x00\x0c\x105\x00\r\x108\x00\x0e\x105\x00\x01\x016\x109\x00\x01\x017\x104\x00\x01\x018\x102\x00\x01\x019\x106\x00\x01\x0210\x105\x00\x01\x0211\x103\x00\x01\x0212\x103\x00\x01\x0213\x104\x00\x01\x0214\x106\x00\x01\x0215\x104\x00\x01\x0216\x104\x00\x01\x0217\x10:\x00\x01\x0218\x104\x00\x01\x0219\x107\x00\x01\x0220\x108\x00\x01\x0221\x105\x00\x01\x0222\x106\x00\x01\x0223\x107\x00\x01\x0224\x105\x00\x01\x0225\x103\x00\x01\x0226\x10:\x00\x01\x0227\x101\x00\x01\x0228\x108\x00\x01\x0229\x104\x00\x01\x0230\x104\x00\x01\x0231\x102\x00\x01\x0232\x105\x00\x01\x0233\x109\x00\x01\x0234\x102\x00\x01\x0235\x102\x00\x01\x0236\x106\x00\x01\x02Lo\x10 `\x00\x01\x02Hi\x10 ^\x00\x01\x03Odd\x10 V\x00\x01\x04Even\x10 r\x00\x01\x05Black\x10 l\x00\x01\x03Red\x10 R\x00\x01\x041-12\x10 @\x00\x01\x0513-24\x10 F\x00\x01\x0525-36\x10 8\x00\x01\x07Sector1\x10 &\x00\x01\x07Sector2\x10 \x1d\x00\x01\x07Sector3\x10 \x1b\x00\x01\x07Sector4\x10 $\x00\x01\x07Sector5\x10 \x1c\x00\x01\x07Sector6\x10  \x00\x00\x01\x0fPreviousResults\x00\x00"\x8c6\x17\x01\x05event\x02\x02ID"\x8c6\x17\x02\x04Type\x8aSpinAndWin\x02\x04Time\x07\xe0\xdd8}`\xc1\x00\x00\x02\x06Number\x8589305\x02\x08Duration \x14\x02\tHasLevels\x01\x01\x06Market\x01\x03Win\x02\x04Odds\x8236\x00\x01\x03Red\x0c\x812\x00\x01\x05Black\x0c\x812\x00\x01\x05Green\x0c\x8236\x00\x01\x06Dozens\x0c\x813\x00\x01\x07OddEven\x0c\x812\x00\x01\x04HiLo\x0c\x812\x00\x01\x05Split\x0c\x8218\x00\x01\tThreeLine\x0c\x8212\x00\x01\x06Corner\x0c\x819\x00\x01\x0fFirst4Connected\x0c\x819\x00\x01\x07SixLine\x0c\x816\x00\x01\x06Column\x0c\x813\x00\x01\nNeighbours\x0c\x817\x00\x01\x06Sector\x0c\x816\x00\x00\x00"\x10<\x7f\x01\x04info\x02\x02ID"\x8c6\x17\x02\tValidFrom\x07\x00\xd91}`\xc1\x00\x00\x01\tLastGames\x01\x010\x02\x06Number\x8589303\x02\x04Draw0\x00\x01\x011\x08\x8589302\t !\x00\x01\x012\x08\x8589301\t3\x00\x01\x013\x08\x8589300\t \x18\x00\x01\x014\x08\x8589299\t7\x00\x01\x015\x08\x8589298\t2\x00\x00\x01\x03Hot\x07\t \x1a\x02\x04Hits:\x00\n\t \x11\x10:\x00\x0b\t0\x10:\x00\x0c\t !\x109\x00\r\t6\x109\x00\x00\x01\x04Cold\x07\t #\x102\x00\n\t "\x102\x00\x0b\t \x1f\x102\x00\x0c\t8\x102\x00\r\t \x1b\x101\x00\x00\x01\x04Hits\x07\x10:\x00\x07\x10:\x00\n\x105\x00\x0b\x109\x00\x0c\x105\x00\r\x108\x00\x0e\x105\x00\x01\x016\x109\x00\x01\x017\x104\x00\x01\x018\x102\x00\x01\x019\x106\x00\x01\x0210\x105\x00\x01\x0211\x103\x00\x01\x0212\x103\x00\x01\x0213\x104\x00\x01\x0214\x106\x00\x01\x0215\x104\x00\x01\x0216\x104\x00\x01\x0217\x10:\x00\x01\x0218\x104\x00\x01\x0219\x107\x00\x01\x0220\x108\x00\x01\x0221\x105\x00\x01\x0222\x106\x00\x01\x0223\x107\x00\x01\x0224\x105\x00\x01\x0225\x103\x00\x01\x0226\x10:\x00\x01\x0227\x101\x00\x01\x0228\x108\x00\x01\x0229\x104\x00\x01\x0230\x104\x00\x01\x0231\x102\x00\x01\x0232\x105\x00\x01\x0233\x109\x00\x01\x0234\x102\x00\x01\x0235\x102\x00\x01\x0236\x106\x00\x01\x02Lo\x10 `\x00\x01\x02Hi\x10 ^\x00\x01\x03Odd\x10 V\x00\x01\x04Even\x10 r\x00\x01\x05Black\x10 l\x00\x01\x03Red\x10 R\x00\x01\x041-12\x10 @\x00\x01\x0513-24\x10 F\x00\x01\x0525-36\x10 8\x00\x01\x07Sector1\x10 &\x00\x01\x07Sector2\x10 \x1d\x00\x01\x07Sector3\x10 \x1b\x00\x01\x07Sector4\x10 $\x00\x01\x07Sector5\x10 \x1c\x00\x01\x07Sector6\x10  \x00\x00\x01\x0fPreviousResults\x00\x00"\x966\x17\x01\x05event\x02\x02ID"\x966\x17\x02\x04Type\x8aSpinAndWin\x02\x04Time\x07`\x87<}`\xc1\x00\x00\x02\x06Number\x8589306\x02\x08Duration \x14\x02\tHasLevels\x01\x01\x06Market\x01\x03Win\x02\x04Odds\x8236\x00\x01\x03Red\x0c\x812\x00\x01\x05Black\x0c\x812\x00\x01\x05Green\x0c\x8236\x00\x01\x06Dozens\x0c\x813\x00\x01\x07OddEven\x0c\x812\x00\x01\x04HiLo\x0c\x812\x00\x01\x05Split\x0c\x8218\x00\x01\tThreeLine\x0c\x8212\x00\x01\x06Corner\x0c\x819\x00\x01\x0fFirst4Connected\x0c\x819\x00\x01\x07SixLine\x0c\x816\x00\x01\x06Column\x0c\x813\x00\x01\nNeighbours\x0c\x817\x00\x01\x06Sector\x0c\x816\x00\x00\x000"\xa06\x17\x01\x05event\x02\x02ID"\xa06\x17\x02\x04Type\x8aSpinAndWin\x02\x04Time\x07\xe00@}`\xc1\x00\x00\x02\x06Number\x8589307\x02\x08Duration \x14\x02\tHasLevels\x01\x01\x06Market\x01\x03Win\x02\x04Odds\x8236\x00\x01\x03Red\x0c\x812\x00\x01\x05Black\x0c\x812\x00\x01\x05Green\x0c\x8236\x00\x01\x06Dozens\x0c\x813\x00\x01\x07OddEven\x0c\x812\x00\x01\x04HiLo\x0c\x812\x00\x01\x05Split\x0c\x8218\x00\x01\tThreeLine\x0c\x8212\x00\x01\x06Corner\x0c\x819\x00\x01\x0fFirst4Connected\x0c\x819\x00\x01\x07SixLine\x0c\x816\x00\x01\x06Column\x0c\x813\x00\x01\nNeighbours\x0c\x817\x00\x01\x06Sector\x0c\x816\x00\x00\x000"\xaa6\x17\x01\x05event\x02\x02ID"\xaa6\x17\x02\x04Type\x8aSpinAndWin\x02\x04Time\x07`\xdaC}`\xc1\x00\x00\x02\x06Number\x8589308\x02\x08Duration \x14\x02\tHasLevels\x01\x01\x06Market\x01\x03Win\x02\x04Odds\x8236\x00\x01\x03Red\x0c\x812\x00\x01\x05Black\x0c\x812\x00\x01\x05Green\x0c\x8236\x00\x01\x06Dozens\x0c\x813\x00\x01\x07OddEven\x0c\x812\x00\x01\x04HiLo\x0c\x812\x00\x01\x05Split\x0c\x8218\x00\x01\tThreeLine\x0c\x8212\x00\x01\x06Corner\x0c\x819\x00\x01\x0fFirst4Connected\x0c\x819\x00\x01\x07SixLine\x0c\x816\x00\x01\x06Column\x0c\x813\x00\x01\nNeighbours\x0c\x817\x00\x01\x06Sector\x0c\x816\x00\x00\x000"\xb46\x17\x01\x05event\x02\x02ID"\xb46\x17\x02\x04Type\x8aSpinAndWin\x02\x04Time\x07\xe0\x83G}`\xc1\x00\x00\x02\x06Number\x8589309\x02\x08Duration \x14\x02\tHasLevels\x01\x01\x06Market\x01\x03Win\x02\x04Odds\x8236\x00\x01\x03Red\x0c\x812\x00\x01\x05Black\x0c\x812\x00\x01\x05Green\x0c\x8236\x00\x01\x06Dozens\x0c\x813\x00\x01\x07OddEven\x0c\x812\x00\x01\x04HiLo\x0c\x812\x00\x01\x05Split\x0c\x8218\x00\x01\tThreeLine\x0c\x8212\x00\x01\x06Corner\x0c\x819\x00\x01\x0fFirst4Connected\x0c\x819\x00\x01\x07SixLine\x0c\x816\x00\x01\x06Column\x0c\x813\x00\x01\nNeighbours\x0c\x817\x00\x01\x06Sector\x0c\x816\x00\x00\x0000\x07%\x1d2}`\xc1\x00\x00\x07%\x1d2}`\xc1\x00\x00')
    # full_byte_array = bytearray(b'"n\\\x17\x01\x05event\x02\x02ID"n\\\x17\x02\x04Type\x8aSpinAndWin\x02\x04Time\x07\xe0(\x0b\x8d`\xc1\x00\x00\x02\x06Number\x8590276\x02\x08Duration \x14\x02\tHasLevels\x01\x01\x06Market\x01\x03Win\x02\x04Odds\x8236\x00\x01\x03Red\x0c\x812\x00\x01\x05Black\x0c\x812\x00\x01\x05Green\x0c\x8236\x00\x01\x06Dozens\x0c\x813\x00\x01\x07OddEven\x0c\x812\x00\x01\x04HiLo\x0c\x812\x00\x01\x05Split\x0c\x8218\x00\x01\tThreeLine\x0c\x8212\x00\x01\x06Corner\x0c\x819\x00\x01\x0fFirst4Connected\x0c\x819\x00\x01\x07SixLine\x0c\x816\x00\x01\x06Column\x0c\x813\x00\x01\nNeighbours\x0c\x817\x00\x01\x06Sector\x0c\x816\x00\x00\x00"\x83)\x80\x01\x04info\x02\x02ID"n\\\x17\x02\tValidFrom\x07\x80\xcd\x07\x8d`\xc1\x00\x00\x01\tLastGames\x01\x010\x02\x06Number\x8590275\x02\x04Draw  \x00\x01\x011\x08\x8590274\t9\x00\x01\x012\x08\x8590273\t1\x00\x01\x013\x08\x8590272\t \x1a\x00\x01\x014\x08\x8590271\t9\x00\x01\x015\x08\x8590270\t<\x00\x00\x01\x03Hot\x07\t<\x02\x04Hits:\x00\n\t?\x109\x00\x0b\t:\x109\x00\x0c\t \x1f\x108\x00\r\t \x1e\x108\x00\x00\x01\x04Cold\x07\t1\x103\x00\n\t \x10\x102\x00\x0b\t;\x102\x00\x0c\t3\x102\x00\r\t0\x102\x00\x00\x01\x04Hits\x07\x102\x00\x07\x102\x00\n\x103\x00\x0b\x105\x00\x0c\x102\x00\r\x106\x00\x0e\x108\x00\x01\x016\x103\x00\x01\x017\x106\x00\x01\x018\x105\x00\x01\x019\x103\x00\x01\x0210\x109\x00\x01\x0211\x102\x00\x01\x0212\x10:\x00\x01\x0213\x105\x00\x01\x0214\x107\x00\x01\x0215\x109\x00\x01\x0216\x102\x00\x01\x0217\x105\x00\x01\x0218\x106\x00\x01\x0219\x107\x00\x01\x0220\x107\x00\x01\x0221\x105\x00\x01\x0222\x107\x00\x01\x0223\x103\x00\x01\x0224\x108\x00\x01\x0225\x108\x00\x01\x0226\x105\x00\x01\x0227\x103\x00\x01\x0228\x105\x00\x01\x0229\x103\x00\x01\x0230\x108\x00\x01\x0231\x108\x00\x01\x0232\x107\x00\x01\x0233\x104\x00\x01\x0234\x105\x00\x01\x0235\x105\x00\x01\x0236\x104\x00\x01\x02Lo\x10 `\x00\x01\x02Hi\x10 f\x00\x01\x03Odd\x10 Y\x00\x01\x04Even\x10 o\x00\x01\x05Black\x10 e\x00\x01\x03Red\x10 a\x00\x01\x041-12\x10 >\x00\x01\x0513-24\x10 G\x00\x01\x0525-36\x10 A\x00\x01\x07Sector1\x10 \'\x00\x01\x07Sector2\x10 \x1d\x00\x01\x07Sector3\x10 \x1f\x00\x01\x07Sector4\x10  \x00\x01\x07Sector5\x10 "\x00\x01\x07Sector6\x10 !\x00\x00\x01\x0fPreviousResults\x00\x00"x\\\x17\x01\x05event\x02\x02ID"x\\\x17\x02\x04Type\x8aSpinAndWin\x02\x04Time\x07`\xd2\x0e\x8d`\xc1\x00\x00\x02\x06Number\x8590277\x02\x08Duration \x14\x02\tHasLevels\x01\x01\x06Market\x01\x03Win\x02\x04Odds\x8236\x00\x01\x03Red\x0c\x812\x00\x01\x05Black\x0c\x812\x00\x01\x05Green\x0c\x8236\x00\x01\x06Dozens\x0c\x813\x00\x01\x07OddEven\x0c\x812\x00\x01\x04HiLo\x0c\x812\x00\x01\x05Split\x0c\x8218\x00\x01\tThreeLine\x0c\x8212\x00\x01\x06Corner\x0c\x819\x00\x01\x0fFirst4Connected\x0c\x819\x00\x01\x07SixLine\x0c\x816\x00\x01\x06Column\x0c\x813\x00\x01\nNeighbours\x0c\x817\x00\x01\x06Sector\x0c\x816\x00\x00\x00"\x85)\x80\x01\x04info\x02\x02ID"x\\\x17\x02\tValidFrom\x07\x80\xcd\x07\x8d`\xc1\x00\x00\x01\tLastGames\x01\x010\x02\x06Number\x8590275\x02\x04Draw  \x00\x01\x011\x08\x8590274\t9\x00\x01\x012\x08\x8590273\t1\x00\x01\x013\x08\x8590272\t \x1a\x00\x01\x014\x08\x8590271\t9\x00\x01\x015\x08\x8590270\t<\x00\x00\x01\x03Hot\x07\t<\x02\x04Hits:\x00\n\t?\x109\x00\x0b\t:\x109\x00\x0c\t \x1f\x108\x00\r\t \x1e\x108\x00\x00\x01\x04Cold\x07\t1\x103\x00\n\t \x10\x102\x00\x0b\t;\x102\x00\x0c\t3\x102\x00\r\t0\x102\x00\x00\x01\x04Hits\x07\x102\x00\x07\x102\x00\n\x103\x00\x0b\x105\x00\x0c\x102\x00\r\x106\x00\x0e\x108\x00\x01\x016\x103\x00\x01\x017\x106\x00\x01\x018\x105\x00\x01\x019\x103\x00\x01\x0210\x109\x00\x01\x0211\x102\x00\x01\x0212\x10:\x00\x01\x0213\x105\x00\x01\x0214\x107\x00\x01\x0215\x109\x00\x01\x0216\x102\x00\x01\x0217\x105\x00\x01\x0218\x106\x00\x01\x0219\x107\x00\x01\x0220\x107\x00\x01\x0221\x105\x00\x01\x0222\x107\x00\x01\x0223\x103\x00\x01\x0224\x108\x00\x01\x0225\x108\x00\x01\x0226\x105\x00\x01\x0227\x103\x00\x01\x0228\x105\x00\x01\x0229\x103\x00\x01\x0230\x108\x00\x01\x0231\x108\x00\x01\x0232\x107\x00\x01\x0233\x104\x00\x01\x0234\x105\x00\x01\x0235\x105\x00\x01\x0236\x104\x00\x01\x02Lo\x10 `\x00\x01\x02Hi\x10 f\x00\x01\x03Odd\x10 Y\x00\x01\x04Even\x10 o\x00\x01\x05Black\x10 e\x00\x01\x03Red\x10 a\x00\x01\x041-12\x10 >\x00\x01\x0513-24\x10 G\x00\x01\x0525-36\x10 A\x00\x01\x07Sector1\x10 \'\x00\x01\x07Sector2\x10 \x1d\x00\x01\x07Sector3\x10 \x1f\x00\x01\x07Sector4\x10  \x00\x01\x07Sector5\x10 "\x00\x01\x07Sector6\x10 !\x00\x00\x01\x0fPreviousResults\x00\x00"\x82\\\x17\x01\x05event\x02\x02ID"\x82\\\x17\x02\x04Type\x8aSpinAndWin\x02\x04Time\x07\xe0{\x12\x8d`\xc1\x00\x00\x02\x06Number\x8590278\x02\x08Duration \x14\x02\tHasLevels\x01\x01\x06Market\x01\x03Win\x02\x04Odds\x8236\x00\x01\x03Red\x0c\x812\x00\x01\x05Black\x0c\x812\x00\x01\x05Green\x0c\x8236\x00\x01\x06Dozens\x0c\x813\x00\x01\x07OddEven\x0c\x812\x00\x01\x04HiLo\x0c\x812\x00\x01\x05Split\x0c\x8218\x00\x01\tThreeLine\x0c\x8212\x00\x01\x06Corner\x0c\x819\x00\x01\x0fFirst4Connected\x0c\x819\x00\x01\x07SixLine\x0c\x816\x00\x01\x06Column\x0c\x813\x00\x01\nNeighbours\x0c\x817\x00\x01\x06Sector\x0c\x816\x00\x00\x000"\x8c\\\x17\x01\x05event\x02\x02ID"\x8c\\\x17\x02\x04Type\x8aSpinAndWin\x02\x04Time\x07`%\x16\x8d`\xc1\x00\x00\x02\x06Number\x8590279\x02\x08Duration \x14\x02\tHasLevels\x01\x01\x06Market\x01\x03Win\x02\x04Odds\x8236\x00\x01\x03Red\x0c\x812\x00\x01\x05Black\x0c\x812\x00\x01\x05Green\x0c\x8236\x00\x01\x06Dozens\x0c\x813\x00\x01\x07OddEven\x0c\x812\x00\x01\x04HiLo\x0c\x812\x00\x01\x05Split\x0c\x8218\x00\x01\tThreeLine\x0c\x8212\x00\x01\x06Corner\x0c\x819\x00\x01\x0fFirst4Connected\x0c\x819\x00\x01\x07SixLine\x0c\x816\x00\x01\x06Column\x0c\x813\x00\x01\nNeighbours\x0c\x817\x00\x01\x06Sector\x0c\x816\x00\x00\x000"\x96\\\x17\x01\x05event\x02\x02ID"\x96\\\x17\x02\x04Type\x8aSpinAndWin\x02\x04Time\x07\xe0\xce\x19\x8d`\xc1\x00\x00\x02\x06Number\x8590280\x02\x08Duration \x14\x02\tHasLevels\x01\x01\x06Market\x01\x03Win\x02\x04Odds\x8236\x00\x01\x03Red\x0c\x812\x00\x01\x05Black\x0c\x812\x00\x01\x05Green\x0c\x8236\x00\x01\x06Dozens\x0c\x813\x00\x01\x07OddEven\x0c\x812\x00\x01\x04HiLo\x0c\x812\x00\x01\x05Split\x0c\x8218\x00\x01\tThreeLine\x0c\x8212\x00\x01\x06Corner\x0c\x819\x00\x01\x0fFirst4Connected\x0c\x819\x00\x01\x07SixLine\x0c\x816\x00\x01\x06Column\x0c\x813\x00\x01\nNeighbours\x0c\x817\x00\x01\x06Sector\x0c\x816\x00\x00\x000"\xa0\\\x17\x01\x05event\x02\x02ID"\xa0\\\x17\x02\x04Type\x8aSpinAndWin\x02\x04Time\x07`x\x1d\x8d`\xc1\x00\x00\x02\x06Number\x8590281\x02\x08Duration \x14\x02\tHasLevels\x01\x01\x06Market\x01\x03Win\x02\x04Odds\x8236\x00\x01\x03Red\x0c\x812\x00\x01\x05Black\x0c\x812\x00\x01\x05Green\x0c\x8236\x00\x01\x06Dozens\x0c\x813\x00\x01\x07OddEven\x0c\x812\x00\x01\x04HiLo\x0c\x812\x00\x01\x05Split\x0c\x8218\x00\x01\tThreeLine\x0c\x8212\x00\x01\x06Corner\x0c\x819\x00\x01\x0fFirst4Connected\x0c\x819\x00\x01\x07SixLine\x0c\x816\x00\x01\x06Column\x0c\x813\x00\x01\nNeighbours\x0c\x817\x00\x01\x06Sector\x0c\x816\x00\x00\x0000\x07\xfa\x04\x0b\x8d`\xc1\x00\x00\x07\xfb\x04\x0b\x8d`\xc1\x00\x00')
    
    # data object byte array
    # full_byte_array = bytearray(b'\x8aS&W_Levels \xbc\x01\x04data\x02\x02ID"n\\\x17\x01\x06Number\x02\x01N0\x02\x01L:\x00\x05\x061\x078\x00\x05\x062\x079\x00\x05\x063\x077\x00\x05\x064\x076\x00\x05\x065\x077\x00\x05\x066\x077\x00\x05\x067\x076\x00\x05\x068\x078\x00\x05\x069\x075\x00\x05\x06:\x077\x00\x05\x06;\x077\x00\x05\x06<\x077\x00\x05\x06=\x078\x00\x05\x06>\x076\x00\x05\x06?\x079\x00\x05\x06 \x10\x079\x00\x05\x06 \x11\x078\x00\x05\x06 \x12\x076\x00\x05\x06 \x13\x077\x00\x05\x06 \x14\x077\x00\x05\x06 \x15\x077\x00\x05\x06 \x16\x078\x00\x05\x06 \x17\x078\x00\x05\x06 \x18\x078\x00\x05\x06 \x19\x074\x00\x05\x06 \x1a\x076\x00\x05\x06 \x1b\x075\x00\x05\x06 \x1c\x076\x00\x05\x06 \x1d\x076\x00\x05\x06 \x1e\x077\x00\x05\x06 \x1f\x077\x00\x05\x06  \x075\x00\x05\x06 !\x077\x00\x05\x06 "\x078\x00\x05\x06 #\x077\x00\x05\x06 $\x076\x00\x00\x10')
   
    parser = UnifiedParser(full_byte_array)
    parser.parse()