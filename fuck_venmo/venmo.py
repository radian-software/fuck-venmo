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
        password: str,
        bank_account_number: str,
        fastmail: Fastmail,
    ):
        self.device_id = f"fp01-{uuid.uuid4()}"
        self.user_agent = (
            "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0"
        )
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
                    r"[?&]{key}=(?P<key>[^&]+)".format(key=key), email["text"]
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
            resp = requests.post(
                "https://venmo.com/api/account/changePassword",
                headers={
                    "user-agent": self.user_agent,
                    "xsrf-token": csrf.token,
                },
                cookies={
                    "v_id": self.device_id,
                    "_csrf": csrf.cookie,
                },
                json={
                    "clientId": "10",
                    "externalId": params["user_external_id"],
                    "newPassword": self.password,
                    "resetKey": params["reset_key"],
                    "retypeNewPassword": self.password,
                    "ts": params["ts"],
                },
                allow_redirects=False,
            )
            resp.raise_for_status()
