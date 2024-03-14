import dotenv

dotenv.load_dotenv()

import argparse
from datetime import datetime
import os
import sys

from fuck_venmo.fastmail import Fastmail
from fuck_venmo.state import state_loaded
from fuck_venmo.ticket import TicketInfo
from fuck_venmo.venmo import VenmoClient
from fuck_venmo.util import get_ipv4_address

f = Fastmail(os.environ["FASTMAIL_ACCOUNT_ID"], os.environ["FASTMAIL_API_TOKEN"])
v = VenmoClient(
    os.environ["VENMO_EMAIL_ADDRESS"],
    os.environ["VENMO_USERNAME"],
    os.environ["VENMO_PASSWORD"],
    os.environ["VENMO_BANK_ACCOUNT_NUMBER"],
    f,
)

parser = argparse.ArgumentParser("fuck_venmo")
parser.add_argument("-r", "--reset-password", action="store_true")
parser.add_argument("-n", "--new-ticket", action="store_true")
args = parser.parse_args()

if args.reset_password:
    v.reset_password()

block_info = v.is_login_blocked()
if not block_info:
    print("Login is not currently blocked")
    sys.exit(0)

recipient, amount, txn_date = v.get_last_payment()

with state_loaded() as state:
    last_password_reset = datetime.fromtimestamp(
        state["venmo_password_reset"]["completed_end"]
    )

date = datetime.now().strftime("%Y-%m-%d")

if args.new_ticket:
    replyto_id = ""
    subject = f"Login attempt incorrectly blocked ({date})"
else:
    replyto_id = v.get_replyto_id()
    subject = "Re: You have an update from Venmo"

ticket_info = TicketInfo(
    username=v.username,
    email_address=v.email_address,
    ip_address=get_ipv4_address(),
    timestamp=datetime.now(),
    endpoint=block_info.endpoint,
    status_code=block_info.status_code,
    error_message=block_info.error_message,
    last_password_reset=last_password_reset,
    last_recipient_name=recipient,
    last_recipient_amount=amount,
    last_recipient_time=txn_date,
)

print(subject)
print()
print(ticket_info.format())
print()
input("[Press enter to send email, or ^C to abort] ")

f.send_email(
    "Radon Rosborough",
    "radon@intuitiveexplanations.com",
    "Venmo",
    "support@venmo.com",
    subject,
    ticket_info.format(),
    replyto_id,
)
