# Analyst Stage Integration Examples

Complete examples for integrating the OSINT Intelligence Analyst stage into your workflow.

---

## 🚀 Quick Start: Single Investigation

### Example 1: Analyze a Person Target with Local Privacy

```python
#!/usr/bin/env python3
"""
Example: Run complete pipeline analysis on a person target
Uses local Ollama for privacy-preserving bio analysis
"""

import os
from datetime import datetime
import asyncio

# Import analyst components
from osint_analyst_stage import OSINTAnalystStage, load_harvest_results

async def main():
    print("🔍 Starting Analyst Stage Analysis")
    
    # Load harvested results from previous stage
    harvest_file = 'harvest_output/harvest_result_20240115.json'
    
    if not os.path.exists(harvest_file):
        print(f"❌ No harvested results found at {harvest_file}")
        return
    
    raw_data = load_harvest_results(harvest_file)
    
    # Initialize analyst with privacy mode
    analyst = OSINTAnalystStage(privacy_mode='local')
    
    # Process through analysis pipeline
    print("\n📊 Processing analysis...")
    report = analyst.process_harvest_results(raw_data)
    
    # Save to file with custom name
    output_path = analyst.save_report(report, f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    
    # Display summary in terminal
    analyst.display_summary(report)
    
    print(f"\n✅ Analysis complete! Report saved to: {output_path}")

if __name__ == '__main__':
    asyncio.run(main())
```

**Run this example:**
```bash
python docs/examples/analyst_single_investigation.py
```

---

## 🔄 Integration with Kanban Pipeline

### Example 2: Full Pipeline Orchestration

```python
#!/usr/bin/env python3
"""
Example: Run complete OSINT pipeline with analyst stage integration
Demonstrates pull-based workflow with privacy mode enabled
"""

import os
from datetime import datetime
import asyncio

from osint_kanban_manager import OsintPipelineManager, PipelineConfig
from dotenv import load_dotenv

async def main():
    # Load environment variables (API keys)
    load_dotenv()
    
    print("🚀 Starting Complete OSINT Pipeline")
    print("="*60)
    
    # Configure pipeline with privacy mode enabled
    config = PipelineConfig(
        target_name="John Doe",
        target_type="person",
        wip_limits={
            "RECON": 3,
            "HARVESTING": 5,
            "ANALYST": 2,      # Analyst stage WIP limit
            "SCRIBE": 1
        },
        api_keys={
            "SERPER_API_KEY": os.environ.get("SERPER_API_KEY"),
            "SCRAPINGANT_API_KEY": os.environ.get("SCRAPINGANT_API_KEY"),
            "PRIVACY_MODE": "local"  # Enable privacy mode for analyst
        }
    )
    
    # Initialize pipeline manager
    manager = OsintPipelineManager(config)
    
    try:
        # Start the pipeline with a new investigation
        await manager.start_pipeline(
            user_query="John Doe, Apple Inc software engineer",
            target_type="person"
        )
        
        print("\n✅ Pipeline completed successfully!")
        
        # Results are available in manager.results
        result = manager.results
        
        print(f"\n📊 Execution Summary:")
        print(f"   Total processed: {result.total_processed}")
        print(f"   Successful: {result.successful}")
        print(f"   Failed retryable: {result.failed_retryable}")
        print(f"   Total time: {result.total_execution_time_seconds:.1f}s")
        
    except KeyboardInterrupt:
        print("\n⚠️ Pipeline interrupted by user")
    except Exception as e:
        print(f"\n❌ Pipeline error: {e}")

if __name__ == '__main__':
    asyncio.run(main())
```

**Requirements:**
- Set your API keys in `.env` file or environment variables
- Ensure Ollama is running for local privacy mode: `ollama serve`

**Run this example:**
```bash
python docs/examples/analyst_full_pipeline.py
```

---

## 🔒 Privacy-Focused Analysis

### Example 3: Maximum Privacy Mode (No Cloud LLMs)

