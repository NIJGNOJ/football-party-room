import json
import os
import random
import string
import threading
import time
import uuid
from copy import deepcopy
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8123"))
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
ROOM_TTL_SECONDS = int(os.getenv("ROOM_TTL_SECONDS", str(6 * 60 * 60)))
CLEANUP_INTERVAL_SECONDS = int(os.getenv("CLEANUP_INTERVAL_SECONDS", "60"))
BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
STATE_LOCK = threading.Lock()
ROOMS = {}


ROUND_BANK = [
    {
        "type": "quiz",
        "prompt": "Which country has won the most FIFA World Cups?",
        "options": ["Germany", "Brazil", "Argentina", "Italy"],
        "answer": "Brazil",
        "explanation": "Brazil has won the men's FIFA World Cup five times.",
    },
    {
        "type": "word",
        "prompt": "Enter a football position or tactical word that starts with M.",
        "answer": ["midfielder", "man-marking", "marker"],
        "explanation": "Example answer: midfielder",
    },
    {
        "type": "quiz",
        "prompt": "Which club has won the most UEFA Champions League titles?",
        "options": ["Barcelona", "Liverpool", "AC Milan", "Real Madrid"],
        "answer": "Real Madrid",
        "explanation": "Real Madrid holds the record for most Champions League titles.",
    },
    {
        "type": "word",
        "prompt": "Enter a football skill or play word that starts with D.",
        "answer": ["dribble", "dummy", "dive", "deflection"],
        "explanation": "Example answer: dribble",
    },
    {
        "type": "quiz",
        "prompt": "What does a hat-trick usually mean in one match?",
        "options": ["3 assists", "3 goals", "3 saves", "3 yellow cards"],
        "answer": "3 goals",
        "explanation": "A hat-trick usually means one player scores three goals in a match.",
    },
    {
        "type": "word",
        "prompt": "Enter a football field or match-flow word that starts with P.",
        "answer": ["pitch", "penalty", "press", "possession"],
        "explanation": "Example answer: pitch",
    },
    {
        "type": "quiz",
        "prompt": "What is the key idea behind an offside call?",
        "options": ["Shirt color", "Ball speed", "Position ahead of defenders", "Crowd size"],
        "answer": "Position ahead of defenders",
        "explanation": "Offside depends on the attacker's position at the moment the pass is made.",
    },
    {
        "type": "word",
        "prompt": "Enter a football equipment word that starts with B.",
        "answer": ["ball", "boots", "bib"],
        "explanation": "Example answer: boots",
    },
]


def now_ts():
    return int(time.time())


def normalize_text(value):
    return " ".join(str(value).strip().lower().split())


def make_room_code():
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = "".join(random.choice(alphabet) for _ in range(5))
        if code not in ROOMS:
            return code


def build_deck():
    deck = deepcopy(ROUND_BANK)
    random.shuffle(deck)
    return deck[:6]


def new_player(nickname):
    return {
        "id": uuid.uuid4().hex[:8],
        "nickname": nickname[:18],
        "score": 0,
        "joinedAt": now_ts(),
    }


def touch_room(room):
    room["updatedAt"] = now_ts()


def cleanup_rooms():
    while True:
        time.sleep(CLEANUP_INTERVAL_SECONDS)
        cutoff = now_ts() - ROOM_TTL_SECONDS
        with STATE_LOCK:
            expired_codes = [
                code for code, room in ROOMS.items()
                if room["updatedAt"] < cutoff
            ]
            for code in expired_codes:
                ROOMS.pop(code, None)


def room_snapshot(room, viewer_id=None):
    players = sorted(room["players"], key=lambda item: (-item["score"], item["joinedAt"]))
    game = room["game"]
    current_round = None

    if 0 <= game["roundIndex"] < len(game["deck"]):
        src = game["deck"][game["roundIndex"]]
        current_round = {
            "index": game["roundIndex"] + 1,
            "total": len(game["deck"]),
            "type": src["type"],
            "prompt": src["prompt"],
            "options": src.get("options", []),
            "revealed": game["status"] == "revealed",
            "explanation": src["explanation"] if game["status"] == "revealed" else "",
            "submissions": {
                pid: {
                    "answered": True,
                    "display": entry["answer"] if game["status"] == "revealed" or pid == viewer_id else "Submitted",
                    "correct": entry["correct"] if game["status"] == "revealed" else None,
                }
                for pid, entry in game["submissions"].items()
            },
        }
        if game["status"] == "revealed":
            answer = src["answer"]
            current_round["answer"] = answer if isinstance(answer, str) else src["answer"][0]

    return {
        "roomCode": room["code"],
        "hostId": room["hostId"],
        "viewerId": viewer_id,
        "players": players,
        "phase": room["phase"],
        "game": {
            "status": game["status"],
            "roundIndex": game["roundIndex"],
            "currentRound": current_round,
            "message": game["message"],
        },
        "updatedAt": room["updatedAt"],
        "expiresInSeconds": max(0, ROOM_TTL_SECONDS - (now_ts() - room["updatedAt"])),
    }


