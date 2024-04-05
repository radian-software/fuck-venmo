import dotenv

dotenv.load_dotenv()

from datetime import datetime, timedelta
import os
from pathlib import Path

from fuck_venmo.fastmail import Fastmail, Query
from fuck_venmo.util import iso_format_but_not_fucked_up
from fuck_venmo.venmo import VenmoClient

id_files = [
    Path(os.environ["VENMO_DRIVER_LICENSE_FILENAME"]).resolve(),
    Path(os.environ["VENMO_DRIVER_LICENSE_SELFIE_FILENAME"]).resolve(),
]

f = Fastmail(os.environ["FASTMAIL_ACCOUNT_ID"], os.environ["FASTMAIL_API_TOKEN"])
v = VenmoClient(
    os.environ["VENMO_EMAIL_ADDRESS"],
    os.environ["VENMO_USERNAME"],
    os.environ["VENMO_PASSWORD"],
    os.environ["VENMO_BANK_ACCOUNT_NUMBER"],
    f,
)
