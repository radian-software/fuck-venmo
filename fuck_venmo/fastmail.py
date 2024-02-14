from dataclasses import dataclass
from typing import Any

import bs4
from html2text import html2text
import requests
from requests.models import HTTPError


class JMAPError(Exception):
    pass


@dataclass
class Query:
    route: str
    params: dict[str, Any]
    name: str = ""


class Fastmail:
    def __init__(self, user_id, api_token):
        self.user_id = user_id
        self.api_token = api_token

    def _call(self, *calls: Query, force_multiple=False):
        http_resp = requests.post(
            "https://api.fastmail.com/jmap/api/",
            headers={
                "Authorization": f"Bearer {self.api_token}",
            },
            json={
                "using": [
                    "urn:ietf:params:jmap:core",
                    "urn:ietf:params:jmap:mail",
                    "urn:ietf:params:jmap:submission",
                ],
                "methodCalls": [[call.route, call.params, call.name] for call in calls],
            },
        )
        try:
            http_resp.raise_for_status()
        except HTTPError as e:
            raise JMAPError(http_resp.text) from e
        responses_struct = http_resp.json()["methodResponses"]
        responses = []
        for status, contents, _ in responses_struct:
            if status == "error":
                raise JMAPError(contents["type"] + ": " + contents["description"])
            responses.append(contents)
        if len(responses) == 1 and not force_multiple:
            return responses[0]
        return responses

    def search_emails(
        self,
        filtering: dict,
        sorting: list[dict] = [{"property": "receivedAt", "isAscending": False}],
        limit: int = 10,
    ):
        _, emails = self._call(
            Query(
                "Email/query",
                {
                    "accountId": self.user_id,
                    "filter": filtering,
                    "sort": sorting,
                    "limit": limit,
                },
                name="get_ids",
            ),
            Query(
                "Email/get",
                {
                    "accountId": self.user_id,
                    "#ids": {
                        "resultOf": "get_ids",
                        "name": "Email/query",
                        "path": "/ids",
                    },
                    "properties": [
                        "id",
                        "subject",
                        "sentAt",
                        "receivedAt",
                        "from",
                        "to",
                        "textBody",
                        "htmlBody",
                        "bodyValues",
                    ],
                    "fetchTextBodyValues": True,
                    "fetchHTMLBodyValues": True,
                },
            ),
        )
        for email in emails["list"]:
            collected_content = {}
            for key in ("textBody", "htmlBody"):
                for part in email[key]:
                    part["content"] = email["bodyValues"][part["partId"]]["value"]
                    if part["type"] == "text/html":
                        part["content"] = html2text(part["content"])
                collected_content[key] = "\n".join(
                    part["content"] for part in email[key]
                ).strip()
                email.pop(key)
            email.pop("bodyValues")
            email["text"] = (
                collected_content["textBody"] or collected_content["htmlBody"]
            )
        return emails["list"]
