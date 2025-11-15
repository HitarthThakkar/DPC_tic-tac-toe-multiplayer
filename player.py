# player.py -- cleaned, redesigned UI + correct networking behavior
import ast
import contextlib
import pygame
import socket
import time
import threading

# -------------------------
# Configuration / Globals
# -------------------------
HOST_PROMPT = "Server host (IP or hostname, e.g. 127.0.0.1): "
PORT_PROMPT = "Server port (e.g. 9999): "
ROOM_PROMPT = "Enter room code (e.g., ABC): "
MODE_PROMPT = "Mode [P=Play, S=Spectate] (default P): "

# Networking
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# Defaults
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 9999

host_input = input(f"Server host (default {DEFAULT_HOST}): ").strip()
host = host_input or DEFAULT_HOST

port_input = input(f"Server port (default {DEFAULT_PORT}): ").strip()
port = int(port_input) if port_input else DEFAULT_PORT

room_code = input("Enter room code (e.g., ABC): ").strip()
mode = input("Mode [P=Play, S=Spectate] (default P): ").strip().upper() or "P"

# Chat state
chat_messages = []          # list[str] messages (label: text)
chat_input = ""             # current typing buffer
chat_typing = False
MAX_CHAT = 300

# Game state
PLAYER_ONE = 1
PLAYER_TWO = 2
PLAYER_ONE_COLOR = (255, 0, 0)   # red X
PLAYER_TWO_COLOR = (0, 0, 200)   # blue O
title_color = (0, 0, 0)
subtitle_color = (80, 0, 130)
line_color = (0, 0, 0)

bottomMsg = ""
msg = "Waiting for peer"
currentPlayer = 0    # local player's number (0 if spectator)
allow = 0            # whether this client may send a move (server sent "Input")
matrix = [[0,0,0],[0,0,0],[0,0,0]]

# -------------------------
# Layout constants (redesign)
# -------------------------
SCREEN_WIDTH  = 1200
SCREEN_HEIGHT = 720   # taller so top bar fits

TOP_BAR_HEIGHT = 120

# Game area (left)
GAME_X = 40
GAME_Y = TOP_BAR_HEIGHT + 20
GAME_W = 700
GAME_H = SCREEN_HEIGHT - GAME_Y - 40

# Chat area (right)
CHAT_X = GAME_X + GAME_W + 20
CHAT_Y = TOP_BAR_HEIGHT + 20
CHAT_W = SCREEN_WIDTH - CHAT_X - 40
CHAT_H = GAME_H

# Grid geometry inside the game area
GRID_LEFT = GAME_X + 140
GRID_TOP  = GAME_Y + 60
CELL_SIZE = 120

# -------------------------
# Pygame init & fonts
# -------------------------
pygame.init()
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Tic Tac Toe")

# fonts
bigfont = pygame.font.Font('freesansbold.ttf', 56)
medfont = pygame.font.Font('freesansbold.ttf', 30)
smallfont = pygame.font.Font('freesansbold.ttf', 22)

clock = pygame.time.Clock()

# -------------------------
# Helpers: wrapping & rendering
# -------------------------
def wrap_lines(text, max_chars=40):
    """Simple fixed-width wrap preserving newlines."""
    if not text:
        return []
    out = []
    for paragraph in text.splitlines():
        p = paragraph.strip()
        if p == "":
            out.append("")
            continue
        while p:
            out.append(p[:max_chars])
            p = p[max_chars:]
    return out

def render_multiline_centered(text, center_x, start_y, font, color, max_chars=48, line_spacing=None):
    """Render wrapped lines centered horizontally at center_x. Returns end y."""
    if line_spacing is None:
        line_spacing = int(font.get_linesize() * 0.95)
    lines = wrap_lines(text, max_chars)
    y = start_y
    for line in lines:
        surf = font.render(line, True, color)
        x = center_x - surf.get_width() // 2
        screen.blit(surf, (x, y))
        y += line_spacing
    return y

