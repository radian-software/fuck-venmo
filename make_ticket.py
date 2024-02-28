#!/usr/bin/env python3

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
import os
import re
import sys
import types
import uuid

import dotenv
import requests


@dataclass
class TicketInfo:

    username: str
    ip_address: str
    timestamp: datetime
    endpoint: str
    status_code: int
    error_message: str

    def format(self):
        return f"""

The following legitimate login attempt using correct account credentials was blocked by Venmo systems:

- Username: {self.username}
- Timestamp: {self.timestamp.isoformat()}
- IP address: {self.ip_address}
- Endpoint: {self.endpoint}
- Status code: {self.status_code}
- Error message: {self.error_message}

Please adjust your systems so that similar login attempts are not blocked.

Additional information:

- Account password has been reset at 2024-02-28T11:18:29
- Most recent payment was to "Fiona Hall-Zazueta" on 2024-01-27

        """.strip()


def log(msg):
    print(f"make_ticket: {msg}", file=sys.stderr)


def fatal(msg):
    log(msg)
    sys.exit(1)


USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.0.0 Safari/537.36"
DEVICE_ID = f"fp01-{uuid.uuid4()}"


def get_next_data(resp):
    assert resp.status_code == 200, resp.status_code
    next_data_match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">([^<>]+)</script>',
        resp.text,
    )
    assert next_data_match
    return json.loads(next_data_match.group(1))


def get_csrf_data(resp):
    next_data = get_next_data(resp)
    csrf_cookie = resp.cookies["_csrf"]
    csrf_token = next_data["props"]["pageProps"]["csrfToken"]
    return types.SimpleNamespace(cookie=csrf_cookie, token=csrf_token)


def perform_login(username, password):
    requests.get("https://venmo.com/account/sign-in", cookies={"v_id": DEVICE_ID})
    csrf = get_csrf_data(
        requests.get(
            "https://venmo.com/account/sign-in",
            cookies={
                "v_id": DEVICE_ID,
            },
            headers={
                "user-agent": USER_AGENT,
            },
        )
    )
    timestamp = datetime.now()
    resp = requests.get("https://ipv4.icanhazip.com")
    resp.raise_for_status()
    ip_address = resp.text.strip()
    resp = requests.post(
        "https://venmo.com/api/login",
        json={
            "username": username,
            "password": password,
            "isGroup": "false",
        },
        cookies={
            "v_id": DEVICE_ID,
            "_csrf": csrf.cookie,
        },
        headers={
            "csrf-token": csrf.token,
            "xsrf-token": csrf.token,
            "user-agent": USER_AGENT,
        },
    )
    assert resp.status_code == 400
    assert resp.request.url
    return TicketInfo(
        username=username,
        ip_address=ip_address,
        timestamp=timestamp,
        endpoint=resp.request.url,
        status_code=resp.status_code,
        error_message=resp.text,
    )


def main():
    parser = argparse.ArgumentParser("make_ticket")
    parser.parse_args()
    dotenv.load_dotenv()
    username = os.environ["VENMO_USERNAME"]
    ticket_info = perform_login(
        username,
        os.environ["VENMO_PASSWORD"],
    )
    print(ticket_info.format())
    sys.exit(0)


if __name__ == "__main__":
    main()
