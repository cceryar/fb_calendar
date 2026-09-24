#!/usr/bin/env python3
"""Builds fenerbahce.ics (all Fenerbahçe football matches) for Apple Calendar.

Sources, merged in this order of trust:
  1. Transfermarkt fixtures page (all competitions)
  2. ESPN public API          - fills in matches Transfermarkt doesn't have
  3. Sofascore public API     - fills in anything still missing
A match from a lower source is only added if no higher source already has a
game against the same opponent within 4 days.

Rule: if a kick-off time is not announced yet (TBA), the match is put on the
Saturday of that weekend at 19:00 (Hamburg time) and marked "(TBA)".
If nothing usable is fetched, the old calendar file is left untouched.
"""
import datetime as dt
import hashlib
import re
import sys
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

try:  # pretends to be a real Chrome browser, which many sports sites require
    from curl_cffi import requests as _http
    _EXTRA = {"impersonate": "chrome"}
except ImportError:
    import requests as _http
    _EXTRA = {}

# ---------------- settings you can change ----------------
TEAM = "Fenerbahçe"
TM_URL = "https://www.transfermarkt.com.tr/fenerbahce-sk/spielplan/verein/36"
TM_TZ = ZoneInfo("Europe/Istanbul")      # time zone the .com.tr site shows kick-offs in
TBA_TZ = ZoneInfo("Europe/Berlin")       # TBA placeholder time zone (your calendar)
TBA_TIME = dt.time(19, 0)                # TBA placeholder: Saturday 19:00
DURATION = dt.timedelta(hours=2)
ALERT_MINUTES = 30                       # set to 0 for no reminder
OUT_FILE = "fenerbahce.ics"
ESPN_TEAM_ID = "436"
SOFASCORE_TEAM_ID = 3052
SOFA_TBA_DAYS = 14   # Sofascore has no "time not confirmed" flag: its Süper Lig times
                     # further away than this are treated as TBA (TFF sets times ~2 weeks ahead)
ESPN_LEAGUES = ["tur.1", "tur.cup", "uefa.champions", "uefa.europa", "uefa.europa.conf"]
# ----------------------------------------------------------

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}
HOME_MARKS = {"H", "E", "İ", "I", "EV", "HOME"}
AWAY_MARKS = {"A", "D", "DEP", "AWAY"}


def fetch(url, want_json=False):
    """Download a page; print what went wrong so failures are visible in the log."""
    h = dict(HEADERS)
    if want_json:
        h["Accept"] = "application/json"
    try:
        r = _http.get(url, headers=h, timeout=30, **_EXTRA)
    except Exception as ex:
        print(f"  ! {url} -> connection error: {ex}")
        return None
    if r.status_code != 200:
        print(f"  ! {url} -> HTTP {r.status_code}: {r.text[:150]!r}")
        return None
    if want_json:
        try:
            return r.json()
        except Exception:
            print(f"  ! {url} -> not JSON: {r.text[:150]!r}")
            return None
    return r.text


def parse_date(s):
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})", s)          # 22.08.2026
    if m:
        d, mo, y = map(int, m.groups())
    else:
        m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", s)        # 8/22/26 (.com)
        if not m:
            return None
        mo, d, y = map(int, m.groups())
    if y < 100:
        y += 2000
    try:
        return dt.date(y, mo, d)
    except ValueError:
        return None


def parse_time(s):
    m = re.search(r"(\d{1,2}):(\d{2})\s*([AaPp][Mm])?", s)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if m.group(3):
        h = h % 12 + (12 if m.group(3).lower() == "pm" else 0)
    return dt.time(h, mi)


def weekend_saturday(d):
    """Fri/Sat/Sun/Mon -> Saturday of that weekend; midweek dates stay as they are."""
    shift = {4: 1, 5: 0, 6: -1, 0: -2}.get(d.weekday())
    return d + dt.timedelta(days=shift) if shift is not None else d


