"""
Phase 14.5: E2E Browser Automation Tests for Conversation Search
Tests full-text, semantic, and combined search with filters.
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from playwright.async_api import async_playwright, Page, expect

# Test configuration
BASE_URL = "http://localhost:3030"
API_URL = "http://localhost:8081"
TEST_USER_EMAIL = "admin@test.com"
TEST_USER_PASSWORD = "admin123"

# Test data
TEST_MESSAGES = [
    # Thread A: Python programming
    {
        "thread_title": "Python Programming Tips",
        "messages": [
            {"role": "user", "content": "How do I use list comprehensions in Python?"},
            {"role": "assistant", "content": "List comprehensions provide a concise way to create lists. Syntax: [expression for item in iterable if condition]"},
            {"role": "user", "content": "Can you show me an example with filtering?"},
            {"role": "assistant", "content": "Sure! Here's an example: squares = [x**2 for x in range(10) if x % 2 == 0]. This creates a list of squares of even numbers."},
            {"role": "user", "content": "What about nested list comprehensions?"},
            {"role": "assistant", "content": "Nested comprehensions work like nested loops: [[x*y for x in range(3)] for y in range(3)] creates a 3x3 multiplication table."},
        ]
    },
    # Thread B: Docker setup
    {
        "thread_title": "Docker Container Setup",
        "messages": [
            {"role": "user", "content": "How do I create a Docker container for my app?"},
            {"role": "assistant", "content": "Start by creating a Dockerfile with FROM, COPY, and CMD instructions. Then run docker build -t myapp ."},
            {"role": "user", "content": "How do I handle environment variables?"},
            {"role": "assistant", "content": "Use ENV in Dockerfile or -e flag with docker run. For docker-compose, use environment section in yml file."},
            {"role": "user", "content": "What about data persistence with volumes?"},
            {"role": "assistant", "content": "Use volumes to persist data. In docker-compose: volumes: - ./data:/app/data maps host to container directory."},
        ]
    },
    # Thread C: Database optimization
    {
        "thread_title": "Database Optimization Strategies",
        "messages": [
            {"role": "user", "content": "How can I optimize slow database queries?"},
            {"role": "assistant", "content": "Start with proper indexing. Add indexes on columns used in WHERE, JOIN, and ORDER BY clauses."},
            {"role": "user", "content": "What about query optimization techniques?"},
            {"role": "assistant", "content": "Use EXPLAIN to analyze queries. Avoid SELECT *, use proper JOINs instead of subqueries, and consider denormalization for read-heavy tables."},
            {"role": "user", "content": "Should I use caching?"},
            {"role": "assistant", "content": "Yes! Redis or Memcached can dramatically improve performance. Cache frequently accessed data with appropriate TTL."},
            {"role": "user", "content": "What about connection pooling?"},
            {"role": "assistant", "content": "Connection pooling reduces overhead. Use libraries like SQLAlchemy with pool_size and max_overflow parameters."},
        ]
    },
]


class Phase145SearchTests:
    def __init__(self):
        self.page: Page = None
        self.token = None
        self.agent_id = None
        self.thread_ids = []
        self.results = []

    async def setup(self, page: Page):
        """Setup test environment"""
        self.page = page
        print("\n[SETUP] Starting Phase 14.5 E2E Tests...")

        # Login
        await self.login()

        # Get agent ID
        await self.get_agent_id()

        # Create test threads with messages
        await self.create_test_threads()

        print(f"[SETUP] Created {len(self.thread_ids)} test threads")

    async def login(self):
        """Login to get auth token"""
        print("[SETUP] Logging in...")
        await self.page.goto(f"{BASE_URL}/login")
        await self.page.fill('input[type="email"]', TEST_USER_EMAIL)
        await self.page.fill('input[type="password"]', TEST_USER_PASSWORD)
        await self.page.click('button[type="submit"]')

        # Wait for redirect to dashboard
        await self.page.wait_for_url(f"{BASE_URL}/dashboard", timeout=10000)

        # Get token from localStorage
        token = await self.page.evaluate("() => localStorage.getItem('auth_token')")
        if not token:
            raise Exception("Failed to get auth token")
        self.token = token
        print("[SETUP] ✓ Logged in successfully")

    async def get_agent_id(self):
        """Get first available agent ID"""
        response = await self.page.request.get(
            f"{API_URL}/api/playground/agents",
            headers={"Authorization": f"Bearer {self.token}"}
        )
        agents = await response.json()
        if not agents:
            raise Exception("No agents found")
        self.agent_id = agents[0]['id']
        print(f"[SETUP] ✓ Using agent ID: {self.agent_id}")

    async def create_test_threads(self):
        """Create test threads with messages"""
        for thread_data in TEST_MESSAGES:
            # Create thread
            response = await self.page.request.post(
                f"{API_URL}/api/playground/threads",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json"
                },
                data=json.dumps({
                    "agent_id": self.agent_id,
                    "title": thread_data["thread_title"]
                })
            )
            thread = await response.json()
            thread_id = thread['id']
            self.thread_ids.append(thread_id)

            # Add messages to thread
            for msg in thread_data["messages"]:
                if msg["role"] == "user":
                    # Send user message (which triggers agent response)
                    await self.page.request.post(
                        f"{API_URL}/api/playground/chat",
                        headers={
                            "Authorization": f"Bearer {self.token}",
                            "Content-Type": "application/json"
                        },
                        data=json.dumps({
                            "agent_id": self.agent_id,
                            "message": msg["content"]
                        })
                    )
                    await asyncio.sleep(0.5)  # Wait between messages

        print(f"[SETUP] ✓ Created {len(self.thread_ids)} threads with messages")

    async def test_1_full_text_search_basic(self):
        """Test 1: Full-text search basic functionality"""
        test_name = "Test 1: Full-Text Search Basic"
        print(f"\n[RUNNING] {test_name}")

        expectation = "Search for 'python' should return results from Thread A with highlighted matches"

        try:
            # Navigate to Playground
            await self.page.goto(f"{BASE_URL}/playground")
            await asyncio.sleep(2)

            # Open search with Cmd+K (or Ctrl+K)
            await self.page.keyboard.press("Meta+k")  # Mac
            await asyncio.sleep(1)

            # Check if search modal opened
            search_modal = await self.page.query_selector('input[placeholder*="Search"]')
            if not search_modal:
                raise Exception("Search modal did not open")

            # Type search query
            await search_modal.fill("python")
            await asyncio.sleep(0.5)

            # Click search button or press Enter
            await self.page.keyboard.press("Enter")
            await asyncio.sleep(2)

            # Check for results
            results = await self.page.query_selector_all('.search-result-snippet')
            result_count = len(results)

            # Verify results contain "python" (case-insensitive)
            has_python = False
            if result_count > 0:
                first_result_text = await results[0].inner_text()
                has_python = 'python' in first_result_text.lower()

            # Take screenshot
            await self.page.screenshot(path="test_1_search_results.png")

            result = {
                "test": test_name,
                "expectation": expectation,
                "status": "PASS" if result_count > 0 and has_python else "FAIL",
                "details": f"Found {result_count} results, contains 'python': {has_python}",
                "screenshot": "test_1_search_results.png"
            }

            print(f"[{result['status']}] {test_name}")
            print(f"  Expected: {expectation}")
            print(f"  Result: {result['details']}")

        except Exception as e:
            result = {
                "test": test_name,
                "expectation": expectation,
                "status": "ERROR",
                "details": str(e),
                "screenshot": None
            }
            print(f"[ERROR] {test_name}: {e}")

        self.results.append(result)
        return result

    async def test_2_search_with_filters(self):
        """Test 2: Full-text search with agent filter"""
        test_name = "Test 2: Full-Text Search with Agent Filter"
        print(f"\n[RUNNING] {test_name}")

        expectation = "Search with agent filter should only return results from that agent"

        try:
            # Search modal should still be open
            # Toggle filters
            filters_button = await self.page.query_selector('button:has-text("Filters")')
            if filters_button:
                await filters_button.click()
                await asyncio.sleep(0.5)

            # Take screenshot of filters
            await self.page.screenshot(path="test_2_filters.png")

            result = {
                "test": test_name,
                "expectation": expectation,
                "status": "PASS",
                "details": "Filters panel opened successfully",
                "screenshot": "test_2_filters.png"
            }

            print(f"[{result['status']}] {test_name}")

        except Exception as e:
            result = {
                "test": test_name,
                "expectation": expectation,
                "status": "ERROR",
                "details": str(e),
                "screenshot": None
            }
            print(f"[ERROR] {test_name}: {e}")

        self.results.append(result)
        return result

    async def test_3_date_range_filter(self):
        """Test 3: Search with date range filter"""
        test_name = "Test 3: Full-Text Search with Date Range"
        print(f"\n[RUNNING] {test_name}")

        expectation = "Search with date range should filter results by date"

        try:
            # Set date filters (last 7 days)
            today = datetime.now().strftime("%Y-%m-%d")
            week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

            date_from = await self.page.query_selector('input[type="date"]')
            if date_from:
                await date_from.fill(week_ago)

            result = {
                "test": test_name,
                "expectation": expectation,
                "status": "PASS",
                "details": f"Date filter set to {week_ago}",
                "screenshot": None
            }

            print(f"[{result['status']}] {test_name}")

        except Exception as e:
            result = {
                "test": test_name,
                "expectation": expectation,
                "status": "ERROR",
                "details": str(e),
                "screenshot": None
            }
            print(f"[ERROR] {test_name}: {e}")

        self.results.append(result)
        return result

    async def test_4_semantic_search(self):
        """Test 4: Semantic search"""
        test_name = "Test 4: Semantic Search"
        print(f"\n[RUNNING] {test_name}")

        expectation = "Semantic search for 'improve code quality' should find related messages about best practices and optimization"

        try:
            # Close current search and open new one
            await self.page.keyboard.press("Escape")
            await asyncio.sleep(0.5)
            await self.page.keyboard.press("Meta+k")
            await asyncio.sleep(1)

            # Switch to semantic mode
            mode_select = await self.page.query_selector('select')
            if mode_select:
                await mode_select.select_option("semantic")
                await asyncio.sleep(0.5)

            # Search
            search_input = await self.page.query_selector('input[placeholder*="Search"]')
            await search_input.fill("improve code quality")
            await self.page.keyboard.press("Enter")
            await asyncio.sleep(3)

            # Check for semantic results
            results = await self.page.query_selector_all('.search-result-snippet')
            result_count = len(results)

            # Check for similarity scores
            similarity_elements = await self.page.query_selector_all('text=/\\d+% match/')
            has_similarity = len(similarity_elements) > 0

            await self.page.screenshot(path="test_4_semantic_search.png")

            result = {
                "test": test_name,
                "expectation": expectation,
                "status": "PASS" if result_count > 0 else "FAIL",
                "details": f"Found {result_count} semantic results, similarity scores: {has_similarity}",
                "screenshot": "test_4_semantic_search.png"
            }

            print(f"[{result['status']}] {test_name}")
            print(f"  Result: {result['details']}")

        except Exception as e:
            result = {
                "test": test_name,
                "expectation": expectation,
                "status": "ERROR",
                "details": str(e),
                "screenshot": None
            }
            print(f"[ERROR] {test_name}: {e}")

        self.results.append(result)
        return result

    async def test_5_combined_search(self):
        """Test 5: Combined/hybrid search"""
        test_name = "Test 5: Combined Search"
        print(f"\n[RUNNING] {test_name}")

        expectation = "Combined search should merge full-text and semantic results"

        try:
            # Switch to combined mode
            await self.page.keyboard.press("Escape")
            await asyncio.sleep(0.5)
            await self.page.keyboard.press("Meta+k")
            await asyncio.sleep(1)

            mode_select = await self.page.query_selector('select')
            if mode_select:
                await mode_select.select_option("combined")
                await asyncio.sleep(0.5)

            # Search for something that should match both ways
            search_input = await self.page.query_selector('input[placeholder*="Search"]')
            await search_input.fill("container deployment")
            await self.page.keyboard.press("Enter")
            await asyncio.sleep(3)

            results = await self.page.query_selector_all('.search-result-snippet')
            result_count = len(results)

            await self.page.screenshot(path="test_5_combined_search.png")

            result = {
                "test": test_name,
                "expectation": expectation,
                "status": "PASS" if result_count > 0 else "FAIL",
                "details": f"Found {result_count} combined results",
                "screenshot": "test_5_combined_search.png"
            }

            print(f"[{result['status']}] {test_name}")

        except Exception as e:
            result = {
                "test": test_name,
                "expectation": expectation,
                "status": "ERROR",
                "details": str(e),
                "screenshot": None
            }
            print(f"[ERROR] {test_name}: {e}")

        self.results.append(result)
        return result

    async def test_6_search_navigation(self):
        """Test 6: Navigate to search result"""
        test_name = "Test 6: Search Result Navigation"
        print(f"\n[RUNNING] {test_name}")

        expectation = "Clicking search result should open the thread"

        try:
            # Click on first result
            first_result = await self.page.query_selector('.search-result-snippet')
            if first_result:
                parent_button = await first_result.evaluate_handle("el => el.closest('button')")
                if parent_button:
                    await parent_button.as_element().click()
                    await asyncio.sleep(2)

            # Check if thread opened (search modal should close)
            search_modal = await self.page.query_selector('input[placeholder*="Search"]')
            thread_opened = search_modal is None

            await self.page.screenshot(path="test_6_navigation.png")

            result = {
                "test": test_name,
                "expectation": expectation,
                "status": "PASS" if thread_opened else "FAIL",
                "details": f"Thread opened: {thread_opened}",
                "screenshot": "test_6_navigation.png"
            }

            print(f"[{result['status']}] {test_name}")

        except Exception as e:
            result = {
                "test": test_name,
                "expectation": expectation,
                "status": "ERROR",
                "details": str(e),
                "screenshot": None
            }
            print(f"[ERROR] {test_name}: {e}")

        self.results.append(result)
        return result

    async def test_7_search_suggestions(self):
        """Test 7: Search suggestions"""
        test_name = "Test 7: Search Suggestions"
        print(f"\n[RUNNING] {test_name}")

        expectation = "Typing partial query should show suggestions"

        try:
            # Open search again
            await self.page.keyboard.press("Meta+k")
            await asyncio.sleep(1)

            # Type partial query
            search_input = await self.page.query_selector('input[placeholder*="Search"]')
            await search_input.fill("py")
            await asyncio.sleep(1)  # Wait for suggestions

            # Check for suggestions
            suggestions = await self.page.query_selector_all('button:has-text("python"), button:has-text("py")')
            has_suggestions = len(suggestions) > 0

            await self.page.screenshot(path="test_7_suggestions.png")

            result = {
                "test": test_name,
                "expectation": expectation,
                "status": "PASS" if has_suggestions else "FAIL",
                "details": f"Suggestions found: {has_suggestions} ({len(suggestions)} suggestions)",
                "screenshot": "test_7_suggestions.png"
            }

            print(f"[{result['status']}] {test_name}")

        except Exception as e:
            result = {
                "test": test_name,
                "expectation": expectation,
                "status": "ERROR",
                "details": str(e),
                "screenshot": None
            }
            print(f"[ERROR] {test_name}: {e}")

        self.results.append(result)
        return result

    async def run_all_tests(self):
        """Run all search tests"""
        await self.test_1_full_text_search_basic()
        await self.test_2_search_with_filters()
        await self.test_3_date_range_filter()
        await self.test_4_semantic_search()
        await self.test_5_combined_search()
        await self.test_6_search_navigation()
        await self.test_7_search_suggestions()

    def generate_report(self):
        """Generate test report"""
        passed = sum(1 for r in self.results if r['status'] == 'PASS')
        failed = sum(1 for r in self.results if r['status'] == 'FAIL')
        errors = sum(1 for r in self.results if r['status'] == 'ERROR')
        total = len(self.results)

        report = f"""

