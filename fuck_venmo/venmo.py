from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from pathlib import Path
import re
import time
import types
from urllib.parse import parse_qs, urlparse
import uuid

import gql
from gql import gql as GraphQLQuery
from gql.transport.requests import RequestsHTTPTransport
import requests
from selenium.webdriver.common.by import By

from fuck_venmo.fastmail import Fastmail
from fuck_venmo.state import state_loaded
from fuck_venmo.util import (
    from_iso_format_but_not_fucked_up,
    headless_browser,
    iso_format_but_not_fucked_up,
    log,
)


class CaptchaException(Exception):
    pass


@dataclass
class Payment:
    person: str
    amount: str
    timestamp: datetime
    outbound: bool

    @property
    def inbound(self):
        return not self.outbound


class SpecialPhrase(ABC):
    @abstractmethod
    def get_message(self) -> str:
        raise NotImplemented

    @property
    def triggers_autoresponse(self) -> bool:
        return False


@dataclass
class BannedPhrase(SpecialPhrase):
    phrase: str
    reason: str

    def get_message(self):
        return f'Your prior email used the phrase "{self.phrase}", which is not allowed. {self.reason} As a result, your prior email has been discarded without being read, and the request has been restated. Please try again.'

    @property
    def triggers_autoresponse(self):
        return True


@dataclass
class DoesItWorkNow(SpecialPhrase):
    phrase: str

    def get_message(self):
        return f'Your prior email used the phrase "{self.phrase}", which suggests you think that the problem is resolved. Please be advised that if you are receiving this email, then the problem is not resolved, and your prior email has been discarded without being read. Refer to the details below for updated timestamps, and please try again.'

    @property
    def triggers_autoresponse(self):
        return True


SPECIAL_PHRASES = [
    BannedPhrase(
        phrase="the error message is almost certainly an issue with either your ISP/cellular network",
        reason='The use of this phrase indicates that you did not read the preceding email, which clearly stated: "Please note that this is an issue with your systems, and not with the device, network, or application used to access them. No changes will be made to the device, network, or application used to access your systems unless a specific technical reason is given."'
    ),
    BannedPhrase(
        phrase="we need you to first reset your password",
        reason="The use of this phrase indicates that you did not read the preceding email, which clearly stated that the password on this account was reset, and provided a timestamp for this action.",
    ),
    BannedPhrase(
        phrase="can you please confirm the dollar amount",
        reason="The use of this phrase indicates that you did not read the preceding email, which provides a complete listing of all recent transactions on the account along with their dollar amounts.",
    ),
    DoesItWorkNow(
        phrase="let us know if you are able to login",
    ),
    DoesItWorkNow(
        phrase="you should be able to login",
    ),
]


