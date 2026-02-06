"""
Search Tool - Web search using Brave Search API

Provides web search capabilities with result summarization.
"""

import requests
import os
import logging
from typing import Dict, Optional
from sqlalchemy.orm import Session
from services.api_key_service import get_api_key


class SearchTool:
    """Tool for web search using Brave Search API"""

    def __init__(self, api_key: Optional[str] = None, db: Optional[Session] = None):
        """
        Initialize Search Tool

        Args:
            api_key: Brave Search API key (optional, overrides database/env)
            db: Database session for loading API key (Phase 4.6)
        """
        # Priority: explicit api_key > database (env var fallback removed)
        if api_key:
            self.api_key = api_key
        elif db:
            self.api_key = get_api_key('brave_search', db)
        else:
            self.api_key = None

        self.base_url = "https://api.search.brave.com/res/v1/web/search"
        self.logger = logging.getLogger(__name__)

        if not self.api_key:
            self.logger.warning("Brave Search API key not configured")

    def search(self, query: str, count: int = 5) -> Dict:
        """
        Perform web search

        Args:
            query: Search query
            count: Number of results to return (default 5, max 20)

        Returns:
            Dictionary with search results or error
        """
        if not self.api_key:
            return {
                "error": "Search API key not configured. Configure Brave Search in Hub → Tool APIs."
            }

        try:
            headers = {
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": self.api_key
            }

            params = {
                "q": query,
                "count": min(count, 20)
            }

            response = requests.get(
                self.base_url,
                headers=headers,
                params=params,
                timeout=10
            )
            response.raise_for_status()

            data = response.json()

            # Extract relevant results
            results = []
            if "web" in data and "results" in data["web"]:
                for item in data["web"]["results"][:count]:
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "description": item.get("description", "")
                    })

            return {
                "success": True,
                "query": query,
                "results": results,
                "result_count": len(results)
            }

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                return {"error": "Invalid API key"}
            elif e.response.status_code == 429:
                return {"error": "Rate limit exceeded. Please try again later."}
            else:
                return {"error": f"Search API error: {e.response.status_code}"}

        except requests.exceptions.Timeout:
            return {"error": "Search request timed out"}

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Search request failed: {e}")
            return {"error": f"Failed to perform search: {str(e)}"}

        except Exception as e:
            self.logger.error(f"Unexpected error in search tool: {e}", exc_info=True)
            return {"error": f"Unexpected error: {str(e)}"}

    def format_search_results(self, search_data: Dict) -> str:
        """
        Format search results into human-readable string

        Args:
            search_data: Data from search()

        Returns:
            Formatted string
        """
        if "error" in search_data:
            return f"❌ {search_data['error']}"

        if not search_data.get("results"):
            return f"🔍 No results found for: {search_data.get('query', '')}"

        formatted = f"🔍 **Search Results for:** {search_data['query']}\n\n"
        formatted += f"Found {search_data['result_count']} results:\n\n"

        for i, result in enumerate(search_data['results'], 1):
            formatted += f"**{i}. {result['title']}**\n"
            formatted += f"🔗 {result['url']}\n"
            if result['description']:
                formatted += f"📝 {result['description']}\n"
            formatted += "\n"

        return formatted
