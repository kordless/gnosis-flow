#!/usr/bin/env python3
"""
Claude-Flow Package Analyzer
Investigates the true nature of the claude-flow package
"""

import os
import json
import re
from pathlib import Path
from collections import defaultdict

def analyze_directory(root_path):
    """Analyze the claude-flow directory structure and contents"""
    
    stats = {
        'total_files': 0,
        'total_size': 0,
        'file_types': defaultdict(int),
        'large_files': [],
        'mock_indicators': [],
        'real_implementations': [],
        'suspicious_patterns': []
    }
    
    # Patterns that indicate mocking
    mock_patterns = [
        r'Math\.random\(\)',
        r'mock[A-Z]\w*',
        r'fake[A-Z]\w*',
        r'return\s*{\s*success:\s*true',
        r'// TODO:?\s*implement',
        r'throw\s*new\s*Error\(["\']Not implemented',
        r'setTimeout.*Math\.random'
    ]
    
    # Patterns that indicate real implementation
    real_patterns = [
        r'await\s+fetch\s*\(',
        r'new\s+WebSocket\s*\(',
        r'database\.\w+\(',
        r'\.query\s*\(',
        r'tensorflow',
        r'torch\.',
        r'model\.predict\(',
        r'fs\.writeFile',
        r'child_process'
    ]
    
    print(f"Analyzing directory: {root_path}")
    print("-" * 80)
    
    for root, dirs, files in os.walk(root_path):
        # Skip node_modules and .git
        dirs[:] = [d for d in dirs if d not in ['node_modules', '.git', '.vscode', 'coverage']]
        
        for file in files:
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, root_path)
            
            try:
                size = os.path.getsize(file_path)
                stats['total_files'] += 1
                stats['total_size'] += size
                
                # Track file types
                ext = Path(file).suffix.lower()
                stats['file_types'][ext] += 1
                
                # Track large files
                if size > 100_000:  # 100KB
                    stats['large_files'].append({
                        'path': rel_path,
                        'size': f"{size:,} bytes",
                        'size_mb': f"{size/1024/1024:.2f} MB"
                    })
                
                # Analyze code files
                if ext in ['.js', '.ts', '.jsx', '.tsx', '.mjs']:
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            
                        # Check for mock patterns
                        for pattern in mock_patterns:
                            matches = re.findall(pattern, content, re.IGNORECASE)
                            if matches:
                                stats['mock_indicators'].append({
                                    'file': rel_path,
                                    'pattern': pattern,
                                    'count': len(matches),
                                    'sample': matches[0] if matches else ''
                                })
                        
                        # Check for real implementations
                        for pattern in real_patterns:
                            matches = re.findall(pattern, content, re.IGNORECASE)
                            if matches:
                                stats['real_implementations'].append({
                                    'file': rel_path,
                                    'pattern': pattern,
                                    'count': len(matches),
                                    'sample': matches[0] if matches else ''
                                })
                        
                        # Check for suspicious patterns
                        if 'eval(' in content:
                            stats['suspicious_patterns'].append({
                                'file': rel_path,
                                'issue': 'Uses eval()',
                                'risk': 'high'
                            })
                        
                        if 'require("child_process")' in content and 'exec(' in content:
                            stats['suspicious_patterns'].append({
                                'file': rel_path,
                                'issue': 'Executes system commands',
                                'risk': 'high'
                            })
                            
                    except Exception as e:
                        pass
                        
            except Exception as e:
                print(f"Error processing {rel_path}: {e}")
    
    # Generate summary
    print("\n=== PACKAGE SUMMARY ===")
    print(f"Total Files: {stats['total_files']}")
    print(f"Total Size: {stats['total_size']:,} bytes ({stats['total_size']/1024/1024:.2f} MB)")
    
    print("\n=== FILE TYPES ===")
    for ext, count in sorted(stats['file_types'].items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"{ext or 'no extension'}: {count}")
    
    print("\n=== LARGE FILES (>100KB) ===")
    for file in sorted(stats['large_files'], key=lambda x: x['size'], reverse=True)[:10]:
        print(f"{file['path']}: {file['size_mb']}")
    
    print(f"\n=== MOCK INDICATORS FOUND: {len(stats['mock_indicators'])} ===")
    # Group by file
    mock_files = defaultdict(list)
    for mock in stats['mock_indicators']:
        mock_files[mock['file']].append(mock)
    
    for file, mocks in list(mock_files.items())[:5]:
        print(f"\n{file}:")
        for mock in mocks[:3]:
            print(f"  - {mock['pattern']} ({mock['count']} times)")
    
    print(f"\n=== REAL IMPLEMENTATIONS FOUND: {len(stats['real_implementations'])} ===")
    # Group by file
    real_files = defaultdict(list)
    for real in stats['real_implementations']:
        real_files[real['file']].append(real)
    
    for file, reals in list(real_files.items())[:5]:
        print(f"\n{file}:")
        for real in reals[:3]:
            print(f"  - {real['pattern']} ({real['count']} times)")
    
    if stats['suspicious_patterns']:
        print(f"\n=== SUSPICIOUS PATTERNS: {len(stats['suspicious_patterns'])} ===")
        for susp in stats['suspicious_patterns'][:5]:
            print(f"{susp['file']}: {susp['issue']} (risk: {susp['risk']})")
    
    # Check package.json
    package_json_path = os.path.join(root_path, 'package.json')
    if os.path.exists(package_json_path):
        print("\n=== PACKAGE.JSON ANALYSIS ===")
        try:
            with open(package_json_path, 'r') as f:
                package = json.load(f)
            
            print(f"Name: {package.get('name', 'Unknown')}")
            print(f"Version: {package.get('version', 'Unknown')}")
            print(f"Description: {package.get('description', 'None')}")
            print(f"Main: {package.get('main', 'None')}")
            print(f"Author: {package.get('author', 'Unknown')}")
            
            # Check dependencies
            deps = package.get('dependencies', {})
            print(f"\nDependencies: {len(deps)}")
            
            # Look for suspicious dependencies
            suspicious_deps = []
            for dep, version in deps.items():
                if any(word in dep.lower() for word in ['crypto', 'miner', 'track', 'analytics', 'telemetry']):
                    suspicious_deps.append(f"{dep}: {version}")
            
            if suspicious_deps:
                print("\nPotentially suspicious dependencies:")
                for dep in suspicious_deps:
                    print(f"  - {dep}")
                    
        except Exception as e:
            print(f"Error reading package.json: {e}")
    
    # Final verdict
    print("\n=== ANALYSIS VERDICT ===")
    mock_ratio = len(stats['mock_indicators']) / (len(stats['mock_indicators']) + len(stats['real_implementations']) + 1)
    print(f"Mock Indicator Ratio: {mock_ratio:.1%}")
    
    if mock_ratio > 0.7:
        print("⚠️  HIGH MOCK CONTENT DETECTED - Package appears to be mostly mocked implementations")
    elif mock_ratio > 0.4:
        print("⚠️  SIGNIFICANT MOCKING - Package contains substantial mock implementations")
    elif len(stats['real_implementations']) > 50:
        print("✓ Package appears to contain real implementations")
    else:
        print("? INCONCLUSIVE - Further investigation needed")
    
    return stats

if __name__ == "__main__":
    # Get the current directory or use command line argument
    import sys
    
    if len(sys.argv) > 1:
        target_dir = sys.argv[1]
    else:
        target_dir = os.getcwd()
    
    if not os.path.exists(target_dir):
        print(f"Error: Directory {target_dir} does not exist")
        sys.exit(1)
    
    print(f"Claude-Flow Package Analyzer v1.0")
    print(f"Target: {target_dir}")
    print("=" * 80)
    
    stats = analyze_directory(target_dir)
    
    print("\n" + "=" * 80)
    print("Analysis complete. Review the findings above.")
    print("\nTo run on claude-flow package:")
    print("python analyze_claude_flow.py /path/to/claude-flow")
