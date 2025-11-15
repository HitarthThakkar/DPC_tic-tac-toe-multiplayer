# server.py (fixed)
import contextlib
import socket
import threading
import time
import select

# Server configuration
HOST = "0.0.0.0"   # Listen on all interfaces
PORT = 9999

# Player identifiers
PLAYER_ONE = 1
PLAYER_TWO = 2

# Room management
rooms = {}           # code -> room dict
rooms_lock = threading.Lock()

def room_conns_all(room):
    """Return all connections in the room (players + spectators)."""
    return room["players"] + room.get("spectators", [])

def send_to_all(room, text):
    """Send a message to all connections in the room (raw text)."""
    data = text.encode()
    for c in room_conns_all(room):
        with contextlib.suppress(Exception):
            c.send(data)
    # small pause is optional
    time.sleep(0.02)

def send_to_players(room, text):
    """Send a message to both players in the room (raw text)."""
    data = text.encode()
    for c in room["players"]:
        with contextlib.suppress(Exception):
            c.send(data)
    time.sleep(0.02)

def send_common_msg(room, text):
    """
    Send a plain text message to all in the room.
    Used for control messages like 'Over', or winner messages.
    """
    send_to_all(room, text)

def get_sender_label(room, conn):
    """Return a label string for the given connection: Player1/Player2/spec_N."""
    try:
        if conn in room["players"]:
            idx = room["players"].index(conn)
            return f"Player{idx + 1}"
        if conn in room.get("spectators", []):
            # spectators are indexed starting at 1 for readability
            idx = room["spectators"].index(conn)
            return f"spec_{idx + 1}"
    except Exception:
        pass
    return "Unknown"

def broadcast_chat(room, origin_conn, text):
    """Broadcast a chat message to all in the room with a sender label."""
    label = get_sender_label(room, origin_conn)
    # Format: CHAT:<label>:<text>
    send_to_all(room, f"CHAT:{label}:{text}")

def get_input(room, current_player):
    """
    Handle input for the current player's turn.
    Also relays chat messages from players and spectators.
    """
    # pick connections for players (may be missing until both in)
    if len(room["players"]) < 2:
        # can't proceed until two players present
        return

    turn_conn = room["players"][0] if current_player == PLAYER_ONE else room["players"][1]
    other_conn = room["players"][1] if current_player == PLAYER_ONE else room["players"][0]
    turn_label = "Player One's Turn" if current_player == PLAYER_ONE else "Player Two's Turn"

    print(f"[{room['code']}] {turn_label}")
    send_to_all(room, turn_label)

    # Prompt the current player for input
    try:
        turn_conn.send("Input".encode())
    except Exception:
        with contextlib.suppress(Exception):
            turn_conn.send("Error".encode())
        return

    # listen on all room sockets (players + spectators) so chat comes through immediately
    sockets = room_conns_all(room)[:]
    # set small timeout and loop until a valid move arrives from turn_conn
    while True:
        try:
            if not sockets:
                time.sleep(0.1)
                continue
            readable, _, _ = select.select(sockets, [], [], 0.5)
            for r in readable:
                data = r.recv(2048 * 10)
                if not data:
                    # closed or empty; drop it
                    with contextlib.suppress(Exception):
                        if r in room.get("spectators", []):
                            room["spectators"].remove(r)
                        elif r in room.get("players", []):
                            # player disconnected - notify and end
                            print(f"[{room['code']}] player disconnected")
                            try:
                                r.close()
                            except Exception:
                                pass
                        # refresh sockets
                        sockets = room_conns_all(room)[:]
                    continue
                text = data.decode().strip()

                # If this is the current player sending a move "x,y"
                if r is turn_conn and ("," in text) and text.count(",") == 1:
                    xs, ys = text.split(",")
                    try:
                        x, y = int(xs), int(ys)
                    except Exception:
                        # bad coordinates - ignore
                        continue
                    # update matrix and inform all clients
                    room["matrix"][x][y] = current_player
                    send_to_all(room, "Matrix")
                    send_to_all(room, str(room["matrix"]))
                    return  # end this get_input (turn completed)

                # Chat handling: expected "CHAT:<message>" from client
                if text.startswith("CHAT:"):
                    msg = text[len("CHAT:"):].strip()
                    # broadcast including the origin connection for labeling
                    broadcast_chat(room, r, msg)
                    continue

                # Allow server admin messages or other control messages to be ignored/handled
            # loop back waiting for next readable
        except Exception as e:
            # keep the game alive if possible, but log issues
            print(f"[{room['code']}] select/recv error: {e}")
            time.sleep(0.1)
            continue

def check_rows(matrix):
    return next((row[0] for row in matrix if row[0] == row[1] == row[2] != 0), 0)

