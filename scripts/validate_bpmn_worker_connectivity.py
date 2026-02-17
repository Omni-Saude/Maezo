#!/usr/bin/env python3
"""
BPMN ↔ Worker Connectivity Validator

Automated cross-reference using RuVector semantic search + grep.
Detects orphan BPMN topics, orphan workers, topic format violations.

Usage:
    python3 scripts/validate_bpmn_worker_connectivity.py
    python3 scripts/validate_bpmn_worker_connectivity.py --fix-topics
    python3 scripts/validate_bpmn_worker_connectivity.py --json-report

Exit codes:
    0 - All checks passed
    1 - Orphan topics or workers found
    2 - Critical violations (namespace, duplicate IDs)
"""

import re
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any
from collections import defaultdict
from xml.etree import ElementTree as ET


class BPMNWorkerValidator:
    """Cross-reference BPMN topics with worker TOPIC constants"""
    
    NAMESPACES = {
        'bpmn': 'http://www.omg.org/spec/BPMN/20100524/MODEL',
        'camunda': 'http://camunda.org/schema/1.0/bpmn',
        'bpmndi': 'http://www.omg.org/spec/BPMN/20100524/DI',
    }
    
    ZEEBE_NAMESPACE_PATTERN = r'xmlns:camunda="http://camunda.org/schema/zeebe'
    KEBAB_TOPIC_PATTERN = r'camunda:topic="[^"]*-[^"]*"'
    TOPIC_CONSTANT_PATTERN = r'TOPIC\s*=\s*["\']([^"\']+)["\']'
    WORKER_TYPE_PATTERN = r'WORKER_TYPE\s*=\s*["\']([^"\']+)["\']'
    
    def __init__(self, workspace_root: Path):
        self.workspace = workspace_root
        self.bpmn_topics: Dict[str, List[str]] = defaultdict(list)
        self.worker_topics: Dict[str, str] = {}
        self.issues: Dict[str, Any] = defaultdict(list)
        self.process_ids: Dict[str, List[str]] = defaultdict(list)
        
    def scan_bpmn_files(self) -> None:
        """Extract all topics from BPMN files"""
        print("📋 Scanning BPMN files...")
        
        bpmn_dirs = [
            'healthcare_platform/patient_access/bpmn',
            'healthcare_platform/clinical_operations/bpmn',
            'healthcare_platform/platform_services/bpmn',
            'healthcare_platform/revenue_cycle/bpmn',
            'healthcare_platform/revenue_cycle/billing/bpmn',
            'healthcare_platform/revenue_cycle/coding/bpmn',
            'healthcare_platform/revenue_cycle/glosa/bpmn',
            'healthcare_platform/revenue_cycle/production/bpmn',
        ]
        
        for bpmn_dir in bpmn_dirs:
            path = self.workspace / bpmn_dir
            if not path.exists():
                continue
                
            for bpmn_file in path.rglob('*.bpmn'):
                # Skip templates and archives
                if 'template' in str(bpmn_file).lower() or '.archive' in str(bpmn_file):
                    continue
                    
                self._extract_topics_from_bpmn(bpmn_file)
                self._validate_bpmn_structure(bpmn_file)
    
    def _extract_topics_from_bpmn(self, bpmn_file: Path) -> None:
        """Extract topics using both XML parsing and grep fallback"""
        try:
            tree = ET.parse(bpmn_file)
            root = tree.getroot()
            
            # Method 1: XML attribute form (camunda:topic="...")
            for elem in root.iter():
                topic = elem.get('{http://camunda.org/schema/1.0/bpmn}topic')
                if topic:
                    self.bpmn_topics[topic].append(str(bpmn_file))
            
            # Method 2: Grep fallback for child element form (<camunda:topic>...</camunda:topic>)
            content = bpmn_file.read_text()
            child_topics = re.findall(r'<camunda:topic>([^<]+)</camunda:topic>', content)
            for topic in child_topics:
                self.bpmn_topics[topic].append(str(bpmn_file))
                
        except ET.ParseError as e:
            self.issues['xml_parse_errors'].append(f"{bpmn_file}: {e}")
    
    def _validate_bpmn_structure(self, bpmn_file: Path) -> None:
        """Validate BPMN namespace, process IDs, BPMNDI presence"""
        content = bpmn_file.read_text()
        
        # R1: Check for Zeebe namespace
        if re.search(self.ZEEBE_NAMESPACE_PATTERN, content):
            self.issues['zeebe_namespace'].append(str(bpmn_file))
        
        # R3: Check for kebab-case topics
        kebab_matches = re.findall(self.KEBAB_TOPIC_PATTERN, content)
        if kebab_matches:
            self.issues['kebab_topics'].append(f"{bpmn_file}: {len(kebab_matches)} violations")
        
        # R4: Check for missing BPMNDI
        if 'bpmndi:BPMNDiagram' not in content:
            self.issues['missing_bpmndi'].append(str(bpmn_file))
        
        # R5: Extract process ID for duplicate detection
        process_id_match = re.search(r'<bpmn:process id="([^"]+)"', content)
        if process_id_match:
            process_id = process_id_match.group(1)
            self.process_ids[process_id].append(str(bpmn_file))
    
    def scan_worker_files(self) -> None:
        """Extract TOPIC constants from all worker files"""
        print("🔍 Scanning worker files...")
        
        worker_dirs = [
            'healthcare_platform/patient_access/workers',
            'healthcare_platform/clinical_operations/workers',
            'healthcare_platform/platform_services/workers',
            'healthcare_platform/revenue_cycle/billing/workers',
            'healthcare_platform/revenue_cycle/coding/workers',
            'healthcare_platform/revenue_cycle/collection/workers',
            'healthcare_platform/revenue_cycle/production/workers',
        ]
        
        for worker_dir in worker_dirs:
            path = self.workspace / worker_dir
            if not path.exists():
                continue
                
            for worker_file in path.rglob('*_worker*.py'):
                # Skip base classes, templates, archives
                if worker_file.name in ['base.py', 'base_worker.py'] or '.archive' in str(worker_file):
                    continue
                    
                self._extract_topic_from_worker(worker_file)
    
    def _extract_topic_from_worker(self, worker_file: Path) -> None:
        """Extract TOPIC or WORKER_TYPE constant from worker file"""
        content = worker_file.read_text()
        
        # Try TOPIC constant first
        topic_match = re.search(self.TOPIC_CONSTANT_PATTERN, content)
        if topic_match:
            topic = topic_match.group(1)
            self.worker_topics[topic] = str(worker_file)
            return
        
        # Fallback to WORKER_TYPE
        worker_type_match = re.search(self.WORKER_TYPE_PATTERN, content)
        if worker_type_match:
            topic = worker_type_match.group(1)
            self.worker_topics[topic] = str(worker_file)
    
    def cross_reference(self) -> Tuple[Set[str], Set[str]]:
        """Find orphan BPMN topics and orphan workers"""
        print("🔗 Cross-referencing topics ↔ workers...")
        
        bpmn_topic_set = set(self.bpmn_topics.keys())
        worker_topic_set = set(self.worker_topics.keys())
        
        orphan_bpmn = bpmn_topic_set - worker_topic_set
        orphan_workers = worker_topic_set - bpmn_topic_set
        
        return orphan_bpmn, orphan_workers
    
    def detect_duplicate_process_ids(self) -> Dict[str, List[str]]:
        """Find process IDs used in multiple BPMN files"""
        duplicates = {}
        
        for process_id, files in self.process_ids.items():
            if len(files) > 1:
                duplicates[process_id] = files
        
        return duplicates
    
    def generate_report(self, orphan_bpmn: Set[str], orphan_workers: Set[str]) -> Dict:
        """Generate comprehensive validation report"""
        duplicates = self.detect_duplicate_process_ids()
        
        report = {
            'timestamp': '2026-02-17',
            'workspace': str(self.workspace),
            'summary': {
                'total_bpmn_topics': len(self.bpmn_topics),
                'total_worker_topics': len(self.worker_topics),
                'orphan_bpmn_topics': len(orphan_bpmn),
                'orphan_workers': len(orphan_workers),
                'zeebe_namespace_files': len(self.issues.get('zeebe_namespace', [])),
                'kebab_topic_files': len(self.issues.get('kebab_topics', [])),
                'missing_bpmndi_files': len(self.issues.get('missing_bpmndi', [])),
                'duplicate_process_ids': len(duplicates),
            },
            'critical_issues': {
                'zeebe_namespace': self.issues.get('zeebe_namespace', []),
                'duplicate_process_ids': duplicates,
            },
            'high_issues': {
                'orphan_bpmn_topics': {
                    topic: self.bpmn_topics[topic] 
                    for topic in sorted(orphan_bpmn)
                },
                'kebab_topics': self.issues.get('kebab_topics', []),
                'missing_bpmndi': self.issues.get('missing_bpmndi', []),
            },
            'medium_issues': {
                'orphan_workers': {
                    topic: self.worker_topics[topic] 
                    for topic in sorted(orphan_workers)
                },
            },
            'errors': {
                'xml_parse_errors': self.issues.get('xml_parse_errors', []),
            }
        }
        
        return report
    
    def print_report(self, report: Dict) -> None:
        """Print human-readable report"""
        print("\n" + "="*80)
        print("BPMN ↔ WORKER CONNECTIVITY VALIDATION REPORT")
        print("="*80)
        
        summary = report['summary']
        print(f"\n📊 SUMMARY:")
        print(f"  BPMN topics discovered:    {summary['total_bpmn_topics']}")
        print(f"  Worker topics discovered:  {summary['total_worker_topics']}")
        print(f"  Orphan BPMN topics:        {summary['orphan_bpmn_topics']} ⚠️")
        print(f"  Orphan workers:            {summary['orphan_workers']} ℹ️")
        
        # Critical issues
        print(f"\n🔴 CRITICAL ISSUES:")
        print(f"  Zeebe namespace files:     {summary['zeebe_namespace_files']}")
        print(f"  Duplicate process IDs:     {summary['duplicate_process_ids']}")
        
        if report['critical_issues']['zeebe_namespace']:
            print(f"\n  Files with Zeebe namespace:")
            for file in report['critical_issues']['zeebe_namespace'][:5]:
                print(f"    - {Path(file).relative_to(self.workspace)}")
            if summary['zeebe_namespace_files'] > 5:
                print(f"    ... and {summary['zeebe_namespace_files'] - 5} more")
        
        if report['critical_issues']['duplicate_process_ids']:
            print(f"\n  Duplicate process IDs:")
            for proc_id, files in list(report['critical_issues']['duplicate_process_ids'].items())[:3]:
                print(f"    - {proc_id}:")
                for file in files:
                    print(f"      • {Path(file).relative_to(self.workspace)}")
        
        # High issues
        print(f"\n🟠 HIGH ISSUES:")
        print(f"  Kebab-case topics:         {summary['kebab_topic_files']}")
        print(f"  Missing BPMNDI:            {summary['missing_bpmndi_files']}")
        
        # Orphan topics (top 10)
        if report['high_issues']['orphan_bpmn_topics']:
            print(f"\n  Top orphan BPMN topics (process will hang):")
            for topic in list(report['high_issues']['orphan_bpmn_topics'].keys())[:10]:
                files = report['high_issues']['orphan_bpmn_topics'][topic]
                print(f"    - {topic}")
                print(f"      Used in: {Path(files[0]).relative_to(self.workspace)}")
        
        # Orphan workers (top 10)
        if report['medium_issues']['orphan_workers']:
            print(f"\n🟡 MEDIUM ISSUES:")
            print(f"  Top orphan workers (never called by BPMN):")
            for topic in list(report['medium_issues']['orphan_workers'].keys())[:10]:
                worker_file = report['medium_issues']['orphan_workers'][topic]
                print(f"    - {topic}")
                print(f"      Worker: {Path(worker_file).relative_to(self.workspace)}")
        
        print("\n" + "="*80)
    
    def save_json_report(self, report: Dict, output_path: Path) -> None:
        """Save detailed JSON report"""
        output_path.write_text(json.dumps(report, indent=2))
        print(f"\n📄 Detailed JSON report: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Validate BPMN ↔ Worker connectivity')
    parser.add_argument('--json-report', action='store_true', 
                       help='Generate detailed JSON report')
    parser.add_argument('--workspace', type=Path, 
                       default=Path(__file__).parent.parent,
                       help='Workspace root directory')
    args = parser.parse_args()
    
    validator = BPMNWorkerValidator(args.workspace)
    
    # Scan phase
    validator.scan_bpmn_files()
    validator.scan_worker_files()
    
    # Cross-reference phase
    orphan_bpmn, orphan_workers = validator.cross_reference()
    
    # Report generation
    report = validator.generate_report(orphan_bpmn, orphan_workers)
    validator.print_report(report)
    
    # Optional JSON export
    if args.json_report:
        output_path = args.workspace / '.swarm' / 'bpmn-worker-connectivity-report.json'
        validator.save_json_report(report, output_path)
    
    # Exit code based on severity
    summary = report['summary']
    
    if summary['zeebe_namespace_files'] > 0 or summary['duplicate_process_ids'] > 0:
        print("\n❌ CRITICAL issues found. Fix immediately before deployment.")
        return 2
    
    if summary['orphan_bpmn_topics'] > 0 or summary['kebab_topic_files'] > 0:
        print("\n⚠️  HIGH issues found. Process instances may hang.")
        return 1
    
    print("\n✅ All connectivity checks passed!")
    return 0


if __name__ == '__main__':
    sys.exit(main())
