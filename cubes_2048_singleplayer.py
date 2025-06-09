# -*- coding: utf-8 -*-
"""Single player prototype of the game "Cubes 2048.io" using the Ursina engine.

This script implements most of the mechanics described in the prompt:
- Snake like movement with smooth trailing segments and cube merging similar to 2048.
- A large arena with random collectible cubes.
- Basic AI controlled snakes that farm cubes, hunt weaker players or flee from stronger ones.
- Leaderboard, kill feed and simple game state machine (menu, game, death, end).
- Boost mechanic with cost and small visual effects.

The code is intentionally verbose and heavily commented for educational purposes.
"""

from ursina import (
    Ursina, Entity, Text, Sky, camera, color, time, Vec3, lerp,
    destroy, distance, held_keys, mouse, invoke
)
import random
from collections import deque
from enum import Enum

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------
MAP_SIZE = 100                             # size of the square arena
INITIAL_CUBES = 30                         # number of cubes to spawn at start
BOT_COUNT = 10                             # how many AI snakes
BOOST_SPEED = 8                            # movement speed while boosting
NORMAL_SPEED = 4                           # base movement speed
BOOST_DROP_INTERVAL = 1.0                  # seconds between dropping a tail cube

# Color mapping for cube values (extend as needed)
CUBE_COLORS = {
    2: color.rgb(238, 228, 218),
    4: color.rgb(237, 224, 200),
    8: color.rgb(242, 177, 121),
    16: color.rgb(245, 149, 99),
    32: color.rgb(246, 124, 95),
    64: color.rgb(246, 94, 59),
    128: color.rgb(237, 207, 114),
    256: color.rgb(237, 204, 97),
    512: color.rgb(237, 200, 80),
    1024: color.rgb(237, 197, 63),
    2048: color.rgb(237, 194, 46)
}

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def text_color_for(bg):
    """Return white or black text depending on background brightness."""
    brightness = (bg.r + bg.g + bg.b) / 3
    return color.black if brightness > 0.5 else color.white


def play_sound(name):
    """Placeholder for sound effect calls."""
    print(f"play_sound: {name}")

# ---------------------------------------------------------------------------
# Game entities
# ---------------------------------------------------------------------------

class Cube(Entity):
    """Collectible or snake body cube with a numeric value."""

    def __init__(self, value=2, position=(0, 0.5, 0), parent=None):
        col = CUBE_COLORS.get(value, color.white)
        super().__init__(model="cube", color=col, position=position,
                         scale=1, collider="box", parent=parent)
        self.value = value
        self.label = Text(str(value), parent=self, scale=8, y=0.6,
                          origin=(0, 0), color=text_color_for(col))

    def set_value(self, value):
        self.value = value
        self.color = CUBE_COLORS.get(value, color.white)
        self.label.text = str(value)
        self.label.color = text_color_for(self.color)