```python
#!/usr/bin/env python3
"""
Example: Run analyst with maximum privacy settings
Uses only local Ollama, no cloud APIs for sensitive analysis
"""

from osint_analyst_stage import OSINTAnalystStage

def run_privacy_mode_analysis():
    """Run complete analysis in strict privacy mode"""
    
    print("🔒 Starting Privacy-Focused Analysis")
    
    # Initialize with explicit local mode
    analyst = OSINTAnalystStage(privacy_mode='local')
    
    # Verify privacy mode is active
    print(f"Privacy Mode: {analyst.llm_analyzer.privacy_mode.value}")
    
    if analyst.llm_analyzer.privacy_mode.value != 'local':
        raise RuntimeError("Local LLM not available - cannot run in privacy mode")
    
    # Load sample data (replace with your actual data)
    raw_data = {
        "_target": "Sensitive Target",
        "shodan": [
            {"email": "sensitive@example.com", "bio": "Machine learning expert working on AI safety"},
            {"company": "Secure Corp"}
        ],
        "spiderfoot": [
            {"username": "ml_expert", "bio": "AI researcher passionate about machine learning and data science"},
            {"location": "San Francisco, CA"}
        ]
    }
    
    # Process analysis
    report = analyst.process_harvest_results(raw_data)
    
    # Verify no external calls were made (check logs for confirmation)
    print(f"\n✅ Analysis complete with full privacy protection")
    print(f"   Facts analyzed: {len(report.facts)}")
    print(f"   Avg confidence: {sum(f.confidence_score for f in report.facts)/len(report.facts):.1f}%")

if __name__ == '__main__':
    run_privacy_mode_analysis()
```

---

## 📊 Custom Analysis Configuration

### Example 4: Adjust Confidence Thresholds and Fact Types

```python
#!/usr/bin/env python3
"""
Example: Customize analyst behavior for specific use cases
Override confidence thresholds and add custom fact types
"""

from osint_analyst_stage import OSINTAnalystStage, CrossReferenceEngine

class CustomAnalyst(OSINTAnalystStage):
    """Custom analyst with modified behavior"""
    
    def __init__(self, privacy_mode='local'):
        super().__init__(privacy_mode=privacy_mode)
        
        # Customize confidence thresholds for specific fact types
        self.confidence_thresholds = {
            'email': 80.0,      # Require higher confidence for emails
            'username': 75.0,   # Slightly lower threshold for usernames
            'location': 60.0    # Lower threshold for locations (harder to verify)
        }
    
    def _adjust_confidence(self, base_score: float, facts):
        """Custom confidence adjustment logic"""
        
        # Get fact type from first fact
        if not facts:
            return base_score
        
        fact_type = facts[0].fact_type
        
        # Apply custom threshold adjustments
        if fact_type in self.confidence_thresholds:
            target_conf = self.confidence_thresholds[fact_type]
            
            if base_score >= 90 and fact_type == 'email':
                return min(100, base_score + 5)  # Boost highly confident emails
            
            if fact_type == 'location' and len(facts) == 2:
                return max(base_score, target_conf)  # Minimum threshold for locations
        
        # Apply parent class adjustment for other cases
        return super()._adjust_confidence(base_score, facts)

def run_custom_analysis():
    """Run analysis with custom thresholds"""
    
    print("🔧 Running Custom Analyst Configuration")
    
    analyst = CustomAnalyst(privacy_mode='local')
    
    # Load your data here
    raw_data = {
        "_target": "Custom Target",
        "shodan": [
            {"email": "test@example.com"},
            {"location": "New York"}
        ]
    }
    
    report = analyst.process_harvest_results(raw_data)
    
    print(f"\n✅ Custom analysis complete")
    for fact in report.facts:
        print(f"   {fact.fact_type}: {fact.value} ({fact.confidence_score:.0f}%)")

if __name__ == '__main__':
    run_custom_analysis()
```

