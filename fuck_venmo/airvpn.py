import random

import requests

class AirVPN:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def get_random_server(self):
        resp = requests.get(
            "https://airvpn.org/api/status/",
            headers={
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        resp.raise_for_status()
        servers = resp.json()["servers"]
        ok_servers = []
        for server in servers:
            if server["country_name"] == "United States" and server["health"] == "ok":
                ok_servers.append(server["public_name"])
        return random.choice(ok_servers)