class Snake:
    """Snake controlled by player or AI. Handles movement and merging."""

    def __init__(self, name="Player", color=color.azure, is_bot=False):
        self.name = name
        self.color = color
        self.is_bot = is_bot
        self.speed = NORMAL_SPEED
        self.direction = Vec3(0, 0, 1)
        self.segments = []          # list of Cube entities
        self.ghost_trail = deque()  # positions for smooth following
        self.ghost_spacing = 0.5
        self.alive = True
        self.score = 0
        self.boosting = False
        self._boost_timer = 0

        head = Cube(value=2, position=(random.uniform(-5, 5), 0.5, random.uniform(-5, 5)))
        head.color = color
        head.label.color = text_color_for(color)
        self.segments.append(head)
        self.name_tag = Text(self.name, scale=1.5, origin=(0,0), parent=camera.ui)

    # ------------------------------------------------------------------
    # Movement and segment following
    # ------------------------------------------------------------------
    def update(self):
        if not self.alive:
            return

        # Determine target direction
        if not self.is_bot:
            self._update_direction_from_mouse()
        # AI bots override this method to choose direction

        # Apply boost if active
        current_speed = BOOST_SPEED if self.boosting else NORMAL_SPEED

        # Move head
        self.segments[0].position += self.direction * current_speed * time.dt

        # Record ghost position for trailing segments
        self.ghost_trail.appendleft(Vec3(self.segments[0].position))
        max_len = int(len(self.segments) * self.ghost_spacing / (current_speed * time.dt)) + 10
        if len(self.ghost_trail) > max_len:
            self.ghost_trail.pop()

        # Update tail segments by following ghost trail with spacing
        for i in range(1, len(self.segments)):
            idx = int(i * self.ghost_spacing / (current_speed * time.dt))
            if idx < len(self.ghost_trail):
                target = self.ghost_trail[idx]
                self.segments[i].position = lerp(self.segments[i].position, target, 8 * time.dt)

        # Update UI name tag above head
        screen_pos = camera.world_to_screen_point(self.segments[0].position + Vec3(0,1.5,0))
        self.name_tag.position = (screen_pos.x, screen_pos.y)

        # Handle boost cost
        if self.boosting:
            self._boost_timer += time.dt
            if self._boost_timer > BOOST_DROP_INTERVAL:
                self._boost_timer = 0
                self.drop_tail_cube()

    def _update_direction_from_mouse(self):
        """Rotate head towards mouse position on the plane."""
        if not mouse.world_point:
            return
        target = mouse.world_point
        target.y = self.segments[0].y
        self.direction = lerp(self.direction, (target - self.segments[0].position).normalized(), 4 * time.dt)
        self.segments[0].look_at(target)

    def drop_tail_cube(self):
        """Remove smallest cube when boosting."""
        if len(self.segments) <= 1:
            self.boosting = False
            return
        play_sound('boost_drop')
        segment = self.segments.pop()
        self.score -= segment.value
        spawn_collectible_cube(segment.position, value=segment.value)
        destroy(segment)

    # ------------------------------------------------------------------
    # Cube collection and merging
    # ------------------------------------------------------------------
    def collect_cube(self, cube):
        """Add cube to tail and trigger merging logic."""
        play_sound('collect')
        cube.disable()
        destroy(cube)
        new_seg = Cube(value=cube.value, position=self.segments[-1].position)
        new_seg.color = self.color
        self.segments.append(new_seg)
        self.score += cube.value
        self.merge_tail()

    def merge_tail(self):
        """Check tail from end to head for adjacent equal cubes and merge them."""
        merged = True
        while merged and len(self.segments) > 1:
            merged = False
            for i in range(len(self.segments)-1, 0, -1):
                a = self.segments[i]
                b = self.segments[i-1]
                if a.value == b.value:
                    play_sound('merge')
                    b.set_value(b.value * 2)
                    self.score += b.value
                    destroy(a)
                    self.segments.pop(i)
                    merged = True
                    break

    # ------------------------------------------------------------------
    # Combat with other snakes
    # ------------------------------------------------------------------
    def check_combat(self, snakes):
        if not self.alive:
            return
        head = self.segments[0]
        for other in snakes:
            if other is self or not other.alive:
                continue
            # Collision with any cube of other snake
            for seg in other.segments:
                if distance(head.position, seg.position) < 0.9:
                    self._handle_collision(other, seg)
                    return

    def _handle_collision(self, other, segment):
        head_value = self.segments[0].value
        seg_value = segment.value
        other_head_value = other.segments[0].value

        # If colliding with enemy head
        if segment is other.segments[0]:
            if head_value > other_head_value:
                self.absorb_other(other)
            elif head_value < other_head_value:
                self.die(killer=other)
            else:  # equal heads -> both die and new cube
                self.absorb_other(other)
                self.segments[0].set_value(head_value * 2)
        else:
            # colliding with enemy tail cube
            if head_value >= seg_value:
                other.remove_segment(segment)
                new = Cube(value=seg_value, position=self.segments[-1].position)
                new.color = self.color
                self.segments.append(new)
                self.score += seg_value
                other.score -= seg_value
                play_sound('eat_player')
                self.merge_tail()
            else:
                self.die(killer=other)

    def absorb_other(self, other):
        play_sound('eat_player')
        for seg in other.segments:
            spawn_collectible_cube(seg.position, value=seg.value)
            destroy(seg)
        other.segments.clear()
        other.alive = False
        kill_feed.add_message(f"{self.name} defeated {other.name}")

    def remove_segment(self, segment):
        if segment in self.segments:
            self.segments.remove(segment)
            spawn_collectible_cube(segment.position, value=segment.value)
            destroy(segment)

    def die(self, killer=None):
        play_sound('death')
        self.alive = False
        for seg in self.segments:
            spawn_collectible_cube(seg.position, value=seg.value)
            destroy(seg)
        self.segments.clear()
        kill_feed.add_message(f"{self.name} was killed" + (f" by {killer.name}" if killer else ""))


