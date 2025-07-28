import io
from datetime import datetime
from typing import List, Union

from models import Event, Info, Market, Game, HotColdItem, HitsItem

# --- Value-decoding helpers ---
def _decode_single_byte_value(byte_val):
    """Decodes a single byte into its intended integer value."""
    if byte_val is None: return None
    # The byte value itself is what's needed.
    # Special characters might still need handling.
    if byte_val == ord(':'): return 10
    return byte_val

def _decode_multi_byte_value(byte_data):
    """Decodes multiple bytes into an integer."""
    if not byte_data: return None
    return int.from_bytes(byte_data, 'little')


class Deserializer:
    """A deserializer for the custom binary format."""
    def __init__(self, data: bytearray):
        self.stream = io.BytesIO(data)
        self.last_field_name = None

    def deserialize(self) -> List[Union[Event, Info]]:
        """Parses the entire byte stream and returns a list of Event and Info objects."""
        objects = []
        while self.stream.tell() < len(self.stream.getbuffer()):
            start_marker = self.stream.read(1)
            if not start_marker: break

            if start_marker == b'"':
                header = self.stream.read(3)
                id_val = _decode_multi_byte_value(header)
                
                obj_marker = self.stream.read(1)
                if not obj_marker or obj_marker[0] != 0x01:
                    continue

                name_len_byte = self.stream.read(1)
                if not name_len_byte: break
                name_len = name_len_byte[0]
                name = self.stream.read(name_len).decode('utf-8')

                if name == 'event':
                    event_obj = self._parse_event_object(id_val)
                    objects.append(event_obj)
                elif name == 'info':
                    info_obj = self._parse_info_object(id_val)
                    objects.append(info_obj)
        return objects

    def _parse_value(self):
        """Generic value parser for object fields."""
        marker_byte = self.stream.read(1)
        if not marker_byte: return None
        marker = marker_byte[0]
        
        if marker == ord('"'): return _decode_multi_byte_value(self.stream.read(3))
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
            self.stream.read(2) 
            return ts_bytes # Return raw bytes as requested
        else: return marker

    def _parse_generic_object_dict(self, last_field_from_parent=None):
        """Recursive parser that returns a dictionary."""
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
                inner_obj, last_field_from_inner = self._parse_generic_object_dict(last_field_in_scope)
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

    def _parse_event_object(self, event_id) -> Event:
        """Parses the 'event' object into an Event model."""
        event_dict, _ = self._parse_generic_object_dict()
        
        # Basic market parsing from the dictionary
        market_list = []
        if "Market" in event_dict:
            for name, data in event_dict["Market"].items():
                market_list.append(Market(name=name, data=data))

        return Event(
            id=event_id,
            type=event_dict.get("Type"),
            time=event_dict.get("Time"),
            number=event_dict.get("Number"),
            duration=event_dict.get("Duration"),
            has_levels=event_dict.get("HasLevels"),
            markets=market_list
        )

    def _parse_info_object(self, info_id) -> Info:
        """Top-level parser for the specialized 'info' object fields."""
        # The first two fields are standard
        self.stream.read(1); id_len = self.stream.read(1)[0]; id_name = self.stream.read(id_len).decode('utf-8', 'ignore'); event_id = self._parse_value()
        self.stream.read(1); vf_len = self.stream.read(1)[0]; vf_name = self.stream.read(vf_len).decode('utf-8', 'ignore'); valid_from = self._parse_value()

        last_games = []
        hot = []
        cold = []
        hits = []
        
        while True:
            pos = self.stream.tell()
            peek = self.stream.read(1)
            if not peek: break
            self.stream.seek(pos)

            if peek == b'\x00':
                self.stream.read(1)
                continue

            if peek == b'\x01':
                self.stream.read(1)
                name_len = self.stream.read(1)[0]
                name = self.stream.read(name_len).decode('utf-8', 'ignore')
                if name == "PreviousResults":
                    self.stream.read(1)
                elif name == "LastGames": last_games = self._parse_last_games_list()
                elif name == "Hot": hot = self._parse_hot_cold_list()
                elif name == "Cold": cold = self._parse_hot_cold_list()
                elif name == "Hits": hits = self._parse_hits_object()
            else:
                break
        
        return Info(
            id=event_id,
            valid_from=valid_from,
            last_games=last_games,
            hot=hot,
            cold=cold,
            hits=hits
        )

    def _parse_last_games_list(self) -> List[Game]:
        games, fields = [], []
        while True:
            pos = self.stream.tell()
            peek_marker = self.stream.read(1)
            if not peek_marker or peek_marker != b'\x01':
                self.stream.seek(pos); break
            
            name_peek_pos = self.stream.tell()
            name_len_byte = self.stream.read(1)
            if not name_len_byte: self.stream.seek(pos); break
            name_len = name_len_byte[0]
            if len(self.stream.getbuffer()) < self.stream.tell() + name_len: self.stream.seek(pos); break
            name = self.stream.read(name_len).decode('utf-8', 'ignore')
            self.stream.seek(pos)

            if name in ["Hot", "Cold", "Hits", "PreviousResults"]: break

            self.stream.read(1)
            name_len = self.stream.read(1)[0]
            game_name = self.stream.read(name_len).decode('utf-8', 'ignore')
            game = Game(name=game_name)

            if not fields:
                self.stream.read(1); fl = self.stream.read(1)[0]; fn = self.stream.read(fl).decode('utf-8', 'ignore'); fields.append(fn)
                game.number = self._parse_value()
                self.stream.read(1); fl = self.stream.read(1)[0]; fn = self.stream.read(fl).decode('utf-8', 'ignore'); fields.append(fn)
                value_bytes = []
                while True:
                    b = self.stream.read(1)
                    if not b or b[0] == 0x00: break
                    value_bytes.append(b)
                val_str = b''.join(value_bytes).decode('utf-8', 'ignore').strip()
                try: game.draw = int(val_str)
                except (ValueError, TypeError): game.draw = val_str if val_str else 0
            else:
                marker1 = self.stream.read(1)
                if not marker1 or marker1[0] != 0x08: self.stream.seek(pos); break
                game.number = self._parse_value()
                marker2 = self.stream.read(1)
                if not marker2 or marker2[0] != 0x09: self.stream.seek(pos); break
                value_bytes = []
                while True:
                    b = self.stream.read(1)
                    if not b or b[0] == 0x00: break
                    value_bytes.append(b)
                if value_bytes:
                    val_str = b''.join(value_bytes).decode('utf-8', 'ignore').strip()
                    try: game.draw = int(val_str)
                    except (ValueError, TypeError):
                        if len(val_str) == 1: game.draw = _decode_single_byte_value(ord(val_str[0]))
                        else: game.draw = val_str if val_str else 0
                else: game.draw = 0
            games.append(game)
        return games

    def _parse_hot_cold_list(self) -> List[HotColdItem]:
        items = []
        field_name = "Hits"  # Default field name
        while True:
            pos = self.stream.tell()
            
            peek_byte = self.stream.read(1)
            if not peek_byte or peek_byte in [b'\x01', b'\x00']:
                self.stream.seek(pos)
                break
            
            self.stream.seek(pos)

            key_byte = self.stream.read(1)
            if not key_byte: break
            key = _decode_single_byte_value(key_byte[0])
            
            tab = self.stream.read(1)
            if not tab or tab != b'\t':
                self.stream.seek(pos)
                break

            # Handle optional space after tab
            peek_space = self.stream.read(1)
            if peek_space != b' ':
                self.stream.seek(self.stream.tell() - 1)

            draw_byte = self.stream.read(1)
            if not draw_byte: break
            draw = _decode_single_byte_value(draw_byte[0])

            hits = 0
            marker_byte = self.stream.read(1)
            if not marker_byte: break

            if marker_byte[0] == 0x02:
                field_len_byte = self.stream.read(1)
                if not field_len_byte: break
                field_len = field_len_byte[0]
                field_name_bytes = self.stream.read(field_len)
                if len(field_name_bytes) < field_len: break
                field_name = field_name_bytes.decode('utf-8', 'ignore')
                
                hits_byte = self.stream.read(1)
                if not hits_byte: break
                hits = _decode_single_byte_value(hits_byte[0])
            elif marker_byte[0] == 0x10:
                hits_byte = self.stream.read(1)
                if not hits_byte: break
                hits = _decode_single_byte_value(hits_byte[0])
            else:
                self.stream.seek(pos)
                break

            items.append(HotColdItem(key=key, draw=draw, hits=hits))
            
            term_byte = self.stream.read(1)
            if not term_byte or term_byte[0] != 0x00:
                self.stream.seek(self.stream.tell() - 1)
                break
        return items

    def _parse_hits_object(self) -> List[HitsItem]:
        items = []
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
                        name_bytes = self.stream.read(name_len)
                        if len(name_bytes) < name_len:
                            self.stream.seek(pos)
                            break
                        name = name_bytes.decode('utf-8', 'ignore')
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
                key_bytes = self.stream.read(key_len)
                if len(key_bytes) < key_len: break
                key = key_bytes.decode('utf-8', 'ignore')
            else:
                self.stream.seek(self.stream.tell() - 1)
                key = _decode_single_byte_value(self.stream.read(1)[0])

            marker_byte = self.stream.read(1)
            if not marker_byte or marker_byte != b'\x10':
                self.stream.seek(pos)
                break

            val_byte = self.stream.read(1)
            if not val_byte: break
            val = _decode_single_byte_value(val_byte[0])
            
            items.append(HitsItem(key=key, hits=val))

            term_byte = self.stream.read(1)
            if not term_byte or term_byte[0] != 0x00:
                self.stream.seek(self.stream.tell() - 1)
                break
        return items