---

## 📤 Exporting Analyst Results

### Example 5: Export to Different Formats

#### Export to CSV for Spreadsheet Analysis

```python
#!/usr/bin/env python3
"""
Example: Export analyst results to CSV format
Useful for spreadsheet analysis and reporting
"""

import csv
from osint_analyst_stage import OSINTAnalystStage, load_harvest_results

def export_to_csv(analyst_report, output_file='analysis_export.csv'):
    """Export analyst report to CSV format"""
    
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = [
            'fact_type', 'value', 'confidence_score', 
            'sources', 'source_count', 'context'
        ]
        
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for fact in analyst_report.facts:
            writer.writerow({
                'fact_type': fact.fact_type,
                'value': fact.value,
                'confidence_score': f"{fact.confidence_score:.1f}%",
                'sources': '; '.join(fact.sources),
                'source_count': len(fact.sources),
                'context': str(fact.context)
            })
    
    print(f"✅ Exported to: {output_file}")

def main():
    # Load and process data
    analyst = OSINTAnalystStage(privacy_mode='local')
    raw_data = load_harvest_results('harvest_output/latest.json')
    report = analyst.process_harvest_results(raw_data)
    
    # Export to CSV
    export_to_csv(report, 'analysis_export.csv')

if __name__ == '__main__':
    main()
```

#### Export JSON with Enhanced Metadata

```python
#!/usr/bin/env python3
"""
Example: Export analyst results with enhanced metadata
Add analysis timestamps and processing details
"""

import json
from osint_analyst_stage import OSINTAnalystStage, load_harvest_results
from datetime import datetime

def export_enriched_json(analyst_report, output_file='analysis_enriched.json'):
    """Export analyst report with additional metadata"""
    
    enriched_data = {
        "report_metadata": {
            "generated_at": datetime.now().isoformat(),
            "privacy_mode": analyst_report.llm_analyzer.privacy_mode.value,
            "target_name": analyst_report.target_name,
            "total_facts": len(analyst_report.facts),
            "avg_confidence": sum(f.confidence_score for f in analyst_report.facts) / 
                             max(1, len(analyst_report.facts))
        },
        "facts_by_type": {},
        "raw_facts": [fact.__dict__ for fact in analyst_report.facts]
    }
    
    # Group facts by type
    from collections import defaultdict
    type_groups = defaultdict(list)
    for fact in analyst_report.facts:
        type_groups[fact.fact_type].append(fact.__dict__)
    
    enriched_data["facts_by_type"] = dict(type_groups)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(enriched_data, f, indent=2)
    
    print(f"✅ Enriched export saved to: {output_file}")

if __name__ == '__main__':
    analyst = OSINTAnalystStage(privacy_mode='local')
    raw_data = load_harvest_results('harvest_output/latest.json')
    report = analyst.process_harvest_results(raw_data)
    
    export_enriched_json(report, 'analysis_enriched.json')
```

---

## 🧪 Testing and Validation

### Example 6: Automated Test Suite for Analyst Stage

