from ursina import Entity, Text, color
import random


def choose_text_color(base_color):
    """Pick black or white text based on brightness for readability."""
    brightness = (base_color.r + base_color.g + base_color.b) / 3
    return color.black if brightness > 0.5 else color.white

class SnakeSegment(Entity):
    """Single segment of a snake with a numeric value."""
    def __init__(self, position=(0, 0, 0), value=2, player_color=color.blue):
        super().__init__(
            model='cube',
            color=player_color,
            position=position,
            scale=1,
            collider='box'
        )
        self.value = value
        self.text_entity = Text(
            text=str(self.value), parent=self, y=0.6, scale=10,
            origin=(0, 0), color=choose_text_color(self.color)
        )

class CollectibleCube(Entity):
    """Cube that can be collected by snakes."""
    def __init__(self, position=(0, 0, 0), value=2, cube_id=None):
        super().__init__(
            model='cube',
            color=color.red if value == 2 else color.green if value == 4 else color.yellow,
            position=position,
            scale=1,
            collider='box'
        )
        self.value = value
        self.cube_id = cube_id or random.randint(1000, 9999)
        self.text_entity = Text(
            text=str(self.value), parent=self, y=0.6, scale=10,
            origin=(0, 0), color=choose_text_color(self.color)
        )
