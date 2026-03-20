# OSINT Pipeline - Quick Start Guide (After API Fixes)

## 🚀 Getting Started in 5 Minutes

This guide shows you how to run the fixed OSINT pipeline immediately.

---

## Step 1: Set Up Environment Variables

Create or update your `.env` file with required API keys:

```bash
# .env file (in project root directory)
SERPER_API_KEY=your_serper_api_key_here
SCRAPEANT_API_KEY=your_scrapingant_api_key_here
LEAK_LOOKUP_API_KEY=your_leak_lookup_api_key_here  # Optional but recommended
```

**Get API Keys:**
- **Serper.dev**: Sign up at https://serper.dev (free tier available)
- **ScrapingAnt**: Sign up at https://www.scrapingant.com (v2 API)
- **Leak-Lookup**: Sign up at https://leak-lookup.com (optional for breach checking)

---

## Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

**Required Packages:**
- `aiohttp>=3.8.0`
- `python-dotenv>=1.0.0`
- `jinja2>=3.1.0`
- `reportlab>=4.0.0`

---

## Step 3: Run Basic Investigation

```bash
python main.py "john.doe@example.com" --target-type person -v
```

**Expected Output:**
```
Starting OSINT investigation for: john.doe@example.com (Type: person)
✓ RECON: Generated 3 search queries
✓ HARVESTING: Processed h_recon_abc123_0, found 5 search results
✓ ANALYST: Processed h_recon_abc123_0, found 2 high-confidence facts
   - Cross-Reference: Found in 2 breach databases (+0.6 confidence boost)
✓ SCRIBE: Generated PDF report at ./OSINT_WORKSPACE/data/reports/osint_person.pdf

==============================================================
PIPELINE EXECUTION COMPLETE
==============================================================
Total Processed: 1
Successful: 1
Failed: 0
Execution Time: 12.34s

📄 Report generated at: /path/to/report.pdf
```

---

## Step 4: Verify the Fixes

Run the test suite to confirm all fixes are working:

```bash
python test_api_fixes.py -v
```

**Expected Output:**
```
✅ PASS - serper_api_integration (Single JSON parse, proper headers)
✅ PASS - scrapingant_v2_api (Correct endpoint and parameters)
✅ PASS - data_extraction_type_safety (No AttributeError crashes)
✅ PASS - cross_reference_with_leak_lookup (Confidence boost working)
✅ PASS - confidence_scoring_with_leak_boost (+0.3 boost applied)

Overall: 5/5 tests passed (100%)
```

---

## Quick Commands Reference

### Basic Investigations

**Person Search:**
```bash
python main.py "john.doe@example.com" --target-type person -v
```

**Company Research:**
```bash
python main.py "example.com" --target-type company -v
```

**Domain Investigation:**
```bash
python main.py "example.org" --target-type domain -v
```

**Product Intelligence:**
```bash
python main.py "product name" --target-type product -v
```

### With Leak-Lookup (Recommended)

Make sure `LEAK_LOOKUP_API_KEY` is set in `.env`:

```bash
python main.py "john.doe@example.com" --target-type person -v
```

**You'll see cross-reference boosts:**
```
✓ ANALYST: Processed h_recon_abc123_0, found 2 high-confidence facts
   - Cross-Reference: Found in 2 breach databases (+0.6 confidence boost)
```

---

## Troubleshooting Quick Fixes

### Issue: "Missing required API keys"
**Solution:** Add to `.env`:
```bash
SERPER_API_KEY=your_key_here
SCRAPEANT_API_KEY=your_scrapingant_key_here
LEAK_LOOKUP_API_KEY=your_leak_lookup_key_here  # Optional
```

### Issue: PDF reports are empty (2KB)
**Solution:** Run extraction test:
```bash
python test_api_fixes.py --test extraction
# Should show: ✅ PASS - data_extraction_type_safety
```