def render_multiline_left(text, start_x, start_y, font, color, max_chars=36, line_spacing=None):
    """Render wrapped lines left-aligned; returns end y."""
    if line_spacing is None:
        line_spacing = int(font.get_linesize() * 0.95)
    lines = wrap_lines(text, max_chars)
    y = start_y
    for line in lines:
        surf = font.render(line, True, color)
        screen.blit(surf, (start_x, y))
        y += line_spacing
    return y

# -------------------------
# Drawing functions
# -------------------------
def draw_top_bar(title_text, subtitle_text):
    # top bar background (keeps it separate from game panel)
    pygame.draw.rect(screen, (255,255,255), (0, 0, SCREEN_WIDTH, TOP_BAR_HEIGHT))
    # Title centered top
    title_surf = bigfont.render(title_text, True, title_color)
    title_x = SCREEN_WIDTH // 2 - title_surf.get_width() // 2
    screen.blit(title_surf, (title_x, 8))
    # Subtitle (turn/status)
    subcolor = subtitle_color
    st = subtitle_text or ""
    lower = st.lower()
    if "player 1" in lower or "player one" in lower or "1" in lower and "player" in lower:
        subcolor = PLAYER_ONE_COLOR
    elif "player 2" in lower or "player two" in lower or "2" in lower and "player" in lower:
        subcolor = PLAYER_TWO_COLOR
    render_multiline_centered(st, SCREEN_WIDTH // 2, 72, medfont, subcolor, max_chars=60)

def draw_game_panel():
    # background rectangle for the game area
    pygame.draw.rect(screen, (245,245,245), (GAME_X, GAME_Y, GAME_W, GAME_H))
    pygame.draw.rect(screen, (200,200,200), (GAME_X, GAME_Y, GAME_W, GAME_H), 2)

    # draw grid lines
    x0 = GRID_LEFT
    y0 = GRID_TOP
    # verticals
    pygame.draw.line(screen, line_color, (x0 + CELL_SIZE, y0), (x0 + CELL_SIZE, y0 + 3*CELL_SIZE), 5)
    pygame.draw.line(screen, line_color, (x0 + 2*CELL_SIZE, y0), (x0 + 2*CELL_SIZE, y0 + 3*CELL_SIZE), 5)
    # horizontals
    pygame.draw.line(screen, line_color, (x0, y0 + CELL_SIZE), (x0 + 3*CELL_SIZE, y0 + CELL_SIZE), 5)
    pygame.draw.line(screen, line_color, (x0, y0 + 2*CELL_SIZE), (x0 + 3*CELL_SIZE, y0 + 2*CELL_SIZE), 5)

def draw_board_matrix(mat):
    # draw X and O based on matrix
    for r in range(3):
        for c in range(3):
            cx = GRID_LEFT + int((c + 0.5) * CELL_SIZE) - 32
            cy = GRID_TOP + int((r + 0.5) * CELL_SIZE) - 40
            if mat[r][c] == PLAYER_ONE:
                surf = bigfont.render("X", True, PLAYER_ONE_COLOR)
                screen.blit(surf, (cx, cy))
            elif mat[r][c] == PLAYER_TWO:
                surf = bigfont.render("O", True, PLAYER_TWO_COLOR)
                screen.blit(surf, (cx, cy))

def draw_bottom_message(text):
    # draw centered message above bottom edge of game area
    bottom_center_x = GAME_X + GAME_W // 2
    bottom_start_y = GAME_Y + GAME_H - 120
    color = subtitle_color
    lower = (text or "").lower()
    if "winner" in lower:
        if "one" in lower or "player one" in lower or "player 1" in lower:
            color = PLAYER_ONE_COLOR
        elif "two" in lower or "player two" in lower or "player 2" in lower:
            color = PLAYER_TWO_COLOR
        else:
            color = (100, 0, 150)
    elif "draw" in lower:
        color = (140, 0, 205)
    render_multiline_centered(text, bottom_center_x, bottom_start_y, medfont, color, max_chars=48)

def draw_chat_panel():
    # background/border
    pygame.draw.rect(screen, (240,240,240), (CHAT_X, CHAT_Y, CHAT_W, CHAT_H))
    pygame.draw.rect(screen, (200,200,200), (CHAT_X, CHAT_Y, CHAT_W, CHAT_H), 2)
    # header
    header = medfont.render("CHAT", True, (0,0,0))
    screen.blit(header, (CHAT_X + 8, CHAT_Y + 6))
    # messages area
    y = CHAT_Y + 46
    max_lines = 20
    recent = chat_messages[-(MAX_CHAT if MAX_CHAT < 1000 else MAX_CHAT):]  # avoid tiny negative
    # show only recent region that fits
    start_index = max(0, len(recent) - max_lines)
    for line in recent[start_index:]:
        if ":" in line:
            label, _, rest = line.partition(":")
            label_surf = smallfont.render(label + ":", True, (0,100,0))
            screen.blit(label_surf, (CHAT_X + 8, y))
            # wrap remainder
            wrapped = wrap_lines(rest.strip(), max_chars=28)
            if not wrapped:
                wrapped = [""]
            for i, wline in enumerate(wrapped):
                surf = smallfont.render(wline, True, (0,0,120))
                if i == 0:
                    screen.blit(surf, (CHAT_X + 8 + label_surf.get_width() + 6, y))
                else:
                    screen.blit(surf, (CHAT_X + 8, y + 20 * i))
            y += max(1, len(wrapped)) * 20
        else:
            wrapped = wrap_lines(line, max_chars=36)
            for wline in wrapped:
                surf = smallfont.render(wline, True, (40,40,40))
                screen.blit(surf, (CHAT_X + 8, y))
                y += 20
    # input box
    pygame.draw.rect(screen, (255,255,255), (CHAT_X + 8, CHAT_Y + CHAT_H - 54, CHAT_W - 16, 40))
    pygame.draw.rect(screen, (0,0,0), (CHAT_X + 8, CHAT_Y + CHAT_H - 54, CHAT_W - 16, 40), 2)
    prompt = f"> {chat_input}" if chat_typing else "> (press Enter to chat)"
    in_surf = medfont.render(prompt, True, (0,0,0))
    screen.blit(in_surf, (CHAT_X + 16, CHAT_Y + CHAT_H - 46))

# -------------------------
# Event handling & logic
# -------------------------
def validate_input(r, c):
    if r < 0 or r > 2 or c < 0 or c > 2:
        return False
    return matrix[r][c] == 0

def handle_mouse_click(pos):
    global allow
    x, y = pos
    # ensure click inside grid
    if x < GRID_LEFT or x > GRID_LEFT + 3*CELL_SIZE or y < GRID_TOP or y > GRID_TOP + 3*CELL_SIZE:
        return
    c = int((x - GRID_LEFT) / CELL_SIZE)
    r = int((y - GRID_TOP) / CELL_SIZE)
    if not allow:
        return
    if not validate_input(r, c):
        return
    # send move to server; server will broadcast Matrix update
    try:
        s.send(f"{r},{c}".encode())
    except Exception as e:
        print("Error sending move:", e)
    # prevent repeat send until server signals next "Input"
    # server will set allow again when appropriate
    # set allow=0 locally to avoid accidental double sends
    set_allow(0)

def handle_keydown(event):
    global chat_typing, chat_input
    if chat_typing:
        if event.key == pygame.K_RETURN:
            text = chat_input.strip()
            if text:
                with contextlib.suppress(Exception):
                    s.send(f"CHAT:{text}".encode())
                chat_input = ""
            chat_typing = False
        elif event.key == pygame.K_BACKSPACE:
            chat_input = chat_input[:-1]
        elif event.unicode and 32 <= ord(event.unicode) <= 126:
            chat_input += event.unicode
    else:
        if event.key == pygame.K_RETURN:
            chat_typing = True
            chat_input = ""

def process_pygame_events():
    for ev in pygame.event.get():
        if ev.type == pygame.QUIT:
            return False
        if ev.type == pygame.MOUSEBUTTONUP:
            handle_mouse_click(pygame.mouse.get_pos())
        if ev.type == pygame.KEYDOWN:
            handle_keydown(ev)
    return True

def set_allow(v):
    global allow
    allow = v

# -------------------------
# Networking: receiver thread
# -------------------------
def accept_msg():
    """Receiver thread: process server messages and update UI state."""
    global matrix, msg, bottomMsg, allow, chat_messages, currentPlayer
    while True:
        try:
            data = s.recv(4096)
            if not data:
                time.sleep(0.05)
                continue
            decoded = data.decode(errors="ignore").strip()

            # direct "Input" message: now it's your turn
            if decoded == "Input":
                set_allow(1)
                continue

            # If server sends "Matrix" then next recv should be the matrix string
            if decoded == "Matrix":
                nxt = s.recv(8192)
                if not nxt:
                    continue
                try:
                    matrix = ast.literal_eval(nxt.decode())
                except Exception:
                    # fallback: ignore bad parse
                    pass
                # after matrix update, local client should wait for server "Input" if it's next player's turn
                set_allow(0)
                continue

            # Over then next msg will be result string
            if decoded == "Over":
                nxt = s.recv(4096)
                if nxt:
                    bottomMsg = nxt.decode(errors="ignore")
                    msg = "~~~Game Over~~~"
                else:
                    msg = "~~~Game Over~~~"
                # allow loop to finish or let user quit
                continue

            # Chat messages: "CHAT:<label>:<text>"
            if decoded.startswith("CHAT:"):
                payload = decoded[len("CHAT:"):].strip()
                # payload usually label:text
                if ":" in payload:
                    lbl, _, rest = payload.partition(":")
                    chat_messages.append(f"{lbl}:{rest}")
                else:
                    chat_messages.append(payload)
                # auto trim
                if len(chat_messages) > MAX_CHAT:
                    chat_messages = chat_messages[-MAX_CHAT:]
                continue

            # Greeting or status messages: server may send "<<< You are player 1 >>>" etc.
            # Save into bottomMsg or msg as appropriate
            # Try to interpret player assignment
            if "player 1" in decoded.lower():
                currentPlayer = 1
                bottomMsg = decoded
                msg = "You are Player 1"
                continue
            if "player 2" in decoded.lower():
                currentPlayer = 2
                bottomMsg = decoded
                msg = "You are Player 2"
                continue

            # Any other server-sent status (like "Player One's Turn")
            msg = decoded

        except Exception as e:
            # keep alive; print for debugging
            # (do not spam console)
            # print("accept_msg error:", e)
            time.sleep(0.05)
            continue

# -------------------------
# Startup & Main loop
# -------------------------
def start_client():
    global bottomMsg, currentPlayer
    try:
        s.connect((host, port))
    except Exception as e:
        print("Could not connect to server:", e)
        return

    # initial handshake: send ROOM or SPECTATE exactly once
    try:
        if mode == "S":
            s.send(f"SPECTATE {room_code}".encode())
        else:
            s.send(f"ROOM {room_code}".encode())
    except Exception:
        pass

    # receive initial greeting (may contain player assignment)
    try:
        init = s.recv(4096)
        if init:
            decoded = init.decode(errors="ignore")
            bottomMsg = decoded
            if "player 1" in decoded.lower():
                currentPlayer = 1
            elif "player 2" in decoded.lower():
                currentPlayer = 2
    except Exception:
        pass

    # start receiver thread
    t = threading.Thread(target=accept_msg, daemon=True)
    t.start()

    # main pygame loop
    running = True
    while running:
        running = process_pygame_events()
        # drawing
        screen.fill((255,255,255))
        draw_top_bar("TIC TAC TOE", msg)
        draw_game_panel()
        draw_board_matrix(matrix)
        draw_bottom_message(bottomMsg)
        draw_chat_panel()
        pygame.display.flip()
        clock.tick(30)

    # cleanup socket on exit
    try:
        s.close()
    except Exception:
        pass
    pygame.quit()

if __name__ == "__main__":
    start_client()