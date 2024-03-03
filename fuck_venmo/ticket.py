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

    def format(self):
        return f"""

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
- Most recent outgoing payment was to "Ingrid Tsang" for $32.56 on 2024-02-29

        """.strip()
