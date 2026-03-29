import asyncio, aiohttp, xml.etree.ElementTree as ET, os

# ---------- configuration ----------
BASE_URL   = "https://api.publicdata.com"
SEARCH_ENDPOINT = "/pdsearchdocs.php"

# BUGFIX: credentials must never be hard-coded in source. Load from environment
# variables (set in .env or the shell) so they are not committed to version control.
USERNAME    = os.getenv("PUBLICDATA_USERNAME", "")
PASSWORD    = os.getenv("PUBLICDATA_PASSWORD", "")
DATABASE_ID = int(os.getenv("PUBLICDATA_DATABASE_ID", "1"))
QUERY_TERM  = os.getenv("PUBLICDATA_QUERY_TERM", "Braden Leeds")

MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 2

# ---------- helper functions ----------
async def authenticate(session):
    """Return a bearer token (simple implementation)"""
    auth_url = f"{BASE_URL}/authenticate.php"
    data = {"username": USERNAME, "password": PASSWORD}
    try:
        # BUGFIX: aiohttp requires ClientTimeout, not a bare int; bare int raises ValueError.
        async with session.post(auth_url, data=data, timeout=aiohttp.ClientTimeout(total=30)) as resp:
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
    page_count = 0
    
    print(f"[DEBUG] Starting search for '{QUERY_TERM}'")
    
    while True:
        page_count += 1
        # BUGFIX: same as authenticate — must use ClientTimeout, not bare int.
        async with session.get(url, params=params, headers=headers,
                               timeout=aiohttp.ClientTimeout(total=30)) as resp:
            raw = await resp.text()

            # ---- sanity check ----
            if not raw.lstrip().startswith("<"):
                print(f"[ERROR] Page {page_count}: Received non‑XML response (status {resp.status})")
                print(f"Response preview: {raw[:200]}")
                break

            try:
                tree = ET.fromstring(raw)
            except ET.ParseError as e:
                print(f"[ERROR] Page {page_count}: XML parse error: {e}")
                print(f"Raw content: {raw[:500]}")
                break

            records = tree.findall(".//record")
            page_record_count = len(records)
            
            if not records:
                print(f"[INFO] Page {page_count}: No more records found, stopping pagination")
                # no more data
                break

            print(f"[DEBUG] Page {page_count}: Retrieved {page_record_count} records")
            
            for r in records:
                title   = r.findtext("title", "")
                link    = r.findtext("link", "")
                snippet = r.findtext("snippet", "")
                
                # Validate required fields
                if not title and not link:
                    print(f"[WARNING] Skipping malformed record")
                    continue
                    
                all_records.append({"title": title, "link": link,
                                   "snippet": snippet})

            # ----- pagination -----
            next_rec = tree.findtext(".//next_record")
            if next_rec is None:
                print("[INFO] No 'next_record' element found, stopping pagination")
                break
            params["rec"] = int(next_rec)
            
            # Safety limit to prevent infinite loops
            if page_count > 10:
                print("[WARNING] Reached maximum page count (10), stopping pagination")
                break

    print(f"[INFO] Search complete. Total records retrieved: {len(all_records)}")
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
