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
                "methodCalls": [
                    [call.route, {"accountId": self.user_id, **call.params}, call.name]
                    for call in calls
                ],
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
                try:
                    raise JMAPError(contents["type"] + ": " + contents["description"])
                except KeyError:
                    raise JMAPError(
                        contents.pop("type") + ": " + repr(contents)
                    ) from None
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
                    "filter": filtering,
                    "sort": sorting,
                    "limit": limit,
                },
                name="get_ids",
            ),
            Query(
                "Email/get",
                {
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

    def send_email(
        self,
        from_name: str,
        from_email: str,
        to_name: str,
        to_email: str,
        subject: str,
        body_text: str,
        reply_to_id: str = "",
    ):
        drafts_folders, sent_folders = self._call(
            Query(
                "Mailbox/query",
                {"filter": {"role": "drafts"}},
            ),
            Query("Mailbox/query", {"filter": {"role": "sent"}}),
        )
        (drafts_folder,) = drafts_folders["ids"]
        (sent_folder,) = sent_folders["ids"]
        self._call(
            Query(
                "Identity/get", {"filter": {"email": from_email}}, name="get_identity"
            ),
            Query(
                "Email/set",
                {
                    "create": {
                        "draft_id": {
                            "mailboxIds": {
                                drafts_folder: True,
                            },
                            "keywords": {"$seen": True, "$draft": True},
                            "from": [
                                {
                                    "name": from_name,
                                    "email": from_email,
                                }
                            ],
                            "to": [
                                {
                                    "name": to_name,
                                    "email": to_email,
                                }
                            ],
                            "subject": subject,
                            "bodyStructure": {
                                "type": "text/plain",
                                "partId": "body_id",
                            },
                            "bodyValues": {
                                "body_id": {"value": body_text, "isTruncated": False}
                            },
                        }
                    }
                },
            ),
            Query(
                "EmailSubmission/set",
                {
                    "create": {
                        "sent_id": {
                            "#identityId": {
                                "resultOf": "get_identity",
                                "name": "Identity/get",
                                "path": "/id",
                            },
                            "emailId": "#draft_id",
                            "envelope": {
                                "mailFrom": {
                                    "email": from_email,
                                    "parameters": None,
                                },
                                "rcptTo": [
                                    {
                                        "email": to_email,
                                        "parameters": None,
                                    }
                                ],
                            },
                        }
                    },
                    "onSuccessUpdateEmail": {
                        "#sent_id": {
                            drafts_folder: None,
                            sent_folder: True,
                            "keywords/$draft": None,
                        }
                    },
                },
            ),
        )
