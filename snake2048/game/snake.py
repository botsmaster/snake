from ursina import Vec3, destroy, distance, held_keys, color, time, invoke
import random
from .entities import SnakeSegment, CollectibleCube

# Shared collections for cubes and non-local snakes
collectible_cubes = []
other_players = {}

# Restart callback is injected by main
restart_callback = lambda: None

def set_restart_callback(callback):
    global restart_callback
    restart_callback = callback

class Snake:
    """Snake controlled by a player."""
    def __init__(self, player_id="player1", player_color=color.blue):
        self.player_id = player_id
        self.player_color = player_color
        self.segments = []
        self.head = SnakeSegment(position=(0, 0.5, 0), value=2, player_color=player_color)
        self.segments.append(self.head)
        self.speed = 5
        self.direction = Vec3(0, 0, 1)
        self.position_history = []
        self.segment_spacing = 1.0
        self.alive = True
        self.score = 0

    def update(self):
        if not self.alive:
            return
        # Save head position history
        self.position_history.insert(0, self.head.position)
        # Move head
        self.head.position += self.direction * time.dt * self.speed

        # Move segments using stored history
        for i in range(1, len(self.segments)):
            target_idx = int(i * self.segment_spacing / (self.speed * time.dt))
            if target_idx < len(self.position_history):
                self.segments[i].position = self.position_history[target_idx]
            else:
                self.segments[i].position = (
                    self.segments[i-1].position - self.direction * self.segment_spacing
                )
        max_len = int(len(self.segments) * self.segment_spacing / (self.speed * time.dt)) + 10
        if len(self.position_history) > max_len:
            self.position_history = self.position_history[:max_len]

        # Local player input
        if self.player_id == "local_player":
            if held_keys['w'] and self.direction != Vec3(0, 0, -1):
                self.direction = Vec3(0, 0, 1)
            if held_keys['s'] and self.direction != Vec3(0, 0, 1):
                self.direction = Vec3(0, 0, -1)
            if held_keys['a'] and self.direction != Vec3(1, 0, 0):
                self.direction = Vec3(-1, 0, 0)
            if held_keys['d'] and self.direction != Vec3(-1, 0, 0):
                self.direction = Vec3(1, 0, 0)

    def grow(self, value: int):
        new_segment = SnakeSegment(
            position=self.segments[-1].position,
            value=value,
            player_color=self.player_color,
        )
        self.segments.append(new_segment)
        self.score += value

    def collect_cube(self, cube: CollectibleCube, websocket_client=None):
        """Collect cube if value is valid and notify server."""
        if cube.value <= self.head.value:
            if cube.value == self.head.value:
                self.head.value *= 2
                self.head.text_entity.text = str(self.head.value)
            self.grow(cube.value)
            collectible_cubes.remove(cube)
            destroy(cube)
            if websocket_client and websocket_client.websocket and websocket_client.websocket.open:
                websocket_client.send_threadsafe({"type": "collect_cube", "cube_id": cube.cube_id})
        else:
            print("Cannot collect cube: value too high!")

    def check_collision_with_other_snakes(self, other_snakes, websocket_client=None):
        if not self.alive:
            return
        for other_snake in other_snakes:
            if other_snake.player_id != self.player_id and other_snake.alive:
                if distance(self.head.position, other_snake.head.position) < 1.0:
                    if self.head.value > other_snake.head.value:
                        other_snake.die(websocket_client)
                    elif self.head.value < other_snake.head.value:
                        self.die(websocket_client)
                    else:
                        self.die(websocket_client)
                        other_snake.die(websocket_client)

    def die(self, websocket_client=None):
        self.alive = False
        if websocket_client and websocket_client.websocket and websocket_client.websocket.open:
            websocket_client.send_threadsafe({"type": "player_death", "id": self.player_id})
        for segment in self.segments:
            segment.visible = False
        if self.player_id == "local_player":
            invoke(restart_callback, delay=3)

    def check_collision(self, websocket_client=None):
        if not self.alive:
            return
        if abs(self.head.x) > 24 or abs(self.head.z) > 24:
            self.die(websocket_client)
        for i in range(1, len(self.segments)):
            if distance(self.head.position, self.segments[i].position) < 0.8:
                self.die(websocket_client)
        if self.player_id == "local_player":
            for cube in collectible_cubes[:]:
                if distance(self.head.position, cube.position) < 1.0:
                    if cube.value <= self.head.value:
                        self.collect_cube(cube, websocket_client)
                    else:
                        self.die(websocket_client)
                    break

def spawn_collectible_cube(position=None, value=None, cube_id=None):
    """Utility function to create collectible cubes."""
    if position is None:
        x = random.uniform(-20, 20)
        z = random.uniform(-20, 20)
        position = (x, 0.5, z)
    value = value or random.choice([2, 4, 8])
    cube = CollectibleCube(position=position, value=value, cube_id=cube_id)
    collectible_cubes.append(cube)
    return cube
