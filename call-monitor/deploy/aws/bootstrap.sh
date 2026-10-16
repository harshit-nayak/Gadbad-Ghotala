#!/bin/bash
# EC2 user-data for the detection backend. Runs ONCE, as root, on the first
# boot of a fresh Ubuntu 24.04 instance; later boots just start the services.
# deploy.sh fills in the __PLACEHOLDERS__ before launching the instance.
#
# Leaves behind:
#   gg-backend.service   uvicorn on :8000 (one worker -- the monitor feed and
#                        sessions live in process memory)
#   gg-idle-stop.timer   powers the machine off (= EC2 "stopped", no compute
#                        bill) once nothing has been analysed for IDLE_MINUTES
set -euxo pipefail
exec > >(tee -a /var/log/gg-bootstrap.log) 2>&1

CODE_URL='__CODE_URL__'
HEAD_URL='__HEAD_URL__'
AUTH_TOKEN='__AUTH_TOKEN__'
IDLE_MINUTES='__IDLE_MINUTES__'
B=/opt/gg/call-monitor/backend

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv curl

# Code (a tarball of call-monitor/backend) and the private Indic head both come
# from short-lived presigned S3 links, so the instance needs no GitHub token
# and no AWS credentials of its own.
mkdir -p /opt/gg
curl -fsSL "$CODE_URL" | tar -xz -C /opt/gg
mkdir -p "$B/models/xlsr-mamba"
curl -fsSL -o "$B/models/xlsr-mamba/conformer_head_only.safetensors" "$HEAD_URL"

python3 -m venv "$B/.venv"
"$B/.venv/bin/python" -m pip install -q --upgrade pip
"$B/.venv/bin/python" -m pip install -q -r "$B/requirements.txt" -r "$B/requirements-antideepfake.txt"
"$B/.venv/bin/python" "$B/scripts/fetch_silero.py"
"$B/.venv/bin/python" "$B/scripts/fetch_xlsr_mamba.py"   # 1.28 GB public base, from Hugging Face

useradd --system --home-dir /opt/gg --shell /usr/sbin/nologin gg || true
mkdir -p /var/lib/gg/recordings
chown -R gg:gg /opt/gg /var/lib/gg

cat > /etc/gg-backend.env <<EOF
AUTH_TOKEN=$AUTH_TOKEN
RECORDINGS_DIR=/var/lib/gg/recordings
# Other people's audio shouldn't pile up on a server: keep the verdict logs and
# speech-only audio, drop the raw per-chunk and per-window copies.
RECORD_CHUNKS=false
RECORD_WINDOWS=false
EOF
chmod 600 /etc/gg-backend.env

cat > /etc/systemd/system/gg-backend.service <<EOF
[Unit]
Description=GG deepfake detection backend
After=network-online.target
Wants=network-online.target

[Service]
User=gg
WorkingDirectory=$B
Environment=PYTHONPATH=.
EnvironmentFile=/etc/gg-backend.env
ExecStart=$B/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

cat > /usr/local/bin/gg-idle-stop <<EOF
#!/bin/bash
# Power off once the detector has been idle for $IDLE_MINUTES minutes.
# A backend that never comes up must not keep the machine (and the bill)
# running either: if /activity is unreachable 30 minutes after boot, stop too.
uptime_s=\$(cut -d. -f1 /proc/uptime)
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
Description=Stop the instance when the detector is idle

[Service]
Type=oneshot
ExecStart=/usr/local/bin/gg-idle-stop
EOF

cat > /etc/systemd/system/gg-idle-stop.timer <<'EOF'
[Unit]
Description=Check detector idleness every minute

[Timer]
OnBootSec=5min
OnUnitActiveSec=1min

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now gg-backend.service gg-idle-stop.timer
echo "gg bootstrap complete"
