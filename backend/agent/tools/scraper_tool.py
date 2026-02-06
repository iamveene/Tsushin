"""
Web Scraping Tool - Extract text and data from web pages

Provides safe, rate-limited web scraping with robots.txt compliance.
"""

import requests
from bs4 import BeautifulSoup
import logging
import time
from typing import Dict, Optional
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser
import re


class ScraperTool:
    """Tool for safe web scraping"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.user_agent = "WhatsAppBot/1.0 (Educational Purpose)"
        self.last_request_time = {}
        self.rate_limit_seconds = 2  # Minimum 2 seconds between requests to same domain
        self.timeout = 10
        self.max_content_length = 1_000_000  # 1MB max

    def _can_fetch(self, url: str) -> bool:
        """
        Check if URL can be fetched according to robots.txt

        Args:
            url: URL to check

        Returns:
            True if allowed, False otherwise
        """
        try:
            parsed = urlparse(url)
            robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

            rp = RobotFileParser()
            rp.set_url(robots_url)
            rp.read()

            return rp.can_fetch(self.user_agent, url)

        except Exception as e:
            self.logger.warning(f"Could not check robots.txt for {url}: {e}")
            # If we can't check robots.txt, be conservative and allow
            return True

    def _respect_rate_limit(self, domain: str):
        """
        Enforce rate limiting per domain

        Args:
            domain: Domain name to rate limit
        """
        if domain in self.last_request_time:
            elapsed = time.time() - self.last_request_time[domain]
            if elapsed < self.rate_limit_seconds:
                wait_time = self.rate_limit_seconds - elapsed
                time.sleep(wait_time)

        self.last_request_time[domain] = time.time()

    def _is_safe_url(self, url: str) -> tuple[bool, str]:
        """
        Check if URL is safe to scrape

        Args:
            url: URL to validate

        Returns:
            Tuple of (is_safe, error_message)
        """
        try:
            parsed = urlparse(url)

            # Check scheme
            if parsed.scheme not in ('http', 'https'):
                return False, "Only HTTP and HTTPS URLs are allowed"

            # Block localhost and private IPs
            hostname = parsed.hostname
            if not hostname:
                return False, "Invalid URL"

            if hostname in ('localhost', '127.0.0.1', '0.0.0.0'):
                return False, "Cannot scrape localhost"

            # Block private IP ranges
            if hostname.startswith('192.168.') or hostname.startswith('10.') or hostname.startswith('172.'):
                return False, "Cannot scrape private IP addresses"

            return True, ""

        except Exception as e:
            return False, f"Invalid URL: {str(e)}"

    def fetch_url(self, url: str) -> Dict:
        """
        Fetch and parse a web page

        Args:
            url: URL to scrape

        Returns:
            Dictionary with extracted data or error
        """
        # Validate URL
        is_safe, error = self._is_safe_url(url)
        if not is_safe:
            return {"error": error}

        # Check robots.txt
        if not self._can_fetch(url):
            return {"error": f"robots.txt disallows scraping of {url}"}

        try:
            parsed = urlparse(url)
            domain = parsed.netloc

            # Respect rate limits
            self._respect_rate_limit(domain)

            # Make request
            headers = {
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9"
            }

            response = requests.get(
                url,
                headers=headers,
                timeout=self.timeout,
                allow_redirects=True,
                stream=True
            )

            # Check content length
            content_length = response.headers.get('content-length')
            if content_length and int(content_length) > self.max_content_length:
                return {"error": f"Content too large (max {self.max_content_length/1000000}MB)"}

            response.raise_for_status()

            # Parse HTML
            soup = BeautifulSoup(response.content, 'html.parser')

            # Extract text
            text = self.extract_text(str(soup))

            # Extract metadata
            title = soup.find('title')
            title_text = title.get_text().strip() if title else ""

            description_meta = soup.find('meta', attrs={'name': 'description'})
            description = description_meta.get('content', '') if description_meta else ""

            return {
                "success": True,
                "url": url,
                "title": title_text,
                "description": description,
                "text": text[:5000],  # Limit to first 5000 chars
                "text_length": len(text),
                "status_code": response.status_code
            }

        except requests.exceptions.HTTPError as e:
            return {"error": f"HTTP error {e.response.status_code}: {e.response.reason}"}

        except requests.exceptions.Timeout:
            return {"error": f"Request timed out after {self.timeout} seconds"}

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request failed for {url}: {e}")
            return {"error": f"Failed to fetch URL: {str(e)}"}

        except Exception as e:
            self.logger.error(f"Unexpected error scraping {url}: {e}", exc_info=True)
            return {"error": f"Unexpected error: {str(e)}"}

    def extract_text(self, html: str) -> str:
        """
        Extract clean text from HTML

        Args:
            html: HTML content

        Returns:
            Extracted text
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Remove script and style elements
            for script in soup(['script', 'style', 'nav', 'footer', 'header']):
                script.decompose()

            # Get text
            text = soup.get_text()

            # Clean up whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)

            return text

        except Exception as e:
            self.logger.error(f"Error extracting text: {e}")
            return ""

    def extract_structured_data(self, html: str) -> Dict:
        """
        Extract structured data from HTML (links, images, headings)

        Args:
            html: HTML content

        Returns:
            Dictionary with structured data
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Extract headings
            headings = []
            for level in range(1, 7):
                for heading in soup.find_all(f'h{level}'):
                    headings.append({
                        'level': level,
                        'text': heading.get_text().strip()
                    })

            # Extract links
            links = []
            for link in soup.find_all('a', href=True):
                links.append({
                    'text': link.get_text().strip(),
                    'href': link['href']
                })

            # Extract images
            images = []
            for img in soup.find_all('img', src=True):
                images.append({
                    'src': img['src'],
                    'alt': img.get('alt', '')
                })

            return {
                "headings": headings[:20],  # Limit to 20
                "links": links[:50],  # Limit to 50
                "images": images[:20]  # Limit to 20
            }

        except Exception as e:
            self.logger.error(f"Error extracting structured data: {e}")
            return {"headings": [], "links": [], "images": []}

    def format_scrape_result(self, scrape_data: Dict) -> str:
        """
        Format scraping result into human-readable string

        Args:
            scrape_data: Data from fetch_url()

        Returns:
            Formatted string
        """
        if "error" in scrape_data:
            return f"❌ {scrape_data['error']}"

        formatted = f"""🌐 **{scrape_data['title']}**

📝 Description: {scrape_data.get('description', 'N/A')}

🔗 URL: {scrape_data['url']}

📄 Content Preview:
{scrape_data['text'][:1000]}...

Total content length: {scrape_data['text_length']} characters"""

        return formatted
