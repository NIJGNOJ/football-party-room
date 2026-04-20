# Football Party Room

No-account football party game for 2 to 4 players.

## Run locally

```powershell
cd C:\Users\ajj07\Documents\Codex\2026-04-20-4-pc-football-party
python server.py
```

Open `http://127.0.0.1:8123`.

## Render deployment

This project is now set up for Render.

1. Push this folder to GitHub.
2. In Render, create a new Blueprint and point it at the repo.
3. Render will read [render.yaml](C:\Users\ajj07\Documents\Codex\2026-04-20-4-pc-football-party\render.yaml) and create the web service.
4. After deploy, open the public `onrender.com` URL, create a room, and copy the invite link.
5. Friends on different internet networks can join from that link.

Files to upload:

- [server.py](C:\Users\ajj07\Documents\Codex\2026-04-20-4-pc-football-party\server.py)
- [render.yaml](C:\Users\ajj07\Documents\Codex\2026-04-20-4-pc-football-party\render.yaml)
- [Dockerfile](C:\Users\ajj07\Documents\Codex\2026-04-20-4-pc-football-party\Dockerfile)
- [Procfile](C:\Users\ajj07\Documents\Codex\2026-04-20-4-pc-football-party\Procfile)
- [.gitignore](C:\Users\ajj07\Documents\Codex\2026-04-20-4-pc-football-party\.gitignore)
- [static](C:\Users\ajj07\Documents\Codex\2026-04-20-4-pc-football-party\static)

You usually do not need to set `PUBLIC_BASE_URL` on Render because the app now auto-detects Render's public URL from `RENDER_EXTERNAL_URL`.

If you want to override it with a custom domain:

```powershell
$env:PUBLIC_BASE_URL='https://your-football-party.example.com'
python server.py
```

## Internet-ready changes

- Reads `PORT` so it works on public hosting platforms.
- Reads `PUBLIC_BASE_URL` for custom invite-link overrides.
- Auto-detects Render public URLs from `RENDER_EXTERNAL_URL`.
- Uses forwarded host and protocol headers behind reverse proxies.
- Generates direct invite links like `https://your-domain.example/?room=ABCDE`.
- Expires inactive rooms after 6 hours by default.

## Deployment files

- `Dockerfile`
- `Procfile`
- `render.yaml`
- `.env.example`

## Notes

- Room state is stored in memory, so a server restart clears all rooms.
- For longer-term hosting, add a real database later.
