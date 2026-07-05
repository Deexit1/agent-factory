from dataclasses import dataclass


@dataclass
class Product:
    name: str
    price: float

    def __post_init__(self):
        if self.price < 0:
            raise ValueError("price must be non-negative")
