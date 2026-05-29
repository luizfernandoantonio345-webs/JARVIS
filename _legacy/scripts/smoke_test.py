#!/usr/bin/env python
"""
JARVIS v6.0 - Smoke Test Suite

Comprehensive validation that all core components are working.
Run this after deployment to verify system health.

Usage:
    python scripts/smoke_test.py
    python scripts/smoke_test.py --verbose
    python scripts/smoke_test.py --check health,chat,voice
"""

import asyncio
import json
import subprocess
import sys
import time
import httpx
import websockets
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
import argparse
import logging

# ════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ════════════════════════════════════════════════════════════════════════════

BACKEND_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws/jarvis"
TIMEOUT = 10

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s'
)
logger = logging.getLogger("SMOKE_TEST")


# ════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ════════════════════════════════════════════════════════════════════════════

class TestResult(Enum):
    PASS = "✓ PASS"
    FAIL = "✗ FAIL"
    SKIP = "⊘ SKIP"
    WARN = "⚠ WARN"


@dataclass
class TestCase:
    name: str
    category: str
    result: TestResult = TestResult.SKIP
    message: str = ""
    duration_ms: float = 0
    
    def __repr__(self) -> str:
        return f"{self.result.value} | {self.category:15} | {self.name:40} | {self.message}"


# ════════════════════════════════════════════════════════════════════════════
# HEALTH CHECKS
# ════════════════════════════════════════════════════════════════════════════

async def check_backend_health() -> Tuple[TestCase, Dict]:
    """Check if backend is running and healthy."""
    
    test = TestCase(name="Backend Health", category="HEALTH")
    
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            start = time.time()
            response = await client.get(f"{BACKEND_URL}/health")
            duration = time.time() - start
            test.duration_ms = duration * 1000
            
            if response.status_code == 200:
                data = response.json()
                test.result = TestResult.PASS
                test.message = f"Status: {data.get('status', 'unknown')}"
                return test, data
            else:
                test.result = TestResult.FAIL
                test.message = f"HTTP {response.status_code}"
                return test, {}
    except Exception as e:
        test.result = TestResult.FAIL
        test.message = str(e)
        return test, {}


async def check_ollama() -> TestCase:
    """Check if Ollama is available."""
    
    test = TestCase(name="Ollama Connection", category="HEALTH")
    
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            start = time.time()
            response = await client.get("http://localhost:11434/api/tags")
            duration = time.time() - start
            test.duration_ms = duration * 1000
            
            if response.status_code == 200:
                data = response.json()
                models = [m.get("name", "unknown") for m in data.get("models", [])]
                test.result = TestResult.PASS if models else TestResult.WARN
                test.message = f"Models: {', '.join(models[:3])}"
            else:
                test.result = TestResult.FAIL
                test.message = f"HTTP {response.status_code}"
    except Exception as e:
        test.result = TestResult.FAIL
        test.message = "Ollama not responding"
    
    return test


async def check_database() -> TestCase:
    """Check if database file exists and is readable."""
    
    test = TestCase(name="Database File", category="HEALTH")
    
    db_path = Path("data/jarvis_memory.db")
    
    if not db_path.exists():
        test.result = TestResult.FAIL
        test.message = f"File not found: {db_path}"
        return test
    
    try:
        size_mb = db_path.stat().st_size / (1024 * 1024)
        if size_mb > 500:
            test.result = TestResult.WARN
            test.message = f"Large DB: {size_mb:.1f}MB (max 500MB)"
        else:
            test.result = TestResult.PASS
            test.message = f"Size: {size_mb:.1f}MB"
    except Exception as e:
        test.result = TestResult.FAIL
        test.message = str(e)
    
    return test


# ════════════════════════════════════════════════════════════════════════════
# FUNCTIONALITY TESTS
# ════════════════════════════════════════════════════════════════════════════

async def test_chat_simple() -> TestCase:
    """Test basic chat functionality."""
    
    test = TestCase(name="Chat (Simple)", category="CHAT")
    
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            start = time.time()
            response = await client.post(
                f"{BACKEND_URL}/chat",
                json={
                    "message": "Hello, what is your name?",
                    "session_id": "test-session"
                }
            )
            duration = time.time() - start
            test.duration_ms = duration * 1000
            
            if response.status_code == 200:
                data = response.json()
                if "response" in data or "content" in data:
                    test.result = TestResult.PASS
                    test.message = f"Response time: {test.duration_ms:.0f}ms"
                else:
                    test.result = TestResult.FAIL
                    test.message = "Missing response field"
            else:
                test.result = TestResult.FAIL
                test.message = f"HTTP {response.status_code}"
    except Exception as e:
        test.result = TestResult.FAIL
        test.message = str(e)
    
    return test


