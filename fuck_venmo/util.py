from contextlib import contextmanager
from datetime import datetime
import sys

import requests
from selenium import webdriver
from selenium.webdriver.firefox.options import Options as FirefoxOptions


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] fuck_venmo: {msg}", file=sys.stderr)


def iso_format_but_not_fucked_up(dt: datetime):
    return datetime.utcfromtimestamp(dt.timestamp()).isoformat() + "Z"


def from_iso_format_but_not_fucked_up(fmt: str):
    return datetime.fromtimestamp(
        datetime.fromisoformat(fmt.replace("Z", "+00:00")).timestamp()
    )


def get_ipv4_address():
    resp = requests.get("https://ipv4.icanhazip.com")
    resp.raise_for_status()
    return resp.text.strip()


@contextmanager
def headless_browser(headless=True):
    options = FirefoxOptions()
    if headless:
        options.add_argument("--headless")
    browser = webdriver.Firefox(options=options)
    try:
        yield browser
    finally:
        browser.close()
