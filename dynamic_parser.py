import io
from datetime import datetime

class DynamicParser:
    """
    A dynamic parser that decodes byte streams based on observed patterns
    rather than a fixed, hardcoded schema.
    """

    def __init__(self, data: bytearray):
        self.stream = io.BytesIO(data)
        # Context to store learned field names for compact list structures
        self.list_fields_context = {}

    def parse(self):
        """
        Parses the entire byte stream and returns the structured data.
        """
        # The top-level message is a container of objects and fields.
        return self._parse_container()

    def _parse_container(self):
        """
        Parses a container, which is a collection of key-value pairs.
        The keys can be objects or simple fields.
        """
        container = {}
        while self.stream.tell() < len(self.stream.getbuffer()):
            pos = self.stream.tell()
            marker = self.stream.read(1)
            if not marker:
                break
            
            self.stream.seek(pos)

            if marker == b'\x01':
                key, value = self._parse_object()
                container[key] = value
            elif marker == b'\x02':
                key, value = self._parse_field()
                container[key] = value
            elif marker == b'\x00':
                # Null byte often acts as a terminator for a container or list.
                self.stream.read(1)
                break
            else:
                # If we see a marker we don't recognize at this level,
                # we assume the container has ended.
                break
        return container

    def _parse_object(self):
        """
        Parses a named object, which starts with marker \x01.
        An object contains a container of its own.
        """
        self.stream.read(1)  # Consume \x01
        name = self._decode_length_prefixed_string()
        
        # Peek at the next byte to decide how to parse the content.
        pos = self.stream.tell()
        marker = self.stream.read(1)
        self.stream.seek(pos)

        # This pattern-based approach replaces the hardcoded name-checking.
        if marker == b'\x01':
            # An object starting with \x01 containing items that also start with \x01
            # is a list that uses a "learnable" schema (e.g., LastGames).
            content = self._parse_schema_learning_list(name)
        elif marker == b'\x07':
            # An object starting with \x01 followed by \x07 is a list
            # with its own unique structure (e.g., Hot, Cold, Hits).
            content = self._parse_marker_7_list(name)
        else:
            # Otherwise, it's a standard container of fields.
            content = self._parse_container()
            
        return name, content

    def _parse_field(self):
        """
        Parses a key-value field, which starts with marker \x02.
        """
        self.stream.read(1)  # Consume \x02
        key = self._decode_length_prefixed_string()
        value = self._parse_value()
        return key, value

    def _parse_schema_learning_list(self, context_key):
        """
        Parses a list where the first item defines the schema for subsequent
        compact items (e.g., LastGames).
        """
        items = {}
        item_key = 0
        while True:
            pos = self.stream.tell()
            marker = self.stream.read(1)
            if not marker or marker != b'\x01':
                self.stream.seek(pos)
                break

            self._decode_length_prefixed_string() # Item name ("0", "1", etc.) is read but not used
            item_content = self._parse_list_item(context_key)
            items[str(item_key)] = item_content
            item_key += 1

            # Consume the item terminator
            pos = self.stream.tell()
            if self.stream.read(1) != b'\x00':
                self.stream.seek(pos)
        return items

    def _parse_marker_7_list(self, context_key):
        """
        Parses lists that start with the \x07 marker. This can be a simple
        list of pairs (like Hot/Cold) or a complex object (like Hits).
        """
        items = {}
        self.stream.read(1) # Consume \x07 marker

        # Peek ahead to see if this is a complex object like 'Hits'
        # which contains \x01 field markers immediately after the list part.
        is_complex_hits_object = False
        
        # We need a lookahead without consuming bytes permanently
        original_pos = self.stream.tell()
        temp_buffer = self.stream.read()
        self.stream.seek(original_pos)

        # Simple check: if \x01 is soon, it's likely the Hits object.
        if b'\x01' in temp_buffer[:100]: # Look within a reasonable distance
             # A better check would be to see if it's followed by known field names
             if b'Lo' in temp_buffer or b'Hi' in temp_buffer:
                 is_complex_hits_object = True

        if is_complex_hits_object:
            # The 'Hits' object pattern: a list of number-hits pairs, followed by regular fields.
            while True:
                pos = self.stream.tell()
                marker = self.stream.read(1)
                if not marker or marker == b'\x01' or marker == b'\x00':
                    self.stream.seek(pos)
                    break
                self.stream.seek(pos)
                
                number = self._parse_value()
                hits = self._parse_value()
                items[str(number)] = {'Hits': hits}
            
            # The rest of the object is a standard container
            items.update(self._parse_container())

        else:
            # The 'Hot'/'Cold' object pattern: a simple list of draw-hits pairs.
            item_key = 0
            while True:
                pos = self.stream.tell()
                marker = self.stream.read(1)
                if not marker or marker == b'\x01' or marker == b'\x00':
                    self.stream.seek(pos)
                    break
                self.stream.seek(pos)

                item = {}
                item['Draw'] = self._parse_value()
                item['Hits'] = self._parse_value()
                items[str(item_key)] = item
                item_key += 1
        
        return items

    def _parse_list_item(self, context_key):
        """ Parses a single item within a list. """
        item = {}
        
        pos = self.stream.tell()
        marker = self.stream.read(1)
        self.stream.seek(pos)

        if not marker:
            return {}

        # Branch for "full" items that define the schema (like in LastGames)
        if marker == b'\x02':
            fields = []
            # Loop as long as we see fields starting with the \x02 marker
            while True:
                # Peek ahead to see if the next byte is our field marker
                pos = self.stream.tell()
                if self.stream.read(1) != b'\x02':
                    self.stream.seek(pos) # Not a field marker, so stop.
                    break
                self.stream.seek(pos) # It is a field marker, so rewind for _parse_field.

                key, value = self._parse_field()
                item[key] = value
                fields.append(key)
            
            # "Learn" the fields for this list type for subsequent compact items
            if fields:
                self.list_fields_context[context_key] = fields
        
        # Branch for "compact" items that use the learned schema
        elif marker == b'\x08' and context_key in self.list_fields_context:
            learned_fields = self.list_fields_context[context_key]
            self.stream.read(1) # Consume the \x08 marker

            # A compact item has a value for each learned field, separated by a tab
            for i, field_name in enumerate(learned_fields):
                item[field_name] = self._parse_value()
                
                # After parsing a value, check for a tab separator, but only if it's not the last field
                if i < len(learned_fields) - 1:
                    pos = self.stream.tell()
                    if self.stream.read(1) != b'\t':
                        # If there's no tab, it means the compact item is shorter than expected.
                        # We should stop and rewind.
                        self.stream.seek(pos)
                        break
        
        return item

    def _parse_value(self):
        """
        Parses a value, determining its type by the marker that precedes it.
        """
        marker_byte = self.stream.read(1)
        if not marker_byte: return None
        
        marker = marker_byte[0]

        if marker == ord('"'):
            return int.from_bytes(self.stream.read(3), 'little')
        elif marker == 0x07:
            ts_bytes = self.stream.read(6)
            self.stream.read(2)  # Skip two null bytes
            ts = int.from_bytes(ts_bytes, 'big')
            try:
                return datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d %H:%M:%S')
            except (OSError, ValueError):
                return f"Invalid Timestamp: {ts}"
        elif marker in [0x8a, 0x85, 0x81, 0x82]:
            value_bytes = []
            while True:
                pos = self.stream.tell()
                b = self.stream.read(1)
                if not b or b[0] < 0x20:  # Stop at control characters
                    self.stream.seek(pos)
                    break
                value_bytes.append(b)
            val_str = b''.join(value_bytes).decode('utf-8', 'ignore').strip()
            try:
                return int(val_str)
            except (ValueError, TypeError):
                return val_str if val_str else 0
        else:
            # Fallback for single-byte values
            char = chr(marker)
            if '0' <= char <= '9': return int(char)
            if marker == ord(':'): return 10
            if char.isprintable() and char not in ['\t', '\r', '\n']: return char
            return f"0x{marker:02x}"

    def _decode_length_prefixed_string(self):
        """Reads a length-prefixed string from the stream."""
        length = self.stream.read(1)[0]
        return self.stream.read(length).decode('utf-8', 'ignore')

def pretty_print_compact(data, indent=0):
    """Prints a dictionary or a list in a compact, readable format."""
    prefix = '  ' * indent
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, dict) and value:
                print(prefix + str(key) + ' {')
                pretty_print_compact(value, indent + 1)
                print(prefix + '}')
            elif isinstance(value, list) and value:
                print(prefix + str(key) + ' [')
                for item in value:
                    pretty_print_compact(item, indent + 1)
                print(prefix + ']')
            else:
                val_str = f'"{value}"' if isinstance(value, str) else str(value)
                print(f'{prefix}{key}: {val_str}')
    elif isinstance(data, list):
        for item in data:
            pretty_print_compact(item, indent)
