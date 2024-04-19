import dotenv

dotenv.load_dotenv()

import argparse
from datetime import datetime, timedelta
import os
from pathlib import Path
import subprocess
import sys
import time

import requests

from fuck_venmo.airvpn import AirVPN
from fuck_venmo.fastmail import Fastmail
from fuck_venmo.state import state_loaded
from fuck_venmo.ticket import TicketInfo
from fuck_venmo.venmo import CaptchaException, VenmoClient
from fuck_venmo.util import get_ipv4_address, log

atexit = lambda: None

def main():
    global atexit

    f = Fastmail(os.environ["FASTMAIL_ACCOUNT_ID"], os.environ["FASTMAIL_API_TOKEN"])
    v = VenmoClient(
        os.environ["VENMO_EMAIL_ADDRESS"],
        os.environ["VENMO_USERNAME"],
        os.environ["VENMO_PASSWORD"],
        os.environ["VENMO_BANK_ACCOUNT_NUMBER"],
        f,
    )
    a = AirVPN(os.environ["AIRVPN_API_KEY"])

    driver_license = os.environ["VENMO_DRIVER_LICENSE_URL"]
    driver_license_selfie = os.environ["VENMO_DRIVER_LICENSE_SELFIE_URL"]

    driver_license_filename = Path(os.environ["VENMO_DRIVER_LICENSE_FILENAME"]).resolve()
    driver_license_selfie_filename = Path(os.environ["VENMO_DRIVER_LICENSE_SELFIE_FILENAME"]).resolve()

    assert driver_license_filename.is_file()
    assert driver_license_selfie_filename.is_file()

    parser = argparse.ArgumentParser("fuck_venmo")
    parser.add_argument("-r", "--reset-password", action="store_true")
    parser.add_argument("-n", "--new-ticket", action="store_true")
    parser.add_argument("-v", "--use-vpn", action="store_true")
    parser.add_argument("-a", "--automatic", action="store_true")
    parser.add_argument("-y", "--yes", action="store_true")
    args = parser.parse_args()

    banned_phrases = []

    if args.automatic:

        # This should not be hardcoded when in automatic mode
        assert not args.new_ticket

        inbound = v.get_last_inbound_message()
        outbound = v.get_last_outbound_message()
        last_new = v.get_last_new_ticket()
        now = datetime.now()

        banned_phrases = inbound["banned_phrases"]

        # Lookup the last email that Venmo sent us, go forward in time
        # to the next email that we sent them (in response to that
        # email they sent us), and save that timestamp. This is the
        # timestamp we want to use as reference to see if they have
        # been ignoring us for too long: we want them to respond
        # within 4 days of the first time we mailed them in response
        # to their previous message.
        #
        # We also want to count us filing a new ticket the same as
        # them replying, in that we should wait again 4 days before
        # filing yet another ticket. To avoid falling into a loop of
        # new tickets.
        ts_ignored = [ts for ts in outbound["prev_ts"] if ts > max(inbound["ts"], last_new["ts"])]
        if ts_ignored:
            oldest_ignored_ts = min(ts_ignored)
        else:
            oldest_ignored_ts = None
        if inbound["ts"] > outbound["ts"]:
            log("most recent email was inbound from venmo")
            if inbound["should_autoreply"]:
                log("most recent inbound email flagged for automatic response, proceeding")
            elif inbound["banned_phrases"]:
                log("most recent inbound email uses banned phrases, proceeding unconditionally")
            else:
                log("most recent inbound email not flagged for automatic response, aborting")
                return
        else:
            log("most recent email was outbound from us")
            if now - outbound["ts"] > timedelta(hours=24):
                log("most recent email was sent more than 24 hours ago, proceeding")
            else:
                log("most recent email was sent less than 24 hours ago, aborting")
                return

        if oldest_ignored_ts and (now - oldest_ignored_ts > timedelta(days=4)):
            log("outbound emails have been ignored for more than 4 days, will file a new ticket")
            args.new_ticket = True
        elif oldest_ignored_ts:
            log("outbound emails have been ignored for less than 4 days, will not file a new ticket")
        else:
            log("no outbound emails have been ignored yet, will not file a new ticket")

    if args.use_vpn:
        log("pick random vpn server")
        server = a.get_random_server()
        log(f"start vpn connection via server {server}")
        log_file = open("eddie.log", "w")
        proc = subprocess.Popen(
            ["eddieup", server],
            stdout=log_file,
            stdin=subprocess.PIPE,
        )
        atexit = lambda: subprocess.run(["eddieup", "kill"])
        start_time = datetime.now()
        while True:
            with open("eddie.log") as log_file:
                log_text = log_file.read()
                if "- Connected." in log_text:
                    break
            time.sleep(1)
            if proc.poll() is not None:
                print(log_text)
                raise RuntimeError("failed to start vpn")
            if datetime.now() - start_time > timedelta(seconds=60):
                print(log_text)
                raise RuntimeError("timed out starting vpn")

    if args.reset_password:
        v.reset_password()

    try:
        block_info = v.is_login_blocked()
    except CaptchaException:
        log("normal login is blocked, falling back to selenium")
        block_info = v.is_login_blocked_selenium()

    if not block_info:
        print("Login is not currently blocked")
        sys.exit(0)

    txn_ledger = v.get_transaction_ledger(datetime.now() - timedelta(days=90))

    with state_loaded() as state:
        last_password_reset = datetime.fromtimestamp(
            state["venmo_password_reset"]["completed_end"]
        )

    last_form = v.get_last_document_form()

    needs_document_submission = True
    with state_loaded() as state:
        try:
            if last_form["url"] == state["zendesk_document_submission"]["form_url"]:
                needs_document_submission = False
        except Exception:
            pass

    if needs_document_submission:
        v.submit_documents(
            last_form["url"],
            [driver_license_filename, driver_license_selfie_filename],
        )
    else:
        log("document submission already completed since last new form, skipping")

    with state_loaded() as state:
        last_submission_ts = datetime.fromtimestamp(state["zendesk_document_submission"]["completed_end"])

    date = datetime.now().strftime("%Y-%m-%d")

    if args.new_ticket:
        replyto_id = ""
        subject = f"Login attempt incorrectly blocked ({date})"
        preface = "A new ticket has been filed since the prior ticket went ignored for more than 4 days."
    else:
        replyto_id = v.get_replyto_id()
        subject = "Re: You have an update from Venmo"
        preface = "\n\n".join(phrase.get_message() for phrase in banned_phrases)

    num_outbound = venmo.count_outbound_emails()

    ticket_info = TicketInfo(
        preface=preface,
        username=v.username,
        email_address=v.email_address,
        ip_address=get_ipv4_address(),
        timestamp=datetime.now(),
        endpoint=block_info.endpoint,
        status_code=block_info.status_code,
        error_message=block_info.error_message,
        last_password_reset=last_password_reset,
        transaction_ledger=txn_ledger,
        driver_license_url=driver_license,
        driver_license_selfie_url=driver_license_selfie,
        document_form_requested_time=last_form["ts"],
        document_form_completed_time=last_submission_ts,
        document_form_url=last_form["url"],
        num_outbound=num_outbound,
    )

    print(subject)
    print()
    print(ticket_info.format())
    print()
    if args.yes:
        print("[Skipping confirmation due to --yes]")
    else:
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

hc = os.environ["HEALTHCHECK_ENDPOINT"]

try:
    main()
    log("report to healthcheck endpoint")
    requests.get(hc)
    log("shutting down")
finally:
    atexit()