class VenmoClient:
    def __init__(
        self,
        email_address: str,
        username: str,
        password: str,
        bank_account_number: str,
        fastmail: Fastmail,
    ):
        self.device_id = f"fp01-{uuid.uuid4()}"
        self.user_agent = (
            "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0"
        )
        self.username = username
        self.email_address = email_address
        self.password = password
        self.bank_account_number = bank_account_number
        self.unauthenticated_graphql = gql.Client(
            transport=RequestsHTTPTransport(
                url="https://api.venmo.com/graphql",
                headers={
                    "user-agent": self.user_agent,
                },
            )
        )
        self.fastmail = fastmail
        log("get mailbox labels")
        self.fuck_venmo_label = fastmail.get_mailbox_ids()["fuck-venmo"]["id"]

    def get_next_data(self, resp):
        assert resp.status_code == 200, resp.status_code
        next_data_match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">([^<>]+)</script>',
            resp.text,
        )
        if not next_data_match:
            assert "webcaptcha/ngrlCaptcha" in resp.text
            raise CaptchaException
        return json.loads(next_data_match.group(1))

    def get_csrf_data(self, resp):
        next_data = self.get_next_data(resp)
        csrf_cookie = resp.cookies["_csrf"]
        csrf_token = next_data["props"]["pageProps"]["csrfToken"]
        return types.SimpleNamespace(cookie=csrf_cookie, token=csrf_token)

    def trigger_password_reset(self):
        log("trigger password reset")
        with state_loaded() as state:
            info = {"triggered_start": datetime.now().timestamp()}
            self.unauthenticated_graphql.execute(
                GraphQLQuery(
                    """
    mutation forgotPassword($input: ForgotPasswordInput!) {
      forgotPassword(input: $input)
    }
            """
                ),
                variable_values={"input": {"phoneOrEmail": self.email_address}},
                operation_name="forgotPassword",
            )
            info["triggered_end"] = datetime.now().timestamp()
            if "venmo_password_reset" in state:
                state["venmo_last_password_reset"] = state["venmo_password_reset"]
            state["venmo_password_reset"] = info

    def fetch_password_reset_data(self):
        with state_loaded() as state:
            log("wait for password reset email")
            email = self.fastmail.wait_for_email(
                {"from": "venmo", "subject": "password reset"},
                since=datetime.fromtimestamp(
                    state["venmo_password_reset"]["triggered_start"]
                ),
                timeout=timedelta(minutes=2),
            )
            params = {}
            for key in ("reset_key", "user_external_id", "ts", "client"):
                match = re.search(
                    r"[?&]{key}=(?P<key>[^&)]+)".format(key=key), email["text"]
                )
                if not match:
                    raise RuntimeError(
                        f"password reset email doesn't have a {key} parameter"
                    )
                params[key] = match.group("key")
            state["venmo_password_reset"]["reset_params"] = params

    def complete_password_reset(self):
        log("complete password reset")
        with state_loaded() as state:
            params = state["venmo_password_reset"]["reset_params"]
            info = {
                "completed_start": datetime.now().timestamp(),
            }
            resp = requests.get(
                "https://venmo.com/account/password-new",
                params=params,
                cookies={
                    "v_id": self.device_id,
                },
                headers={
                    "user-agent": self.user_agent,
                },
            )
            csrf = self.get_csrf_data(resp)
            j = {
                "newPassword": self.password,
                "retypeNewPassword": self.password,
                "resetKey": params["reset_key"],
                "externalId": params["user_external_id"],
                "clientId": "10",
                "ts": params["ts"],
            }
            resp = requests.post(
                "https://venmo.com/api/account/changePassword",
                headers={
                    "User-Agent": self.user_agent,
                    "csrf-token": csrf.token,
                    "xsrf-token": csrf.token,
                },
                cookies={
                    "v_id": self.device_id,
                    "_csrf": csrf.cookie,
                },
                json={
                    "newPassword": self.password,
                    "retypeNewPassword": self.password,
                    "resetKey": params["reset_key"],
                    "externalId": params["user_external_id"],
                    "clientId": "10",
                    "client": params["client"],
                    "ts": params["ts"],
                },
                allow_redirects=False,
            )
            try:
                resp.raise_for_status()
            except Exception:
                raise RuntimeError(resp.text)
            info["completed_end"] = datetime.now().timestamp()
            state["venmo_password_reset"] = info
            state["venmo_last_password_reset"] = state["venmo_password_reset"]

    def reset_password(self):
        self.trigger_password_reset()
        self.fetch_password_reset_data()
        self.complete_password_reset()

    def get_transaction_ledger(self, since: datetime) -> list[Payment]:
        log("get transaction ledger")
        email_types = [
            {
                "subject": "you paid",
                "regex": r"You paid ([^$]+) \$([0-9.]+)",
                "outbound": True,
            },
            {
                "subject": "you completed charge request",
                "regex": r"You completed ([^']+)'s \$([0-9.]+) charge request",
                "outbound": True,
            },
            {
                "subject": "paid you",
                "regex": r"([^']+) paid you \$([0-9.]+)",
                "outbound": False,
            },
            {
                "subject": "paid your",
                "regex": r"([^$]+) paid your \$([0-9.]+) request",
                "outbound": False,
            }
        ]
        txns = []
        for email_type in email_types:
            for email in self.fastmail.search_emails({
                    "from": "venmo",
                    "subject": '"' +email_type["subject"] + '"',
                    "after": iso_format_but_not_fucked_up(since),
            }, limit=None):
                match = re.fullmatch(email_type["regex"], email["subject"])
                assert match, email["subject"] + " did not match " + email_type["regex"]
                recipient, amount = match.groups()
                txns.append(Payment(
                    person=recipient,
                    amount=amount,
                    timestamp=from_iso_format_but_not_fucked_up(email["sentAt"]),
                    outbound=email_type["outbound"],
                ))
        txns.sort(key=lambda txn: txn.timestamp)
        return txns

    def is_login_blocked(self):
        start_time = datetime.now()
        while True:
            try:
                log("get csrf data for login form")
                csrf = self.get_csrf_data(
                    requests.get(
                        "https://venmo.com/account/sign-in",
                        cookies={
                            "v_id": self.device_id,
                        },
                        headers={
                            "user-agent": self.user_agent,
                        },
                    )
                )
            except CaptchaException as e:
                if datetime.now() - start_time > timedelta(seconds=15):
                    raise CaptchaException("keep getting captcha, timed out") from e
                time.sleep(1)
                continue
            else:
                break
        log("submit login request")
        resp = requests.post(
            "https://venmo.com/api/login",
            json={
                "username": self.username,
                "password": self.password,
                "isGroup": "false",
            },
            cookies={
                "v_id": self.device_id,
                "_csrf": csrf.cookie,
            },
            headers={
                "csrf-token": csrf.token,
                "xsrf-token": csrf.token,
                "user-agent": self.user_agent,
            },
        )
        if "OAuth2 Exception" in resp.text:
            assert resp.request.url
            return types.SimpleNamespace(
                endpoint=resp.request.url,
                status_code=resp.status_code,
                error_message=resp.text,
            )
        assert (
            resp.status_code == 201
            or "Additional authentication is required" in resp.text
        )
        return None

    def is_login_blocked_selenium(self):
        start_time = datetime.now()
        log("instantiate headless browser for fallback login check")
        with headless_browser() as browser:
            log("load sign-in page")
            browser.get("https://account.venmo.com/account/sign-in")
            time.sleep(1)
            log("submit username form")
            browser.find_element(By.ID, "email").send_keys(self.username)
            browser.find_element(By.ID, "btnNext").click()
            time.sleep(1)
            log("submit password form")
            browser.find_element(By.ID, "password").send_keys(self.password)
            browser.find_element(By.ID, "btnLogin").click()
            time.sleep(5)
            if browser.current_url == "https://account.venmo.com/":
                return None
            if browser.current_url.startswith("https://account.venmo.com/account/mfa/code-prompt?k="):
                return None
            assert browser.current_url == "https://account.venmo.com/login-return-error", browser.current_url
            return types.SimpleNamespace(
                endpoint="https://account.venmo.com/account/sign-in",
                status_code=307,
                error_message=browser.find_element(By.CSS_SELECTOR, "h1").text.rstrip("."),
            )

    def get_replyto_id(self):
        log("get replyto id")
        last_inbound = self.fastmail.search_emails(
            {"from": "venmo", "subject": "you have an update from venmo"}, limit=1
        )[0]
        last_outbound = self.fastmail.search_emails(
            {"from": self.email_address, "to": "venmo"}, limit=1
        )[0]
        return max([last_inbound, last_outbound], key=lambda em: em["receivedAt"])["messageId"]

    def get_last_new_ticket(self):
        log("get last new ticket email")
        last = self.fastmail.search_emails(
            {
                "from": self.email_address,
                "to": "venmo",
                "subject": "Login attempt incorrectly blocked",
            },
            limit=1,
        )[0]
        return {
            "ts": from_iso_format_but_not_fucked_up(last["receivedAt"]),
        }

    def find_special_phrases(self, email_text) -> [SpecialPhrase]:
        found = []
        text = email_text.lower()
        for phrase in SPECIAL_PHRASES:
            if phrase.phrase.lower() in text:
                found.append(phrase)
        return found

    def get_last_inbound_message(self):
        log("get inbound message")
        last_inbound = self.fastmail.search_emails(
            {"from": "venmo", "subject": "you have an update from venmo"}, limit=1
        )[0]
        return {
            "ts": from_iso_format_but_not_fucked_up(last_inbound["receivedAt"]),
            "should_autoreply": self.fuck_venmo_label in last_inbound["mailboxIds"],
            "special_phrases": self.find_special_phrases(last_inbound["text"])
        }

    def get_last_outbound_message(self):
        log("get outbound message")
        outbounds = self.fastmail.search_emails(
            {"from": self.email_address, "to": "venmo"}, limit=10
        )
        return {
            "ts": from_iso_format_but_not_fucked_up(outbounds[0]["receivedAt"]),
            "prev_ts": [
                from_iso_format_but_not_fucked_up(email["receivedAt"]) for email in outbounds
            ],
        }

    def get_last_document_form(self) -> str:
        log("get last document form")
        last = self.fastmail.search_emails(
            {"from": "venmo", "text": "ticket_form_id=360001521814"}, limit=1
        )[0]
        form = re.search(r"https://help.venmo.com/[a-z0-9?&=/_-]+", last["text"])
        return {
            "ts": from_iso_format_but_not_fucked_up(last["receivedAt"]),
            "url": form.group(0),
        }

    def submit_documents(self, form_url: str, document_filepaths: list[Path]):
        proc_start_time = datetime.now()
        tid = parse_qs(urlparse(form_url).query)["tid"]
        log("instantiate headless browser for document submission")
        with headless_browser() as browser:
            log("loading zendesk document submission form")
            browser.get(form_url)
            time.sleep(1)
            log("filling zendesk document submission form")
            browser.find_element(By.ID, "request_anonymous_requester_email").send_keys(self.email_address)
            browser.find_element(By.ID, "request_description").send_keys("All applicable identity documents")
            for p in document_filepaths:
                browser.find_element(By.ID, "request-attachments").send_keys(str(p))
            log("waiting for documents to upload")
            start_time = datetime.now()
            while True:
                try:
                    elts = browser.find_elements(By.CSS_SELECTOR, "span.upload-remove")
                    assert len(elts) >= len(document_filepaths)
                    for elt in elts:
                        assert elt.is_displayed()
                except Exception:
                    pass
                else:
                    break
                time.sleep(1)
                if datetime.now() - start_time > timedelta(seconds=60):
                    raise RuntimeError("timed out waiting for documents to upload")
            log("submitting documents form")
            browser.find_element(By.CSS_SELECTOR, "input[type='submit']").click()
            time.sleep(5)
            assert "Your request was successfully submitted" in browser.page_source
            with state_loaded() as state:
                state["zendesk_document_submission"] = {
                    "completed_start": proc_start_time.timestamp(),
                    "completed_end": datetime.now().timestamp(),
                    "ticket_id": tid,
                    "form_url": form_url,
                }

    def count_outbound_emails(self):
        return len(self.fastmail.search_emails(
            {
                "from": self.email_address,
                "to": "venmo",
                "text": "The following legitimate login attempt using correct account credentials was blocked by Venmo systems",
            }, limit=None,
        ))
