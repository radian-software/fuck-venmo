from dataclasses import dataclass
from datetime import datetime, timedelta
import random
import time
from typing import Any

from html2text import html2text
import requests
from requests.models import HTTPError

from fuck_venmo.util import iso_format_but_not_fucked_up


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

    def _call(self, *calls: Query, force_multiple=False) -> Any:
        req = {
            "using": [
                "urn:ietf:params:jmap:core",
                "urn:ietf:params:jmap:mail",
                "urn:ietf:params:jmap:submission",
            ],
            "methodCalls": [
                [call.route, {"accountId": self.user_id, **call.params}, call.name]
                for call in calls
            ],
        }
        http_resp = requests.post(
            "https://api.fastmail.com/jmap/api/",
            headers={
                "Authorization": f"Bearer {self.api_token}",
            },
            json=req,
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
            for key in (
                "notCreated",
                "notUpdated",
                "notDestroyed",
            ):
                if bad := contents.get(key):
                    raise JMAPError(repr({key: bad}))
            responses.append(contents)
        if len(responses) == 1 and not force_multiple:
            return responses[0]
        return responses

    def get_mailbox_ids(self) -> str:
        res = self._call(
            Query("Mailbox/get", {})
        )
        return {mb["name"]: mb for mb in res["list"]}

    def search_emails(
        self,
        filtering: dict,
        sorting: list[dict] = [{"property": "receivedAt", "isAscending": False}],
        limit: int | None = 10,
    ):
        _, emails = self._call(
            Query(
                "Email/query",
                {
                    "filter": filtering,
                    "sort": sorting,
                    **({"limit": limit} if limit else {}),
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
                        "messageId",
                        "subject",
                        "sentAt",
                        "receivedAt",
                        "from",
                        "to",
                        "textBody",
                        "htmlBody",
                        "bodyValues",
                        "mailboxIds",
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
            email["messageId"] = email["messageId"][0]
        return emails["list"]

    def wait_for_email(self, filtering: dict, since: datetime, timeout: timedelta):
        if since > datetime.now():
            raise RuntimeError("can't wait for email that hasn't been sent yet")
        deadline = since + timeout
        delay = timedelta(seconds=1)
        while True:
            matches = self.search_emails(
                {
                    **filtering,
                    "after": iso_format_but_not_fucked_up(since),
                    "before": iso_format_but_not_fucked_up(since + timeout),
                },
                limit=1,
            )
            if matches:
                return matches[0]
            if datetime.now() > deadline:
                raise TimeoutError("expected email didn't arrive before timeout")
            time.sleep(delay.total_seconds() * random.random())
            delay *= 2

    def send_email(
        self,
        from_name: str,
        from_email: str,
        to_name: str,
        to_email: str,
        subject: str,
        body_text: str,
        replyto_id: str = "",
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
        identities = self._call(
            Query(
                "Identity/get", {"filter": {"email": from_email}}, name="get_identity"
            )
        )
        identity_id = identities["list"][0]["id"]
        self._call(
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
                                **(
                                    {"header:In-Reply-To:asMessageIds": [replyto_id]}
                                    if replyto_id
                                    else {}
                                ),
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
                            "identityId": identity_id,
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
                            f"mailboxIds/{drafts_folder}": None,
                            f"mailboxIds/{sent_folder}": True,
                            "keywords/$draft": None,
                        }
                    },
                },
            ),
        )
