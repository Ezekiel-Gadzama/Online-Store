#!/usr/bin/env python3
"""Upload project to develop-vps and start docker-compose.vps.yml."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from urllib.parse import quote_plus

import paramiko

DEFAULT_HOST = "144.172.100.41"
DEFAULT_USER = "root"
REMOTE_DIR = "/opt/online-store"

EXCLUDE_DIRS = {
    "node_modules",
    ".git",
    "venv",
    ".venv",
    "__pycache__",
    "yandex market API channel",
    ".cursor",
    "_tmp",
    "dist",
    "build",
}


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def make_tarball(src: Path) -> Path:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz")
    tmp.close()
    out = Path(tmp.name)
    with tarfile.open(out, "w:gz") as tar:
        for path in src.rglob("*"):
            rel = path.relative_to(src)
            parts = set(rel.parts)
            if parts & EXCLUDE_DIRS:
                continue
            if path.is_file():
                tar.add(path, arcname=str(rel).replace("\\", "/"))
    return out


def ssh_run(client: paramiko.SSHClient, cmd: str, timeout: int = 600) -> tuple[int, str, str]:
    print(f"$ {cmd[:200]}...")
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    code = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    err = stderr.read().decode()
    if out.strip():
        print(out[-4000:])
    if err.strip():
        print(err[-2000:], file=sys.stderr)
    return code, out, err


def build_server_env() -> str:
    import secrets

    pg_pass = os.environ.get("VPS_POSTGRES_PASSWORD") or secrets.token_urlsafe(24)
    secret = os.environ.get("VPS_SECRET_KEY") or secrets.token_urlsafe(48)
    host = os.environ.get("VPS_HOST", DEFAULT_HOST)
    token = os.environ.get("VPS_YANDEX_TOKEN", "")
    campaign = os.environ.get("VPS_YANDEX_CAMPAIGN_ID", "")
    smtp_pass = os.environ.get("VPS_SMTP_PASSWORD", "")
    smtp_user = os.environ.get("VPS_SMTP_USER", "")
    lines = [
        f"POSTGRES_USER=online_store_user",
        f"POSTGRES_PASSWORD={pg_pass}",
        f"POSTGRES_DB=online_store",
        f"DATABASE_URL=postgresql://online_store_user:{quote_plus(pg_pass)}@postgres:5432/online_store",
        f"SECRET_KEY={secret}",
        f"FRONTEND_URL=http://{host}:3010",
        f"PUBLIC_URL=http://{host}:8010",
        f"YANDEX_MARKET_BUSINESS_ID=217104046",
        f"YANDEX_MARKET_API_TOKEN={token}",
        f"YANDEX_MARKET_CAMPAIGN_ID={campaign}",
        f"SMTP_HOST=smtp.gmail.com",
        f"SMTP_PORT=587",
        f"SMTP_USER={smtp_user}",
        f"SMTP_PASSWORD={smtp_pass}",
        f"VPS_KEEP_EMAIL_SUBSTRING=ezekiel",
    ]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ.get("VPS_HOST", DEFAULT_HOST))
    parser.add_argument("--user", default=os.environ.get("VPS_USER", DEFAULT_USER))
    parser.add_argument("--password", default=os.environ.get("VPS_PASSWORD", ""))
    parser.add_argument("--remote-dir", default=REMOTE_DIR)
    parser.add_argument("--skip-env", action="store_true", help="Do not overwrite remote .env")
    args = parser.parse_args()

    if not args.password:
        print("Set VPS_PASSWORD env or pass --password")
        sys.exit(1)

    root = project_root()
    tarball = make_tarball(root)
    print(f"Created archive {tarball} ({tarball.stat().st_size // 1024} KiB)")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(args.host, username=args.user, password=args.password, timeout=20)

    try:
        ssh_run(client, f"mkdir -p {args.remote_dir}")
        sftp = client.open_sftp()
        remote_tar = f"{args.remote_dir}/project.tar.gz"
        sftp.put(str(tarball), remote_tar)
        sftp.close()
        os.unlink(tarball)

        ssh_run(client, f"cd {args.remote_dir} && tar xzf project.tar.gz && rm -f project.tar.gz")

        ssh_run(
            client,
            f"""python3 -c "
from pathlib import Path
from urllib.parse import quote_plus
p = Path('{args.remote_dir}/.env')
if not p.exists():
    raise SystemExit(0)
text = p.read_text(encoding='utf-8-sig').replace('\\ufeff', '')
lines = {{}}
order = []
for line in text.splitlines():
    s = line.strip()
    if not s or s.startswith('#') or '=' not in s:
        order.append(line)
        continue
    k, v = s.split('=', 1)
    lines[k] = v
    order.append(k)
u = lines.get('POSTGRES_USER') or 'online_store_user'
pw = lines.get('POSTGRES_PASSWORD') or ''
db = lines.get('POSTGRES_DB') or 'online_store'
lines['DATABASE_URL'] = f'postgresql://{{u}}:{{quote_plus(pw)}}@postgres:5432/{{db}}'
out = []
seen = set()
for item in order:
    if item in lines and item not in seen:
        out.append(f'{{item}}={{lines[item]}}')
        seen.add(item)
for k, v in lines.items():
    if k not in seen:
        out.append(f'{{k}}={{v}}')
p.write_text(chr(10).join(out) + chr(10), encoding='utf-8')
" """,
        )

        code, _, _ = ssh_run(client, "command -v docker")
        if code != 0:
            install = """
            apt-get update -qq
            apt-get install -y ca-certificates curl
            install -m 0755 -d /etc/apt/keyrings
            curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
            echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo ${VERSION_CODENAME}) stable" > /etc/apt/sources.list.d/docker.list
            apt-get update -qq
            apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
            """
            ssh_run(client, install.strip(), timeout=900)

        if not args.skip_env:
            env_body = build_server_env()
            sftp = client.open_sftp()
            with sftp.file(f"{args.remote_dir}/.env", "w") as remote_env:
                remote_env.write(env_body)
            sftp.close()
            print("Wrote remote .env")

        compose = f"cd {args.remote_dir} && docker compose -f docker-compose.vps.yml up -d --build"
        code, _, _ = ssh_run(client, compose, timeout=3600)
        if code != 0:
            print("Compose up returned non-zero; check backend logs on the server")

        ssh_run(
            client,
            f"cd {args.remote_dir} && docker compose -f docker-compose.vps.yml exec -T backend python init_db.py",
            timeout=300,
        )
        ssh_run(
            client,
            f"cd {args.remote_dir} && docker compose -f docker-compose.vps.yml exec -T backend python scripts/vps_bootstrap.py",
            timeout=120,
        )
        ssh_run(
            client,
            f"cd {args.remote_dir} && docker compose -f docker-compose.vps.yml exec -T backend python scripts/test_yandex_setup.py",
            timeout=120,
        )
        ssh_run(
            client,
            f"cd {args.remote_dir} && docker compose -f docker-compose.vps.yml ps",
        )
        print(f"\nFrontend: http://{args.host}:3010")
        print(f"Backend:  http://{args.host}:8010/api/health")
    finally:
        client.close()


if __name__ == "__main__":
    main()