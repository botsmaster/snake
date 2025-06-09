import asyncio
import json
import websockets
import random

class GameServer:
    def __init__(self, host='0.0.0.0', port=8765):
        self.host = host
        self.port = port
        self.clients = {}
        self.game_state = {
            'players': {},
            'collectible_cubes': []
        }

    async def handler(self, websocket, _):
        player_id = str(random.randint(1000, 9999))
        self.clients[player_id] = websocket
        self.game_state['players'][player_id] = {
            'position': [0, 0, 0],
            'direction': [0, 0, 1],
            'head_value': 2,
            'segments': [[0,0,0,2]],
            'alive': True
        }
        try:
            await self.send_state()
            async for msg in websocket:
                data = json.loads(msg)
                if data['type'] == 'player_state':
                    self.game_state['players'][player_id].update({
                        'position': data['position'],
                        'direction': data['direction'],
                        'head_value': data['head_value'],
                        'segments': data['segments'],
                        'alive': True
                    })
                elif data['type'] == 'collect_cube':
                    self.game_state['collectible_cubes'] = [
                        c for c in self.game_state['collectible_cubes'] if c['id'] != data['cube_id']
                    ]
                elif data['type'] == 'player_death':
                    self.game_state['players'][player_id]['alive'] = False
                await self.send_state()
        finally:
            self.clients.pop(player_id, None)
            self.game_state['players'].pop(player_id, None)
            await self.send_state()

    async def send_state(self):
        if not self.clients:
            return
        payload = json.dumps({'type': 'game_state_update', 'game_state': self.game_state})
        await asyncio.gather(*(c.send(payload) for c in list(self.clients.values()) if c.open))

    async def run(self):
        async with websockets.serve(self.handler, self.host, self.port):
            print(f"Server started on {self.host}:{self.port}")
            await asyncio.Future()  # Run forever

if __name__ == '__main__':
    server = GameServer()
    asyncio.run(server.run())