```python
#!/usr/bin/env python3
"""
Example: Run automated tests on analyst stage functionality
Verifies cross-referencing, deduplication, and confidence scoring
"""

import unittest
from osint_analyst_stage import (
    OSINTAnalystStage, 
    CrossReferenceEngine, 
    DeduplicationEngine,
    Fact
)

class TestAnalystStage(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures"""
        self.analyst = OSINTAnalystStage(privacy_mode='local')
        self.engine = CrossReferenceEngine()
        
    def test_cross_reference_basic(self):
        """Test basic cross-referencing functionality"""
        
        # Simulate data from two sources with matching email
        sources_data = [
            ("shodan", {"email": "test@example.com"}),
            ("spiderfoot", {"email": "TEST@EXAMPLE.COM"})  # Case variation
        ]
        
        facts = self.engine.cross_reference(sources_data)
        
        # Should find one normalized email fact
        emails = [f for f in facts if f.fact_type == 'email']
        self.assertEqual(len(emails), 1)
        self.assertEqual(emails[0].value.lower(), "test@example.com")
    
    def test_confidence_scoring(self):
        """Test confidence scoring with multiple sources"""
        
        # Single source = lower confidence
        single_source = [("shodan", {"email": "single@test.com"})]
        facts_single = self.engine.cross_reference(single_source)
        
        self.assertGreaterEqual(facts_single[0].confidence_score, 60.0)
        self.assertLessEqual(facts_single[0].confidence_score, 85.0)
    
    def test_deduplication(self):
        """Test deduplication of identical facts"""
        
        # Create duplicate facts
        fact1 = Fact(
            fact_type="email", 
            value="duplicate@test.com",
            sources=["shodan"],
            confidence_score=90.0
        )
        
        fact2 = Fact(
            fact_type="email",
            value="duplicate@test.com",  # Same value
            sources=["spiderfoot"],
            confidence_score=85.0
        )
        
        dedup_engine = DeduplicationEngine()
        merged = dedup_engine.merge_duplicates([fact1, fact2])
        
        # Should be reduced to one fact with merged sources
        self.assertEqual(len(merged), 1)
        self.assertIn("spiderfoot", merged[0].sources)

if __name__ == '__main__':
    unittest.main()
```

**Run tests:**
```bash
python docs/examples/test_analyst_stage.py -v
```

---

## 🔍 Debug Mode: Detailed Analysis Logs

### Example 7: Enable Verbose Logging for Troubleshooting

```python
#!/usr/bin/env python3
"""
Example: Run analyst with detailed logging enabled
Useful for debugging analysis issues and understanding processing flow
"""

import logging
from osint_analyst_stage import OSINTAnalystStage, load_harvest_results

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def run_debug_analysis():
    """Run analysis with debug logging enabled"""
    
    print("🔍 Starting Debug Analysis")
    
    # Create analyst instance
    analyst = OSINTAnalystStage(privacy_mode='local')
    
    # Enable debug logging for specific modules
    logging.getLogger('osint_analyst_stage').setLevel(logging.DEBUG)
    logging.getLogger('cross_reference_engine').setLevel(logging.DEBUG)
    
    # Load data
    raw_data = load_harvest_results('harvest_output/latest.json')
    
    # Process with detailed logs
    report = analyst.process_harvest_results(raw_data)
    
    print(f"\n✅ Analysis complete - check logs above for details")

if __name__ == '__main__':
    run_debug_analysis()
```

---

## 🌐 Integration with External Systems

### Example 8: Push Results to Slack/Teams

```python
#!/usr/bin/env python3
"""
Example: Send analyst results notification via Slack webhook
Automatically alerts team when analysis completes
"""

import requests
from osint_analyst_stage import OSINTAnalystStage, load_harvest_results

def send_slack_notification(report, slack_webhook_url):
    """Send analyst summary to Slack channel"""
    
    # Calculate statistics
    high_conf = len([f for f in report.facts if f.confidence_score >= 85])
    low_conf = len([f for f in report.facts if f.confidence_score < 40])
    
    # Create Slack message
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🔍 OSINT Analysis Complete"}
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Target:* {report.target_name}"},
                {"type": "mrkdwn", "text": f"*Facts Found:* {len(report.facts)}"},
                {"type": "mrkdwn", "text": f"*High Confidence:* {high_conf}"},
                {"type": "mrkdwn", "text": f"*Low Confidence:* {low_conf}"}
            ]
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": "*Privacy Mode:* Local"},
                {"type": "mrkdwn", "text": f"*Avg Confidence:* {sum(f.confidence_score for f in report.facts)/len(report.facts):.0f}%"}
            ]
        }
    ]
    
    payload = {
        "blocks": blocks,
        "username": "OSINT Analyst Bot",
        "icon_emoji": ":mag:"
    }
    
    try:
        response = requests.post(slack_webhook_url, json=payload)
        return response.status_code == 200
    except Exception as e:
        print(f"Failed to send Slack notification: {e}")
        return False

def main():
    # Load your webhook URL from environment variable
    slack_webhook = os.environ.get('SLACK_WEBHOOK_URL')
    
    if not slack_webhook:
        print("❌ SLACK_WEBHOOK_URL environment variable not set")
        return
    
    # Run analysis
    analyst = OSINTAnalystStage(privacy_mode='local')
    raw_data = load_harvest_results('harvest_output/latest.json')
    report = analyst.process_harvest_results(raw_data)
    
    # Send notification
    success = send_slack_notification(report, slack_webhook)
    
    if success:
        print("✅ Slack notification sent successfully")

if __name__ == '__main__':
    main()
```