def require_room(room_code):
    room = ROOMS.get(room_code.upper())
    if not room:
        raise ValueError("Room not found.")
    return room


def require_player(room, player_id):
    for player in room["players"]:
        if player["id"] == player_id:
            return player
    raise ValueError("Player not found.")


def create_room(nickname):
    nickname = nickname.strip()
    if not nickname:
        raise ValueError("Enter a nickname.")
    code = make_room_code()
    host = new_player(nickname)
    room = {
        "code": code,
        "hostId": host["id"],
        "players": [host],
        "phase": "lobby",
        "updatedAt": now_ts(),
        "game": {
            "deck": [],
            "roundIndex": -1,
            "status": "waiting",
            "submissions": {},
            "message": "The host can start the match when everyone has joined.",
        },
    }
    ROOMS[code] = room
    return room, host


def join_room(room_code, nickname):
    nickname = nickname.strip()
    if not nickname:
        raise ValueError("Enter a nickname.")
    room = require_room(room_code)
    if len(room["players"]) >= 4:
        raise ValueError("This room is already full.")
    player = new_player(nickname)
    room["players"].append(player)
    touch_room(room)
    return room, player


def start_game(room, player_id):
    if room["hostId"] != player_id:
        raise ValueError("Only the host can start the game.")
    if len(room["players"]) < 2:
        raise ValueError("At least 2 players are required.")
    room["phase"] = "playing"
    room["game"]["deck"] = build_deck()
    room["game"]["roundIndex"] = 0
    room["game"]["status"] = "question"
    room["game"]["submissions"] = {}
    room["game"]["message"] = "Round 1 started. Everyone can submit an answer."
    for player in room["players"]:
        player["score"] = 0
    touch_room(room)


def reveal_round(room, player_id):
    if room["hostId"] != player_id:
        raise ValueError("Only the host can reveal answers.")
    if room["game"]["status"] != "question":
        raise ValueError("This round cannot be revealed right now.")
    room["game"]["status"] = "revealed"
    room["game"]["message"] = "Answer revealed. The host can move to the next round."
    touch_room(room)


def advance_round(room, player_id):
    if room["hostId"] != player_id:
        raise ValueError("Only the host can move to the next round.")
    game = room["game"]
    if game["status"] == "question":
        raise ValueError("Reveal the answer first.")
    if game["roundIndex"] >= len(game["deck"]) - 1:
        room["phase"] = "finished"
        game["status"] = "finished"
        game["message"] = "Game finished. Check the scores and start a new match if you want."
        touch_room(room)
        return
    game["roundIndex"] += 1
    game["status"] = "question"
    game["submissions"] = {}
    game["message"] = f"Round {game['roundIndex'] + 1} started."
    touch_room(room)


def reset_game(room, player_id):
    if room["hostId"] != player_id:
        raise ValueError("Only the host can reset the game.")
    room["phase"] = "lobby"
    room["game"] = {
        "deck": [],
        "roundIndex": -1,
        "status": "waiting",
        "submissions": {},
        "message": "New match ready. Invite players and start again.",
    }
    for player in room["players"]:
        player["score"] = 0
    touch_room(room)


def score_submission(round_data, raw_answer):
    answer = normalize_text(raw_answer)
    if round_data["type"] == "quiz":
        correct = normalize_text(round_data["answer"]) == answer
        return correct, 2 if correct else 0
    accepted = {normalize_text(item) for item in round_data["answer"]}
    correct = answer in accepted
    return correct, 3 if correct else 0


