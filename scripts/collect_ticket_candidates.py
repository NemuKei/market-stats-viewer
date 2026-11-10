"""Read approved public ticket pages into unreviewed candidates, never live facts.

No ledger, event DB, registry, release, or reviewed timestamp is changed. The
network adapter refuses redirects/access barriers and does not use credentials.
"""

import argparse
from copy import deepcopy
from datetime import date
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser

from .ticket_rounds import utc

HOSTS = {"niziu.com"}  # New official sources require code review, not page links.
MAX_BYTES = 2_000_000
KINDS = ("application_open", "application_close", "results", "payment_deadline")
LABELS = {
    "受付期間": ("application_open", "application_close"),
    "当落発表": ("results",),
    "入金期限": ("payment_deadline",),
}
STAMP = re.compile(
    r"(?:(?P<year>\d{4})年)?(?P<month>\d{1,2})月(?P<day>\d{1,2})日(?:\([月火水木金土日]\))?(?:\s*(?P<time>(?:[01]?\d|2[0-3]):[0-5]\d))?"
)


class FetchError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_url(url):
    p = urlsplit(url)
    if (
        p.scheme != "https"
        or p.hostname not in HOSTS
        or p.username
        or p.password
        or p.port not in (None, 443)
        or p.fragment
    ):
        raise ValueError("approved public HTTPS URL required")


def _read(url):
    validate_url(url)
    request = Request(url, headers={"User-Agent": "DeltaHelmTicketReview/1.0"})
    try:
        # No credentials, retry, redirect, browser challenge or proxy fallback.
        with build_opener(NoRedirect()).open(request, timeout=20) as response:
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise FetchError("response_too_large")
            charset = response.headers.get_content_charset() or "utf-8"
            return body.decode(charset, errors="strict")
    except HTTPError as exc:
        raise FetchError(
            "access_denied" if exc.code in (401, 403, 429) else "http_failed"
        ) from None
    except (URLError, TimeoutError, UnicodeError, LookupError):
        raise FetchError("transport_or_encoding_failed") from None


def fetch_public(url):
    validate_url(url)
    host = urlsplit(url).netloc
    robot_url = f"https://{host}/robots.txt"
    robots = RobotFileParser()
    # A robots failure is not permission to fetch the page.
    robots.parse(_read(robot_url).splitlines())
    if not robots.can_fetch("DeltaHelmTicketReview", url):
        raise FetchError("robots_disallowed")
    return _read(url)


