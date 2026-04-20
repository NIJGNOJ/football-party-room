const TXT = {
  requestFailed: "\uc694\uccad \ucc98\ub9ac \uc911 \uc624\ub958\uac00 \ubc1c\uc0dd\ud588\uc2b5\ub2c8\ub2e4.",
  roomAlivePrefix: "\ub9c8\uc9c0\ub9c9 \ud65c\ub3d9 \ud6c4 \uc57d ",
  roomAliveSuffix: "\ubd84 \ub3d9\uc548 \ubc29\uc774 \uc720\uc9c0\ub429\ub2c8\ub2e4.",
  lobby: "\ub85c\ube44",
  playing: "\uc9c4\ud589 \uc911",
  finished: "\uc885\ub8cc",
  quiz: "\ud034\uc988",
  word: "\ucd95\uad6c \ub2e8\uc5b4 \ud034\uc988",
  notStarted: "\uac8c\uc784\uc774 \uc544\uc9c1 \uc2dc\uc791\ub418\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4.",
  submitted: "\uc81c\ucd9c \uc644\ub8cc",
  answer: "\uc815\ub2f5:",
  liveSync: "\uc2e4\uc2dc\uac04 \ub3d9\uae30\ud654 \uc911",
  syncFailed: "\ub3d9\uae30\ud654\uc5d0 \uc2e4\ud328\ud588\uc2b5\ub2c8\ub2e4.",
  pendingInvite: "\uc0dd\uc131 \ub300\uae30 \uc911",
  copiedInvite: "\ucd08\ub300 \ub9c1\ud06c\ub97c \ubcf5\uc0ac\ud588\uc2b5\ub2c8\ub2e4.",
  pointsSuffix: "\uc810",
};

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
    throw new Error(data.error || TXT.requestFailed);
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
    $("ttlLabel").textContent = `${TXT.roomAlivePrefix}${minutes}${TXT.roomAliveSuffix}`;
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

function setEntryNotice(text = "") {
  const el = $("entryNotice");
  if (!el) return;
  el.textContent = text;
  el.classList.toggle("hidden", !text);
}

function phaseText(room) {
  if (room.phase === "lobby") return TXT.lobby;
  if (room.phase === "playing") return TXT.playing;
  if (room.phase === "finished") return TXT.finished;
  return room.phase;
}

function roundTypeText(type) {
  if (type === "quiz") return TXT.quiz;
  if (type === "word") return TXT.word;
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
  setEntryNotice("");
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
          <strong>${player.score}${TXT.pointsSuffix}</strong>
        </div>
      `;
    })
    .join("");

  const round = room.game.currentRound;
  if (!round) {
    $("roundBox").className = "round empty";
    $("roundBox").innerHTML = TXT.notStarted;
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
              <span>${escapeHtml(info.display || TXT.submitted)}</span>
            </div>`;
          })
          .join("")}
      </div>`
    : "";

  const answerHtml = revealed
    ? `<div class="reveal">
        <strong>${TXT.answer}</strong> ${escapeHtml(round.answer || "")}
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
    if (!res.ok) throw new Error(data.error || TXT.syncFailed);
    state.room = data;
    const snapshot = meaningfulRoomSnapshot(data);
    if (snapshot !== state.lastRenderedSnapshot) {
      state.lastRenderedSnapshot = snapshot;
      renderRoom();
    } else {
      updateInviteLink();
    }
    setSyncLabel(TXT.liveSync);
  } catch (error) {
    setSyncLabel(error.message, true);
  }
}

async function createRoom() {
  const nickname = $("nickname").value.trim();
  setEntryNotice("");
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
  setEntryNotice("");
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
  if (!text || text === TXT.pendingInvite) return;
  await navigator.clipboard.writeText(text);
  setSyncLabel(TXT.copiedInvite);
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
  if (!$("entryCard").classList.contains("hidden")) {
    setEntryNotice(error.message);
  }
  setSyncLabel(error.message, true);
}

async function boot() {
  bindEvents();
  await loadConfig();
  loadSession();
}

boot();
