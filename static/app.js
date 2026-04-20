const state = {
  roomCode: "",
  playerId: "",
  room: null,
  pollHandle: null,
  lastRenderedSnapshot: "",
  config: {
    baseUrl: window.location.origin,
    roomTtlSeconds: 0,
  },
};

const $ = (id) => document.getElementById(id);

async function api(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "요청 처리 중 오류가 발생했습니다.");
  }
  return data;
}

async function loadConfig() {
  const response = await fetch("/api/config");
  const data = await response.json();
  if (response.ok) {
    state.config = data;
  }
}

function saveSession() {
  localStorage.setItem(
    "football-party-session",
    JSON.stringify({
      roomCode: state.roomCode,
      playerId: state.playerId,
    }),
  );
}

function meaningfulRoomSnapshot(room) {
  return JSON.stringify({
    roomCode: room.roomCode,
    hostId: room.hostId,
    viewerId: room.viewerId,
    phase: room.phase,
    updatedAt: room.updatedAt,
    players: room.players,
    game: room.game,
  });
}

function updateInviteLink() {
  if (!state.roomCode) return;
  const inviteUrl = `${state.config.baseUrl}/?room=${encodeURIComponent(state.roomCode)}`;
  $("inviteLink").textContent = inviteUrl;
  const seconds = state.room?.expiresInSeconds ?? state.config.roomTtlSeconds;
  if (seconds > 0) {
    const minutes = Math.max(1, Math.ceil(seconds / 60));
    $("ttlLabel").textContent = `마지막 활동 후 약 ${minutes}분 동안 방이 유지됩니다.`;
  }
}

function loadSession() {
  try {
    const raw = localStorage.getItem("football-party-session");
    const presetRoom = new URLSearchParams(window.location.search).get("room");
    if (presetRoom) {
      $("roomCode").value = presetRoom.toUpperCase();
    }
    if (!raw) return;
    const parsed = JSON.parse(raw);
    if (parsed.roomCode && parsed.playerId) {
      state.roomCode = parsed.roomCode;
      state.playerId = parsed.playerId;
      $("roomCode").value = parsed.roomCode;
      syncState();
    }
  } catch {
    localStorage.removeItem("football-party-session");
  }
}

function setSyncLabel(text, bad = false) {
  const el = $("syncLabel");
  el.textContent = text;
  el.classList.toggle("bad", bad);
}

function phaseText(room) {
  if (room.phase === "lobby") return "로비";
  if (room.phase === "playing") return "진행 중";
  if (room.phase === "finished") return "종료";
  return room.phase;
}