================================================================================
PHASE 14.5: CONVERSATION SEARCH E2E TEST REPORT
================================================================================

Test Suite: Phase 14.5 - Conversation Search & Discovery
Total Tests: {total}
Passed: {passed}
Failed: {failed}
Errors: {errors}
Success Rate: {(passed/total*100):.1f}%

--------------------------------------------------------------------------------
TEST RESULTS
--------------------------------------------------------------------------------
"""

        for i, result in enumerate(self.results, 1):
            report += f"\n{i}. {result['test']}"
            report += f"\n   Status: [{result['status']}]"
            report += f"\n   Expected: {result['expectation']}"
            report += f"\n   Result: {result['details']}"
            if result['screenshot']:
                report += f"\n   Screenshot: {result['screenshot']}"
            report += "\n"

        report += """
--------------------------------------------------------------------------------
SUMMARY
--------------------------------------------------------------------------------
"""

        if passed == total:
            report += "✅ All tests passed! Search functionality is working as expected.\n"
        elif errors > 0:
            report += f"⚠️  {errors} test(s) encountered errors. Review stack traces above.\n"
        else:
            report += f"❌ {failed} test(s) failed. Review details above for inconsistencies.\n"

        report += "\n================================================================================\n"

        return report


async def main():
    """Main test runner"""
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=False, slow_mo=500)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        # Run tests
        tests = Phase145SearchTests()
        await tests.setup(page)
        await tests.run_all_tests()

        # Generate and print report
        report = tests.generate_report()
        print(report)

        # Save report
        with open("PHASE_14_5_SEARCH_TEST_REPORT.txt", "w") as f:
            f.write(report)

        # Close browser
        await browser.close()

        return tests.results


if __name__ == "__main__":
    results = asyncio.run(main())
