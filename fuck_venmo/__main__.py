import dotenv

dotenv.load_dotenv()

import argparse
import atexit
from datetime import datetime, timedelta
import os
import subprocess
import sys
import time

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

driver_license = os.environ["VENMO_DRIVER_LICENSE_URL"]
driver_license_selfie = os.environ["VENMO_DRIVER_LICENSE_SELFIE_URL"]

parser = argparse.ArgumentParser("fuck_venmo")
parser.add_argument("-r", "--reset-password", action="store_true")
parser.add_argument("-n", "--new-ticket", action="store_true")
parser.add_argument("-v", "--use-vpn", action="store_true")
args = parser.parse_args()

if args.use_vpn:
    log_file = open("eddie.log", "w")
    proc = subprocess.Popen(["eddieup"], stdout=log_file, stdin=subprocess.PIPE)
    atexit.register(lambda: proc.communicate(b"x\n"))
    start_time = datetime.now()
    while True:
        with open("eddie.log") as f:
            log_text = f.read()
            if "- Connected." in log_text:
                break
            time.sleep(1)
            if proc.poll():
                print(log_text)
                raise RuntimeError("failed to start vpn")
            if datetime.now() - start_time > timedelta(seconds=60):
                print(log_text)
                raise RuntimeError("timed out starting vpn")

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
    driver_license_url=driver_license,
    driver_license_selfie_url=driver_license_selfie,
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