def check_columns(matrix):
    return next(
        (
            matrix[0][i]
            for i in range(3)
            if matrix[0][i] == matrix[1][i] == matrix[2][i] != 0
        ),
        0,
    )

def check_diagonals(matrix):
    if matrix[0][0] == matrix[1][1] == matrix[2][2] != 0:
        return matrix[0][0]
    return matrix[0][2] if matrix[0][2] == matrix[1][1] == matrix[2][0] != 0 else 0

def check_winner(matrix):
    return check_rows(matrix) or check_columns(matrix) or check_diagonals(matrix)

def start_game_for_room(code):
    room = rooms[code]
    print(f"[{code}] Starting game for players: {room['addrs']}")
    result = 0
    turn_count = 0
    while result == 0 and turn_count < 9:
        current = PLAYER_ONE if (turn_count % 2 == 0) else PLAYER_TWO
        get_input(room, current)
        result = check_winner(room["matrix"])
        turn_count += 1

    # notify game over and winner/draw (plain messages)
    send_common_msg(room, "Over")
    if result == PLAYER_ONE:
        lastmsg = "Player One is the winner!!"
    elif result == PLAYER_TWO:
        lastmsg = "Player Two is the winner!!"
    else:
        lastmsg = "Draw game!! Try again later!"

    send_common_msg(room, lastmsg)
    time.sleep(1)
    # Close connections and clean up
    for conn in room["players"] + room.get("spectators", []):
        with contextlib.suppress(Exception):
            conn.close()
    with rooms_lock:
        rooms.pop(code, None)
    print(f"[{code}] Game finished. Room cleaned up.")

def join_room(conn, addr, code):
    """Add a player to a room, or create a new room if needed."""
    with rooms_lock:
        room = rooms.get(code)
        if room is None:
            # Create new room and add first player
            room = {
                "code": code,
                "players": [conn],
                "addrs":   [addr],
                "spectators": [],
                "matrix":  [[0,0,0],[0,0,0],[0,0,0]],
            }
            rooms[code] = room
            conn.send("<<< You are player 1 >>>".encode())
            print(f"[{code}] Player 1 - [{addr[0]}:{addr[1]}] (waiting for Player 2)")
        elif len(room["players"]) == 1:
            # Add second player and start game
            room["players"].append(conn)
            room["addrs"].append(addr)
            conn.send("<<< You are player 2 >>>".encode())
            print(f"[{code}] Player 2 - [{addr[0]}:{addr[1]}] (room ready)")
            t = threading.Thread(target=start_game_for_room, args=(code,), daemon=True)
            t.start()
        else:
            # Room is full
            conn.send("Room Full".encode())
            conn.close()
            print(f"[{code}] Connection refused (room full)")

def join_as_spectator(conn, addr, code):
    """Add a spectator to a room, or create a waiting room if needed."""
    with rooms_lock:
        room = rooms.get(code)
        if room is None:
            # Create an empty room if not present
            room = {
                "code": code,
                "players": [],
                "addrs":   [],
                "spectators": [],
                "matrix":  [[0,0,0],[0,0,0],[0,0,0]],
            }
            rooms[code] = room

        room.setdefault("spectators", []).append(conn)

    try:
        conn.send("<<< You are spectator >>>".encode())
        # Immediately sync current board
        conn.send("Matrix".encode())
        conn.send(str(room["matrix"]).encode())
        print(f"[{code}] Spectator [{addr[0]}:{addr[1]}] joined ({len(room['spectators'])} total)")
    except Exception:
        # If we can’t talk, drop them
        with contextlib.suppress(Exception):
            conn.close()
        with rooms_lock:
            if conn in room.get("spectators", []):
                room["spectators"].remove(conn)

def start_server():
    """Start the Tic Tac Toe server and handle incoming connections."""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen(10)
    print(f"Tic Tac Toe server started\nListening on {HOST}:{PORT}")

    try:
        while True:
            conn, addr = server_socket.accept()
            # Expect: b"ROOM <code>" or b"SPECTATE <code>"
            try:
                first = conn.recv(1024).decode().strip()
                verb, _, code = first.partition(" ")
                verb = verb.upper().strip()
                code = code.strip().upper()

                if verb not in ("ROOM", "SPECTATE") or not code:
                    conn.send("Protocol Error".encode())
                    conn.close()
                    continue

                if verb == "ROOM":
                    join_room(conn, addr, code)
                else:
                    join_as_spectator(conn, addr, code)

            except Exception as e:
                print("Handshake error:", e)
                with contextlib.suppress(Exception):
                    conn.close()
    except KeyboardInterrupt:
        print("\nKeyboard Interrupt - shutting down")
    finally:
        server_socket.close()

if __name__ == "__main__":
    start_server()