---

## 📋 Complete Workflow Example

### Example 9: End-to-End Investigation Pipeline

```python
#!/usr/bin/env python3
"""
Example: Complete investigation workflow from start to finish
Includes data validation, analysis, reporting, and notification
"""

import asyncio
from datetime import datetime
from osint_kanban_manager import OsintPipelineManager, PipelineConfig
from osint_analyst_stage import OSINTAnalystStage
import os

async def run_complete_investigation():
    """Run complete investigation with analyst integration"""
    
    print("="*60)
    print("🚀 COMPLETE OSINT INVESTIGATION WORKFLOW")
    print("="*60)
    
    # Step 1: Initialize pipeline
    config = PipelineConfig(
        target_name="Target Company",
        target_type="company",
        wip_limits={
            "RECON": 2,
            "HARVESTING": 3,
            "ANALYST": 2,
            "SCRIBE": 1
        },
        api_keys={
            "PRIVACY_MODE": "local"  # Privacy-focused analysis
        }
    )
    
    manager = OsintPipelineManager(config)
    
    print("\n📋 Starting investigation...")
    
    try:
        # Step 2: Execute pipeline
        await manager.start_pipeline(
            user_query="Target Company, cybersecurity firm",
            target_type="company"
        )
        
        print("✅ Investigation completed successfully!")
        
        # Step 3: Access analysis results
        if manager.results.successful > 0:
            print(f"\n📊 Results Summary:")
            print(f"   Successful investigations: {manager.results.successful}")
            
            # Get analyst reports from completed tickets
            for stage_name, column in manager.columns.items():
                if stage_name == "ANALYST":
                    for ticket in column.current_work_in_progress:
                        if 'analysis_results' in ticket.analysis_results:
                            analysis = ticket.analysis_results['all_facts']
                            print(f"   Facts analyzed: {len(analysis)}")
        
    except Exception as e:
        print(f"\n❌ Investigation failed: {e}")

if __name__ == '__main__':
    asyncio.run(run_complete_investigation())
```

---

## 🎯 Key Takeaways

1. **Privacy Mode is Automatic**: Analyst stage automatically uses local LLMs when available, falling back to heuristics if not
2. **Confidence Scoring is Transparent**: All facts include confidence scores and source attribution
3. **Integration is Simple**: The analyst integrates seamlessly with the Kanban pipeline through standard data structures
4. **Customization Available**: Override default behavior by subclassing OSINTAnalystStage or modifying configuration
5. **Extensible Output**: Results can be exported to CSV, JSON, Slack, databases, etc.

---

## 📚 Next Steps

After mastering these examples:
- Review the [ANALYST_STAGE_GUIDE.md](./ANALYST_STAGE_GUIDE.md) for detailed API reference
- Explore the [PROJECT_STATUS_SUMMARY.md](./PROJECT_STATUS_SUMMARY.md) for current development status
- Consider implementing the missing SCRIBE stage for report generation

---

*These examples demonstrate the flexibility and power of the OSINT Intelligence Analyst stage. Customize them to fit your specific investigation requirements.*
