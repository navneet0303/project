import requests
from bs4 import BeautifulSoup
import urllib.parse
import re
import logging

# Set up logging for this module
logger = logging.getLogger("automarketer.scraper")

# A collection of modern User-Agents to alternate and avoid blocks
USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    # Chrome on Android (Mobile)
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
]

def clean_url(url):
    """Ensure the URL has a scheme (http/https)."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url

def extract_fallback_info(url):
    """
    Generate heuristic fallback title and content from the URL
    if requests are completely blocked or offline.
    """
    try:
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc.replace("www.", "")
        # Get brand name by capitalizing domain without extension
        brand_name = domain.split(".")[0].capitalize()
        
        # Parse path for keywords
        path_parts = [p for p in parsed.path.split("/") if p]
        keywords = []
        for part in path_parts:
            # Clean symbols and split CamelCase/hyphens
            clean_part = re.sub(r"[_\-+]", " ", part)
            clean_part = re.sub(r"([a-z])([A-Z])", r"\1 \2", clean_part)
            keywords.extend(clean_part.split())
        
        keywords = [kw.capitalize() for kw in keywords if len(kw) > 1]
        
        if keywords:
            topic = " ".join(keywords)
            title = f"{brand_name} - {topic}"
            content = f"Official online portal for {brand_name} regarding {topic}. Discover features, premium offers, details, services, and products directly on {domain}."
        else:
            title = brand_name
            content = f"Welcome to {brand_name}. Explore services, offerings, and updates on our official website at {domain}."
            
        return {
            "title": title,
            "content": content,
            "source": "fallback_url_heuristics",
            "domain": domain
        }
    except Exception as e:
        logger.error(f"Error extracting URL heuristics: {e}")
        return {
            "title": "Marketing Campaign",
            "content": "Professional brand campaign featuring premium services, innovative solutions, and top-tier product offerings.",
            "source": "fallback_default",
            "domain": "brand"
        }

def scrape_website(url):
    """
    Scrape a website with retry, multiple user agents, metadata extraction,
    and a robust fallback strategy to ensure zero crashes.
    """
    url = clean_url(url)
    
    # Try fetching with multiple user agents
    for attempt, user_agent in enumerate(USER_AGENTS):
        try:
            headers = {
                "User-Agent": user_agent,
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Connection": "keep-alive",
                "Referer": "https://www.google.com/"
            }

            logger.info(f"Attempting live scrape for {url} (Attempt {attempt + 1}/{len(USER_AGENTS)})...")
            response = requests.get(
                url,
                headers=headers,
                timeout=12,
                allow_redirects=True,
                stream=True
            )
            
            # If we get a blocking code (like 403, 401, 503) and we have more attempts, retry
            if response.status_code in [403, 401, 503, 429] and attempt < len(USER_AGENTS) - 1:
                logger.warning(f"Received block code {response.status_code}. Retrying with different agent...")
                continue
                
            response.raise_for_status()
            
            # Validate Content-Type to prevent parsing binary or huge data formats
            content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" not in content_type:
                logger.warning(f"Unsupported content type '{content_type}' for {url}. Live scraping skipped.")
                raise ValueError(f"Content type '{content_type}' is not HTML.")
                
            # Limit download size to 5MB to prevent memory exhaustion
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > 5 * 1024 * 1024:
                raise ValueError(f"HTML size exceeds the 5MB safety limit ({int(content_length)} bytes).")
                
            # Stream the content in chunks to monitor actual size
            html_chunks = []
            total_bytes = 0
            max_bytes = 5 * 1024 * 1024
            
            for chunk in response.iter_content(chunk_size=16384, decode_unicode=True):
                if isinstance(chunk, bytes):
                    chunk = chunk.decode(response.encoding or "utf-8", errors="ignore")
                html_chunks.append(chunk)
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    logger.warning("HTML body exceeded 5MB safety limit during stream. Truncating.")
                    break
                    
            html_text = "".join(html_chunks)
            
            # Parse HTML
            soup = BeautifulSoup(html_text, "html.parser")
            
            # Extract Meta description / OG description (often highly curated marketing summaries!)
            meta_desc = ""
            og_desc = ""
            meta_tags = soup.find_all("meta")
            for tag in meta_tags:
                attrs = tag.attrs
                if "name" in attrs and attrs["name"].lower() == "description":
                    meta_desc = attrs.get("content", "").strip()
                elif "property" in attrs and attrs["property"].lower() == "og:description":
                    og_desc = attrs.get("content", "").strip()
                elif "name" in attrs and attrs["name"].lower() == "og:description":
                    og_desc = attrs.get("content", "").strip()
            
            # Decompose boilerplate scripts and styles
            for tag in soup(["script", "style", "noscript", "iframe", "footer", "header", "nav"]):
                tag.decompose()
            
            # Get Title
            title = ""
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
            else:
                # Fallback to OG title
                for tag in meta_tags:
                    attrs = tag.attrs
                    if "property" in attrs and attrs["property"].lower() == "og:title":
                        title = attrs.get("content", "").strip()
                        break
            
            # Extract core content
            paragraphs = soup.find_all(["p", "h1", "h2", "h3"])
            content_list = []
            for p in paragraphs:
                text = p.get_text(" ", strip=True)
                if len(text) > 15:  # Skip trivial texts
                    content_list.append(text)
            
            content = " ".join(content_list)
            
            # If paragraph text is sparse, fetch raw text
            if len(content) < 100:
                content = soup.get_text(" ", strip=True)
                
            # Clean spaces
            content = " ".join(content.split())
            
            # Build description from metadata if scrapings are thin
            marketing_base = ""
            if og_desc:
                marketing_base += f" {og_desc}"
            elif meta_desc:
                marketing_base += f" {meta_desc}"
                
            final_content = (marketing_base.strip() + " " + content).strip()
            
            # Clean up length
            if len(final_content) < 50:
                # If parsed content is too empty, trigger URL heuristic fallback
                raise ValueError("Extracted page content is too sparse to build marketing copy.")
                
            parsed_url = urllib.parse.urlparse(url)
            return {
                "title": title or "Marketing Campaign",
                "content": final_content[:4000],
                "source": "scraped_live",
                "domain": parsed_url.netloc.replace("www.", "")
            }
            
        except (requests.exceptions.RequestException, ValueError, Exception) as e:
            logger.warning(f"Scrape attempt {attempt + 1} failed for {url}: {e}")
            continue

    # If all live scrape attempts failed or got blocked, return the URL-based fallback info
    logger.info("Live scraping failed or blocked. Activating URL heuristic fallback strategy.")
    return extract_fallback_info(url)