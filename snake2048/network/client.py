import asyncio
import json
import websockets

class WebSocketClient:
    """Handle connection to game server and state exchange."""

    def __init__(self, uri="ws://localhost:8765"):
        self.uri = uri
        self.websocket = None
        self.reconnect_delay = 5
        self.receive_callback = None
        self.running = True
        self.loop = None

    def set_receive_callback(self, callback):
        self.receive_callback = callback

    async def connect(self):
        while self.running:
            try:
                self.websocket = await websockets.connect(self.uri)
                await self.websocket.send(json.dumps({"type": "player_connect"}))
                await self._receive_loop()
            except Exception as exc:
                print(f"WebSocket error: {exc}. Reconnecting in {self.reconnect_delay}s")
                await asyncio.sleep(self.reconnect_delay)

    async def _receive_loop(self):
        try:
            async for message in self.websocket:
                if self.receive_callback:
                    await self.receive_callback(json.loads(message))
        except websockets.exceptions.ConnectionClosed:
            pass

    async def send(self, data: dict):
        if self.websocket and self.websocket.open:
            await self.websocket.send(json.dumps(data))

    async def run(self, send_state_coro):
        self.loop = asyncio.get_running_loop()
        await asyncio.gather(self.connect(), send_state_coro)

    def send_threadsafe(self, data: dict):
        """Send data to the server from outside the websocket thread."""
        if self.loop and self.websocket and self.websocket.open:
            asyncio.run_coroutine_threadsafe(self.send(data), self.loop)