# ---------------- Transfermarkt ----------------
def from_transfermarkt():
    html = fetch(TM_URL)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else "?"
    print(f"  Transfermarkt page: {title!r}, {len(soup.select('div.box'))} boxes, "
          f"{len(soup.select('table'))} tables")
    matches = []
    for box in soup.select("div.box"):
        head = box.select_one("h2")
        table = box.select_one("table")
        if not head or not table:
            continue
        comp = " ".join(head.get_text(" ", strip=True).split())
        for tr in table.select("tbody tr"):
            tds = tr.find_all("td")
            texts = [td.get_text(" ", strip=True) for td in tds]
            di = next((i for i, t in enumerate(texts) if parse_date(t)), None)
            if di is None:
                continue
            date = parse_date(texts[di])
            time = parse_time(texts[di + 1]) if di + 1 < len(texts) else None
            venue = texts[di + 2].strip().upper() if di + 2 < len(texts) else ""
            rnd = texts[0] if di > 0 else ""
            opp = None
            for a in tr.select("a[href*='/verein/']"):
                name = a.get("title") or a.get_text(strip=True)
                if name:
                    opp = name
            if not opp:
                continue
            result, mid = "", None
            link = tr.select_one("a[href*='spielbericht']")
            if link:
                result = link.get_text(strip=True)
                m = re.search(r"spielbericht/(\d+)", link["href"])
                mid = m.group(1) if m else None
            if not re.search(r"\d+\s*:\s*\d+", result):
                result = ""
            if venue in HOME_MARKS:
                home, away = TEAM, opp
            elif venue in AWAY_MARKS:
                home, away = opp, TEAM
            else:
                home, away = TEAM, opp
            uid = mid or hashlib.md5(f"{comp}|{rnd}|{opp}|{venue}".encode()).hexdigest()[:12]
            start = dt.datetime.combine(date, time, TM_TZ) if time else None
            matches.append(dict(uid=f"tm-{uid}", comp=comp, rnd=rnd, date=date, start=start,
                                home=home, away=away, venue="", result=result))
    return matches


# ---------------- ESPN (fallback) ----------------
def from_espn():
    seen = {}
    for lg in ESPN_LEAGUES:
        for fixture in ("true", "false"):
            url = (f"https://site.api.espn.com/apis/site/v2/sports/soccer/{lg}"
                   f"/teams/{ESPN_TEAM_ID}/schedule?fixture={fixture}")
            data = fetch(url, want_json=True)
            if not data:
                continue
            for ev in data.get("events", []):
                c = (ev.get("competitions") or [{}])[0]
                teams = {x.get("homeAway"): x for x in c.get("competitors", [])}
                if "home" not in teams or "away" not in teams:
                    continue
                name = lambda x: x["team"].get("displayName", "?")
                home, away = name(teams["home"]), name(teams["away"])
                home = TEAM if "Fenerbah" in home else home
                away = TEAM if "Fenerbah" in away else away
                when = dt.datetime.fromisoformat(ev["date"].replace("Z", "+00:00"))
                valid = c.get("timeValid", True)
                result = ""
                if c.get("status", {}).get("type", {}).get("completed"):
                    sc = lambda x: (x.get("score") or {}).get("displayValue", x.get("score", ""))
                    result = f"{sc(teams['home'])}:{sc(teams['away'])}"
                seen[ev["id"]] = dict(
                    uid=f"espn-{ev['id']}", comp=(data.get("season") or {}).get("displayName", lg),
                    rnd="", date=when.astimezone(TM_TZ).date(), start=when if valid else None,
                    home=home, away=away, venue=(c.get("venue") or {}).get("fullName", ""),
                    result=result)
    return list(seen.values())


# ---------------- Sofascore ----------------
def from_sofascore():
    out, now = {}, dt.datetime.now(dt.timezone.utc)
    for path in ("next/0", "next/1", "last/0"):
        url = f"https://api.sofascore.com/api/v1/team/{SOFASCORE_TEAM_ID}/events/{path}"
        data = fetch(url, want_json=True)
        if not data:
            continue
        for ev in data.get("events", []):
            when = dt.datetime.fromtimestamp(ev["startTimestamp"], dt.timezone.utc)
            comp = (ev.get("tournament") or {}).get("name", "")
            home = ev["homeTeam"]["name"]
            away = ev["awayTeam"]["name"]
            home = TEAM if "Fenerbah" in home else home
            away = TEAM if "Fenerbah" in away else away
            result = ""
            if (ev.get("status") or {}).get("type") == "finished":
                result = f"{ev['homeScore'].get('current', '')}:{ev['awayScore'].get('current', '')}"
            league = "lig" in comp.lower() and "uefa" not in comp.lower()
            tba = league and not result and (when - now).days > SOFA_TBA_DAYS
            out[ev["id"]] = dict(
                uid=f"sofa-{ev['id']}", comp=comp,
                rnd=str((ev.get("roundInfo") or {}).get("round", "")),
                date=when.astimezone(TM_TZ).date(), start=None if tba else when,
                home=home, away=away, venue="", result=result)
    return list(out.values())


