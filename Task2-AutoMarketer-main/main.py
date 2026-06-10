import os
import sys
import json
import argparse
import time
import re
import unicodedata
import logging
import shutil
from datetime import datetime

from scraper import scrape_website
from llm import generate_campaign_data
from image_generator import generate_image

# Set up logging for this orchestrator module
logger = logging.getLogger("automarketer.main")

def setup_cli_logging():
    """Set up logging to file and stream if running directly from CLI."""
    # Check if root logger has handlers already configured (e.g. by app.py)
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler("automarketer.log", encoding="utf-8")
            ]
        )

def slugify(value):
    """Convert a string to a safe, unicode-friendly directory name."""
    # Normalize unicode characters to their ASCII equivalent where possible
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    # Remove all non-alphanumeric, whitespace and hyphen/underscore characters
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    # Replace spaces and hyphens with a single underscore
    return re.sub(r"[-\s]+", "_", value)

def save_text(filepath, content):
    """Helper to save text content to a file."""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        logger.error(f"Failed to save text to file {filepath}: {e}")

def run_pipeline(url, output_root="output"):
    """
    Run the entire marketing automation pipeline end-to-end.
    Returns the campaign directory path and campaign details dictionary.
    """
    start_time = time.time()
    logger.info("=" * 60)
    logger.info(f"STARTING AUTO-MARKETER PIPELINE FOR: {url}")
    logger.info("=" * 60)
    
    # --- Step 1: Scraping ---
    logger.info("[1/3] Scraping Website Content...")
    scrape_start = time.time()
    scraped_data = scrape_website(url)
    scrape_duration = time.time() - scrape_start
    
    if not scraped_data:
        logger.error("[-] Scraping failed completely. Aborting pipeline.")
        return None, None
        
    logger.info(f"[+] Scraping completed in {scrape_duration:.2f}s ({scraped_data['source']})")
    logger.info(f"    Title: {scraped_data['title']}")
    logger.info(f"    Domain: {scraped_data['domain']}")
    logger.info(f"    Content Length: {len(scraped_data['content'])} characters")
    
    # --- Step 2: LLM Campaign Synthesis & Prompt Translation ---
    logger.info("[2/3] Chaining LLM for Caption Synthesis & Image Prompt Translation...")
    llm_start = time.time()
    campaign_data = generate_campaign_data(scraped_data)
    llm_duration = time.time() - llm_start
    
    logger.info(f"[+] LLM processing completed in {llm_duration:.2f}s")
    logger.info(f"    Tone: {campaign_data['tone']}")
    logger.info(f"    Marketing Caption: {campaign_data['caption']}")
    logger.info(f"    Image Prompt: {campaign_data['image_prompt'][:120]}...")
    
    # Create unified campaign directory
    domain_slug = slugify(scraped_data["domain"])
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    campaign_dir = os.path.join(output_root, f"campaign_{domain_slug}_{timestamp}")
    os.makedirs(campaign_dir, exist_ok=True)
    
    # File paths
    caption_path = os.path.join(campaign_dir, "caption.txt")
    prompt_path = os.path.join(campaign_dir, "image_prompt.txt")
    scraped_path = os.path.join(campaign_dir, "scraped_content.txt")
    image_path = os.path.join(campaign_dir, "marketing_image.png")
    metadata_path = os.path.join(campaign_dir, "metadata.json")
    
    # Save text outputs
    save_text(caption_path, campaign_data["caption"])
    save_text(prompt_path, campaign_data["image_prompt"])
    save_text(scraped_path, scraped_data["content"])
    
    # --- Step 3: Image Generation ---
    logger.info("[3/3] Generating Visual Assets...")
    image_start = time.time()
    
    # Pass prompt, caption, and title for PIL fallback
    generated_image = generate_image(
        prompt=campaign_data["image_prompt"],
        caption=campaign_data["caption"],
        title=scraped_data["title"],
        output_path=image_path
    )
    
    image_duration = time.time() - image_start
    total_duration = time.time() - start_time
    
    if generated_image:
        logger.info(f"[+] Image assets generated in {image_duration:.2f}s")
        status = "Success"
    else:
        logger.warning("[-] Image generation failed or hit empty outcome.")
        status = "Success_With_Failed_Image"
        
    # Compile and save metadata
    metadata = {
        "url": url,
        "domain": scraped_data["domain"],
        "title": scraped_data["title"],
        "scrape_source": scraped_data["source"],
        "tone": campaign_data["tone"],
        "caption": campaign_data["caption"],
        "image_prompt": campaign_data["image_prompt"],
        "timestamp": datetime.now().isoformat(),
        "status": status,
        "metrics": {
            "scrape_time_seconds": scrape_duration,
            "llm_time_seconds": llm_duration,
            "image_time_seconds": image_duration,
            "total_time_seconds": total_duration
        },
        "files": {
            "caption": "caption.txt",
            "image_prompt": "image_prompt.txt",
            "scraped_content": "scraped_content.txt",
            "image": "marketing_image.png" if generated_image else None
        }
    }
    
    try:
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to write metadata json file: {e}")
        
    # --- Create / Update "Latest" Soft-cache for easy referencing ---
    latest_dir = os.path.join(output_root, "latest")
    os.makedirs(latest_dir, exist_ok=True)
    
    save_text(os.path.join(latest_dir, "caption.txt"), campaign_data["caption"])
    save_text(os.path.join(latest_dir, "image_prompt.txt"), campaign_data["image_prompt"])
    
    try:
        with open(os.path.join(latest_dir, "metadata.json"), "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to write latest metadata json file: {e}")
        
    if generated_image and os.path.exists(image_path):
        try:
            shutil.copy2(image_path, os.path.join(latest_dir, "marketing_image.png"))
        except Exception as e:
            logger.error(f"Failed to copy marketing image to latest folder: {e}")
        
    logger.info("=" * 60)
    logger.info("PIPELINE RUN COMPLETED")
    logger.info("=" * 60)
    logger.info(f"    Campaign Output Folder: {campaign_dir}")
    logger.info(f"    Paired Assets:")
    logger.info(f"       - Caption: {caption_path}")
    logger.info(f"       - Image: {image_path if generated_image else 'None (Failed)'}")
    logger.info(f"    Saved 'Latest' Shortcut in: {latest_dir}/")
    logger.info("=" * 60)
    
    return campaign_dir, metadata

def main():
    setup_cli_logging()
    
    parser = argparse.ArgumentParser(description="Auto-Marketer AI Orchestration Pipeline - Modified for Navneet Yadav")
    parser.add_argument(
        "--url", "-u", 
        type=str, 
        help="The website URL to generate the campaign from"
    )
    parser.add_argument(
        "--out", "-o", 
        type=str, 
        default="output", 
        help="Root directory to save generated campaigns (default: output)"
    )
    args = parser.parse_args()
    
    url = args.url
    if not url:
        # Fallback to interactive CLI mode if no argument is passed
        try:
            url = input("Enter Website URL: ").strip()
        except KeyboardInterrupt:
            logger.info("\nExecution cancelled by user.")
            sys.exit(0)
        
    if not url:
        logger.error("[-] Error: URL cannot be empty.")
        sys.exit(1)
        
    campaign_dir, metadata = run_pipeline(url, args.out)
    if not campaign_dir:
        sys.exit(1)

if __name__ == "__main__":
    main()