"""Wakes the sleeping detection backend (Lambda behind a public function URL).

    GET  <url>               -> {"state": "stopped" | "pending" | "running" | ...}
    POST <url>?token=<tok>   -> starts the instance if it is stopped, same reply

The website POSTs here when the backend doesn't answer, then polls the
backend's /health until the model is loaded. Starting an already-running or
pending instance is a no-op, so repeated POSTs are harmless. The token only
stops drive-by wake-ups (it ships in the site bundle, like VITE_BACKEND_TOKEN);
the worst an abuser can do is wake the machine, which then idles back off.
"""

import json
import os

import boto3

ec2 = boto3.client("ec2")
INSTANCE_ID = os.environ["INSTANCE_ID"]
WAKE_TOKEN = os.environ.get("WAKE_TOKEN", "")


def _reply(status: int, body: dict) -> dict:
    return {"statusCode": status, "headers": {"content-type": "application/json"}, "body": json.dumps(body)}


def handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    instance = ec2.describe_instances(InstanceIds=[INSTANCE_ID])["Reservations"][0]["Instances"][0]
    state = instance["State"]["Name"]

    if method == "POST":
        token = (event.get("queryStringParameters") or {}).get("token", "")
        if WAKE_TOKEN and token != WAKE_TOKEN:
            return _reply(403, {"error": "bad token"})
        if state == "stopped":
            ec2.start_instances(InstanceIds=[INSTANCE_ID])
            state = "pending"
        # "stopping": can't start yet; the site keeps POSTing until it can.

    return _reply(200, {"state": state})
