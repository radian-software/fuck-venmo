from contextlib import contextmanager
import json
from pathlib import Path


@contextmanager
def state_loaded():
    try:
        with open("state.json") as f:
            obj = json.load(f)
    except FileNotFoundError:
        obj = {}
    yield obj
    with open("state.json.tmp", "w") as f:
        json.dump(obj, f, indent=2)
        f.write("\n")
    Path("state.json.tmp").rename("state.json")
