from datetime import datetime


def iso_format_but_not_fucked_up(dt: datetime):
    return datetime.utcfromtimestamp(dt.timestamp()).isoformat() + "Z"
