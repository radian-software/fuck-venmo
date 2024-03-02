import dotenv

dotenv.load_dotenv()

import os

from fuck_venmo.fastmail import Fastmail, Query
from fuck_venmo.venmo import VenmoClient

f = Fastmail(os.environ["FASTMAIL_ACCOUNT_ID"], os.environ["FASTMAIL_API_TOKEN"])
v = VenmoClient(
    os.environ["VENMO_EMAIL_ADDRESS"],
    os.environ["VENMO_PASSWORD"],
    os.environ["VENMO_BANK_ACCOUNT_NUMBER"],
    f,
)

v.trigger_password_reset()
