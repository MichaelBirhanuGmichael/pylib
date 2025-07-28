from datetime import datetime
from typing import List, Dict, Any

class Game:
    """Represents a single game from the 'LastGames' list."""
    def __init__(self, name: str = None, number: int = None, draw: Any = None):
        self._name = name
        self._number = number
        self._draw = draw

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str):
        self._name = value

    @property
    def number(self) -> int:
        return self._number

    @number.setter
    def number(self, value: int):
        self._number = value

    @property
    def draw(self) -> Any:
        return self._draw

    @draw.setter
    def draw(self, value: Any):
        self._draw = value

    def __repr__(self) -> str:
        return f"    {self.name} {{ Number={self.number} Draw={self.draw} }}"

class HotColdItem:
    """Represents an item in the 'Hot' or 'Cold' lists."""
    def __init__(self, key: Any = None, draw: Any = None, hits: int = None):
        self._key = key
        self._draw = draw
        self._hits = hits

    @property
    def key(self) -> Any:
        return self._key

    @key.setter
    def key(self, value: Any):
        self._key = value

    @property
    def draw(self) -> Any:
        return self._draw

    @draw.setter
    def draw(self, value: Any):
        self._draw = value

    @property
    def hits(self) -> int:
        return self._hits

    @hits.setter
    def hits(self, value: int):
        self._hits = value

    def __repr__(self) -> str:
        return f"    {self.key} {{ Draw={self.draw} Hits={self.hits} }}"

class HitsItem:
    """Represents an item in the 'Hits' list."""
    def __init__(self, key: Any = None, hits: int = None):
        self._key = key
        self._hits = hits

    @property
    def key(self) -> Any:
        return self._key

    @key.setter
    def key(self, value: Any):
        self._key = value

    @property
    def hits(self) -> int:
        return self._hits

    @hits.setter
    def hits(self, value: int):
        self._hits = value

    def __repr__(self) -> str:
        return f"    {self.key} {{ Hits={self.hits} }}"

class Market:
    """Represents a market with its various odds."""
    def __init__(self, name: str, data: Dict[str, Any]):
        self._name = name
        self._data = data

    @property
    def name(self) -> str:
        return self._name
    
    @name.setter
    def name(self, value: str):
        self._name = value

    @property
    def data(self) -> Dict[str, Any]:
        return self._data

    @data.setter
    def data(self, value: Dict[str, Any]):
        self._data = value

    def __repr__(self) -> str:
        items_str = ' '.join([f'{k}={v}' for k, v in self._data.items()])
        return f"    {self.name} {{ {items_str} }}"

class Event:
    """Represents the 'event' object."""
    def __init__(self, id: int, type: str, time: str, number: int, duration: int, has_levels: bool, markets: list['Market']):
        self._id = id
        self._type = type
        self._time = time
        self._number = number
        self._duration = duration
        self._has_levels = has_levels
        self._markets = markets if markets is not None else []

    @property
    def id(self) -> int:
        return self._id

    @id.setter
    def id(self, value: int):
        self._id = value
    
    @property
    def type(self) -> str:
        return self._type

    @type.setter
    def type(self, value: str):
        self._type = value

    @property
    def time(self) -> str:
        return self._time

    @time.setter
    def time(self, value: str):
        self._time = value

    @property
    def number(self) -> int:
        return self._number

    @number.setter
    def number(self, value: int):
        self._number = value

    @property
    def duration(self) -> int:
        return self._duration

    @duration.setter
    def duration(self, value: int):
        self._duration = value

    @property
    def has_levels(self) -> bool:
        return self._has_levels

    @has_levels.setter
    def has_levels(self, value: bool):
        self._has_levels = value

    @property
    def markets(self) -> list['Market']:
        return self._markets

    @markets.setter
    def markets(self, value: list['Market']):
        self._markets = value

    def __repr__(self):
        market_repr = "\n".join([f"    {repr(m)}" for m in self._markets])
        return (
            f"Event(\n"
            f"  id={self.id},\n"
            f"  type='{self.type}',\n"
            f"  time='{self.time.hex() if isinstance(self.time, bytes) else self.time}',\n"
            f"  number={self.number},\n"
            f"  duration={self.duration},\n"
            f"  has_levels={self.has_levels},\n"
            f"  markets=[\n{market_repr}\n  ]\n"
            f")"
        )

class Info:
    def __init__(self, id: int, valid_from: bytes, last_games: list['Game'], hot: list['HotColdItem'], cold: list['HotColdItem'], hits: list['HitsItem']):
        self._id = id
        self._valid_from = valid_from
        self._last_games = last_games if last_games is not None else []
        self._hot = hot if hot is not None else []
        self._cold = cold if cold is not None else []
        self._hits = hits if hits is not None else []

    @property
    def id(self) -> int:
        return self._id

    @id.setter
    def id(self, value: int):
        self._id = value

    @property
    def valid_from(self) -> bytes:
        return self._valid_from

    @valid_from.setter
    def valid_from(self, value: bytes):
        self._valid_from = value

    @property
    def last_games(self) -> list['Game']:
        return self._last_games

    @last_games.setter
    def last_games(self, value: list['Game']):
        self._last_games = value

    @property
    def hot(self) -> list['HotColdItem']:
        return self._hot

    @hot.setter
    def hot(self, value: list['HotColdItem']):
        self._hot = value

    @property
    def cold(self) -> list['HotColdItem']:
        return self._cold

    @cold.setter
    def cold(self, value: list['HotColdItem']):
        self._cold = value

    @property
    def hits(self) -> list['HitsItem']:
        return self._hits

    @hits.setter
    def hits(self, value: list['HitsItem']):
        self._hits = value

    def __repr__(self):
        return (
            f"info {{\n"
            f"  ID={self.id} ValidFrom={self.valid_from.hex() if isinstance(self.valid_from, bytes) else self.valid_from}\n"
            f"  LastGames={{\n" + "\n".join([f"    {repr(g)}" for g in self.last_games]) + "\n  }}\n"
            f"  Hot={{\n" + "\n".join([f"    {repr(h)}" for h in self.hot]) + "\n  }}\n"
            f"  Cold={{\n" + "\n".join([f"    {repr(c)}" for c in self.cold]) + "\n  }}\n"
            f"  Hits={{\n" + "\n".join([f"    {repr(h)}" for h in self.hits]) + "\n  }}\n"
            f"}}"
        )