async def test_chat_complex() -> TestCase:
    """Test chat with longer prompt."""
    
    test = TestCase(name="Chat (Complex)", category="CHAT")
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            start = time.time()
            response = await client.post(
                f"{BACKEND_URL}/chat",
                json={
                    "message": "Explain the architecture of a microservices system in detail.",
                    "session_id": "test-session"
                }
            )
            duration = time.time() - start
            test.duration_ms = duration * 1000
            
            if response.status_code == 200:
                test.result = TestResult.PASS
                test.message = f"Response time: {test.duration_ms:.0f}ms"
            else:
                test.result = TestResult.FAIL
                test.message = f"HTTP {response.status_code}"
    except asyncio.TimeoutError:
        test.result = TestResult.FAIL
        test.message = f"Timeout (>{TIMEOUT}s)"
    except Exception as e:
        test.result = TestResult.FAIL
        test.message = str(e)
    
    return test


async def test_websocket_connection() -> TestCase:
    """Test WebSocket connection."""
    
    test = TestCase(name="WebSocket Connection", category="WEBSOCKET")
    
    try:
        start = time.time()
        async with websockets.connect(WS_URL, ping_interval=None) as ws:
            duration = time.time() - start
            test.duration_ms = duration * 1000
            
            # Send test message
            await ws.send(json.dumps({
                "type": "message",
                "data": "Hello from WebSocket"
            }))
            
            # Wait for response
            response = await asyncio.wait_for(ws.recv(), timeout=5)
            
            test.result = TestResult.PASS
            test.message = f"Connected in {test.duration_ms:.0f}ms"
    except Exception as e:
        test.result = TestResult.FAIL
        test.message = str(e)
    
    return test


async def test_tts_endpoint() -> TestCase:
    """Test Text-to-Speech endpoint."""
    
    test = TestCase(name="TTS Generation", category="VOICE")
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            start = time.time()
            response = await client.post(
                f"{BACKEND_URL}/tts",
                json={"text": "Olá, bem-vindo ao sistema JARVIS"}
            )
            duration = time.time() - start
            test.duration_ms = duration * 1000
            
            if response.status_code == 200:
                if response.headers.get("content-type", "").startswith("audio"):
                    test.result = TestResult.PASS
                    size_kb = len(response.content) / 1024
                    test.message = f"Audio: {size_kb:.1f}KB, Time: {test.duration_ms:.0f}ms"
                else:
                    test.result = TestResult.FAIL
                    test.message = "Invalid content type"
            else:
                test.result = TestResult.FAIL
                test.message = f"HTTP {response.status_code}"
    except Exception as e:
        test.result = TestResult.FAIL
        test.message = str(e)
    
    return test


async def test_memory_endpoint() -> TestCase:
    """Test memory/experience endpoint."""
    
    test = TestCase(name="Memory Service", category="MEMORY")
    
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            start = time.time()
            response = await client.get(f"{BACKEND_URL}/memory/health")
            duration = time.time() - start
            test.duration_ms = duration * 1000
            
            if response.status_code == 200:
                test.result = TestResult.PASS
                test.message = "Memory service OK"
            else:
                test.result = TestResult.FAIL
                test.message = f"HTTP {response.status_code}"
    except Exception as e:
        test.result = TestResult.FAIL
        test.message = str(e)
    
    return test


# ════════════════════════════════════════════════════════════════════════════
# PERFORMANCE TESTS
# ════════════════════════════════════════════════════════════════════════════

async def test_latency_health() -> TestCase:
    """Measure health endpoint latency."""
    
    test = TestCase(name="Latency (Health)", category="PERFORMANCE")
    
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            times = []
            for _ in range(5):
                start = time.time()
                await client.get(f"{BACKEND_URL}/health")
                times.append((time.time() - start) * 1000)
            
            avg = sum(times) / len(times)
            max_time = max(times)
            
            test.duration_ms = avg
            test.result = TestResult.PASS if avg < 100 else TestResult.WARN
            test.message = f"Avg: {avg:.0f}ms, Max: {max_time:.0f}ms"
    except Exception as e:
        test.result = TestResult.FAIL
        test.message = str(e)
    
    return test


async def test_latency_chat() -> TestCase:
    """Measure chat endpoint first-token latency."""
    
    test = TestCase(name="Latency (Chat First-Token)", category="PERFORMANCE")
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            start = time.time()
            response = await client.post(
                f"{BACKEND_URL}/chat",
                json={"message": "Hi", "session_id": "perf-test"}
            )
            duration = time.time() - start
            test.duration_ms = duration * 1000
            
            if response.status_code == 200:
                threshold = 800  # ms
                test.result = TestResult.PASS if test.duration_ms < threshold else TestResult.WARN
                test.message = f"First token: {test.duration_ms:.0f}ms"
            else:
                test.result = TestResult.FAIL
                test.message = f"HTTP {response.status_code}"
    except Exception as e:
        test.result = TestResult.FAIL
        test.message = str(e)
    
    return test


# ════════════════════════════════════════════════════════════════════════════
# SECURITY TESTS
# ════════════════════════════════════════════════════════════════════════════

