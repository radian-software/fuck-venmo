import dotenv

dotenv.load_dotenv()

import os

from fuck_venmo.fastmail import Fastmail, Query

f = Fastmail(os.environ["FASTMAIL_ACCOUNT_ID"], os.environ["FASTMAIL_API_TOKEN"])
