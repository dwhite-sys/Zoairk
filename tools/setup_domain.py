"""Set Zoairk up to be hosted on a domain of your choosing.

    python3 tools/setup_domain.py --domain play.example.com
    python3 tools/setup_domain.py --domain play.example.com --check     # also check DNS points here
    python3 tools/setup_domain.py --domain www.example.com/zoairk       # under a path on an existing site

Writes:
  zoairk.env                      settings the server reads on start (public URL, port, listen address)
  deploy/<domain>/Caddyfile       HTTPS reverse proxy for the domain (Caddy gets the certificate itself)
  deploy/<domain>/zoairk.service  systemd unit to keep the server running
and prints the remaining steps (DNS record, install Caddy, enable the service). Nothing is installed or started.
"""
from __future__ import annotations

import argparse
import getpass
import os
import re
import socket
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?!-)([a-z0-9-]{1,63}(?<!-)\.)+[a-z]{2,63}$")


def clean_domain(raw: str) -> tuple[str, str]:
    """'https://Play.Example.com/zoairk/' -> ('play.example.com', '/zoairk'). The path is optional."""
    d = re.sub(r"^https?://", "", raw.strip())
    host, _, path = d.partition("/")
    host = host.split(":")[0].lower()
    if not DOMAIN_RE.match(host):
        raise ValueError(f"not a valid domain name: {raw!r} (use something like play.example.com)")
    path = "/" + path.strip("/") if path.strip("/") else ""
    if path and not re.fullmatch(r"(/[A-Za-z0-9._~-]+)+", path):
        raise ValueError(f"not a valid path: {path!r} (use something like /zoairk)")
    return host, path


def render(domain: str, port: int, user: str, root: str, path: str = "") -> dict[str, str]:
    env = (f"# Written by tools/setup_domain.py for {domain}{path}\n"
           f"ZOAIRK_PUBLIC_URL=https://{domain}{path}\n"
           f"ZOAIRK_HOST=127.0.0.1\n"
           f"ZOAIRK_WS_PORT={port}\n")
    if path:   # the game lives under a path of a site that may serve other things too
        caddy = (f"{domain} {{\n"
                 f"    encode gzip\n"
                 f"    redir {path} {path}/\n"
                 f"    handle_path {path}/* {{\n"
                 f"        reverse_proxy 127.0.0.1:{port}\n"
                 f"    }}\n"
                 f"    # keep the rest of your site's directives (file_server, other handles) below\n"
                 f"}}\n")
    else:
        caddy = (f"{domain} {{\n"
                 f"    encode gzip\n"
                 f"    reverse_proxy 127.0.0.1:{port}\n"
                 f"}}\n")
    python = os.path.join(root, ".venv", "bin", "python")
    if not os.path.exists(python):
        python = sys.executable
    service = (f"[Unit]\nDescription=Zoairk game server ({domain}{path})\nAfter=network-online.target\n\n"
               f"[Service]\nUser={user}\nWorkingDirectory={root}\n"
               f"EnvironmentFile={os.path.join(root, 'zoairk.env')}\n"
               f"ExecStart={python} server.py\nRestart=on-failure\n\n"
               f"[Install]\nWantedBy=multi-user.target\n")
    return {"zoairk.env": env, "Caddyfile": caddy, "zoairk.service": service}


def dns_check(domain: str) -> str:
    try:
        addrs = sorted({ai[4][0] for ai in socket.getaddrinfo(domain, 443)})
    except socket.gaierror:
        return f"DNS: {domain} does not resolve yet. Add the record in step 1, then re-run with --check."
    return (f"DNS: {domain} -> {', '.join(addrs)}. That must be this server's public IP "
            f"(check with: curl -4 ifconfig.me).")


def main() -> int:
    ap = argparse.ArgumentParser(description="Host Zoairk on your own domain.")
    ap.add_argument("--domain", required=True, help="e.g. play.example.com")
    ap.add_argument("--port", type=int, default=8765, help="local port the game server uses (default 8765)")
    ap.add_argument("--user", default=getpass.getuser(), help="user the service runs as")
    ap.add_argument("--check", action="store_true", help="look up the domain's DNS")
    a = ap.parse_args()
    try:
        domain, path = clean_domain(a.domain)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    files = render(domain, a.port, a.user, ROOT, path)
    out = os.path.join(ROOT, "deploy", domain)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(ROOT, "zoairk.env"), "w") as fh:
        fh.write(files["zoairk.env"])
    for name in ("Caddyfile", "zoairk.service"):
        with open(os.path.join(out, name), "w") as fh:
            fh.write(files[name])
    rel = os.path.relpath(out, ROOT)
    url = f"https://{domain}{path}/"
    proxy_note = (f"\n    Your site already serves other pages at {domain}? Paste only the redir + handle_path lines into its\n"
                  f"    existing Caddy (or nginx/Apache) config instead of replacing it.") if path else ""
    print(f"""Zoairk is configured for {url}

Wrote zoairk.env, {rel}/Caddyfile and {rel}/zoairk.service. Remaining steps on this server:

 1. DNS: at your domain registrar, add an A record for {domain} pointing to this server's public IP.
 2. Ports: allow inbound 80 and 443 (Caddy uses them to get the HTTPS certificate and serve players).
 3. HTTPS proxy:  sudo apt install caddy
                  sudo cp {rel}/Caddyfile /etc/caddy/Caddyfile && sudo systemctl reload caddy{proxy_note}
 4. Game server:  sudo cp {rel}/zoairk.service /etc/systemd/system/zoairk.service
                  sudo systemctl daemon-reload && sudo systemctl enable --now zoairk
 5. Open {url} and use 📱 Invite: the QR code now points there.

To test before DNS is ready: python3 server.py, then open http://127.0.0.1:{a.port}/.
To undo: delete zoairk.env (the server goes back to local-only).""")
    if a.check:
        print("\n" + dns_check(domain))
    return 0


if __name__ == "__main__":
    sys.exit(main())