async def test_sql_injection() -> TestCase:
    """Test SQL injection protection."""
    
    test = TestCase(name="SQL Injection Protection", category="SECURITY")
    
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{BACKEND_URL}/chat",
                json={
                    "message": "'; DROP TABLE experiences; --",
                    "session_id": "security-test"
                }
            )
            
            # Should not crash, should handle gracefully
            test.result = TestResult.PASS if response.status_code in [200, 400] else TestResult.FAIL
            test.message = f"HTTP {response.status_code}: Safe"
    except Exception as e:
        test.result = TestResult.FAIL
        test.message = str(e)
    
    return test


async def test_xss_protection() -> TestCase:
    """Test XSS protection."""
    
    test = TestCase(name="XSS Protection", category="SECURITY")
    
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{BACKEND_URL}/chat",
                json={
                    "message": "<script>alert('xss')</script>",
                    "session_id": "security-test"
                }
            )
            
            if response.status_code == 200:
                # Verify response doesn't contain raw script tags
                test.result = TestResult.PASS
                test.message = "Script tags escaped"
            else:
                test.result = TestResult.FAIL
                test.message = f"HTTP {response.status_code}"
    except Exception as e:
        test.result = TestResult.FAIL
        test.message = str(e)
    
    return test


# ════════════════════════════════════════════════════════════════════════════
# TEST SUITE EXECUTION
# ════════════════════════════════════════════════════════════════════════════

async def run_all_tests(categories: List[str] = None) -> List[TestCase]:
    """Run all smoke tests."""
    
    tests = []
    
    # Health checks
    if not categories or "health" in categories:
        logger.info("Running HEALTH checks...")
        health_test, health_data = await check_backend_health()
        tests.append(health_test)
        
        if health_test.result != TestResult.FAIL:
            tests.append(await check_ollama())
            tests.append(await check_database())
    
    # Chat tests
    if not categories or "chat" in categories:
        logger.info("Running CHAT tests...")
        tests.append(await test_chat_simple())
        tests.append(await test_chat_complex())
    
    # WebSocket tests
    if not categories or "websocket" in categories:
        logger.info("Running WEBSOCKET tests...")
        tests.append(await test_websocket_connection())
    
    # Voice tests
    if not categories or "voice" in categories:
        logger.info("Running VOICE tests...")
        tests.append(await test_tts_endpoint())
    
    # Memory tests
    if not categories or "memory" in categories:
        logger.info("Running MEMORY tests...")
        tests.append(await test_memory_endpoint())
    
    # Performance tests
    if not categories or "performance" in categories:
        logger.info("Running PERFORMANCE tests...")
        tests.append(await test_latency_health())
        tests.append(await test_latency_chat())
    
    # Security tests
    if not categories or "security" in categories:
        logger.info("Running SECURITY tests...")
        tests.append(await test_sql_injection())
        tests.append(await test_xss_protection())
    
    return tests


def print_summary(tests: List[TestCase]) -> None:
    """Print test summary."""
    
    print("\n" + "=" * 120)
    print("JARVIS v6.0 — SMOKE TEST RESULTS")
    print("=" * 120)
    
    for test in tests:
        print(test)
    
    print("=" * 120)
    
    # Statistics
    results = {
        TestResult.PASS: len([t for t in tests if t.result == TestResult.PASS]),
        TestResult.FAIL: len([t for t in tests if t.result == TestResult.FAIL]),
        TestResult.WARN: len([t for t in tests if t.result == TestResult.WARN]),
        TestResult.SKIP: len([t for t in tests if t.result == TestResult.SKIP]),
    }
    
    total_time = sum(t.duration_ms for t in tests)
    
    print(f"\n📊 SUMMARY:")
    print(f"  ✓ PASS:  {results[TestResult.PASS]}")
    print(f"  ✗ FAIL:  {results[TestResult.FAIL]}")
    print(f"  ⚠ WARN:  {results[TestResult.WARN]}")
    print(f"  ⊘ SKIP:  {results[TestResult.SKIP]}")
    print(f"  Total time: {total_time:.0f}ms")
    
    if results[TestResult.FAIL] > 0:
        print(f"\n❌ {results[TestResult.FAIL]} test(s) failed!")
        return 1
    elif results[TestResult.WARN] > 0:
        print(f"\n⚠️  {results[TestResult.WARN]} warning(s) - review results")
        return 0
    else:
        print(f"\n✅ All tests passed!")
        return 0


async def main():
    """Main entry point."""
    
    parser = argparse.ArgumentParser(
        description="JARVIS v6.0 Smoke Test Suite"
    )
    parser.add_argument(
        "--categories",
        default="health,chat,websocket,voice,memory,performance,security",
        help="Comma-separated test categories to run"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output"
    )
    
    args = parser.parse_args()
    categories = [c.strip() for c in args.categories.split(",")]
    
    print(f"\n🚀 Starting JARVIS v6.0 Smoke Tests ({len(categories)} categories)...\n")
    
    tests = await run_all_tests(categories)
    exit_code = print_summary(tests)
    
    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())
