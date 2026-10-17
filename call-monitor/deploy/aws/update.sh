#!/bin/bash
# Ships the COMMITTED code to the running server and re-applies the setup.
#
#   AWS_PROFILE=gg ./update.sh          (Git Bash on Windows, or any bash)
#
# Starts the machine if it's asleep, lets your current IP in over SSH, copies
# call-monitor/backend + call-monitor/deploy + docPipeline from git HEAD, and
# runs server-setup.sh (idempotent: reinstalls requirements, rewrites the
# services and Caddy config, restarts). Data under /var/lib/gg is untouched.
set -euo pipefail
# Git Bash would rewrite '/aws/...' style args into Windows paths for aws.exe.
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")"

REGION=${AWS_REGION:-ap-south-1}
IDLE_MINUTES=${IDLE_MINUTES:-15}
STATE=.state.env
KEY="$HOME/.ssh/gg-backend.pem"
REPO=$(git rev-parse --show-toplevel)
[ -f "$STATE" ] || { echo "No $STATE -- run deploy.sh first."; exit 1; }
# shellcheck disable=SC1090
source "$STATE"
awsq() { aws --region "$REGION" --output text "$@" | tr -d '\r'; }
step() { printf '\n== %s\n' "$*"; }
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
if command -v cygpath >/dev/null; then WORK=$(cygpath -m "$WORK"); fi

if [ -n "$(git -C "$REPO" status --porcelain -- call-monitor/backend call-monitor/deploy docPipeline)" ]; then
  echo "Note: uncommitted changes are NOT shipped -- only what's committed (git HEAD)."
fi

step "Server"
PUBLIC_IP=$(awsq ec2 describe-addresses --allocation-ids "$EIP_ALLOC" --query 'Addresses[0].PublicIp')
PUBLIC_HOST="${PUBLIC_IP//./-}.sslip.io"
STATE_NOW=$(awsq ec2 describe-instances --instance-ids "$INSTANCE_ID" --query 'Reservations[0].Instances[0].State.Name')
if [ "$STATE_NOW" = "stopping" ]; then
  aws ec2 wait instance-stopped --region "$REGION" --instance-ids "$INSTANCE_ID"; STATE_NOW=stopped
fi
[ "$STATE_NOW" = "stopped" ] && aws ec2 start-instances --region "$REGION" --instance-ids "$INSTANCE_ID" >/dev/null
aws ec2 wait instance-running --region "$REGION" --instance-ids "$INSTANCE_ID"
echo "$INSTANCE_ID running at $PUBLIC_IP ($PUBLIC_HOST)"

# Home IPs change; make sure this one may SSH in (no-op if already allowed).
SG=$(awsq ec2 describe-instances --instance-ids "$INSTANCE_ID" --query 'Reservations[0].Instances[0].SecurityGroups[0].GroupId')
MY_IP=$(curl -fsS https://checkip.amazonaws.com | tr -d '\r\n')
aws ec2 authorize-security-group-ingress --region "$REGION" --group-id "$SG" \
  --protocol tcp --port 22 --cidr "$MY_IP/32" >/dev/null 2>&1 || true

SSH=(ssh -i "$KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 "ubuntu@$PUBLIC_IP")
for _ in $(seq 1 30); do "${SSH[@]}" true 2>/dev/null && break; sleep 3; done

step "Ship code"
git -C "$REPO" -c core.autocrlf=false archive --format=tar.gz -o "$WORK/code.tgz" HEAD \
  call-monitor/backend call-monitor/deploy docPipeline
scp -i "$KEY" -o StrictHostKeyChecking=accept-new "$WORK/code.tgz" "ubuntu@$PUBLIC_IP:/tmp/gg-code.tgz"

step "Apply setup (a few minutes on first run)"
"${SSH[@]}" "sudo bash -s" <<EOF
set -euo pipefail
mkdir -p /opt/gg
tar -xzf /tmp/gg-code.tgz -C /opt/gg
rm -f /tmp/gg-code.tgz
printf 'AUTH_TOKEN=%s\nIDLE_MINUTES=%s\nPUBLIC_HOST=%s\n' '$AUTH_TOKEN' '$IDLE_MINUTES' '$PUBLIC_HOST' > /etc/gg-deploy.env
chmod 600 /etc/gg-deploy.env
bash /opt/gg/call-monitor/deploy/aws/server-setup.sh > /var/log/gg-update.log 2>&1 \
  || { tail -30 /var/log/gg-update.log; exit 1; }
tail -1 /var/log/gg-update.log
EOF

step "Health"
for _ in $(seq 1 40); do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "https://$PUBLIC_HOST/health" || true)
  [ "$code" = "200" ] && break; sleep 3
done
echo "voice backend /health: $code"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 -H "Authorization: Bearer $AUTH_TOKEN" "https://$PUBLIC_HOST/api/status" || true)
echo "docsign /api/status:   $code"
