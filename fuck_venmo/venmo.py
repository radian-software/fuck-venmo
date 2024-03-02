from datetime import datetime

import gql
from gql import gql as GraphQLQuery
from gql.transport.requests import RequestsHTTPTransport

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
        self.email_address = email_address
        self.password = password
        self.bank_account_number = bank_account_number
        self.unauthenticated_graphql = gql.Client(
            transport=RequestsHTTPTransport(
                url="https://api.venmo.com/graphql",
                headers={
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
                },
            )
        )
        self.fastmail = fastmail

    def trigger_password_reset(self):
        with state_loaded() as state:
            state.setdefault("venmo_password_reset", {})
            info = state["venmo_password_reset"]
            info["triggered_start"] = datetime.now().timestamp()
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
