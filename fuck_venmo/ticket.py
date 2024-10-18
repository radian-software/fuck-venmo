from dataclasses import dataclass
from datetime import datetime

from fuck_venmo.venmo import Payment
from fuck_venmo.util import iso_format_but_not_fucked_up


@dataclass
class TicketInfo:

    preface: str
    username: str
    email_address: str
    ip_address: str
    timestamp: datetime
    endpoint: str
    status_code: int
    error_message: str
    last_password_reset: datetime
    transaction_ledger: list[Payment]
    driver_license_url: str
    driver_license_selfie_url: str
    error_message_screenshot_url: str
    document_form_requested_time: datetime
    document_form_completed_time: datetime
    document_form_url: str
    num_outbound: int

    def format(self):
        ledger = "\n".join(f"- ${txn.amount} " + ("sent to" if txn.outbound else "received from") + f" {txn.person} at {iso_format_but_not_fucked_up(txn.timestamp)}" for txn in reversed(self.transaction_ledger)) or "(no transactions)"
        return f"""

{self.preface}

Please read this email in its entirety before responding, as previous support agents have failed to do so and have incorrectly requested information that was already provided. Failure to read this email will result in it being repeated.

When logging in from a new device using correct credentials, I frequently receive spurious errors from Venmo which block me from logging in. Here are the details for one such login attempt, which was performed immediately before this email was sent:

- Username: {self.username}
- Email address: {self.email_address}
- Timestamp: {iso_format_but_not_fucked_up(self.timestamp)}
- IP address: {self.ip_address}
- Endpoint: {self.endpoint}
- Platform: Desktop (Firefox, Linux)
- Status code: {self.status_code}
- Error message: {self.error_message}

Please adjust your systems so that similar login attempts are not blocked. Please note that immediately after your reply, I will perform another login from another new device, and you will receive another follow-up if that login is blocked. I am not able to guarantee that I will only access Venmo from a single device, so any solution that does not solve the problem for new devices will not suffice to close this ticket. Such solutions, if presented, will be ignored and my request will be restated.

Please note that this has been confirmed to be an issue with your systems, and not with the device, network, or application used to access them. No changes will be made to the device, network, or application used to access your systems unless a specific technical reason is given. The same behavior occurs regardless of the device used - mobile application, web browser, etc.

If you suggest any troubleshooting step which I have already performed, or request that I change any aspect of my device or network without a specific technical reason, your email will be ignored and my request will be restated.

Additional information:

- Account password has most recently been reset at {iso_format_but_not_fucked_up(self.last_password_reset)}
- Photograph of unexpired driver license is available at <{self.driver_license_url}>
- Photograph of account-holder holding driver license is available at <{self.driver_license_selfie_url}>
- Example screenshot of error message is available at <{self.error_message_screenshot_url}>
- The aforementioned documents were also uploaded at <{self.document_form_url}> most recently at {iso_format_but_not_fucked_up(self.document_form_completed_time)} as requested at {iso_format_but_not_fucked_up(self.document_form_requested_time)}
- The account-holder and the device accessing Venmo are both located within the United States

For verification purposes, the following is a list of all Venmo transactions on the account from the last 3 months, in reverse chronological order:

{ledger}

Please note that you have received {self.num_outbound} prior emails about this specific issue, but have not resolved it.

        """.strip()

# To set your expectations, if a response is not received within 24 hours, a follow-up email will be sent. If a response is not received within 5 days, a new ticket will be filed. This process will repeat until login issues are resolved.