class Lines(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        if tag in ("br", "p", "div", "li", "h1", "h2", "h3") and not self.skip:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.skip = max(0, self.skip - 1)
        if tag in ("p", "div", "li", "h1", "h2", "h3") and not self.skip:
            self.parts.append("\n")

    def handle_data(self, value):
        if not self.skip:
            self.parts.append(value)


def stamp(value, *, shared_year=None):
    match = STAMP.fullmatch(value.strip())
    if not match or not (match["year"] or shared_year):
        raise ValueError("ambiguous date")
    year = int(match["year"] or shared_year)
    day = date(year, int(match["month"]), int(match["day"])).isoformat()
    clock = match["time"]
    if clock:
        clock = ":".join(x.zfill(2) for x in clock.split(":"))
    return day, clock


def milestone(first, last=None):
    return dict(
        knowledge_status="observed_requires_review",
        precision="range" if last else ("time" if first[1] else "date"),
        date=first[0],
        time=first[1],
        end_date=last[0] if last else None,
        end_time=last[1] if last else None,
        timezone="Asia/Tokyo",
    )


def extract(html, route):
    parser = Lines()
    parser.feed(html)
    lines = [x.strip() for x in "".join(parser.parts).splitlines() if x.strip()]
    start, end = route["section_start"], route["section_end"]
    if lines.count(start) != 1 or lines.count(end) != 1:
        raise ValueError("ambiguous section")
    a, b = lines.index(start), lines.index(end)
    if b <= a:
        raise ValueError("invalid section order")
    scoped = lines[a + 1 : b]
    if any(re.search("中止|延期|変更|訂正|延長", line) for line in scoped):
        raise ValueError("status_or_correction_requires_review")
    out = {
        k: dict(
            knowledge_status="unverified",
            precision=None,
            date=None,
            time=None,
            end_date=None,
            end_time=None,
            timezone="Asia/Tokyo",
        )
        for k in KINDS
    }
    for label, kinds in LABELS.items():
        matches = [line for line in scoped if line.startswith(label)]
        if not matches:
            continue
        if len(matches) != 1:
            raise ValueError("multiple milestone lines")
        raw = re.sub("^" + re.escape(label) + r"\s*[：:]\s*", "", matches[0])
        values = re.split("[～〜]", raw)
        if len(values) not in (1, 2) or (len(kinds) == 2 and len(values) != 2):
            raise ValueError("ambiguous range")
        first = stamp(values[0])
        last = stamp(values[1], shared_year=first[0][:4]) if len(values) == 2 else None
        if last and (bool(first[1]) != bool(last[1]) or last < first):
            raise ValueError("invalid range or implicit year rollover")
        if len(kinds) == 2:
            out[kinds[0]], out[kinds[1]] = milestone(first), milestone(last)
        else:
            out[kinds[0]] = milestone(first, last)
    return out


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


def validate_previous(previous, now):
    def keys(value, expected):
        if not isinstance(value, dict) or set(value) != set(expected):
            raise ValueError("unexpected prior fields")

    keys(previous, ("schema_version", "checked_at_utc", "results", "observations"))
    if type(previous["schema_version"]) is not int or previous["schema_version"] != 1:
        raise ValueError("invalid prior version")
    utc(previous["checked_at_utc"])
    if previous["checked_at_utc"] > now or not isinstance(
        previous["observations"], list
    ):
        raise ValueError("invalid prior timestamp/history")
    prior_time = ""
    for observation in previous["observations"]:
        keys(
            observation, ("observed_at_utc", "facts_sha256", "page_sha256", "candidate")
        )
        utc(observation["observed_at_utc"])
        if (
            not prior_time
            <= observation["observed_at_utc"]
            <= previous["checked_at_utc"]
        ):
            raise ValueError("invalid history order")
        prior_time = observation["observed_at_utc"]
        candidate = observation["candidate"]
        keys(
            candidate,
            (
                "source_id",
                "url",
                "source_name",
                "source_class",
                "ticket_round_id",
                "event_uids",
                "milestones",
            ),
        )
        validate_url(candidate["url"])
        for key in ("source_id", "source_name", "ticket_round_id"):
            value = candidate[key]
            if not isinstance(value, str) or not value or len(value) > 500:
                raise ValueError("invalid candidate identity")
        if candidate["source_class"] not in {
            "artist_official",
            "promoter_official",
            "ticket_official",
            "venue_official",
        }:
            raise ValueError("invalid source class")
        if (
            not isinstance(candidate["event_uids"], list)
            or not candidate["event_uids"]
            or any(
                not isinstance(x, str) or len(x) > 100 for x in candidate["event_uids"]
            )
        ):
            raise ValueError("invalid event links")
        keys(candidate["milestones"], KINDS)
        for m in candidate["milestones"].values():
            keys(
                m,
                (
                    "knowledge_status",
                    "precision",
                    "date",
                    "time",
                    "end_date",
                    "end_time",
                    "timezone",
                ),
            )
            if m["timezone"] != "Asia/Tokyo":
                raise ValueError("invalid timezone")
            if m["knowledge_status"] == "unverified":
                if any(
                    m[k] is not None
                    for k in ("precision", "date", "time", "end_date", "end_time")
                ):
                    raise ValueError("unknown date populated")
            elif m["knowledge_status"] == "observed_requires_review":
                date.fromisoformat(m["date"])
                if m["precision"] not in {"date", "time", "range"}:
                    raise ValueError("invalid precision")
                for k in ("time", "end_time"):
                    if m[k] is not None and not re.fullmatch(
                        r"(?:[01]\d|2[0-3]):[0-5]\d", m[k]
                    ):
                        raise ValueError("invalid clock")
                if m["end_date"] is not None:
                    date.fromisoformat(m["end_date"])
            else:
                raise ValueError("invalid knowledge status")
        if observation["facts_sha256"] != digest(candidate) or not re.fullmatch(
            "[a-f0-9]{64}", observation["page_sha256"]
        ):
            raise ValueError("invalid prior hash")


def collect(routes, event_uids, now, *, previous=None, fetch=fetch_public):
    utc(now)
    if previous:
        validate_previous(previous, now)
    observations = deepcopy(previous["observations"]) if previous else []
    results, blocked_hosts = [], set()
    for route in routes:
        validate_url(route["url"])
        sid, host = route["source_id"], urlsplit(route["url"]).hostname
        result = dict(source_id=sid, status="pending")
        results.append(result)
        if not route["event_uids"] or not set(route["event_uids"]) <= event_uids:
            result["status"] = "unresolved_events"
            continue
        if host in blocked_hosts:
            result["status"] = "not_attempted_after_access_denial"
            continue
        try:
            html = fetch(route["url"])
            facts = extract(html, route)
        except FetchError as exc:
            result["status"] = str(exc)
            if str(exc) in ("access_denied", "robots_disallowed"):
                blocked_hosts.add(host)
            continue
        except ValueError:
            result["status"] = "parse_or_status_requires_review"
            continue
        if all(x["knowledge_status"] == "unverified" for x in facts.values()):
            result["status"] = "empty_unverified"
            continue
        candidate = dict(
            source_id=sid,
            url=route["url"],
            source_name=route["name"],
            source_class=route["source_class"],
            ticket_round_id=route["ticket_round_id"],
            event_uids=sorted(route["event_uids"]),
            milestones=facts,
        )
        page_hash = hashlib.sha256(html.encode()).hexdigest()
        fact_hash = digest(candidate)
        old = next(
            (x for x in reversed(observations) if x["candidate"]["source_id"] == sid),
            None,
        )
        result["status"] = (
            "unchanged_requires_review"
            if old and old["facts_sha256"] == fact_hash
            else "changed_requires_review"
            if old
            else "new_requires_review"
        )
        if old and old["facts_sha256"] == fact_hash and old["page_sha256"] != page_hash:
            result["status"] = "page_changed_requires_review"
        visible = Lines()
        visible.feed(html)
        if re.search("中止|延期|変更|訂正|延長", "".join(visible.parts)):
            result["status"] = "status_or_applicability_requires_review"
        result["facts_sha256"] = fact_hash
        if (
            not old
            or old["facts_sha256"] != fact_hash
            or old["page_sha256"] != page_hash
        ):
            observations.append(
                dict(
                    observed_at_utc=now,
                    facts_sha256=fact_hash,
                    page_sha256=page_hash,
                    candidate=candidate,
                )
            )
    return dict(
        schema_version=1, checked_at_utc=now, results=results, observations=observations
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sources", type=Path, required=True)
    p.add_argument("--events", type=Path, required=True)
    p.add_argument("--previous", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--checked-at-utc", required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.absolute()
    if (
        output.exists()
        or root == output
        or root in output.parents
        or ".." in output.parts
        or any(x.is_symlink() for x in (output, *output.parents))
    ):
        p.error("output must be a new file outside the checkout and symlink paths")
    events = json.loads(args.events.read_text())["events"]
    result = collect(
        json.loads(args.sources.read_text()),
        {x["event_key"] for x in events},
        args.checked_at_utc,
        previous=json.loads(args.previous.read_text()) if args.previous else None,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    # Only counts/status codes in logs, not article text or personal ticket data.
    print(
        json.dumps(
            [
                dict(source_id=x["source_id"], status=x["status"])
                for x in result["results"]
            ]
        )
    )


if __name__ == "__main__":
    main()
