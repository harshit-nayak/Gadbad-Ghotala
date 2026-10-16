#!/bin/bash
# Deploys the detection backend to AWS as a machine that sleeps when unused.
#
#   AWS_PROFILE=gg ./deploy.sh          (Git Bash on Windows, or any bash)
#
# Creates, or reuses if they already exist (safe to re-run):
#   S3 bucket        private; code tarball + the private Indic head
#   EC2 instance     Ubuntu 24.04, $INSTANCE_TYPE, 20 GB gp3, set up by
#                    bootstrap.sh; powers itself off after $IDLE_MINUTES idle
#   Elastic IP       so the address survives stop/start
#   Caddy (on EC2)   https:// + wss:// at <ip>.sslip.io, Let's Encrypt cert
#   Lambda + URL     wake_lambda.py: the website calls it to start the machine
#
# Prints the Vercel environment variables at the end. teardown.sh deletes it all.
set -euo pipefail
# Git Bash would rewrite '/aws/service/...' args into Windows paths for aws.exe.
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")"

REGION=${AWS_REGION:-ap-south-1}
INSTANCE_TYPE=${INSTANCE_TYPE:-c7i.xlarge}
IDLE_MINUTES=${IDLE_MINUTES:-15}
NAME=gg-backend
STATE=.state.env          # ids of what was created (gitignored)
REPO=$(git rev-parse --show-toplevel)
HEAD_FILE="$REPO/call-monitor/backend/models/xlsr-mamba/conformer_head_only.safetensors"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
# aws.exe on Windows can't read /tmp/... in a file:// URL; give it C:/... instead.
if command -v cygpath >/dev/null; then WORK=$(cygpath -m "$WORK"); fi

touch "$STATE"
# shellcheck disable=SC1090
source "$STATE"
save() { printf '%s=%q\n' "$1" "$2" >> "$STATE"; printf -v "$1" '%s' "$2"; }
awsq() { aws --region "$REGION" --output text "$@" | tr -d '\r'; }
step() { printf '\n== %s\n' "$*"; }

[ -f "$HEAD_FILE" ] || { echo "Missing $HEAD_FILE (the Indic head)."; exit 1; }
ACCOUNT=$(awsq sts get-caller-identity --query Account)
echo "Account $ACCOUNT, region $REGION, profile ${AWS_PROFILE:-default}"

# ---------------------------------------------------------------- artefacts
step "Code + model head to S3"
BUCKET=${BUCKET:-gg-deploy-$ACCOUNT-$REGION}
if ! aws s3api head-bucket --bucket "$BUCKET" --region "$REGION" >/dev/null 2>&1; then
  aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \
    --create-bucket-configuration LocationConstraint="$REGION" >/dev/null
fi
# Committed code only, LF line endings, so the server runs what's in git.
git -C "$REPO" -c core.autocrlf=false archive --format=tar.gz -o "$WORK/code.tgz" HEAD call-monitor/backend
aws s3 cp "$WORK/code.tgz" "s3://$BUCKET/code.tgz" --region "$REGION" --only-show-errors
aws s3 cp "$HEAD_FILE" "s3://$BUCKET/conformer_head_only.safetensors" --region "$REGION" --only-show-errors
# Links only need to live until first boot finishes; 7 days is the maximum.
CODE_URL=$(awsq s3 presign "s3://$BUCKET/code.tgz" --expires-in 604800)
HEAD_URL=$(awsq s3 presign "s3://$BUCKET/conformer_head_only.safetensors" --expires-in 604800)

[ -n "${AUTH_TOKEN:-}" ] || save AUTH_TOKEN "$(openssl rand -hex 24)"