# ---------------------------------------------------------------------------
# AI control
# ---------------------------------------------------------------------------

class BotState(Enum):
    FARMING = 0
    HUNTING = 1
    FLEEING = 2


class BotSnake(Snake):
    """AI controlled snake with simple state machine."""

    def __init__(self, name="Bot", color=color.orange):
        super().__init__(name=name, color=color, is_bot=True)
        self.state = BotState.FARMING
        self.target_pos = None

    def update(self):
        if not self.alive:
            return
        self.decide_state()
        self.act_state()
        super().update()

    def decide_state(self):
        """Pick behaviour based on nearby snakes."""
        self.state = BotState.FARMING
        my_value = self.segments[0].value
        for snake in snakes:
            if snake is self or not snake.alive:
                continue
            d = distance(self.segments[0].position, snake.segments[0].position)
            if d < 15:
                if snake.segments[0].value * 1.5 < my_value:
                    self.state = BotState.HUNTING
                    self.target_pos = snake.segments[0].position
                    return
                elif snake.segments[0].value > my_value * 1.5:
                    self.state = BotState.FLEEING
                    self.target_pos = self.segments[0].position - (snake.segments[0].position - self.segments[0].position)
                    return

        # Default: look for nearest cube
        cubes = collectible_cubes
        if cubes:
            self.target_pos = min(cubes, key=lambda c: distance(c.position, self.segments[0].position)).position

    def act_state(self):
        if self.state == BotState.HUNTING:
            self.boosting = True
        elif self.state == BotState.FLEEING:
            self.boosting = True
        else:
            self.boosting = False

        if self.target_pos is not None:
            self.direction = lerp(self.direction, (self.target_pos - self.segments[0].position).normalized(), 3 * time.dt)
            self.segments[0].look_at(self.target_pos)


# ---------------------------------------------------------------------------
# Collectible cubes utilities
# ---------------------------------------------------------------------------
collectible_cubes = []


def spawn_collectible_cube(position=None, value=None):
    if position is None:
        x = random.uniform(-MAP_SIZE/2, MAP_SIZE/2)
        z = random.uniform(-MAP_SIZE/2, MAP_SIZE/2)
        position = Vec3(x, 0.5, z)
    value = value or random.choices([2, 4, 8], weights=[0.6, 0.3, 0.1])[0]
    cube = Cube(value=value, position=position)
    collectible_cubes.append(cube)
    return cube

# ---------------------------------------------------------------------------
# Kill feed UI
# ---------------------------------------------------------------------------
class KillFeed:
    def __init__(self, max_messages=5):
        self.messages = deque()
        self.max_messages = max_messages

    def add_message(self, text):
        msg = Text(text, origin=(0,0), scale=1.2, position=(0, 0), parent=camera.ui)
        self.messages.append({"entity": msg, "timer": 4})
        while len(self.messages) > self.max_messages:
            m = self.messages.popleft()
            destroy(m["entity"])

    def update(self):
        y = 0.45
        for msg in list(self.messages):
            msg["entity"].position = (0, y)
            msg["timer"] -= time.dt
            y -= 0.05
            if msg["timer"] <= 0:
                destroy(msg["entity"])
                self.messages.remove(msg)

