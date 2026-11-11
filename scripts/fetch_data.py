#!/usr/bin/env python3
"""Refresh data/github.json (contribution calendar, featured repos, portrait).

With GITHUB_TOKEN set it uses the GraphQL API (accurate, includes private
contributions if the token allows). Without one it falls back to GitHub's
public contributions page plus the REST API, so it also runs on a laptop.
"""
import base64, datetime as dt, json, os, re, sys, urllib.request

USER = os.environ.get("GH_USER", "yashsrivastavv")
FEATURED = ["QRIntegrity", "plan-it", "system-design-llds"]  # repo cards, in order
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def http(url, data=None, accept=None, binary=False):
    h = {"User-Agent": "profile-cards"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    if accept:
        h["Accept"] = accept
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
    return body if binary else body.decode()


def graphql(query, **variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    out = json.loads(http("https://api.github.com/graphql", body))
    if "errors" in out:
        raise RuntimeError(out["errors"])
    return out["data"]


def calendar_graphql():
    q = """query($u:String!){user(login:$u){contributionsCollection{contributionCalendar{
      weeks{contributionDays{date contributionCount}}}}}}"""
    weeks = graphql(q, u=USER)["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    return [{"date": d["date"], "count": d["contributionCount"]}
            for w in weeks for d in w["contributionDays"]]


def calendar_scrape():
    html = http(f"https://github.com/users/{USER}/contributions")
    ids = dict(re.findall(r'data-date="([\d-]+)" id="([^"]+)"', html))
    tips = dict(re.findall(r'for="([^"]+)"[^>]*>\s*([^<]+?)\s*<', html))
    days = []
    for date, cid in sorted(ids.items()):
        m = re.match(r"(\d+|No) contribution", tips.get(cid, ""))
        days.append({"date": date, "count": 0 if not m or m.group(1) == "No" else int(m.group(1))})
    if not days:
        raise RuntimeError("could not parse contributions page")
    return days


def rest(path):
    return json.loads(http(f"https://api.github.com{path}"))


def main():
    try:
        cal = calendar_graphql() if TOKEN else calendar_scrape()
    except Exception as e:  # token without GraphQL access, etc.
        print("calendar fallback:", e, file=sys.stderr)
        cal = calendar_scrape()
    cutoff = (dt.date.today() - dt.timedelta(days=371)).isoformat()
    cal = [d for d in cal if d["date"] >= cutoff]

    user = rest(f"/users/{USER}")
    repos = []
    for name in FEATURED:
        r = rest(f"/repos/{USER}/{name}")
        repos.append({"name": r["name"], "description": r["description"] or "",
                      "language": r["language"] or "", "stars": r["stargazers_count"],
                      "forks": r["forks_count"], "url": r["html_url"], "pushed": r["pushed_at"][:10]})

    portrait = None
    try:
        portrait = "data:image/jpeg;base64," + base64.b64encode(
            http(user["avatar_url"] + "&s=240", binary=True)).decode()
    except Exception as e:
        print("no portrait:", e, file=sys.stderr)

    out = {"user": USER, "name": user.get("name") or USER, "generated": dt.date.today().isoformat(),
           "portrait": portrait, "calendar": cal, "repos": repos}
    path = os.path.join(ROOT, "data", "github.json")
    with open(path, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"wrote {path}: {len(cal)} days, {sum(d['count'] for d in cal)} contributions, {len(repos)} repos")


if __name__ == "__main__":
    main()
