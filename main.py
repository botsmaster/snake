from ursina import *
from snake2048.game.entities import CollectibleCube
from snake2048.game.snake import (
    Snake,
    spawn_collectible_cube,
    collectible_cubes,
    other_players,
    set_restart_callback,
)
from snake2048.network.client import WebSocketClient
import asyncio
import threading

# Initialize application
app = Ursina()

camera.orthographic = False
camera.fov = 60
mouse.locked = False

# Arena entity
arena = Entity(
    model='plane',
    scale=(50, 1, 50),
    color=color.dark_gray,
    texture='white_cube',
    texture_scale=(50, 50),
    collider='box'
)

# UI Elements
score_text = Text("Score: 0", position=(-0.8, 0.45), scale=2, color=color.white)
size_text = Text("Size: 1", position=(-0.8, 0.4), scale=2, color=color.white)
leaderboard_text = Text("Leaderboard:", position=(0.5, 0.45), scale=1.5, color=color.white)

# Local snake and camera controller
def restart_game():
    for cube in collectible_cubes[:]:
        destroy(cube)
        collectible_cubes.remove(cube)
    for snake in list(other_players.values()):
        for segment in snake.segments:
            destroy(segment)
    other_players.clear()
    for segment in local_snake.segments:
        destroy(segment)
    setup_game()

set_restart_callback(restart_game)

local_snake = None

class CameraController:
    def __init__(self):
        self.distance = 30
        self.height = 20

    def update(self):
        if local_snake and local_snake.alive:
            target_pos = local_snake.head.position
            camera.position = target_pos + Vec3(0, self.height, -self.distance)
            camera.look_at(target_pos)

camera_controller = CameraController()

# WebSocket client
ws_client = WebSocketClient()

async def ws_receive(data):
    if data['type'] != 'game_state_update':
        return
    # Update other players
    for pid, pdata in data['game_state']['players'].items():
        if pid == 'local_player':
            continue
        snake = other_players.get(pid)
        if not snake:
            snake = Snake(player_id=pid, player_color=color.red)
            other_players[pid] = snake
        if pdata['alive']:
            while len(snake.segments) < len(pdata['segments']):
                snake.grow(2)
            for seg, sdata in zip(snake.segments, pdata['segments']):
                seg.position = Vec3(*sdata[:3])
                seg.value = sdata[3]
                seg.text_entity.text = str(seg.value)
            snake.head.position = Vec3(*pdata['position'])
            snake.head.value = pdata['head_value']
            snake.head.text_entity.text = str(pdata['head_value'])
            snake.alive = True
        else:
            snake.die()

    # Update cubes
    server_ids = {c['id'] for c in data['game_state']['collectible_cubes']}
    for cube in collectible_cubes[:]:
        if cube.cube_id not in server_ids:
            destroy(cube)
            collectible_cubes.remove(cube)
    for cube_data in data['game_state']['collectible_cubes']:
        if not any(c.cube_id == cube_data['id'] for c in collectible_cubes):
            spawn_collectible_cube(position=Vec3(*cube_data['position']), value=cube_data['value'], cube_id=cube_data['id'])

ws_client.set_receive_callback(ws_receive)

async def send_state_loop():
    while True:
        if ws_client.websocket and ws_client.websocket.open and local_snake.alive:
            payload = {
                'type': 'player_state',
                'id': 'local_player',
                'position': [local_snake.head.x, local_snake.head.y, local_snake.head.z],
                'direction': [local_snake.direction.x, local_snake.direction.y, local_snake.direction.z],
                'head_value': local_snake.head.value,
                'segments': [[s.x, s.y, s.z, s.value] for s in local_snake.segments]
            }
            await ws_client.send(payload)
        await asyncio.sleep(0.1)

def setup_game():
    global local_snake
    local_snake = Snake(player_id='local_player', player_color=color.azure)
    for _ in range(5):
        spawn_collectible_cube()

setup_game()

# Main update loop
def update():
    if local_snake.alive:
        local_snake.update()
        local_snake.check_collision(ws_client.websocket)
    for snake in other_players.values():
        snake.update()
    all_snakes = [local_snake] + list(other_players.values())
    for snake in all_snakes:
        snake.check_collision_with_other_snakes(all_snakes, ws_client.websocket)
    camera_controller.update()
    score_text.text = f"Score: {local_snake.score}"
    size_text.text = f"Size: {len(local_snake.segments)}"

# Start websocket in separate thread

def start_ws():
    asyncio.run(ws_client.run(send_state_loop()))

threading.Thread(target=start_ws, daemon=True).start()

# Run Ursina app
app.run()
