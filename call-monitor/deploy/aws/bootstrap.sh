#!/bin/bash
# EC2 user-data for the GG backends. Runs ONCE, as root, on the first boot of
# a fresh Ubuntu 24.04 instance: fetches the code and the private model head,
# records the settings, then hands over to server-setup.sh (which update.sh
# re-runs later for code updates). deploy.sh fills in the __PLACEHOLDERS__.
set -euxo pipefail
exec > >(tee -a /var/log/gg-bootstrap.log) 2>&1

CODE_URL='__CODE_URL__'
HEAD_URL='__HEAD_URL__'

# Code (a tarball of call-monitor/backend, call-monitor/deploy and docPipeline)
# and the private Indic head both come from short-lived presigned S3 links, so
# the instance needs no GitHub token and no AWS credentials of its own.
mkdir -p /opt/gg
curl -fsSL "$CODE_URL" | tar -xz -C /opt/gg
mkdir -p /opt/gg/call-monitor/backend/models/xlsr-mamba
curl -fsSL -o /opt/gg/call-monitor/backend/models/xlsr-mamba/conformer_head_only.safetensors "$HEAD_URL"

cat > /etc/gg-deploy.env <<'EOF'
AUTH_TOKEN=__AUTH_TOKEN__
IDLE_MINUTES=__IDLE_MINUTES__
PUBLIC_HOST=__PUBLIC_HOST__
EOF
chmod 600 /etc/gg-deploy.env

bash /opt/gg/call-monitor/deploy/aws/server-setup.sh
echo "gg bootstrap complete"
