#!/bin/bash
# Server setup for the GG backends. Idempotent: bootstrap.sh runs it on a new
# instance's first boot, and update.sh runs it after shipping new code.
#
# Expects the code under /opt/gg (call-monitor/backend, docPipeline) and the
# settings in /etc/gg-deploy.env (AUTH_TOKEN, IDLE_MINUTES, PUBLIC_HOST).
#
# Leaves running:
#   gg-backend.service   voice detection, uvicorn on 127.0.0.1:8000 (one
#                        worker -- the monitor feed and sessions live in memory)
#   gg-docsign.service   document signing (docPipeline), Flask on 127.0.0.1:8765
#   caddy                https:// + wss:// on PUBLIC_HOST (automatic Let's
#                        Encrypt certificate): /api/* and /root_ca.pem go to
#                        docsign, everything else to the voice backend
#   gg-idle-stop.timer   powers the machine off (= EC2 "stopped", no compute
#                        bill) after IDLE_MINUTES with no voice or document work
set -euxo pipefail
# shellcheck disable=SC1091
source /etc/gg-deploy.env
B=/opt/gg/call-monitor/backend
D=/opt/gg/docPipeline
DATA=/var/lib/gg
export DEBIAN_FRONTEND=noninteractive

# ------------------------------------------------------------------ packages
if ! command -v caddy >/dev/null || ! dpkg -s python3-venv >/dev/null 2>&1; then
  apt-get update
  apt-get install -y python3-venv curl debian-keyring debian-archive-keyring apt-transport-https gpg
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
    | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update
  apt-get install -y caddy
fi
id gg >/dev/null 2>&1 || useradd --system --home-dir /opt/gg --shell /usr/sbin/nologin gg
mkdir -p "$DATA/recordings" "$DATA/docsign/keyring"

# ------------------------------------------------------------------ voice backend
[ -x "$B/.venv/bin/python" ] || python3 -m venv "$B/.venv"
"$B/.venv/bin/python" -m pip install -q -r "$B/requirements.txt" -r "$B/requirements-antideepfake.txt"
[ -f "$B/models/silero_vad.onnx" ] || "$B/.venv/bin/python" "$B/scripts/fetch_silero.py"
[ -f "$B/models/xlsr-mamba/model_base.safetensors" ] || "$B/.venv/bin/python" "$B/scripts/fetch_xlsr_mamba.py"

cat > /etc/gg-backend.env <<EOF
AUTH_TOKEN=$AUTH_TOKEN
RECORDINGS_DIR=$DATA/recordings
# Other people's audio shouldn't pile up on a server: keep the verdict logs and
# speech-only audio, drop the raw per-chunk and per-window copies.
RECORD_CHUNKS=false
RECORD_WINDOWS=false
EOF
chmod 600 /etc/gg-backend.env

# ------------------------------------------------------------------ docsign
[ -x "$D/.venv/bin/python" ] || python3 -m venv "$D/.venv"
# keyrings.alt: a server has no OS keychain, so employee signing keys are kept
# in a plaintext keyring file under $DATA/docsign/keyring. Acceptable for the
# demo; a real deployment would use an HSM or KMS.
"$D/.venv/bin/python" -m pip install -q -r "$D/requirements.txt" keyrings.alt

cat > /etc/gg-docsign.env <<EOF
DOCSIGN_DATA_DIR=$DATA/docsign
DOCSIGN_ACTIVITY_FILE=$DATA/docsign/.last-activity
PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring
XDG_DATA_HOME=$DATA/docsign/keyring
EOF
chmod 600 /etc/gg-docsign.env

chown -R gg:gg /opt/gg "$DATA"
chmod 700 "$DATA/docsign"

# ------------------------------------------------------------------ services
cat > /etc/systemd/system/gg-backend.service <<EOF
[Unit]
Description=GG deepfake voice detection backend
After=network-online.target
Wants=network-online.target

[Service]
User=gg
WorkingDirectory=$B
Environment=PYTHONPATH=.
EnvironmentFile=/etc/gg-backend.env
ExecStart=$B/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/gg-docsign.service <<EOF
[Unit]
Description=GG document signing and verification (docPipeline)
After=network-online.target
Wants=network-online.target

[Service]
User=gg
WorkingDirectory=$D
EnvironmentFile=/etc/gg-docsign.env
ExecStart=$D/.venv/bin/python run_server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

cat > /usr/local/bin/gg-idle-stop <<EOF
#!/bin/bash
# Power off once neither service has done real work for $IDLE_MINUTES minutes.
# A voice backend that never comes up must not keep the machine (and the bill)
# running either: if /activity is unreachable 30 minutes after boot, stop too.
uptime_s=\$(cut -d. -f1 /proc/uptime)
docs=$DATA/docsign/.last-activity
if [ -f "\$docs" ] && [ \$(( \$(date +%s) - \$(stat -c %Y "\$docs") )) -lt $((IDLE_MINUTES * 60)) ]; then
  exit 0   # a document was signed/verified recently
fi
if ! a=\$(curl -fs --max-time 5 http://127.0.0.1:8000/activity); then
  [ "\$uptime_s" -gt 1800 ] && { logger "gg-idle-stop: backend down after 30 min, powering off"; systemctl poweroff; }
  exit 0
fi
read -r busy idle < <(python3 -c 'import json,sys; d=json.loads(sys.argv[1]); print(d["busy"], d["idle_seconds"])' "\$a")
if [ "\$busy" -eq 0 ] && [ "\$idle" -ge $((IDLE_MINUTES * 60)) ]; then
  logger "gg-idle-stop: idle \${idle}s, powering off"
  systemctl poweroff
fi
EOF
chmod 755 /usr/local/bin/gg-idle-stop

cat > /etc/systemd/system/gg-idle-stop.service <<'EOF'
[Unit]
Description=Stop the instance when the GG backends are idle

[Service]
Type=oneshot
ExecStart=/usr/local/bin/gg-idle-stop
EOF

cat > /etc/systemd/system/gg-idle-stop.timer <<'EOF'
[Unit]
Description=Check GG backend idleness every minute

[Timer]
OnBootSec=5min
OnUnitActiveSec=1min

[Install]
WantedBy=timers.target
EOF

# ------------------------------------------------------------------ https
# The document API has no auth of its own, so Caddy requires the same bearer
# token the voice backend uses (it ships in the site bundle, so it stops
# drive-by use rather than a determined attacker). /root_ca.pem stays public:
# it's a public certificate, fetched by a plain download link.
cat > /etc/caddy/Caddyfile <<EOF
$PUBLIC_HOST {
	@docs path /api/* /root_ca.pem
	handle @docs {
		header Access-Control-Allow-Origin "*"
		header Access-Control-Allow-Methods "GET, POST, OPTIONS"
		header Access-Control-Allow-Headers "Authorization, Content-Type"
		@preflight method OPTIONS
		respond @preflight 204
		@nokey {
			path /api/*
			not header Authorization "Bearer $AUTH_TOKEN"
		}
		respond @nokey "unauthorized" 401
		reverse_proxy 127.0.0.1:8765
	}
	handle {
		reverse_proxy 127.0.0.1:8000
	}
}
EOF
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile

systemctl daemon-reload
systemctl enable gg-backend.service gg-docsign.service gg-idle-stop.timer caddy
systemctl restart gg-backend.service gg-docsign.service
systemctl start gg-idle-stop.timer
systemctl reload-or-restart caddy
echo "gg server setup complete"
