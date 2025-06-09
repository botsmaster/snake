from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
import random
import asyncio
import websockets
import json
import threading
import time

# Инициализация приложения
app = Ursina()

# Отключение встроенного управления камерой Ursina
camera.orthographic = False
camera.fov = 60
mouse.locked = False  # Разблокируем мышь для свободного управления

# Создание арены
arena = Entity(
    model='plane',
    scale=(50, 1, 50),
    color=color.dark_gray,
    texture='white_cube',
    texture_scale=(50, 50),
    collider='box'
)

# UI элементы
score_text = Text("Score: 0", position=(-0.8, 0.45), scale=2, color=color.white)
size_text = Text("Size: 1", position=(-0.8, 0.4), scale=2, color=color.white)
leaderboard_text = Text("Leaderboard:", position=(0.5, 0.45), scale=1.5, color=color.white)
game_over_text = Text("Game Over!", enabled=False, position=(0, 0), scale=3, color=color.red, origin=(0, 0))

class SnakeSegment(Entity):
    def __init__(self, position=(0, 0, 0), value=2, player_color=color.blue):
        super().__init__(
            model='cube',
            color=player_color,
            position=position,
            scale=1,
            collider='box'
        )
        self.value = value
        self.text_entity = Text(text=str(self.value), parent=self, y=0.6, scale=10, origin=(0, 0), color=color.white)

class CollectibleCube(Entity):
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
        self.text_entity = Text(text=str(self.value), parent=self, y=0.6, scale=10, origin=(0, 0), color=color.white)

class Snake:
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

        # Сохранение позиции головы
        self.position_history.insert(0, self.head.position)

        # Движение головы
        self.head.position += self.direction * time.dt * self.speed

        # Обновление позиций сегментов
        for i in range(1, len(self.segments)):
            target_pos_index = int(i * self.segment_spacing / (self.speed * time.dt))
            if target_pos_index < len(self.position_history):
                self.segments[i].position = self.position_history[target_pos_index]
            else:
                self.segments[i].position = self.segments[i-1].position - self.direction * self.segment_spacing

        # Ограничение длины истории позиций
        max_history_length = int(len(self.segments) * self.segment_spacing / (self.speed * time.dt)) + 10
        if len(self.position_history) > max_history_length:
            self.position_history = self.position_history[:max_history_length]

        # Управление только для локального игрока
        if self.player_id == "local_player":
            # Проверка ввода с клавиатуры
            if held_keys['w'] and self.direction != Vec3(0, 0, -1):
                self.direction = Vec3(0, 0, 1)
            if held_keys['s'] and self.direction != Vec3(0, 0, 1):
                self.direction = Vec3(0, 0, -1)
            if held_keys['a'] and self.direction != Vec3(1, 0, 0):
                self.direction = Vec3(-1, 0, 0)
            if held_keys['d'] and self.direction != Vec3(-1, 0, 0):
                self.direction = Vec3(1, 0, 0)

    def grow(self, value):
        new_segment = SnakeSegment(position=self.segments[-1].position, value=value, player_color=self.player_color)
        self.segments.append(new_segment)
        self.score += value

    def collect_cube(self, cube):
        if cube.value <= self.head.value:
            if cube.value == self.head.value:
                self.head.value *= 2
                self.head.text_entity.text = str(self.head.value)
            self.grow(cube.value)
            collectible_cubes.remove(cube)
            destroy(cube)
            # Отправка сообщения о сборе куба
            if websocket_client and websocket_client.open:
                asyncio.create_task(websocket_client.send(json.dumps({
                    "type": "collect_cube",
                    "cube_id": cube.cube_id
                })))
        else:
            print("Cannot collect cube: value too high!")

    def check_collision_with_other_snakes(self, other_snakes):
        if not self.alive:
            return
        for other_snake in other_snakes:
            if other_snake.player_id != self.player_id and other_snake.alive:
                if distance(self.head.position, other_snake.head.position) < 1.0:
                    if self.head.value > other_snake.head.value:
                        other_snake.die()
                    elif self.head.value < other_snake.head.value:
                        self.die()
                    else:
                        self.die()
                        other_snake.die()

    def die(self):
        self.alive = False
        if websocket_client and websocket_client.open:
            asyncio.create_task(websocket_client.send(json.dumps({
                "type": "player_death",
                "id": self.player_id
            })))
        for segment in self.segments:
            segment.visible = False
        if self.player_id == "local_player":
            game_over_text.enabled = True
            invoke(restart_game, delay=3)  # Перезапуск через 3 секунды

    def check_collision(self):
        if not self.alive:
            return
        # Проверка столкновения с границами
        if abs(self.head.x) > 24 or abs(self.head.z) > 24:
            print("Collision with boundary!")
            self.die()
        # Проверка столкновения с собственным телом
        for i in range(1, len(self.segments)):
            if distance(self.head.position, self.segments[i].position) < 0.8:
                print("Self-collision!")
                self.die()
        # Проверка столкновения с кубами (только для локального игрока)
        if self.player_id == "local_player":
            for cube in collectible_cubes[:]:
                if distance(self.head.position, cube.position) < 1.0:
                    self.collect_cube(cube)
                    break

