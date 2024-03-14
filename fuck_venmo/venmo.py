from datetime import datetime, timedelta
import json
import re
import types
import uuid

import gql
from gql import gql as GraphQLQuery
from gql.transport.requests import RequestsHTTPTransport
import requests

from fuck_venmo.fastmail import Fastmail
from fuck_venmo.state import state_loaded


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

    def get_next_data(self, resp):
        assert resp.status_code == 200, resp.status_code
        next_data_match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">([^<>]+)</script>',
            resp.text,
        )
        assert next_data_match
        return json.loads(next_data_match.group(1))

    def get_csrf_data(self, resp):
        next_data = self.get_next_data(resp)
        csrf_cookie = resp.cookies["_csrf"]
        csrf_token = next_data["props"]["pageProps"]["csrfToken"]
        return types.SimpleNamespace(cookie=csrf_cookie, token=csrf_token)

    def trigger_password_reset(self):
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

    def get_last_payment(self):
        last_initiated = self.fastmail.search_emails(
            {"from": "venmo", "subject": "you paid"}
        )[0]
        last_requested = self.fastmail.search_emails(
            {"from": "venmo", "subject": "you completed charge request"}
        )[0]
        latest_email = max(
            [last_initiated, last_requested], key=lambda email: email["sentAt"]
        )
        match = (
            re.fullmatch(
                r"You completed ([^']+)'s \$([0-9.]+) charge request",
                latest_email["subject"],
            )
            or re.fullmatch(r"You paid ([^$]+) \$([0-9.]+)", latest_email["subject"])
        )
        assert match, latest_email["subject"]
        recipient, amount = match.groups()
        return (
            recipient,
            amount,
            datetime.fromisoformat(latest_email["sentAt"].removesuffix("Z")),
        )

    def is_login_blocked(self):
        requests.get(
            "https://venmo.com/account/sign-in", cookies={"v_id": self.device_id}
        )
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

    def get_replyto_id(self):
        last_reply = self.fastmail.search_emails(
            {"from": "venmo", "subject": "you have an update from venmo"}, limit=1
        )[0]
        return last_reply["messageId"]
