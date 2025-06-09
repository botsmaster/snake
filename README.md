# Snake 2048 Arena

Simple prototype of a multiplayer 3D snake game using the Ursina engine.

## Components
- `main.py` – client application.
- `snake2048/game` – game entities and logic.
- `snake2048/network/server.py` – minimal WebSocket game server.

## Running
1. Install dependencies:
   ```bash
   pip install ursina websockets
   ```
2. Start the server:
   ```bash
   python -m snake2048.network.server
   ```
3. In another terminal, run the client:
   ```bash
   python main.py
   ```

This project is a basic starting point and can be expanded further.