collectible_cubes = []
other_players = {}

def spawn_collectible_cube(position=None, value=None, cube_id=None):
    if position is None:
        x = random.uniform(-20, 20)
        z = random.uniform(-20, 20)
        position = (x, 0.5, z)
    value = value or random.choice([2, 4, 8])
    new_cube = CollectibleCube(position=position, value=value, cube_id=cube_id)
    collectible_cubes.append(new_cube)

# Создание локального игрока
local_snake = Snake(player_id="local_player", player_color=color.blue)

# Спавн начальных кубов
for _ in range(5):
    spawn_collectible_cube()

# WebSocket клиент
websocket_client = None
websocket_reconnect_delay = 5  # Задержка перед повторным подключением

async def connect_to_server():
    global websocket_client
    uri = "ws://localhost:8765"
    while True:
        try:
            websocket_client = await websockets.connect(uri)
            print("Connected to WebSocket server")
            await websocket_client.send(json.dumps({"type": "player_connect", "id": "local_player"}))
            await receive_messages()
        except Exception as e:
            print(f"Could not connect to WebSocket server: {e}. Reconnecting in {websocket_reconnect_delay} seconds...")
            await asyncio.sleep(websocket_reconnect_delay)
        finally:
            if websocket_client:
                await websocket_client.close()

async def receive_messages():
    try:
        async for message in websocket_client:
            data = json.loads(message)
            if data["type"] == "game_state_update":
                # Обновление других игроков
                for player_id, player_data in data["game_state"]["players"].items():
                    if player_id != "local_player":
                        if player_id not in other_players:
                            other_players[player_id] = Snake(player_id=player_id, player_color=color.red)
                        other_snake = other_players[player_id]
                        if player_data["alive"]:
                            other_snake.alive = True
                            other_snake.head.position = Vec3(*player_data["position"])
                            other_snake.head.value = player_data["head_value"]
                            other_snake.head.text_entity.text = str(other_snake.head.value)
                            # Обновление сегментов
                            while len(other_snake.segments) < len(player_data["segments"]):
                                other_snake.grow(2)
                            while len(other_snake.segments) > len(player_data["segments"]):
                                destroy(other_snake.segments[-1])
                                other_snake.segments.pop()
                            for i, segment_data in enumerate(player_data["segments"]):
                                other_snake.segments[i].position = Vec3(*segment_data[:3])
                                other_snake.segments[i].value = segment_data[3]
                                other_snake.segments[i].text_entity.text = str(segment_data[3])
                        else:
                            other_snake.die()
                
                # Обновление кубов
                server_cube_ids = {cube_data["id"] for cube_data in data["game_state"]["collectible_cubes"]}
                for cube in collectible_cubes[:]:
                    if cube.cube_id not in server_cube_ids:
                        destroy(cube)
                        collectible_cubes.remove(cube)
                for cube_data in data["game_state"]["collectible_cubes"]:
                    if not any(c.cube_id == cube_data["id"] for c in collectible_cubes):
                        spawn_collectible_cube(position=Vec3(*cube_data["position"]), value=cube_data["value"], cube_id=cube_data["id"])
    except websockets.exceptions.ConnectionClosed:
        print("WebSocket connection closed")
        raise

