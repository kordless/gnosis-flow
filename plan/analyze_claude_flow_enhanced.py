#!/usr/bin/env python3
"""
Enhanced Claude-Flow Package Analyzer v2.0
Deep analysis of async patterns, tool usage, and API integration
"""

import os
import json
import re
import ast
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any

class EnhancedAnalyzer:
    def __init__(self, root_path: str):
        self.root_path = root_path
        self.stats = {
            'total_files': 0,
            'total_size': 0,
            'file_types': defaultdict(int),
            'large_files': [],
            'mock_indicators': [],
            'real_implementations': [],
            'suspicious_patterns': [],
            'async_patterns': [],
            'tool_patterns': [],
            'api_calls': [],
            'message_patterns': [],
            'promise_patterns': [],
            'error_handling': []
        }
        
        # Enhanced patterns for JavaScript/TypeScript
        self.patterns = {
            'mock': [
                r'Math\.random\(\)',
                r'mock[A-Z]\w*',
                r'fake[A-Z]\w*',
                r'return\s*{\s*success:\s*true',
                r'// TODO:?\s*implement',
                r'throw\s*new\s*Error\(["\']Not implemented',
                r'setTimeout.*Math\.random',
                r'generateFake\w+',
                r'simulat\w+',
                r'dummy\w+'
            ],
            'real': [
                r'await\s+fetch\s*\(',
                r'new\s+WebSocket\s*\(',
                r'database\.\w+\(',
                r'\.query\s*\(',
                r'tensorflow',
                r'torch\.',
                r'model\.predict\(',
                r'fs\.writeFile',
                r'child_process',
                r'sqlite3?\.', 
                r'postgres\.',
                r'redis\.'
            ],
            'async': [
                r'async\s+function',
                r'async\s*\(',
                r'async\s*=>\s*',
                r'await\s+',
                r'Promise\.all',
                r'Promise\.race',
                r'Promise\.allSettled',
                r'new\s+Promise',
                r'\.then\s*\(',
                r'\.catch\s*\(',
                r'\.finally\s*\('
            ],
            'tool_calling': [
                # Claude tool format patterns
                r'tools:\s*\[',
                r'tool_choice:',
                r'function_call',
                r'functions:\s*\[',
                r'tool_use',
                r'use_tools',
                r'invoke.*tool',
                r'executeTool',
                r'callFunction',
                r'runTool',
                # MCP patterns
                r'mcp\.tools',
                r'@tool\(',
                r'registerTool',
                r'toolRegistry'
            ],
            'api_integration': [
                # Anthropic patterns
                r'anthropic\.com',
                r'claude\.ai',
                r'ANTHROPIC_API_KEY',
                r'CLAUDE_API_KEY',
                r'messages\.create',
                r'completions\.create',
                r'\/v1\/messages',
                r'\/v1\/complete',
                r'x-api-key',
                # OpenAI patterns
                r'openai\.com',
                r'OPENAI_API_KEY',
                r'gpt-[34]',
                r'chat\.completions',
                # Generic API patterns
                r'Bearer\s+["\']?\$?\{?[A-Z_]+',
                r'apiKey:',
                r'api_key:',
                r'Authorization:'
            ],
            'message_format': [
                # Claude message format
                r'role:\s*["\'](?:user|assistant|system)',
                r'content:\s*["\'][^"\']+',
                r'messages:\s*\[',
                r'conversation:\s*\[',
                # Tool response format
                r'tool_use_id',
                r'tool_result',
                r'is_error',
                # Multi-turn patterns
                r'history:\s*\[',
                r'context:\s*\[',
                r'previousMessages'
            ],
            'concurrency': [
                r'Worker\(',
                r'cluster\.',
                r'fork\(',
                r'spawn\(',
                r'Thread',
                r'parallel',
                r'concurrent',
                r'queue\.',
                r'pool\.',
                r'semaphore',
                r'mutex',
                r'lock\.'
            ],
            'error_handling': [
                r'try\s*{',
                r'catch\s*\(',
                r'\.catch\(',
                r'throw\s+',
                r'Error\(',
                r'reject\(',
                r'retry',
                r'backoff',
                r'circuit.*break',
                r'fallback'
            ]
        }

    def analyze_javascript_file(self, file_path: str, content: str) -> Dict[str, Any]:
        """Deep analysis of JavaScript/TypeScript files"""
        analysis = {
            'async_usage': self.check_async_patterns(content),
            'tool_usage': self.check_tool_patterns(content),
            'api_calls': self.check_api_patterns(content),
            'message_handling': self.check_message_patterns(content),
            'concurrency': self.check_concurrency_patterns(content),
            'error_handling': self.check_error_handling(content)
        }
        
        # Check for actual vs mock implementations
        analysis['implementation_quality'] = self.assess_implementation_quality(content)
        
        return analysis

    def check_async_patterns(self, content: str) -> Dict[str, Any]:
        """Analyze async/await usage patterns"""
        patterns_found = []
        
        # Count async functions
        async_functions = len(re.findall(r'async\s+function|\basync\s*\(|\basync\s*=>', content))
        await_calls = len(re.findall(r'\bawait\s+', content))
        promise_chains = len(re.findall(r'\.then\s*\(', content))
        
        # Check for proper async error handling
        async_try_catch = len(re.findall(r'try\s*{\s*[^}]*await[^}]*}\s*catch', content, re.DOTALL))
        
        # Check for concurrent execution patterns
        promise_all = len(re.findall(r'Promise\.all', content))
        promise_race = len(re.findall(r'Promise\.race', content))
        
        return {
            'async_functions': async_functions,
            'await_calls': await_calls,
            'promise_chains': promise_chains,
            'async_try_catch': async_try_catch,
            'concurrent_promises': promise_all + promise_race,
            'async_score': self.calculate_async_score(async_functions, await_calls, async_try_catch)
        }

    def check_tool_patterns(self, content: str) -> Dict[str, Any]:
        """Analyze tool/function calling patterns"""
        tool_patterns = {}
        
        # Check for Claude tool format
        claude_tools = re.findall(r'tools:\s*\[([^\]]+)\]', content, re.DOTALL)
        if claude_tools:
            tool_patterns['claude_tool_definitions'] = len(claude_tools)
            # Try to extract tool names
            tool_names = re.findall(r'name:\s*["\']([^"\']+)', ''.join(claude_tools))
            tool_patterns['tool_names'] = tool_names
        
        # Check for OpenAI function format
        openai_functions = re.findall(r'functions:\s*\[([^\]]+)\]', content, re.DOTALL)
        if openai_functions:
            tool_patterns['openai_function_definitions'] = len(openai_functions)
        
        # Check for tool execution
        tool_execution = re.findall(r'execute(?:Tool|Function)\s*\([^)]+\)', content)
        tool_patterns['tool_executions'] = len(tool_execution)
        
        # Check for MCP integration
        mcp_patterns = re.findall(r'mcp\.\w+|MCP[A-Z]\w+', content)
        tool_patterns['mcp_references'] = len(mcp_patterns)
        
        return tool_patterns

    def check_api_patterns(self, content: str) -> Dict[str, Any]:
        """Analyze actual API integration patterns"""
        api_patterns = {}
        
        # Check for API endpoints
        anthropic_calls = re.findall(r'https?://api\.anthropic\.com[^"\'\s]*', content)
        openai_calls = re.findall(r'https?://api\.openai\.com[^"\'\s]*', content)
        
        api_patterns['anthropic_endpoints'] = anthropic_calls
        api_patterns['openai_endpoints'] = openai_calls
        
        # Check for API key usage
        api_key_refs = re.findall(r'process\.env\.[A-Z_]*API[_\s]?KEY', content)
        api_patterns['api_key_references'] = api_key_refs
        
        # Check for actual fetch/axios calls to AI services
        ai_fetch_calls = re.findall(
            r'fetch\s*\([^)]*(?:anthropic|openai|claude)[^)]*\)', 
            content, 
            re.IGNORECASE
        )
        api_patterns['ai_api_calls'] = len(ai_fetch_calls)
        
        # Check for request construction
        request_bodies = re.findall(r'body:\s*JSON\.stringify\s*\([^)]+messages[^)]+\)', content)
        api_patterns['request_constructions'] = len(request_bodies)
        
        return api_patterns

    def check_message_patterns(self, content: str) -> Dict[str, Any]:
        """Analyze message formatting and conversation handling"""
        message_patterns = {}
        
        # Check for message array construction
        message_arrays = re.findall(r'messages:\s*\[[\s\S]*?\](?=\s*[,}])', content)
        message_patterns['message_arrays'] = len(message_arrays)
        
        # Check for role assignments
        roles = re.findall(r'role:\s*["\']?(user|assistant|system|function)', content)
        message_patterns['role_assignments'] = len(roles)
        message_patterns['role_types'] = list(set(roles))
        
        # Check for conversation history handling
        history_patterns = re.findall(r'conversationHistory|messageHistory|chatHistory', content)
        message_patterns['history_handling'] = len(history_patterns)
        
        # Check for tool responses
        tool_responses = re.findall(r'tool_use_id|tool_result|function_call', content)
        message_patterns['tool_response_handling'] = len(tool_responses)
        
        return message_patterns

    def check_concurrency_patterns(self, content: str) -> Dict[str, Any]:
        """Check for actual concurrency/parallelism patterns"""
        concurrency = {}
        
        # Node.js cluster/worker patterns
        workers = re.findall(r'worker_threads|cluster\.fork|Worker\(', content)
        concurrency['worker_usage'] = len(workers)
        
        # Queue patterns
        queues = re.findall(r'Queue\(|queue\.push|queue\.pop|bull|bee-queue|kue', content)
        concurrency['queue_usage'] = len(queues)
        
        # Parallel execution patterns
        parallel = re.findall(r'parallel|concurrent|Promise\.all|Promise\.allSettled', content)
        concurrency['parallel_patterns'] = len(parallel)
        
        # Rate limiting patterns
        rate_limit = re.findall(r'rateLimit|throttle|debounce|semaphore', content)
        concurrency['rate_limiting'] = len(rate_limit)
        
        return concurrency

    def check_error_handling(self, content: str) -> Dict[str, Any]:
        """Analyze error handling sophistication"""
        error_handling = {}
        
        # Basic try-catch
        try_catch = len(re.findall(r'try\s*{[^}]+}\s*catch', content))
        error_handling['try_catch_blocks'] = try_catch
        
        # Async error handling
        async_catch = len(re.findall(r'\.catch\s*\(|catch\s*\([^)]*\)\s*{[^}]*await', content))
        error_handling['async_error_handling'] = async_catch
        
        # Retry patterns
        retry = len(re.findall(r'retry|backoff|exponential', content, re.IGNORECASE))
        error_handling['retry_logic'] = retry
        
        # Circuit breaker patterns
        circuit = len(re.findall(r'circuit.*breaker|fallback|degraded', content, re.IGNORECASE))
        error_handling['circuit_breaker'] = circuit
        
        return error_handling

    def assess_implementation_quality(self, content: str) -> str:
        """Assess if implementation is real or mocked"""
        mock_score = sum(len(re.findall(pattern, content)) for pattern in self.patterns['mock'])
        real_score = sum(len(re.findall(pattern, content)) for pattern in self.patterns['real'])
        
        if mock_score > real_score * 2:
            return "MOSTLY_MOCKED"
        elif real_score > mock_score * 2:
            return "LIKELY_REAL"
        elif mock_score > 0 and real_score > 0:
            return "MIXED"
        else:
            return "UNCLEAR"

    def calculate_async_score(self, async_funcs: int, awaits: int, try_catch: int) -> float:
        """Calculate a quality score for async implementation"""
        if async_funcs == 0:
            return 0.0
        
        # Good async code has awaits and error handling
        await_ratio = min(awaits / (async_funcs * 2), 1.0)  # Expect ~2 awaits per async function
        error_ratio = min(try_catch / async_funcs, 1.0)  # Expect error handling
        
        return (await_ratio * 0.7 + error_ratio * 0.3) * 100

    def analyze_directory(self):
        """Main analysis function"""
        print(f"Enhanced Analysis of: {self.root_path}")
        print("=" * 80)
        
        for root, dirs, files in os.walk(self.root_path):
            # Skip node_modules and other non-relevant directories
            dirs[:] = [d for d in dirs if d not in ['node_modules', '.git', '.vscode', 'coverage', 'dist', 'build']]
            
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, self.root_path)
                
                try:
                    size = os.path.getsize(file_path)
                    self.stats['total_files'] += 1
                    self.stats['total_size'] += size
                    
                    # Track file types
                    ext = Path(file).suffix.lower()
                    self.stats['file_types'][ext] += 1
                    
                    # Analyze JavaScript/TypeScript files
                    if ext in ['.js', '.ts', '.jsx', '.tsx', '.mjs']:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            
                        analysis = self.analyze_javascript_file(file_path, content)
                        
                        # Store significant findings
                        if analysis['async_usage']['async_score'] > 70:
                            self.stats['async_patterns'].append({
                                'file': rel_path,
                                'score': analysis['async_usage']['async_score'],
                                'details': analysis['async_usage']
                            })
                        
                        if analysis['tool_usage']:
                            self.stats['tool_patterns'].append({
                                'file': rel_path,
                                'patterns': analysis['tool_usage']
                            })
                        
                        if analysis['api_calls'].get('ai_api_calls', 0) > 0:
                            self.stats['api_calls'].append({
                                'file': rel_path,
                                'calls': analysis['api_calls']
                            })
                        
                        if analysis['message_handling'].get('message_arrays', 0) > 0:
                            self.stats['message_patterns'].append({
                                'file': rel_path,
                                'patterns': analysis['message_handling']
                            })
                            
                except Exception as e:
                    print(f"Error processing {rel_path}: {e}")
        
        self.generate_report()

    def generate_report(self):
        """Generate comprehensive analysis report"""
        print("\n" + "=" * 80)
        print("ENHANCED ANALYSIS REPORT")
        print("=" * 80)
        
        # Basic stats
        print(f"\nTotal Files: {self.stats['total_files']}")
        print(f"Total Size: {self.stats['total_size']/1024/1024:.2f} MB")
        
        # Async implementation quality
        print("\n=== ASYNC IMPLEMENTATION ANALYSIS ===")
        if self.stats['async_patterns']:
            high_quality_async = [p for p in self.stats['async_patterns'] if p['score'] > 80]
            print(f"Files with proper async implementation: {len(high_quality_async)}/{len(self.stats['async_patterns'])}")
            for pattern in high_quality_async[:3]:
                print(f"  - {pattern['file']}: Score {pattern['score']:.1f}%")
                print(f"    Async functions: {pattern['details']['async_functions']}, Awaits: {pattern['details']['await_calls']}")
        else:
            print("  ⚠️ No significant async patterns found")
        
        # Tool/Function calling analysis
        print("\n=== TOOL/FUNCTION CALLING ANALYSIS ===")
        if self.stats['tool_patterns']:
            print(f"Files with tool patterns: {len(self.stats['tool_patterns'])}")
            for pattern in self.stats['tool_patterns'][:3]:
                print(f"  - {pattern['file']}:")
                for key, value in pattern['patterns'].items():
                    if value:
                        print(f"    {key}: {value}")
        else:
            print("  ⚠️ No tool calling patterns found")
        
        # API Integration analysis
        print("\n=== API INTEGRATION ANALYSIS ===")
        if self.stats['api_calls']:
            print(f"Files with API calls: {len(self.stats['api_calls'])}")
            total_ai_calls = sum(p['calls'].get('ai_api_calls', 0) for p in self.stats['api_calls'])
            print(f"Total AI API calls found: {total_ai_calls}")
            
            # Check for actual vs mock
            has_real_endpoints = any(
                p['calls'].get('anthropic_endpoints') or p['calls'].get('openai_endpoints') 
                for p in self.stats['api_calls']
            )
            
            if has_real_endpoints:
                print("  ✓ Real API endpoints detected")
            else:
                print("  ⚠️ No real API endpoints found - likely mocked")
        else:
            print("  ⚠️ No API integration found")
        
        # Message handling analysis
        print("\n=== MESSAGE FORMAT ANALYSIS ===")
        if self.stats['message_patterns']:
            print(f"Files handling messages: {len(self.stats['message_patterns'])}")
            total_arrays = sum(p['patterns'].get('message_arrays', 0) for p in self.stats['message_patterns'])
            total_tool_responses = sum(p['patterns'].get('tool_response_handling', 0) for p in self.stats['message_patterns'])
            
            print(f"Message array constructions: {total_arrays}")
            print(f"Tool response handling: {total_tool_responses}")
            
            if total_tool_responses > 0:
                print("  ✓ Appears to handle tool responses")
            else:
                print("  ⚠️ No tool response handling found")
        else:
            print("  ⚠️ No message handling patterns found")
        
        # Final verdict
        print("\n=== FINAL ASSESSMENT ===")
        
        real_indicators = 0
        mock_indicators = 0
        
        # Check various indicators
        if len(self.stats['async_patterns']) > 5:
            real_indicators += 1
        else:
            mock_indicators += 1
            
        if self.stats['api_calls'] and any(p['calls'].get('ai_api_calls', 0) > 0 for p in self.stats['api_calls']):
            real_indicators += 1
        else:
            mock_indicators += 1
            
        if self.stats['tool_patterns']:
            real_indicators += 1
        else:
            mock_indicators += 1
            
        if self.stats['message_patterns'] and any(p['patterns'].get('tool_response_handling', 0) > 0 for p in self.stats['message_patterns']):
            real_indicators += 1
        else:
            mock_indicators += 1
        
        print(f"Real Implementation Indicators: {real_indicators}/4")
        print(f"Mock Implementation Indicators: {mock_indicators}/4")
        
        if real_indicators > mock_indicators:
            print("\n✓ Package appears to have SOME real implementation")
            print("  However, verify that API calls aren't just returning mocked data")
        else:
            print("\n⚠️ Package appears to be MOSTLY MOCKED")
            print("  Limited or no real API integration detected")
            print("  Async patterns may be theatrical rather than functional")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        target_dir = sys.argv[1]
    else:
        target_dir = os.getcwd()
    
    if not os.path.exists(target_dir):
        print(f"Error: Directory {target_dir} does not exist")
        sys.exit(1)
    
    print("Enhanced Claude-Flow Package Analyzer v2.0")
    print("Analyzing async patterns, tool usage, and API integration")
    print("=" * 80)
    
    analyzer = EnhancedAnalyzer(target_dir)
    analyzer.analyze_directory()