### Issue: Cross-references not found
**Solution:** Verify Leak-Lookup API key is valid:
```bash
python -c "from osint_connector.leak_lookup import search_leak_lookup; print(search_leak_lookup('test@example.com', 'YOUR_KEY'))"
```

---

## What's New? (After Fixes)

### ✅ Serper.dev Integration Fixed
- Single JSON parsing (no double-parse errors)
- Proper `X-API-KEY` header configuration
- Response structure validation

### ✅ ScrapingAnt v2 Integration Fixed  
- Correct endpoint: `/v2/text`
- API key passed as query parameter
- Proper URL encoding and error handling

### ✅ Type-Safe Data Extraction
- No more `AttributeError` crashes
- Handles dict, list, string, None inputs gracefully
- Comprehensive logging of extraction issues

### ✅ Leak-Lookup Cross-Reference Integration (NEW!)
- Matches search results with breach database findings
- Gmail dot normalization (john.doe@gmail.com == johndoe@gmail.com)
- Confidence boost of +0.3 per matching breach database found

### ✅ Complete Data Flow Between Stages
- `harvest_results` stored as parsed JSON dict (not string)
- Analyst stage receives properly typed data for 'organic' extraction
- Scribe stage gets flattened list of facts for PDF population

---

## Report Output

After a successful run, you'll find reports in:
```
./OSINT_WORKSPACE/data/reports/
├── osint_person_20241217_123456.pdf  (PDF report)
└── osint_person_20241217_123456.html (HTML report)
```

**Report Contents:**
- ✅ Full investigation summary
- ✅ Verified facts with confidence scores
- ✅ Cross-reference information (if Leak-Lookup used)
- ✅ Evidence trail and sources
- ✅ MythWorx branding included

---

## Advanced Usage

### Custom Concurrency Limits

Modify `osint_kanban_manager.py` to adjust WIP limits:

```python
# In _process_harvesting method
max_concurrent = 10  # Increase for faster processing
```

### Enable Verbose Logging

Add `-v` flag for detailed output:

```bash
python main.py "john.doe@example.com" -v
```

### Run Specific Stage Tests

Test individual components:

```bash
# Test Serper API only
python test_api_fixes.py --test serper

# Test ScrapingAnt v2 only
python test_api_fixes.py --test scrapingant

# Test data extraction only
python test_api_fixes.py --test extraction
```

---

## Performance Tips

1. **Use Leak-Lookup**: Adds valuable breach intelligence with minimal overhead
2. **Set appropriate WIP limits**: Balance speed vs API rate limits
3. **Monitor execution time**: Typical investigation takes 10-20 seconds
4. **Check API quotas**: Free tiers have limited requests per day

---

## Next Steps

After running successfully:

1. ✅ Review the generated PDF report in `./OSINT_WORKSPACE/data/reports/`
2. ✅ Check cross-reference information for enhanced intelligence
3. ✅ Adjust confidence thresholds if needed (default: 0.4)
4. ✅ Explore the detailed documentation in `API_FIXES_SUMMARY.md`

---

## Support Resources

- **Detailed Fix Documentation**: `API_FIXES_SUMMARY.md`
- **Key Methods Reference**: `KEY_METHODS_REFERENCE.md`
- **Complete Implementation Summary**: `FIXES_IMPLEMENTATION_SUMMARY.md`
- **Automated Test Suite**: `test_api_fixes.py`

---

## Status: ✅ READY TO USE

All critical API integration issues have been resolved. The pipeline is production-ready with:

- ✅ Reliable Serper.dev and ScrapingAnt v2 integrations
- ✅ Type-safe data extraction (no crashes)
- ✅ Leak-Lookup cross-referencing with confidence boosts
- ✅ Complete PDF reports populated with verified facts
- ✅ Comprehensive error handling and logging

**You're all set to start investigating!** 🎉

---

**Quick Command:**
```bash
python main.py "target@example.com" --target-type person -v
```

Happy OSINT hunting! 🔍
