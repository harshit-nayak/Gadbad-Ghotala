# Hosting the detection backend on AWS (sleeps when unused)

The backend is a stateful FastAPI service (WebSockets, ~1.3 GB model held in
memory, one inference worker), so it runs on one EC2 machine, not Lambda or
SageMaker. Because it's used rarely, the machine **powers itself off after
15 idle minutes** and is started again on demand:

```
browser ──https/wss──> Caddy :443 ─┬─ /api/*, /root_ca.pem ──> docsign  127.0.0.1:8765
   │        <ip>.sslip.io           └─ everything else ───────> voice    127.0.0.1:8000
   │        Let's Encrypt                     (one EC2 machine, stopped when idle) ▲
   └──POST──> Lambda function URL ──StartInstances─────────────────────────────────┘
```

- **Two services, one machine:** the voice detector (`call-monitor/backend`) and
  the document signing pipeline (`docPipeline`). Both require the same bearer
  token (docsign's is enforced by Caddy); `/root_ca.pem` is public.
- **Document data** (root CA, employee certificates, signature registry) lives in
  `/var/lib/gg/docsign` and survives stop/start. Employee **signing keys are a
  plaintext keyring file** there (a server has no OS keychain): fine for the demo,
  not for production, where they belong in an HSM/KMS or on employees' devices.

- **HTTPS without a domain:** `15-207-160-92.sslip.io` resolves to the Elastic
  IP, and Caddy gets a Let's Encrypt certificate for it and renews it on its
  own. WebSockets and the streamed `/analyse` response pass straight through.
  (CloudFront was the first plan; new AWS accounts can't create distributions
  until AWS Support verifies them.)
- **Idle stop:** `gg-idle-stop.timer` checks every minute and powers off after
  15 minutes without a live stream, upload, or document sign/verify/enrol. Open
  dashboards (`/ws/monitor`, `/health`, document status/history) don't count.

## Wake-up time (measured, Oct 2026)

From `start-instances` to the backend answering over HTTPS: **37 s**. The machine
boots in ~10 s, Caddy is up at ~14 s, and the model loads in ~18 s from a cold
disk (~5 s when cached). Once awake, each 4 s window is scored in **~0.7 s**.

## Deploy

```bash
aws configure --profile gg          # keys live in ~/.aws, never in the repo
cd call-monitor/deploy/aws
AWS_PROFILE=gg ./deploy.sh          # Git Bash on Windows
```

It needs the Indic head at `backend/models/xlsr-mamba/conformer_head_only.safetensors`
locally (uploaded to a private S3 bucket; the instance fetches it through a
7-day presigned link), and deploys the **committed** code (`git archive HEAD`).
First boot installs everything in ~5 minutes.

Then set in Vercel → Project Settings → Environment Variables, and redeploy
(Vite bakes them in at build time):

| Variable | Value |
|---|---|
| `VITE_BACKEND_URL` | `https://<ip-with-dashes>.sslip.io` (printed by deploy.sh) |
| `VITE_BACKEND_TOKEN` | `AUTH_TOKEN` from `.state.env` (gitignored) |
| `VITE_WAKE_URL` | the Lambda function URL, once the wake function exists |

Knobs: `INSTANCE_TYPE` (default `c7i.xlarge`), `IDLE_MINUTES` (default 15),
`AWS_REGION` (default `ap-south-1`). `AWS_PROFILE=gg ./teardown.sh` deletes everything.

## Updating the code on the server

Commit first, then:

```bash
AWS_PROFILE=gg ./update.sh
```

It wakes the machine if needed, allows your current IP over SSH, ships
`call-monitor/backend`, `call-monitor/deploy` and `docPipeline` from git HEAD,
and re-runs `server-setup.sh` (the same idempotent setup the first boot runs).
Data in `/var/lib/gg` is kept. Uncommitted changes are not shipped.

## Waking it

**Automatic (website button):** needs the wake Lambda, and creating a Lambda
needs an IAM role. If your IAM user can't create roles (`iam:CreateRole`), the
account owner must either grant `iam:CreateRole`, `iam:PutRolePolicy`,
`iam:AttachRolePolicy` and `iam:PassRole` on `role/gg-backend-wake`, or create
that role themselves (trusted by `lambda.amazonaws.com`, with
`AWSLambdaBasicExecutionRole` plus `ec2:StartInstances` on the instance and
`ec2:DescribeInstances`). Then re-run `deploy.sh`, which picks up from there.

**Manual (until then):** start it ~1 minute before use:

```bash
aws ec2 start-instances --profile gg --region ap-south-1 --instance-ids <INSTANCE_ID from .state.env>
```

## Cost at ~1 check per day (Mumbai prices, AWS Price List API)

Each check keeps the machine up ~17 minutes (≤1 boot + use + 15 idle), about
9 hours a month.

| Item | Price | Per month |
|---|---|---|
| EC2 `c7i.xlarge` | $0.1785/h × ~9 h | ~$1.60 |
| EBS 20 GB gp3 (billed while stopped too) | $0.0912/GB-month | $1.82 |
| Public IPv4 / Elastic IP (billed all month) | $0.005/h | $3.65 |
| Lambda, S3 | free tier / a few MB | ~$0 |
| **Total** | | **~$7 (~₹600)** |

Left running 24/7 it would be ~$136/month.

## Debugging

```bash
ssh -i ~/.ssh/gg-backend.pem ubuntu@<elastic ip>    # only from the IP that ran deploy.sh
sudo tail -f /var/log/gg-bootstrap.log    # first boot
journalctl -u gg-backend -f               # the backend
journalctl -u caddy -f                    # https / certificate
journalctl -t gg-idle-stop                # when and why it powered off
```
