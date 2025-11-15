# Multiplayer Game (Server + Player)

This project is a simple multiplayer game built with Python sockets and Pygame.  
It supports **multiple players** and **spectators**, all connecting through a central server.

---

## Requirements

- **Python 3.x**
- **pygame** library  

Install pygame with:

```bash
pip install pygame
```

## Steps to Execute

### 1. Start the Server

Open a terminal in the folder containing the files and run:

```bash
python server.py
```

This starts the server and listens for incoming connections.

## Start Player 1

Open a new terminal and run:

```bash
python player.py
```

You will be prompted to enter the following details:

Server host: localhost (or 127.0.0.1 if on the same machine)
Server port: 9999 (or whatever port you set)
Enter room code: ABC (you can use any code)
Mode: P (P = Play)

## Start Player 2

Open another terminal and run:

```bash
python player.py
```

Enter the same details as Player 1:

Server host: localhost
Server port: 9999
Enter room code: ABC
Mode: P

Once both players join the same room, the game will start automatically.

## (Optional) Start a Spectator

To watch the game as a spectator, open another terminal and run:

```bash
python player.py
```

Enter:

Server host: localhost
Server port: 9999
Enter room code: ABC
Mode: S (S = Spectate)

Spectators can watch the match in real time.

## Notes

All players must use the same room code to join the same game session.
Players and spectators can connect from different machines as long as they use the server’s IP address.
The server must remain running the entire time for the game to function.
