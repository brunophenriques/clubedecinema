"""Week phases derived from UTC deadlines on every request (no scheduler needed)."""
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException


def phase(week, now=None):
    now = time.time() if now is None else now
    if not week.is_open:
        return "closed"
    if week.voting_deadline is not None and now >= week.voting_deadline:
        return "voting_closed"
    started = (now >= week.submission_deadline if week.submission_deadline is not None
               else week.is_ready)
    if not started:
        return "submissions"
    return "paused" if week.voting_paused else "voting"


def parse_deadlines(body):
    def timestamp(value):
        if not isinstance(value, str):
            return value
        try:
            local = datetime.strptime(value, "%Y-%m-%dT%H:%M")
            aware = local.replace(tzinfo=ZoneInfo("Europe/Lisbon"))
            result = int(aware.timestamp())
            if datetime.fromtimestamp(result, aware.tzinfo).replace(tzinfo=None) != local:
                raise ValueError("Nonexistent local time")
            return result
        except ValueError:
            raise HTTPException(422, "Data ou hora inválida. Escolhe outra hora.")

    submission = timestamp(body.get("submission_deadline"))
    voting = timestamp(body.get("voting_deadline"))
    if submission is None and voting is None:
        return None, None
    if (type(submission) is not int or type(voting) is not int
            or not 0 < submission < voting <= 2147483647):
        raise HTTPException(422, "Define ambos os prazos; o fim da votação deve ser posterior ao das submissões.")
    return submission, voting


def require_submissions(week):
    if phase(week) != "submissions":
        raise HTTPException(400, "Submissions are closed")


def require_voting(week):
    state = phase(week)
    if state == "submissions":
        raise HTTPException(400, "Voting not started yet")
    if state != "voting":
        raise HTTPException(400, "Voting is closed")
