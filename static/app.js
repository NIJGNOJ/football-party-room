const state = {
  roomCode: "",
  playerId: "",
  room: null,
  pollHandle: null,
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
    throw new Error(data.error || "Request failed.");
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

function updateInviteLink() {
  if (!state.roomCode) return;
  const inviteUrl = `${state.config.baseUrl}/?room=${encodeURIComponent(state.roomCode)}`;
  $("inviteLink").textContent = inviteUrl;
  const seconds = state.room?.expiresInSeconds ?? state.config.roomTtlSeconds;
  if (seconds > 0) {
    const minutes = Math.max(1, Math.ceil(seconds / 60));
    $("ttlLabel").textContent = `Room stays alive for about ${minutes} minutes after the last activity.`;
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
  if (room.phase === "lobby") return "Lobby";
  if (room.phase === "playing") return "Live";
  if (room.phase === "finished") return "Finished";
  return room.phase;
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
          <strong>${player.score} pts</strong>
        </div>
      `;
    })
    .join("");

  const round = room.game.currentRound;
  if (!round) {
    $("roundBox").className = "round empty";
    $("roundBox").innerHTML = "The game has not started yet.";
    $("answerBox").classList.add("hidden");
    return;
  }

  const submissions = Object.entries(round.submissions || {});
  const revealed = round.revealed;
  const optionsHtml =
    round.type === "quiz"
      ? `<div class="options">${round.options
          .map((item) => `<button class="option" data-choice="${escapeHtml(item)}">${escapeHtml(item)}</button>`)
          .join("")}</div>`
      : `<p class="hint">Enter one exact football word in English.</p>`;

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
              <span>${escapeHtml(info.display || "Submitted")}</span>
            </div>`;
          })
          .join("")}
      </div>`
    : "";

  const answerHtml = revealed
    ? `<div class="reveal">
        <strong>Answer:</strong> ${escapeHtml(round.answer || "")}
        <p>${escapeHtml(round.explanation || "")}</p>
      </div>`
    : "";

  $("roundBox").className = "round";
  $("roundBox").innerHTML = `
    <p class="small">ROUND ${round.index}/${round.total} · ${round.type === "quiz" ? "Quiz" : "Word round"}</p>
    <h4>${escapeHtml(round.prompt)}</h4>
    ${optionsHtml}
    ${submissionHtml}
    ${answerHtml}
  `;

  const alreadySubmitted = Boolean(round.submissions?.[room.viewerId]);
  const canAnswer = room.phase === "playing" && !revealed && !alreadySubmitted;
  $("answerBox").classList.toggle("hidden", !canAnswer);
  if (!canAnswer) {
    $("answerInput").value = "";
  }

  document.querySelectorAll("[data-choice]").forEach((button) => {
    button.addEventListener("click", () => {
      $("answerInput").value = button.dataset.choice || "";
      $("submitBtn").click();
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
    if (!res.ok) throw new Error(data.error || "Sync failed.");
    state.room = data;
    renderRoom();
    setSyncLabel("Live sync active");
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
  renderRoom();
}

function startPolling() {
  if (state.pollHandle) clearInterval(state.pollHandle);
  state.pollHandle = setInterval(syncState, 1200);
  syncState();
}

async function copyInviteLink() {
  const text = $("inviteLink").textContent;
  if (!text || text === "Pending") return;
  await navigator.clipboard.writeText(text);
  setSyncLabel("Invite link copied");
}

function bindEvents() {
  $("createBtn").addEventListener("click", () => createRoom().catch(showError));
  $("joinBtn").addEventListener("click", () => joinRoom().catch(showError));
  $("startBtn").addEventListener("click", () => sendAction("start").catch(showError));
  $("revealBtn").addEventListener("click", () => sendAction("reveal").catch(showError));
  $("nextBtn").addEventListener("click", () => sendAction("next").catch(showError));
  $("resetBtn").addEventListener("click", () => sendAction("reset").catch(showError));
  $("copyInviteBtn").addEventListener("click", () => copyInviteLink().catch(showError));
  $("submitBtn").addEventListener("click", () => {
    const answer = $("answerInput").value.trim();
    sendAction("submit", { answer })
      .then(() => {
        $("answerInput").value = "";
      })
      .catch(showError);
  });
  $("answerInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      $("submitBtn").click();
    }
  });
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
