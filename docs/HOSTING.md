# Hosting Zoairk for other people

## Server and client, in one paragraph

**The server** is `server.py` running on one machine (yours, a lab machine, or a cloud VM). It owns the game:
the worlds, the lobbies, the NPCs, and the calls to the language model through Ollama. **The client** is the
web page the server hands out. Players open a link in any browser, on a laptop or a phone, and play. They
install nothing, need no account, and never touch the model; every turn goes over a WebSocket to the server.

```
 players' browsers (clients)                       one machine (server)
 ┌───────────────┐                               ┌──────────────────────────────┐
 │ phone browser │──┐                            │ server.py                    │
 ├───────────────┤  │  https://zoairk.your.domain│  ├ web page (the client)     │
 │ laptop browser│──┼───────────────────────────▶│  ├ game WebSocket             │
 ├───────────────┤  │   (one port: 8765)         │  ├ lobbies, worlds, NPCs     │
 │ ...           │──┘                            │  └ logs/ → play-logs branch  │
 └───────────────┘                               │ Ollama → DeepSeek V4.1 Flash │
                                                 └──────────────────────────────┘
```

## 1. Set up the server (one time)

You need Python 3.10+, git, and Ollama (https://ollama.com/download). Every turn is a model call on the
**host's** Ollama account.

```sh
git clone https://github.com/dwhite-sys/Zoairk.git
cd Zoairk
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

ollama signin                            # the host's Ollama account
ollama pull deepseek-v4.1-flash:cloud
```

Check it works locally first: `python3 server.py`, then open http://127.0.0.1:8765/.

## 2. Let people reach it

Pick one.

**A. Same Wi-Fi or LAN only** (a classroom, a booth):

```sh
ZOAIRK_HOST=0.0.0.0 python3 server.py
```

It prints the address to share, e.g. `http://192.168.1.20:8765/`. Players on the same network open it.

**B. A domain of your choosing, with HTTPS** (recommended for the public). One command sets it up for any
domain or subdomain you control:

```sh
python3 tools/setup_domain.py --domain play.your-domain.com
```

It writes `zoairk.env` (the server reads it on start: public URL, port, listen address), plus a ready-made
`deploy/<domain>/Caddyfile` (HTTPS reverse proxy; Caddy gets the certificate itself) and
`deploy/<domain>/zoairk.service` (keeps the server running). Then it prints the remaining steps:

1. At your registrar, add an **A record** for the domain pointing to the server's public IP.
2. Allow inbound ports 80 and 443.
3. `sudo apt install caddy`, copy the Caddyfile to `/etc/caddy/Caddyfile`, `sudo systemctl reload caddy`.
4. Copy the service file to `/etc/systemd/system/`, then `sudo systemctl enable --now zoairk`.

**Under a path of a site you already run** (this is how the AI Society hosts it, at
`https://www.byui-ai-society.site/zoairk/`):

```sh
python3 tools/setup_domain.py --domain www.byui-ai-society.site/zoairk
```

The Caddyfile it writes uses `handle_path /zoairk/*` (the proxy strips the path before passing requests to the
game) and redirects `/zoairk` to `/zoairk/`. If the site already has a proxy config, paste just those lines into
it. With nginx, use `location /zoairk/ { proxy_pass http://127.0.0.1:8765/; proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade"; }`. The game works whether or not
the proxy strips the path: the page connects through its own folder, and the server also understands
`/zoairk/...` requests directly.

Re-run with `--check` to see whether the domain's DNS points at the server yet. Players open
`https://play.your-domain.com/`, and **📱 Invite** QR codes point there automatically. Each team can host on its
own domain this way; nothing in the code names a domain. Delete `zoairk.env` to go back to local-only.

**C. A tunnel, with no domain or open ports needed:**

```sh
cloudflared tunnel --url http://127.0.0.1:8765      # prints a public https://….trycloudflare.com link
# or
tailscale funnel 8765                               # public link through your tailnet
```

## 3. Keep it running

Run it as a service so it survives logouts and restarts (Linux, systemd):

```ini
# /etc/systemd/system/zoairk.service
[Unit]
Description=Zoairk game server
After=network-online.target

[Service]
User=YOUR_USER
WorkingDirectory=/home/YOUR_USER/Zoairk
ExecStart=/home/YOUR_USER/Zoairk/.venv/bin/python server.py
Environment=ZOAIRK_HOST=127.0.0.1
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```sh
sudo systemctl enable --now zoairk
journalctl -u zoairk -f          # watch it
sudo systemctl stop zoairk       # take it down
```

Use `ZOAIRK_HOST=127.0.0.1` behind a reverse proxy or tunnel (B or C), and `0.0.0.0` for LAN play (A).

## 4. Play logs (free play-testing)

Every turn is logged to `logs/<date>.jsonl` on the server. Every 10 minutes the server pushes an **anonymized**
copy to this repo's `play-logs` branch. Player names are replaced everywhere with IDs like `player-3fa2c1`, and the
secret used to make them (`logs/.salt`) never leaves the server. The branch holds only logs, never code.

For the push to work, the server needs permission to push to this repo. The simplest option is a **deploy key**:

```sh
ssh-keygen -t ed25519 -f ~/.ssh/zoairk_deploy -N ""
# GitHub → repo Settings → Deploy keys → Add key → paste ~/.ssh/zoairk_deploy.pub → tick "Allow write access"
git remote set-url origin git@github.com:dwhite-sys/Zoairk.git
git config core.sshCommand "ssh -i ~/.ssh/zoairk_deploy -o IdentitiesOnly=yes"
python3 tools/sync_logs.py       # test: should print "pushed ..."
```

Read them anywhere:

```sh
git fetch origin play-logs
git worktree add ../zoairk-play-logs play-logs
python3 tools/log_report.py ../zoairk-play-logs/logs/*.jsonl
```

The report lists success rate, errors, timing, NPC decisions, and every input that got "Nothing happens": those
are the next fixes. Set `ZOAIRK_LOG_SYNC_MINUTES=0` to turn the push off.

## 5. Settings

| Variable | Default | Meaning |
|---|---|---|
| `ZOAIRK_HOST` | `127.0.0.1` | interface to listen on (`0.0.0.0` = whole network) |
| `ZOAIRK_PUBLIC_URL` | (auto) | the address players use, e.g. `https://zoairk.your.domain` or `https://site/zoairk`; used for invite links and QR codes |
| `ZOAIRK_BASE_PATH` | (from the public URL) | path the game sits under behind a proxy, e.g. `/zoairk` |
| `ZOAIRK_WS_PORT` | `8765` | the one port for page + game |
| `ZOAIRK_MIN_TURN_GAP` | `2` | seconds between one player's turns |
| `ZOAIRK_MAX_PENDING` | `12` | queued turns per lobby |
| `ZOAIRK_MAX_PLAYERS` | `8` | players per lobby |
| `ZOAIRK_MAX_LOBBIES` | `20` | lobbies per server |
| `ZOAIRK_LOG_SYNC_MINUTES` | `10` | how often to push anonymized logs (`0` = off) |
| `ZOAIRK_LOG_BRANCH` | `play-logs` | branch the logs go to |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | which Ollama to use |
| `ZOAIRK_MODEL` | `deepseek-v4.1-flash:cloud` | which model to use |

## 6. Tell players: QR codes

In the game, **📱 Invite** shows a QR code and link for the lobby you are in. Anyone who scans it with a phone
camera lands in the same lobby and picks their own name. Put it on a screen at a booth, or share the link.

The QR code has to point at an address other people can reach. The server picks it like this:

1. `ZOAIRK_PUBLIC_URL`, if set. Set this when you use a domain or tunnel (option B or C).
2. Otherwise, the address the host's browser is using, if it is not `localhost`.
3. Otherwise, with `ZOAIRK_HOST=0.0.0.0`, this machine's network address (for same-Wi-Fi play).

If none of those can work, the invite says the link only works on this computer and how to fix it.


> Open **https://zoairk.your.domain/**, type a name, then a lobby name. Share the lobby link (`?lobby=…`) so
> friends join the same world. Type anything: `look`, `open the mailbox`, `"Hello, Jerry!"`, `*I wave*`.

## Troubleshooting

- **The page says "reconnecting…"**: the server isn't running, or the proxy isn't passing WebSocket upgrades.
- **Every turn says "Something went wrong"**: Ollama isn't running or isn't signed in (`ollama list`).
- **Players say "Slow down"**: the turn-gap limit is working; raise `ZOAIRK_MIN_TURN_GAP` if needed.
- **The log sync prints "push failed"**: the deploy key is missing or lacks write access; the logs stay safe on
  the server and are pushed on the next successful sync.
