from datetime import datetime
import sys

import requests


def log(msg: str):
    print(f"fuck_venmo: {msg}", file=sys.stderr)


def iso_format_but_not_fucked_up(dt: datetime):
    return datetime.utcfromtimestamp(dt.timestamp()).isoformat() + "Z"


def get_ipv4_address():
    resp = requests.get("https://ipv4.icanhazip.com")
    resp.raise_for_status()
    return resp.text.strip()