function roundTypeText(type) {
  if (type === "quiz") return "퀴즈";
  if (type === "word") return "축구 단어 퀴즈";
  return type;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function renderRoom() {
  const room = state.room;
  if (!room) return;

  $("entryCard").classList.add("hidden");
  $("gameCard").classList.remove("hidden");
  $("roomLabel").textContent = room.roomCode;
  $("phaseLabel").textContent = phaseText(room);
  $("messageLabel").textContent = room.game.message || "";
  updateInviteLink();

  const isHost = room.viewerId === room.hostId;
  $("hostControls").classList.toggle("hidden", !isHost);

  $("playersList").innerHTML = room.players
    .map((player, index) => {
      const me = player.id === room.viewerId ? " me" : "";
      const host = player.id === room.hostId ? " host" : "";
      return `
        <div class="player${me}${host}">
          <span>${index + 1}. ${escapeHtml(player.nickname)}</span>
          <strong>${player.score}점</strong>
        </div>
      `;
    })
    .join("");

  const round = room.game.currentRound;
  if (!round) {
    $("roundBox").className = "round empty";
    $("roundBox").innerHTML = "게임이 아직 시작되지 않았습니다.";
    $("answerBox").classList.add("hidden");
    return;
  }

  const submissions = Object.entries(round.submissions || {});
  const revealed = round.revealed;
  const alreadySubmitted = Boolean(round.submissions?.[room.viewerId]);
  const canAnswer = room.phase === "playing" && !revealed && !alreadySubmitted;
  const optionsHtml = `<div class="options">${round.options
    .map((item) => {
      const disabled = canAnswer ? "" : "disabled";
      const classes = `option${canAnswer ? "" : " locked"}`;
      return `<button class="${classes}" data-choice="${escapeHtml(item)}" ${disabled}>${escapeHtml(item)}</button>`;
    })
    .join("")}</div>`;

  const submissionHtml = submissions.length
    ? `<div class="submissions">
        ${submissions
          .map(([playerId, info]) => {
            const player = room.players.find((entry) => entry.id === playerId);
            if (!player) return "";
            const badge =
              revealed && info.correct === true
                ? "correct"
                : revealed && info.correct === false
                  ? "wrong"
                  : "pending";
            return `<div class="submission ${badge}">
              <span>${escapeHtml(player.nickname)}</span>
              <span>${escapeHtml(info.display || "제출 완료")}</span>
            </div>`;
          })
          .join("")}
      </div>`
    : "";

  const answerHtml = revealed
    ? `<div class="reveal">
        <strong>정답:</strong> ${escapeHtml(round.answer || "")}
        <p>${escapeHtml(round.explanation || "")}</p>
      </div>`
    : "";

  $("roundBox").className = "round";
  $("roundBox").innerHTML = `
    <p class="small">ROUND ${round.index}/${round.total} · ${roundTypeText(round.type)}</p>
    <h4>${escapeHtml(round.prompt)}</h4>
    ${optionsHtml}
    ${submissionHtml}
    ${answerHtml}
  `;

  $("answerBox").classList.add("hidden");
  $("answerInput").value = "";

  document.querySelectorAll("[data-choice]").forEach((button) => {
    button.addEventListener("click", () => {
      const choice = button.dataset.choice || "";
      if (!choice || !canAnswer) return;
      sendAction("submit", { answer: choice }).catch(showError);
    });
  });
}

async function syncState() {
  if (!state.roomCode || !state.playerId) return;
  try {
    const res = await fetch(
      `/api/state?roomCode=${encodeURIComponent(state.roomCode)}&playerId=${encodeURIComponent(state.playerId)}`,
    );
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "동기화에 실패했습니다.");
    state.room = data;
    const snapshot = meaningfulRoomSnapshot(data);
    if (snapshot !== state.lastRenderedSnapshot) {
      state.lastRenderedSnapshot = snapshot;
      renderRoom();
    } else {
      updateInviteLink();
    }
    setSyncLabel("실시간 동기화 중");
  } catch (error) {
    setSyncLabel(error.message, true);
  }
}

async function createRoom() {
  const nickname = $("nickname").value.trim();
  const data = await api("/api/create-room", { nickname });
  state.roomCode = data.room.roomCode;
  state.playerId = data.playerId;
  state.room = data.room;
  state.lastRenderedSnapshot = meaningfulRoomSnapshot(data.room);
  window.history.replaceState({}, "", `/?room=${encodeURIComponent(state.roomCode)}`);
  saveSession();
  renderRoom();
  startPolling();
}

async function joinRoom() {
  const nickname = $("nickname").value.trim();
  const roomCode = $("roomCode").value.trim().toUpperCase();
  const data = await api("/api/join-room", { nickname, roomCode });
  state.roomCode = roomCode;
  state.playerId = data.playerId;
  state.room = data.room;
  state.lastRenderedSnapshot = meaningfulRoomSnapshot(data.room);
  window.history.replaceState({}, "", `/?room=${encodeURIComponent(state.roomCode)}`);
  saveSession();
  renderRoom();
  startPolling();
}

async function sendAction(action, extra = {}) {
  const data = await api("/api/action", {
    roomCode: state.roomCode,
    playerId: state.playerId,
    action,
    ...extra,
  });
  state.room = data.room;
  state.lastRenderedSnapshot = meaningfulRoomSnapshot(data.room);
  renderRoom();
}

function startPolling() {
  if (state.pollHandle) clearInterval(state.pollHandle);
  state.pollHandle = setInterval(syncState, 1200);
  syncState();
}

async function copyInviteLink() {
  const text = $("inviteLink").textContent;
  if (!text || text === "생성 대기 중") return;
  await navigator.clipboard.writeText(text);
  setSyncLabel("초대 링크를 복사했습니다.");
}

function bindEvents() {
  $("createBtn").addEventListener("click", () => createRoom().catch(showError));
  $("joinBtn").addEventListener("click", () => joinRoom().catch(showError));
  $("startBtn").addEventListener("click", () => sendAction("start").catch(showError));
  $("revealBtn").addEventListener("click", () => sendAction("reveal").catch(showError));
  $("nextBtn").addEventListener("click", () => sendAction("next").catch(showError));
  $("resetBtn").addEventListener("click", () => sendAction("reset").catch(showError));
  $("copyInviteBtn").addEventListener("click", () => copyInviteLink().catch(showError));
}

function showError(error) {
  setSyncLabel(error.message, true);
}

async function boot() {
  bindEvents();
  await loadConfig();
  loadSession();
}

boot();