# ---------------------------------------------------------------- network
step "Security group"
VPC=$(awsq ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId')
[ "$VPC" != "None" ] || { echo "No default VPC in $REGION."; exit 1; }
SG=$(awsq ec2 describe-security-groups --filters Name=group-name,Values=$NAME Name=vpc-id,Values="$VPC" --query 'SecurityGroups[0].GroupId')
if [ "$SG" = "None" ]; then
  SG=$(awsq ec2 create-security-group --group-name $NAME --vpc-id "$VPC" \
        --description "GG detection backend: https via Caddy" --query GroupId)
  MY_IP=$(curl -fsS https://checkip.amazonaws.com | tr -d '\r\n')
  aws ec2 authorize-security-group-ingress --region "$REGION" --group-id "$SG" \
    --protocol tcp --port 22 --cidr "$MY_IP/32" >/dev/null
fi
# 443 serves the site's https/wss traffic; 80 only answers Let's Encrypt's
# certificate challenge (Caddy redirects everything else to https). The
# backend's own :8000 listens on localhost and is never exposed.
for port in 80 443; do
  aws ec2 authorize-security-group-ingress --region "$REGION" --group-id "$SG" \
    --protocol tcp --port $port --cidr 0.0.0.0/0 >/dev/null 2>&1 || true   # already there
done
echo "$SG"

step "SSH key (for debugging only)"
KEY_FILE="$HOME/.ssh/$NAME.pem"
if [ "$(awsq ec2 describe-key-pairs --filters Name=key-name,Values=$NAME --query 'KeyPairs[0].KeyName')" = "None" ]; then
  mkdir -p "$HOME/.ssh"
  awsq ec2 create-key-pair --key-name $NAME --query KeyMaterial > "$KEY_FILE"
  chmod 600 "$KEY_FILE"
fi
echo "$KEY_FILE"

# The address comes first: the certificate is issued for a hostname derived
# from it, and that hostname is baked into the instance's first-boot script.
step "Elastic IP"
ALLOC=$(awsq ec2 describe-addresses --filters Name=tag:Name,Values=$NAME --query 'Addresses[0].AllocationId')
if [ "$ALLOC" = "None" ]; then
  ALLOC=$(awsq ec2 allocate-address --domain vpc \
    --tag-specifications "ResourceType=elastic-ip,Tags=[{Key=Name,Value=$NAME}]" --query AllocationId)
  save EIP_ALLOC "$ALLOC"
fi
PUBLIC_IP=$(awsq ec2 describe-addresses --allocation-ids "$ALLOC" --query 'Addresses[0].PublicIp')
# sslip.io answers <a-b-c-d>.sslip.io with a.b.c.d: a free, stable hostname
# that Let's Encrypt can issue a certificate for. No domain to buy or manage.
PUBLIC_HOST="${PUBLIC_IP//./-}.sslip.io"
echo "$PUBLIC_IP -> $PUBLIC_HOST"

# ---------------------------------------------------------------- instance
step "EC2 instance"
INSTANCE=$(awsq ec2 describe-instances \
  --filters Name=tag:Name,Values=$NAME Name=instance-state-name,Values=pending,running,stopping,stopped \
  --query 'Reservations[0].Instances[0].InstanceId')
if [ "$INSTANCE" = "None" ]; then
  AMI=$(awsq ssm get-parameter --name /aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id --query Parameter.Value)
  # Bash substitution, not sed: presigned URLs are full of '&', and a quoted
  # replacement keeps every character literal.
  ud=$(tr -d '\r' < bootstrap.sh)
  ud=${ud//__CODE_URL__/"$CODE_URL"}
  ud=${ud//__HEAD_URL__/"$HEAD_URL"}
  ud=${ud//__AUTH_TOKEN__/"$AUTH_TOKEN"}
  ud=${ud//__IDLE_MINUTES__/"$IDLE_MINUTES"}
  ud=${ud//__PUBLIC_HOST__/"$PUBLIC_HOST"}
  printf '%s\n' "$ud" > "$WORK/user-data.sh"
  INSTANCE=$(awsq ec2 run-instances --image-id "$AMI" --instance-type "$INSTANCE_TYPE" \
    --key-name $NAME --security-group-ids "$SG" \
    --instance-initiated-shutdown-behavior stop \
    --metadata-options HttpTokens=required \
    --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=20,VolumeType=gp3,DeleteOnTermination=true}' \
    --user-data "file://$WORK/user-data.sh" \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME}]" "ResourceType=volume,Tags=[{Key=Name,Value=$NAME}]" \
    --query 'Instances[0].InstanceId')
  save INSTANCE_ID "$INSTANCE"
fi
aws ec2 wait instance-running --region "$REGION" --instance-ids "$INSTANCE" 2>/dev/null || true
aws ec2 associate-address --region "$REGION" --instance-id "$INSTANCE" --allocation-id "$ALLOC" >/dev/null
echo "$INSTANCE"
BACKEND_URL="https://$PUBLIC_HOST"

# ---------------------------------------------------------------- wake
step "Wake function"
ROLE=$NAME-wake
if ! aws iam get-role --role-name $ROLE >/dev/null 2>&1; then
  aws iam create-role --role-name $ROLE --assume-role-policy-document \
    '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  aws iam attach-role-policy --role-name $ROLE \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
fi
# Can start exactly this one instance, and read instance states. Nothing else.
aws iam put-role-policy --role-name $ROLE --policy-name start-backend --policy-document "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [
    {\"Effect\": \"Allow\", \"Action\": \"ec2:StartInstances\",
     \"Resource\": \"arn:aws:ec2:$REGION:$ACCOUNT:instance/$INSTANCE\"},
    {\"Effect\": \"Allow\", \"Action\": \"ec2:DescribeInstances\", \"Resource\": \"*\"}
  ]}" 2>/dev/null \
  || echo "   (can't edit the role's policy -- using the role as the account owner set it up)"
ROLE_ARN=$(awsq iam get-role --role-name $ROLE --query Role.Arn)
python -c "import zipfile,sys; z=zipfile.ZipFile(sys.argv[1],'w'); z.write('wake_lambda.py'); z.close()" "$WORK/wake.zip"
ENV="Variables={INSTANCE_ID=$INSTANCE,WAKE_TOKEN=$AUTH_TOKEN}"
if aws lambda get-function --function-name $NAME-wake --region "$REGION" >/dev/null 2>&1; then
  aws lambda update-function-code --function-name $NAME-wake --region "$REGION" --zip-file "fileb://$WORK/wake.zip" >/dev/null
  aws lambda wait function-updated --function-name $NAME-wake --region "$REGION"
  aws lambda update-function-configuration --function-name $NAME-wake --region "$REGION" --environment "$ENV" >/dev/null
else
  # A new role takes a few seconds to become usable by Lambda.
  for i in 1 2 3 4 5 6 7 8 9 10; do
    aws lambda create-function --function-name $NAME-wake --region "$REGION" \
      --runtime python3.12 --handler wake_lambda.handler --role "$ROLE_ARN" \
      --timeout 15 --memory-size 128 --zip-file "fileb://$WORK/wake.zip" \
      --environment "$ENV" >/dev/null 2>&1 && break
    sleep 5
  done
  aws lambda wait function-active-v2 --function-name $NAME-wake --region "$REGION"
fi
WAKE_URL=$(awsq lambda get-function-url-config --function-name $NAME-wake --query FunctionUrl 2>/dev/null || true)
if [ -z "$WAKE_URL" ]; then
  WAKE_URL=$(awsq lambda create-function-url-config --function-name $NAME-wake --auth-type NONE \
    --cors 'AllowOrigins=*,AllowMethods=GET,AllowMethods=POST' --query FunctionUrl)
  aws lambda add-permission --function-name $NAME-wake --region "$REGION" --statement-id public-url \
    --action lambda:InvokeFunctionUrl --principal '*' --function-url-auth-type NONE >/dev/null
  aws lambda add-permission --function-name $NAME-wake --region "$REGION" --statement-id public-url-invoke \
    --action lambda:InvokeFunction --principal '*' --invoked-via-function-url >/dev/null 2>&1 || true
fi
echo "$WAKE_URL"

cat <<EOF

Done. First boot installs everything (~10 min); then the backend answers at
$BACKEND_URL/health

Set these in Vercel -> Project Settings -> Environment Variables, then redeploy:
  VITE_BACKEND_URL=$BACKEND_URL
  VITE_BACKEND_TOKEN=$AUTH_TOKEN
  VITE_WAKE_URL=${WAKE_URL%/}

Watch first boot:  ssh -i "$KEY_FILE" ubuntu@$PUBLIC_IP 'tail -f /var/log/gg-bootstrap.log'
EOF
