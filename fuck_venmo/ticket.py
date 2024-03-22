from dataclasses import dataclass
from datetime import datetime

from fuck_venmo.util import iso_format_but_not_fucked_up


@dataclass
class TicketInfo:

    username: str
    email_address: str
    ip_address: str
    timestamp: datetime
    endpoint: str
    status_code: int
    error_message: str
    last_password_reset: datetime
    last_recipient_name: str
    last_recipient_amount: str
    last_recipient_time: datetime
    driver_license_url: str
    driver_license_selfie_url: str

    def format(self):
        return f"""

Please read this email in its entirety before responding, as previous support agents have failed to do so and have incorrectly requested information that was already provided. Failure to read this email will result in it being repeated.

The following legitimate login attempt using correct account credentials was blocked by Venmo systems:

- Username: {self.username}
- Email address: {self.email_address}
- Timestamp: {iso_format_but_not_fucked_up(self.timestamp)}
- IP address: {self.ip_address}
- Endpoint: {self.endpoint}
- Status code: {self.status_code}
- Error message: {self.error_message}

Please adjust your systems so that similar login attempts are not blocked.

Additional information:

- Account password has most recently been reset at {iso_format_but_not_fucked_up(self.last_password_reset)}
- Most recent outgoing payment was to "{self.last_recipient_name}" for ${self.last_recipient_amount} on {self.last_recipient_time.strftime('%Y-%m-%d')}
- Photograph of unexpired driver license is available at <{self.driver_license_url}>
- Photograph of account-holder holding driver license is available at <{self.driver_license_selfie_url}>

Please note that tickets will continue to be filed until a response is received.

        """.strip()
