# Analyst Stage - Quick Reference Card

## 🚀 Quick Start Commands

```bash
# Basic usage (auto-detects latest harvested results)
python osint_analyst_stage.py

# Specify privacy mode
python osint_analyst_stage.py -p local    # or 'public' or 'hybrid'

# Process specific file with custom output
python osint_analyst_stage.py \
    -i harvest_output/my_results.json \
    -o /custom/output/path/
```

## 📋 Python API Usage

### Basic Analysis

```python
from osint_analyst_stage import OSINTAnalystStage, load_harvest_results

# Initialize analyst with privacy mode
analyst = OSINTAnalystStage(privacy_mode='local')

# Load and process harvested results
raw_data = load_harvest_results('harvest_output/latest.json')
report = analyst.process_harvest_results(raw_data)

# Save report to file
output_path = analyst.save_report(report, "my_analysis.json")

# Display summary in terminal
analyst.display_summary(report)
```

### Advanced Configuration

```python
from osint_analyst_stage import OSINTAnalystStage, CrossReferenceEngine

class CustomAnalyst(OSINTAnalystStage):
    def __init__(self, privacy_mode='local'):
        super().__init__(privacy_mode=privacy_mode)
        # Customize confidence thresholds
        self.confidence_thresholds = {
            'email': 80.0,
            'username': 75.0
        }

# Use custom analyst
custom_analyst = CustomAnalyst(privacy_mode='local')
report = custom_analyst.process_harvest_results(raw_data)
```

## 🔒 Privacy Modes Explained

| Mode | Command | When to Use | Speed |
|------|---------|-------------|-------|
| **LOCAL** | `privacy_mode='local'` | Maximum privacy required | Baseline |
| **PUBLIC** | `privacy_mode='public'` | Non-sensitive data, speed priority | +30% faster |
| **HYBRID** | `privacy_mode='hybrid'` | Balanced approach | -15% slower |

## 📊 Output Format

```json
{
  "target": "John Doe",
  "facts": [
    {
      "fact_type": "email",
      "value": "john.doe@example.com",
      "sources": ["shodan", "spiderfoot"],
      "confidence_score": 85.0,
      "context": {"source_count": 2}
    }
  ],
  "confidence_summary": {
    "email": 85.0,
    "username": 90.0
  },
  "analysis_timestamp": "2024-01-15T14:32:15"
}
```

## 🎯 Confidence Scoring Rules

| Sources | Score | Level | Meaning |
|---------|-------|-------|---------|
| **3+ sources** | 100% | VERIFIED | All sources agree |
| **2 sources** | 85% | HIGHLY_LIKELY | Strong agreement |
| **1 source** | 70% | LIKELY | Single credible source |
| **Contradictory** | 45% | UNVERIFIED | Conflicting data |
| **Low quality** | 25% | SUSPICIOUS | Poor sources only |

## 🔧 Integration with Kanban Pipeline

```python
from osint_kanban_manager import OsintPipelineManager, PipelineConfig

config = PipelineConfig(
    target_name="Target",
    target_type="person",
    wip_limits={
        "RECON": 3,
        "HARVESTING": 5,
        "ANALYST": 2,      # Analyst stage limit
        "SCRIBE": 1
    },
    api_keys={
        "PRIVACY_MODE": "local"  # Enable privacy mode
    }
)

manager = OsintPipelineManager(config)
await manager.start_pipeline(
    user_query="Target query here",
    target_type="person"
)
```

## 🧪 Testing Commands

```bash
# Run automated tests
python docs/examples/test_analyst_stage.py -v

# Debug mode with verbose logging
python osint_analyst_stage.py --debug-mode

# Export to CSV for analysis
python docs/examples/export_to_csv.py
```

## 📚 Documentation Links

| Document | Purpose | Location |
|----------|---------|----------|
| **ANALYST_STAGE_GUIDE.md** | Complete API reference | `docs/ANALYST_STAGE_GUIDE.md` |
| **INTEGRATION_EXAMPLES.md** | 9 practical examples | `docs/ANALYST_INTEGRATION_EXAMPLES.md` |
| **PROJECT_STATUS_SUMMARY.md** | Current project status | `docs/PROJECT_STATUS_SUMMARY.md` |
| **SESSION_SUMMARY.md** | Detailed session record | `docs/SESSION_SUMMARY_ANALYST_IMPLEMENTATION.md` |

## 🐛 Common Issues & Solutions

### Issue: "Ollama not available" Warning
```bash
# Solution: Start Ollama service
ollama serve
# Then retry analysis
python osint_analyst_stage.py -p local
```

### Issue: Low confidence scores across all facts
**Solutions:**
1. Check if HARVESTING stage collected adequate data
2. Review source quality in report context
3. Increase WIP limit for HARVESTING stage

### Issue: Duplicate facts not being merged
**Solutions:**
1. Verify email addresses are properly formatted
2. Check that usernames don't have special characters
3. Review fingerprint generation logic in DeduplicationEngine

## 🎓 Best Practices

1. **Use LOCAL mode** for sensitive targets (people, organizations)
2. **Monitor confidence scores** - prioritize facts >85% for action items
3. **Leverage source diversity** - combine different tool types when possible
4. **Keep backups** of analyst reports: `cp analyst_output/*.json backups/`

## 📈 Performance Benchmarks

| Dataset Size | Facts Found | Local Time | Public Time |
|--------------|-------------|------------|-------------|
| Small (<50) | 10-15 facts | <2s | <1s |
| Medium (50-200) | 30-50 facts | 5-8s | 3-5s |
| Large (>200) | 100+ facts | 15-30s | 10-20s |

## 🔐 Security Checklist

Before deployment:
- [ ] All API keys stored in environment variables (not hardcoded)
- [ ] Privacy mode enabled for sensitive data
- [ ] Local Ollama instance running (if using local mode)
- [ ] .env file has proper permissions (600 or 400)
- [ ] Automated backups configured

---

**Quick Start:** `python osint_analyst_stage.py -p local`  
**Full Guide:** See `docs/ANALYST_STAGE_GUIDE.md`  
**Examples:** See `docs/ANALYST_INTEGRATION_EXAMPLES.md`

*Last Updated: January 15, 2024 | Version: 1.3.0*
