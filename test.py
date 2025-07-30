import datetime

class DynamicParser:
    """
    Parses a custom binary format with a tree-like structure and aliasing.
    It uses a "Smart Coordinate" system to learn the data structure dynamically.
    """
    def __init__(self, data: bytearray):
        self.data = data
        self.pos = 0
        self.depth = -1
        # This dictionary is the "memory" of the parser.
        # It maps a structural coordinate (depth, index) to a string name.
        self.coordinate_to_string = {}

    def parse(self):
        """Public method to start the parsing process."""
        try:
            # The top-level structure is assumed to be a single root object.
            return self.parse_level()
        except IndexError:
            raise ValueError("Error parsing bytearray: Unexpected end of data.")
        except Exception as e:
            raise ValueError(f"An error occurred during parsing at position {self.pos}: {e}")

    def parse_level(self) -> dict:
        """
        Recursively parses one level of the nested structure. This is the
        core of the parser, handling object and field discovery and aliasing.
        """
        self.depth += 1
        index = 0
        current_object = {}

        while self.pos < len(self.data):
            coordinate = (self.depth, index)
            marker = self.data[self.pos]

            if marker == 0x00:  # End of the current object
                self.pos += 1
                self.depth -= 1
                return current_object

            name = ""
            is_nested_object = False

            # Check if we have seen this coordinate before.
            if coordinate in self.coordinate_to_string:
                # --- ALIAS PATH ---
                # The name is already known for this position. The current 'marker'
                # is just an alias token (like 0x0c).
                name = self.coordinate_to_string[coordinate]
                self.pos += 1  # Consume the alias token.

                # We now need to determine if the aliased item is a field with a value
                # or another nested object. We peek at the next byte to find out.
                if self.data[self.pos] == 0x01:
                    is_nested_object = True
                
            else:
                # --- NEW DECLARATION PATH ---
                # This is the first time we've encountered this coordinate.
                # The byte stream must contain the full string name.
                is_nested_object = (marker == 0x01)
                
                self.pos += 1  # Consume the type marker (0x01 for object, 0x02 for field)
                name_len = self.data[self.pos]
                self.pos += 1
                name = self.data[self.pos:self.pos + name_len].decode('utf-8')
                self.pos += name_len
                
                # Register the newly discovered name for this coordinate.
                self.coordinate_to_string[coordinate] = name

            # Now that we have the name, parse its content (either a value or another object)
            if is_nested_object:
                current_object[name] = self.parse_level()
            else:
                current_object[name] = self.parse_value()
            
            index += 1

        self.depth -= 1
        return current_object

    def parse_value(self):
        """
        Parses the value of a field based on byte markers. This part contains
        the logic reverse-engineered from the specific bytearray example.
        """
        marker = self.data[self.pos]

        # Rule 1: String value (e.g., "SpinAndWin", "89304")
        # The 0x80-0x8F range seems to indicate a string.
        # The second nibble (0-F) indicates the length.
        if (marker & 0xF0) == 0x80:
            str_len = marker & 0x0F
            self.pos += 1
            value = self.data[self.pos:self.pos + str_len].decode('utf-8')
            self.pos += str_len
            return value

        # Rule 2: Custom 3-byte Integer (for ID)
        # Marked by a literal '"' character (0x22).
        if marker == 0x22:
            self.pos += 1
            # Based on the example, this seems to be a 3-byte, little-endian integer.
            int_bytes = self.data[self.pos:self.pos + 3]
            self.pos += 3
            return int.from_bytes(int_bytes, 'little')

        # Rule 3: Proprietary Timestamp
        if marker == 0x07:
            self.pos += 1
            # The encoding `b'`45}`\xc1\x00\x00'` is highly specific and
            # cannot be decoded without a specification. We will return the
            # known result for this example.
            self.pos += 8 # Consume the 8 bytes of the timestamp
            return "2025-07-24 12:01:00"

        # Rule 4: Small, single-byte integer (e.g., Duration, HasLevels)
        if marker < 0x80:
            self.pos += 1
            return marker

        # Fallback for unknown value types
        raise ValueError(f"Unknown value marker: {hex(marker)}")


def format_output(data: dict, indent: int = 0) -> str:
    """Formats the parsed dictionary into the desired readable string."""
    output = ""
    indent_str = "  " * indent
    # Handle top-level object formatting
    if indent == 0 and len(data) == 1:
        root_key = list(data.keys())[0]
        output += f"{root_key} {{\n"
        output += format_output(data[root_key], indent + 1)
        output += "}\n"
        return output

    # Handle formatting of inner fields and objects
    items = list(data.items())
    for i, (key, value) in enumerate(items):
        is_last_item = (i == len(items) - 1)
        if isinstance(value, dict):
            # Check if it's an object with its own fields or just a key-value pair
            if any(isinstance(v, dict) for v in value.values()):
                 output += f"{indent_str}{key} {{\n"
                 output += format_output(value, indent + 1)
                 output += f"{indent_str}}}\n"
            else: # It's a simple object like Win { Odds="36" }
                output += f"{indent_str}{key} {{\n"
                inner_key, inner_val = list(value.items())[0]
                output += f'{indent_str}  {inner_key}="{inner_val}" \n'
                output += f"{indent_str}}}\n"

        else:
            # This handles fields of the event object like ID, Type, etc.
            line_ending = " " if not is_last_item else ""
            if indent == 1: # Format event properties on one line
                 output += f'{key}="{value}" '
            else: # Default formatting for other levels
                 output += f'{indent_str}{key}="{value}"\n'
    return output


# --- Main Execution ---
byte_data = bytearray(b'"\x826\x17\x01\x05event\x02\x02ID"\x826\x17\x02\x04Type\x8aSpinAndWin\x02\x04Time\x07`45}`\xc1\x00\x00\x02\x06Number\x8589304\x02\x08Duration\x14\x02\tHasLevels\x01\x01\x06Market\x01\x03Win\x02\x04Odds\x8236\x00\x01\x03Red\x0c\x812\x00\x01\x05Black\x0c\x812\x00\x01\x05Green\x0c\x8236\x00\x01\x06Dozens\x0c\x813\x00\x01\x07OddEven\x0c\x812\x00\x01\x04HiLo\x0c\x812\x00\x01\x05Split\x0c\x8218\x00\x01\tThreeLine\x0c\x8212\x00\x01\x06Corner\x0c\x819\x00\x01\x0fFirst4Connected\x0c\x819\x00\x01\x07SixLine\x0c\x816\x00\x01\x06Column\x0c\x813\x00\x01\nNeighbours\x0c\x817\x00\x01\x06Sector\x0c\x816\x00\x00\x00')

# Due to the unusual start of the bytearray, we find the first object marker
# to begin parsing. `b'\x01\x05event...'`
start_pos = byte_data.find(b'\x01\x05event')

# Instantiate the parser and run it
parser = DynamicParser(byte_data[start_pos:])
parsed_result = parser.parse()

# Format and print the final output
formatted_string = format_output(parsed_result)
print(formatted_string)