async def send_player_state():
    while True:
        if websocket_client and websocket_client.open and local_snake.alive:
            player_state = {
                "type": "player_state",
                "id": "local_player",
                "position": [local_snake.head.x, local_snake.head.y, local_snake.head.z],
                "direction": [local_snake.direction.x, local_snake.direction.y, local_snake.direction.z],
                "head_value": local_snake.head.value,
                "segments": [[s.x, s.y, s.z, s.value] for s in local_snake.segments]
            }
            await websocket_client.send(json.dumps(player_state))
        await asyncio.sleep(0.1)  # Отправка каждые 0.1 секунды

def update_ui():
    score_text.text = f"Score: {local_snake.score}"
    size_text.text = f"Size: {len(local_snake.segments)}"
    leaderboard_info = ["Leaderboard:"]
    all_snakes = [local_snake] + list(other_players.values())
    sorted_snakes = sorted([s for s in all_snakes if s.score > 0], key=lambda x: x.score, reverse=True)
    for i, snake in enumerate(sorted_snakes[:5]):
        player_name = "You" if snake.player_id == "local_player" else snake.player_id
        leaderboard_info.append(f"{i+1}. {player_name}: {snake.score}")
    leaderboard_text.text = "\n".join(leaderboard_info)

class CameraController:
    def __init__(self):
        self.camera_mode = "follow"
        self.distance = 30
        self.height = 20
        self.target_snake = local_snake

    def update(self):
        if held_keys['tab']:  # Переключение режима камеры
            self.camera_mode = "free" if self.camera_mode == "follow" else "follow"

        if self.camera_mode == "follow" and self.target_snake.alive:
            target_pos = self.target_snake.head.position
            camera.position = target_pos + Vec3(0, self.height, -self.distance)
            camera.look_at(target_pos)
        elif self.camera_mode == "free":
            # Управление камерой мышью
            if mouse.right:
                camera.rotation_y += mouse.velocity[0] * 100
                camera.rotation_x -= mouse.velocity[1] * 100
                camera.rotation_x = clamp(camera.rotation_x, -90, 90)
            if held_keys['w']:
                camera.position += camera.forward * 20 * time.dt
            if held_keys['s']:
                camera.position -= camera.forward * 20 * time.dt
            if held_keys['a']:
                camera.position -= camera.right * 20 * time.dt
            if held_keys['d']:
                camera.position += camera.right * 20 * time.dt
            if held_keys['q']:
                camera.position += camera.up * 20 * time.dt
            if held_keys['e']:
                camera.position -= camera.up * 20 * time.dt

        # Управление расстоянием и высотой камеры
        if held_keys['r']:
            self.height = min(40, self.height + 20 * time.dt)
        if held_keys['f']:
            self.height = max(5, self.height - 20 * time.dt)
        if held_keys['t']:
            self.distance = max(10, self.distance - 20 * time.dt)
        if held_keys['g']:
            self.distance = min(50, self.distance + 20 * time.dt)

def restart_game():
    global local_snake, collectible_cubes, other_players
    # Очистка текущего состояния
    for cube in collectible_cubes:
        destroy(cube)
    collectible_cubes.clear()
    for snake in other_players.values():
        for segment in snake.segments:
            destroy(segment)
    other_players.clear()
    for segment in local_snake.segments:
        destroy(segment)
    # Создание нового локального игрока
    local_snake = Snake(player_id="local_player", player_color=color.blue)
    # Спавн новых кубов
    for _ in range(5):
        spawn_collectible_cube()
    game_over_text.enabled = False
    camera_controller.target_snake = local_snake

camera_controller = CameraController()

def update():
    if local_snake.alive:
        local_snake.update()
        local_snake.check_collision()
    for other_snake in other_players.values():
        other_snake.update()
    all_snakes = [local_snake] + list(other_players.values())
    for snake in all_snakes:
        snake.check_collision_with_other_snakes(all_snakes)
    camera_controller.update()
    update_ui()

def start_websocket():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(connect_to_server())
        loop.run_until_complete(send_player_state())
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        loop.close()

# Запуск WebSocket в отдельном потоке
websocket_thread = threading.Thread(target=start_websocket, daemon=True)
websocket_thread.start()

# Запуск приложения
app.run()