kill_feed = KillFeed()

# ---------------------------------------------------------------------------
# Game state machine
# ---------------------------------------------------------------------------
class GameState(Enum):
    MENU = 0
    PLAYING = 1
    DEATH = 2
    END = 3


class Game:
    def __init__(self):
        self.state = GameState.MENU
        self.app = Ursina(borderless=False)
        self.arena = Entity(model='plane', scale=(MAP_SIZE,1,MAP_SIZE), color=color.dark_gray,
                            texture='white_cube', texture_scale=(MAP_SIZE, MAP_SIZE), collider='box')
        self.sky = Sky()
        camera.position = (0, 25, -25)
        camera.rotation_x = 45

        # UI
        self.leaderboard = Text("", origin=(0,0), position=(0.7,0.45), scale=1.2, parent=camera.ui)
        self.game_msg = Text("", scale=3, origin=(0,0), parent=camera.ui, enabled=False)
        self.menu_text = Text("CUBES 2048.io\nClick to start", scale=3, origin=(0,0), parent=camera.ui)

        self.player = None
        self.bots = []

        self.app.run(self.update)

    # ------------------------------------------------------------------
    def start_game(self):
        self.menu_text.enabled = False
        self.state = GameState.PLAYING
        self.player = Snake(name="You", color=color.azure)
        self.bots = [BotSnake(name=f"Bot{i}") for i in range(BOT_COUNT)]
        global snakes
        snakes = [self.player] + self.bots
        for _ in range(INITIAL_CUBES):
            spawn_collectible_cube()
        self.game_msg.enabled = False

    def show_end(self):
        self.state = GameState.END
        self.game_msg.text = "END GAME"
        self.game_msg.enabled = True
        invoke(self.reset_to_menu, delay=3)

    def reset_to_menu(self):
        for cube in collectible_cubes[:]:
            destroy(cube)
        collectible_cubes.clear()
        for s in snakes:
            for seg in s.segments:
                destroy(seg)
        self.menu_text.enabled = True
        self.leaderboard.text = ""
        kill_feed.messages.clear()
        self.state = GameState.MENU

    # ------------------------------------------------------------------
    def update(self):
        if self.state == GameState.MENU:
            if mouse.left:
                self.start_game()
            return

        if self.state in (GameState.PLAYING, GameState.DEATH):
            for cube in collectible_cubes:
                if distance(self.player.segments[0].position, cube.position) < 1:
                    self.player.collect_cube(cube)
                    collectible_cubes.remove(cube)
            for bot in self.bots:
                for cube in collectible_cubes[:]:
                    if distance(bot.segments[0].position, cube.position) < 1:
                        bot.collect_cube(cube)
                        collectible_cubes.remove(cube)

            # Update snakes
            for s in snakes:
                s.boosting = held_keys['shift'] if s is self.player else s.boosting
                s.update()

            # Combat checks
            for s in snakes:
                s.check_combat(snakes)

            # Remove dead snakes and spawn cubes from their body handled inside die()
            if not self.player.alive and self.state == GameState.PLAYING:
                self.state = GameState.DEATH
                self.game_msg.text = "KILLED"
                self.game_msg.enabled = True
                invoke(self.show_end, delay=2)

            # Periodically spawn new cubes
            if len(collectible_cubes) < INITIAL_CUBES:
                spawn_collectible_cube()

            # Leaderboard update
            alive_snakes = [s for s in snakes if s.alive]
            scores = sorted([(s.name, s.score) for s in alive_snakes], key=lambda x: x[1], reverse=True)
            board = "Leaderboard\n" + "\n".join(f"{name}: {score}" for name, score in scores[:10])
            self.leaderboard.text = board

            kill_feed.update()

        if self.state == GameState.END:
            # wait for reset via invoke
            pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    Game()
