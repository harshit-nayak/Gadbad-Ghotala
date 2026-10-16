#!/bin/bash
# Deletes everything deploy.sh created, so nothing keeps billing.
#
#   AWS_PROFILE=gg ./teardown.sh
#
# CloudFront must be disabled and fully redeployed before it can be deleted,
# which takes several minutes; the script waits for it.
set -uo pipefail
cd "$(dirname "$0")"
REGION=${AWS_REGION:-ap-south-1}
NAME=gg-backend
awsq() { aws --region "$REGION" --output text "$@" | tr -d '\r'; }

ACCOUNT=$(awsq sts get-caller-identity --query Account) || exit 1
read -r -p "Delete the GG backend (instance, disk, IP, CloudFront, Lambda, bucket) in account $ACCOUNT? [y/N] " ok
[ "$ok" = "y" ] || exit 0

echo "== Lambda + role"
aws lambda delete-function --function-name $NAME-wake --region "$REGION" 2>/dev/null
aws iam delete-role-policy --role-name $NAME-wake --policy-name start-backend 2>/dev/null
aws iam detach-role-policy --role-name $NAME-wake --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole 2>/dev/null
aws iam delete-role --role-name $NAME-wake 2>/dev/null

echo "== CloudFront"
DIST=$(awsq cloudfront list-distributions --query "DistributionList.Items[?Comment=='$NAME'].Id | [0]")
if [ -n "$DIST" ] && [ "$DIST" != "None" ]; then
  ETAG=$(awsq cloudfront get-distribution-config --id "$DIST" --query ETag)
  aws cloudfront get-distribution-config --id "$DIST" --query DistributionConfig --output json \
    | python -c "import json,sys; c=json.load(sys.stdin); c['Enabled']=False; print(json.dumps(c))" > .dist-disabled.json
  aws cloudfront update-distribution --id "$DIST" --if-match "$ETAG" --distribution-config file://.dist-disabled.json >/dev/null
  rm -f .dist-disabled.json
  echo "   waiting for the disable to deploy (several minutes)..."
  aws cloudfront wait distribution-deployed --id "$DIST"
  ETAG=$(awsq cloudfront get-distribution-config --id "$DIST" --query ETag)
  aws cloudfront delete-distribution --id "$DIST" --if-match "$ETAG"
fi

echo "== Instance, IP, security group, key"
INSTANCE=$(awsq ec2 describe-instances --filters Name=tag:Name,Values=$NAME Name=instance-state-name,Values=pending,running,stopping,stopped --query 'Reservations[0].Instances[0].InstanceId')
if [ "$INSTANCE" != "None" ]; then
  aws ec2 terminate-instances --region "$REGION" --instance-ids "$INSTANCE" >/dev/null
  aws ec2 wait instance-terminated --region "$REGION" --instance-ids "$INSTANCE"
fi
ALLOC=$(awsq ec2 describe-addresses --filters Name=tag:Name,Values=$NAME --query 'Addresses[0].AllocationId')
[ "$ALLOC" != "None" ] && aws ec2 release-address --region "$REGION" --allocation-id "$ALLOC"
SG=$(awsq ec2 describe-security-groups --filters Name=group-name,Values=$NAME --query 'SecurityGroups[0].GroupId')
[ "$SG" != "None" ] && aws ec2 delete-security-group --region "$REGION" --group-id "$SG"
aws ec2 delete-key-pair --region "$REGION" --key-name $NAME

echo "== Bucket"
BUCKET=gg-deploy-$ACCOUNT-$REGION
aws s3 rb "s3://$BUCKET" --force --region "$REGION" 2>/dev/null

rm -f .state.env
echo "Done."
