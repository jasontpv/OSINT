import asyncio, aiohttp, xml.etree.ElementTree as ET, os

# ---------- configuration ----------
BASE_URL   = "https://api.publicdata.com"
SEARCH_ENDPOINT = "/pdsearchdocs.php"

USERNAME  = "MaDMaX828"
PASSWORD  = "RE98N7"
DATABASE_ID = 1          # e.g. “PublicData” database
QUERY_TERM  = "Braden Leeds"

MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 2

# ---------- helper functions ----------
async def authenticate(session):
    """Return a bearer token (simple implementation)"""
    auth_url = f"{BASE_URL}/authenticate.php"
    data = {"username": USERNAME, "password": PASSWORD}
    try:
        async with session.post(auth_url, data=data, timeout=30) as resp:
            if resp.status != 200:
                print(f"[ERROR] Authentication failed with status {resp.status}")
                return None
            text = await resp.text()
            token = text.strip()
            # Validate token is reasonable length
            if len(token) < 10:
                print(f"[WARNING] Received suspiciously short token: '{token[:20]}...'")
                return None
            print(f"[DEBUG] Authentication successful. Token length: {len(token)}")
            return token
    except Exception as e:
        print(f"[ERROR] Authentication error: {e}")
        return None

async def do_search(session, token):
    """Issue a search request and follow pagination until no more records."""
    url = f"{BASE_URL}{SEARCH_ENDPOINT}"
    params = {
        "q": QUERY_TERM,
        "database_id": DATABASE_ID,
        "rec": 0,          # start at first record
        "ed": 0            # edition number (latest)
    }
    headers = {"Authorization": f"Bearer {token}"}

    all_records = []

    while True:
        async with session.get(url, params=params, headers=headers,
                               timeout=30) as resp:
            raw = await resp.text()

            # ---- sanity check ----
            if not raw.lstrip().startswith("<"):
                print("⚠️  Received non‑XML response")
                break

            try:
                tree = ET.fromstring(raw)
            except ET.ParseError as e:
                print(f"⚠️  XML parse error: {e}")
                break

            records = tree.findall(".//record")
            if not records:
                # no more data
                break

            for r in records:
                title   = r.findtext("title", "")
                link    = r.findtext("link", "")
                snippet = r.findtext("snippet", "")
                all_records.append({"title": title, "link": link,
                                   "snippet": snippet})

            # ----- pagination -----
            next_rec = tree.findtext(".//next_record")
            if next_rec is None:
                break
            params["rec"] = int(next_rec)

    return all_records

def report(records):
    print("\n=== SEARCH RESULTS ===")
    for i, r in enumerate(records, 1):
        print(f"{i}. {r['title']}")
        print(f"   Link:   {r['link']}")
        print(f"   Snip.:  {r['snippet'][:60]}…\n")

# ---------- main ----------
async def main():
    async with aiohttp.ClientSession() as sess:
        token = await authenticate(sess)
        if not token:
            raise RuntimeError("Authentication failed")
        records = await do_search(sess, token)

        # ---- final checks ----
        assert records, "No records returned – possible pagination error"
        for r in records:
            assert r["link"], "Missing link field"

        report(records)
    print("\n✅  Full integration test PASSED")

if __name__ == "__main__":
    asyncio.run(main())
