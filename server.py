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
        "prompt": "FIFA 월드컵 최다 우승 국가는 어디일까요?",
        "options": ["독일", "브라질", "아르헨티나", "이탈리아"],
        "answer": "브라질",
        "points": 2,
        "explanation": "브라질은 남자 FIFA 월드컵에서 총 5회 우승했습니다.",
    },
    {
        "type": "word",
        "prompt": "다음 중 M으로 시작하는 축구 포지션 또는 전술 용어는 무엇일까요?",
        "options": ["미드필더", "스위퍼", "윙어", "타깃맨"],
        "answer": "미드필더",
        "points": 3,
        "explanation": "정답은 미드필더입니다.",
    },
    {
        "type": "quiz",
        "prompt": "UEFA 챔피언스리그 최다 우승 클럽은 어디일까요?",
        "options": ["바르셀로나", "리버풀", "AC 밀란", "레알 마드리드"],
        "answer": "레알 마드리드",
        "points": 2,
        "explanation": "레알 마드리드는 챔피언스리그 최다 우승 클럽입니다.",
    },
    {
        "type": "word",
        "prompt": "다음 중 D로 시작하는 축구 기술 또는 플레이 용어는 무엇일까요?",
        "options": ["드리블", "태클", "발리", "헤더"],
        "answer": "드리블",
        "points": 3,
        "explanation": "정답은 드리블입니다.",
    },
    {
        "type": "quiz",
        "prompt": "한 경기에서 해트트릭은 보통 무엇을 뜻할까요?",
        "options": ["도움 3개", "3골", "선방 3개", "옐로카드 3장"],
        "answer": "3골",
        "points": 2,
        "explanation": "해트트릭은 일반적으로 한 선수가 3골을 넣는 것을 뜻합니다.",
    },
    {
        "type": "word",
        "prompt": "다음 중 P로 시작하는 축구 경기장 또는 경기 흐름 관련 용어는 무엇일까요?",
        "options": ["피치", "코너", "벤치", "터널"],
        "answer": "피치",
        "points": 3,
        "explanation": "정답은 피치입니다.",
    },
    {
        "type": "quiz",
        "prompt": "오프사이드 판정의 핵심 기준으로 가장 가까운 것은 무엇일까요?",
        "options": ["유니폼 색상", "공의 속도", "수비수보다 앞선 위치", "관중 수"],
        "answer": "수비수보다 앞선 위치",
        "points": 2,
        "explanation": "오프사이드는 패스 순간 공격수의 위치를 기준으로 판단합니다.",
    },
    {
        "type": "word",
        "prompt": "다음 중 B로 시작하는 축구 장비 용어는 무엇일까요?",
        "options": ["축구화", "호루라기", "골망", "주장 완장"],
        "answer": "축구화",
        "points": 3,
        "explanation": "정답은 축구화입니다.",
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
                    "display": entry["answer"] if game["status"] == "revealed" or pid == viewer_id else "제출 완료",
                    "correct": entry["correct"] if game["status"] == "revealed" else None,
                }
                for pid, entry in game["submissions"].items()
            },
        }
        if game["status"] == "revealed":
            current_round["answer"] = src["answer"]

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
        raise ValueError("방을 찾을 수 없습니다.")
    return room


def require_player(room, player_id):
    for player in room["players"]:
        if player["id"] == player_id:
            return player
    raise ValueError("플레이어를 찾을 수 없습니다.")


def create_room(nickname):
    nickname = nickname.strip()
    if not nickname:
        raise ValueError("닉네임을 입력해주세요.")
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
            "message": "모든 플레이어가 들어오면 방장이 게임을 시작할 수 있습니다.",
        },
    }
    ROOMS[code] = room
    return room, host


def join_room(room_code, nickname):
    nickname = nickname.strip()
    if not nickname:
        raise ValueError("닉네임을 입력해주세요.")
    room = require_room(room_code)
    if len(room["players"]) >= 4:
        raise ValueError("이 방은 이미 가득 찼습니다.")
    player = new_player(nickname)
    room["players"].append(player)
    touch_room(room)
    return room, player


def start_game(room, player_id):
    if room["hostId"] != player_id:
        raise ValueError("방장만 게임을 시작할 수 있습니다.")
    if len(room["players"]) < 2:
        raise ValueError("최소 2명이 필요합니다.")
    room["phase"] = "playing"
    room["game"]["deck"] = build_deck()
    room["game"]["roundIndex"] = 0
    room["game"]["status"] = "question"
    room["game"]["submissions"] = {}
    room["game"]["message"] = "1라운드 시작. 정답을 선택해주세요."
    for player in room["players"]:
        player["score"] = 0
    touch_room(room)


def reveal_round(room, player_id):
    if room["hostId"] != player_id:
        raise ValueError("방장만 정답을 공개할 수 있습니다.")
    if room["game"]["status"] != "question":
        raise ValueError("지금은 정답을 공개할 수 없습니다.")
    room["game"]["status"] = "revealed"
    room["game"]["message"] = "정답이 공개되었습니다. 다음 라운드로 넘어갈 수 있습니다."
    touch_room(room)


def advance_round(room, player_id):
    if room["hostId"] != player_id:
        raise ValueError("방장만 다음 라운드로 이동할 수 있습니다.")
    game = room["game"]
    if game["status"] == "question":
        raise ValueError("먼저 정답을 공개해주세요.")
    if game["roundIndex"] >= len(game["deck"]) - 1:
        room["phase"] = "finished"
        game["status"] = "finished"
        game["message"] = "게임이 끝났습니다. 점수를 확인하고 새 게임을 시작해보세요."
        touch_room(room)
        return
    game["roundIndex"] += 1
    game["status"] = "question"
    game["submissions"] = {}
    game["message"] = f"{game['roundIndex'] + 1}라운드 시작."
    touch_room(room)


def reset_game(room, player_id):
    if room["hostId"] != player_id:
        raise ValueError("방장만 게임을 초기화할 수 있습니다.")
    room["phase"] = "lobby"
    room["game"] = {
        "deck": [],
        "roundIndex": -1,
        "status": "waiting",
        "submissions": {},
        "message": "새 게임 준비 완료. 플레이어를 모은 뒤 다시 시작하세요.",
    }
    for player in room["players"]:
        player["score"] = 0
    touch_room(room)


def score_submission(round_data, raw_answer):
    answer = normalize_text(raw_answer)
    correct = normalize_text(round_data["answer"]) == answer
    return correct, round_data.get("points", 2) if correct else 0


def submit_answer(room, player_id, answer):
    game = room["game"]
    if room["phase"] != "playing" or game["status"] != "question":
        raise ValueError("지금은 제출할 수 없습니다.")
    if player_id in game["submissions"]:
        raise ValueError("이번 라운드에는 이미 답했습니다.")
    if not str(answer).strip():
        raise ValueError("답을 선택해주세요.")
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
        game["message"] = "모든 플레이어가 답했습니다. 라운드 결과가 공개되었습니다."
    else:
        game["message"] = f"{len(game['submissions'])}/{len(room['players'])}명이 답했습니다."
    touch_room(room)


class GameHandler(BaseHTTPRequestHandler):
    server_version = "FootballParty/1.2"

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
                        raise ValueError("알 수 없는 요청입니다.")
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
    print("공개 주소를 직접 지정하려면 PUBLIC_BASE_URL을 설정하세요.")
    print(f"방은 마지막 활동 후 {ROOM_TTL_SECONDS // 60}분이 지나면 만료됩니다.")
    server.serve_forever()


if __name__ == "__main__":
    main()