def submit_answer(room, player_id, answer):
    game = room["game"]
    if room["phase"] != "playing" or game["status"] != "question":
        raise ValueError("You cannot submit right now.")
    if player_id in game["submissions"]:
        raise ValueError("You already answered this round.")
    if not str(answer).strip():
        raise ValueError("Enter an answer.")
    current_round = game["deck"][game["roundIndex"]]
    correct, points = score_submission(current_round, answer)
    player = require_player(room, player_id)
    player["score"] += points
    game["submissions"][player_id] = {
        "answer": str(answer).strip()[:40],
        "correct": correct,
        "points": points,
    }
    if len(game["submissions"]) == len(room["players"]):
        game["status"] = "revealed"
        game["message"] = "All players answered. The round result is now revealed."
    else:
        game["message"] = f"{len(game['submissions'])}/{len(room['players'])} players have answered."
    touch_room(room)


class GameHandler(BaseHTTPRequestHandler):
    server_version = "FootballParty/1.1"

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.serve_static("index.html", "text/html; charset=utf-8")
            return
        if parsed.path.startswith("/static/"):
            rel_path = parsed.path.removeprefix("/static/")
            path = STATIC_DIR / rel_path
            if path.suffix == ".css":
                ctype = "text/css; charset=utf-8"
            elif path.suffix == ".js":
                ctype = "application/javascript; charset=utf-8"
            else:
                ctype = "text/plain; charset=utf-8"
            self.serve_static(path.name, ctype)
            return
        if parsed.path == "/api/state":
            query = parse_qs(parsed.query)
            room_code = query.get("roomCode", [""])[0]
            player_id = query.get("playerId", [""])[0]
            with STATE_LOCK:
                room = require_room(room_code)
                require_player(room, player_id)
                snapshot = room_snapshot(room, player_id)
            self.send_json(snapshot)
            return
        if parsed.path == "/api/config":
            self.send_json(
                {
                    "baseUrl": self.base_url(),
                    "roomTtlSeconds": ROOM_TTL_SECONDS,
                }
            )
            return
        if parsed.path == "/api/health":
            self.send_json({"ok": True, "rooms": len(ROOMS)})
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        payload = self.read_json()
        try:
            with STATE_LOCK:
                if parsed.path == "/api/create-room":
                    room, player = create_room(payload.get("nickname", ""))
                    data = {"playerId": player["id"], "room": room_snapshot(room, player["id"])}
                elif parsed.path == "/api/join-room":
                    room, player = join_room(payload.get("roomCode", ""), payload.get("nickname", ""))
                    data = {"playerId": player["id"], "room": room_snapshot(room, player["id"])}
                elif parsed.path == "/api/action":
                    room = require_room(payload.get("roomCode", ""))
                    player_id = payload.get("playerId", "")
                    require_player(room, player_id)
                    action = payload.get("action")
                    if action == "start":
                        start_game(room, player_id)
                    elif action == "reveal":
                        reveal_round(room, player_id)
                    elif action == "next":
                        advance_round(room, player_id)
                    elif action == "reset":
                        reset_game(room, player_id)
                    elif action == "submit":
                        submit_answer(room, player_id, payload.get("answer", ""))
                    else:
                        raise ValueError("Unknown action.")
                    data = {"room": room_snapshot(room, player_id)}
                else:
                    self.send_error(HTTPStatus.NOT_FOUND, "Not found")
                    return
        except ValueError as exc:
            self.send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        self.send_json(data)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def serve_static(self, filename, content_type):
        target = STATIC_DIR / filename
        if not target.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        payload = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def send_json(self, payload, status=HTTPStatus.OK):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def base_url(self):
        if PUBLIC_BASE_URL:
            return PUBLIC_BASE_URL
        if RENDER_EXTERNAL_URL:
            return RENDER_EXTERNAL_URL
        host = self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or f"127.0.0.1:{PORT}"
        proto = self.headers.get("X-Forwarded-Proto") or "http"
        return f"{proto}://{host}".rstrip("/")

    def log_message(self, fmt, *args):
        return


def main():
    cleanup_thread = threading.Thread(target=cleanup_rooms, daemon=True)
    cleanup_thread.start()
    server = ThreadingHTTPServer((HOST, PORT), GameHandler)
    public_hint = PUBLIC_BASE_URL or RENDER_EXTERNAL_URL or f"http://127.0.0.1:{PORT}"
    print(f"Football Party server running on {public_hint}")
    print("Set PUBLIC_BASE_URL only if you want to override the detected public URL.")
    print(f"Rooms expire after {ROOM_TTL_SECONDS // 60} minutes of inactivity.")
    server.serve_forever()


if __name__ == "__main__":
    main()
