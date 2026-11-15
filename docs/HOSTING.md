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

**B. Your own domain with HTTPS** (recommended for the public). Run the server on the machine, then put a
reverse proxy in front of port 8765. With Caddy (it gets the HTTPS certificate for you):

```
zoairk.your.domain {
    reverse_proxy 127.0.0.1:8765
}
```

Point the domain's DNS at the machine. Players open `https://zoairk.your.domain/`. The page switches to a secure
WebSocket (`wss://`) on its own.

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
| `ZOAIRK_WS_PORT` | `8765` | the one port for page + game |
| `ZOAIRK_MIN_TURN_GAP` | `2` | seconds between one player's turns |
| `ZOAIRK_MAX_PENDING` | `12` | queued turns per lobby |
| `ZOAIRK_MAX_PLAYERS` | `8` | players per lobby |
| `ZOAIRK_MAX_LOBBIES` | `20` | lobbies per server |
| `ZOAIRK_LOG_SYNC_MINUTES` | `10` | how often to push anonymized logs (`0` = off) |
| `ZOAIRK_LOG_BRANCH` | `play-logs` | branch the logs go to |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | which Ollama to use |
| `ZOAIRK_MODEL` | `deepseek-v4.1-flash:cloud` | which model to use |

## 6. Tell players

> Open **https://zoairk.your.domain/**, type a name, then a lobby name. Share the lobby link (`?lobby=…`) so
> friends join the same world. Type anything: `look`, `open the mailbox`, `"Hello, Jerry!"`, `*I wave*`.

## Troubleshooting

- **The page says "reconnecting…"**: the server isn't running, or the proxy isn't passing WebSocket upgrades.
- **Every turn says "Something went wrong"**: Ollama isn't running or isn't signed in (`ollama list`).
- **Players say "Slow down"**: the turn-gap limit is working; raise `ZOAIRK_MIN_TURN_GAP` if needed.
- **The log sync prints "push failed"**: the deploy key is missing or lacks write access; the logs stay safe on
  the server and are pushed on the next successful sync.