# ---------------- merging ----------------
def _tokens(name):
    t = name.lower().translate(str.maketrans("çğıöşüâîİ", "cgiosuaii"))
    return {w for w in re.split(r"[^a-z0-9]+", t) if len(w) >= 4}


def _opponent(m):
    return m["away"] if m["home"] == TEAM else m["home"]


def same_match(a, b):
    if abs((a["date"] - b["date"]).days) > 4:
        return False
    ta, tb = _tokens(_opponent(a)), _tokens(_opponent(b))
    return bool(ta & tb) or any(x in y or y in x for x in ta for y in tb)


def merge(*sources):
    merged = []
    for src in sources:
        for m in src:
            if not any(same_match(m, k) for k in merged):
                merged.append(m)
    return merged


# ---------------- ICS ----------------
def esc(s):
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line):
    b, out = line.encode(), []
    while len(b) > 74:
        i = 74
        while (b[i] & 0xC0) == 0x80:
            i -= 1
        out.append(b[:i].decode())
        b = b[i:]
    out.append(b.decode())
    return "\r\n ".join(out)


def build_ics(matches):
    utc = dt.timezone.utc
    L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//fenerbahce-calendar//EN",
         "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:Fenerbahçe ⚽",
         "X-WR-TIMEZONE:Europe/Berlin", "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
         "X-PUBLISHED-TTL:PT6H"]
    for m in sorted(matches, key=lambda m: (m["date"], m["uid"])):
        tba = m["start"] is None
        start = (dt.datetime.combine(weekend_saturday(m["date"]), TBA_TIME, TBA_TZ)
                 if tba else m["start"])
        s, e = start.astimezone(utc), (start + DURATION).astimezone(utc)
        title = f"⚽ {m['home']} – {m['away']}"
        if m["result"]:
            title += f" ({m['result']})"
        if tba:
            title += " (TBA)"
        desc = m["comp"] + (f" – {m['rnd']}" if m["rnd"] and not m["rnd"].isdigit()
                            else f" – Round {m['rnd']}" if m["rnd"] else "")
        if tba:
            desc += f"\nKick-off not announced yet (listed for {m['date']:%d.%m.%Y}). Placeholder: Saturday 19:00."
        desc += f"\nSource: {m['src']}"
        L += ["BEGIN:VEVENT", f"UID:{m['uid']}@fenerbahce-calendar",
              "DTSTAMP:20260901T000000Z",
              f"DTSTART:{s:%Y%m%dT%H%M%SZ}", f"DTEND:{e:%Y%m%dT%H%M%SZ}",
              fold("SUMMARY:" + esc(title)), fold("DESCRIPTION:" + esc(desc))]
        if m["venue"]:
            L.append(fold("LOCATION:" + esc(m["venue"])))
        if ALERT_MINUTES and not m["result"]:
            L += ["BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:Match soon",
                  f"TRIGGER:-PT{ALERT_MINUTES}M", "END:VALARM"]
        L.append("END:VEVENT")
    L.append("END:VCALENDAR")
    return "\r\n".join(L) + "\r\n"


def main():
    results = {}
    for name, fn in (("Transfermarkt", from_transfermarkt), ("ESPN", from_espn),
                     ("Sofascore", from_sofascore)):
        try:
            results[name] = fn()
        except Exception as ex:
            print(f"{name} failed:", ex)
            results[name] = []
        print(f"{name}: {len(results[name])} matches")
    for name, ms in results.items():
        for m in ms:
            m["src"] = name
    matches = merge(*[list({m["uid"]: m for m in ms}.values()) for ms in results.values()])
    if len(matches) < 5:
        sys.exit("Not enough matches found - keeping the old calendar.")
    with open(OUT_FILE, "w", encoding="utf-8", newline="") as f:
        f.write(build_ics(matches))
    tba = sum(m["start"] is None for m in matches)
    print(f"Wrote {len(matches)} matches ({tba} TBA).")

if __name__ == "__main__":
    main()
