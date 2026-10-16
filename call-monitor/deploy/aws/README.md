# Hosting the detection backend on AWS (sleeps when unused)

The backend is a stateful FastAPI service (WebSockets, ~1.3 GB model held in
memory, one inference worker), so it runs on one EC2 machine, not Lambda or
SageMaker. Because it's used rarely, the machine **powers itself off after
15 idle minutes** and the website **wakes it on demand**:

```
browser ──https/wss──> CloudFront ──:8000──> EC2 (stopped when idle)
   │                                            ▲
   └──POST──> Lambda function URL ──StartInstances┘
```

1. Someone presses *Live check* (or uploads a file) on the site.
2. The site can't reach `/health`, so it POSTs to the wake function and shows
   "Waking it up…". Boot plus model load takes ~1.5–2 minutes.
3. The check starts on its own once `/health` answers.
4. 15 minutes after the last stream or upload ends, `gg-idle-stop` powers the
   machine off. Open dashboards (`/ws/monitor`, `/health`) don't count as use.

## Deploy

```bash
aws configure --profile gg          # keys live in ~/.aws, never in the repo
cd call-monitor/deploy/aws
AWS_PROFILE=gg ./deploy.sh          # Git Bash on Windows
```

It needs the Indic head at `backend/models/xlsr-mamba/conformer_head_only.safetensors`
locally (uploaded to a private S3 bucket; the instance fetches it through a
7-day presigned link), and deploys the **committed** code (`git archive HEAD`).
It prints three values for Vercel → Project Settings → Environment Variables:
`VITE_BACKEND_URL`, `VITE_BACKEND_TOKEN`, `VITE_WAKE_URL`. Redeploy the site
after setting them (Vite bakes them in at build time).

Knobs: `INSTANCE_TYPE` (default `c7i.xlarge`), `IDLE_MINUTES` (default 15),
`AWS_REGION` (default `ap-south-1`).

`AWS_PROFILE=gg ./teardown.sh` deletes everything.

## Cost at ~1 check per day

Each check keeps the machine up ~22 minutes (2 boot + ~5 use + 15 idle), about
11 hours a month. US list prices; Mumbai is within a few percent.

| Item | Basis | Per month |
|---|---|---|
| EC2 `c7i.xlarge` | ~$0.18/h × ~11 h | ~$2.00 |
| EBS 20 GB gp3 | billed even while stopped, ~$0.08–0.09/GB | ~$1.70 |
| Elastic IP | $0.005/h, billed all month | ~$3.65 |
| CloudFront | well inside the always-free 1 TB / 10 M requests | $0 |
| Lambda wake | inside the free tier | $0 |
| S3 | a few MB | <$0.01 |
| **Total** | | **~$7–8 (~₹600–700)** |

The same machine left on 24/7 is ~$135/month. Each extra check-day adds ~7¢.
The Elastic IP is the largest line; it buys a fixed address that CloudFront
can point at across stop/start.

## Debugging

```bash
ssh -i ~/.ssh/gg-backend.pem ubuntu@<public DNS printed by deploy.sh>
sudo tail -f /var/log/gg-bootstrap.log        # first boot (~10 min)
journalctl -u gg-backend -f                   # the backend
journalctl -t gg-idle-stop                    # why/when it powered off
```

SSH is allowed only from the IP that ran `deploy.sh`.
