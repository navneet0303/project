import os
import sys
import json
import re
import shutil
import logging
from flask import Flask, request, jsonify, render_template, send_from_directory
from main import run_pipeline
from scraper import clean_url

# Configure central logging for the entire application
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("automarketer.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("automarketer.app")

app = Flask(__name__, template_folder="templates", static_folder="output")

# Ensure output directory exists
os.makedirs("output", exist_ok=True)
os.makedirs("templates", exist_ok=True)

# URL validation regex pattern
URL_REGEX = re.compile(
    r'^https?://'
    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'
    r'localhost|'
    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
    r'(?::\d+)?'
    r'(?:/?|[/?]\S+)$', re.IGNORECASE
)

def is_safe_campaign_id(campaign_id):
    """Ensure campaign_id matches standard pattern, preventing path traversal."""
    return bool(re.match(r"^campaign_[a-zA-Z0-9_-]+$", campaign_id))

@app.route("/")
def index():
    """Render the dashboard UI."""
    return render_template("index.html")

@app.route("/api/generate", methods=["POST"])
def generate():
    """
    Trigger the marketing pipeline for a given URL.
    Expects JSON: { "url": "https://example.com" }
    """
    data = request.json or {}
    url = data.get("url", "").strip()
    
    if not url:
        return jsonify({"success": False, "error": "URL is required"}), 400
        
    # Pre-clean the URL by adding https:// if missing, then validate
    cleaned_url = clean_url(url)
    if not URL_REGEX.match(cleaned_url):
        logger.warning(f"Rejected invalid URL input: '{url}' (cleaned: '{cleaned_url}')")
        return jsonify({"success": False, "error": "Please enter a valid HTTP/HTTPS URL."}), 400
        
    try:
        logger.info(f"API request received to generate campaign for URL: {cleaned_url}")
        # Run the orchestrator pipeline
        campaign_dir, metadata = run_pipeline(cleaned_url, "output")
        if not campaign_dir:
            return jsonify({"success": False, "error": "Pipeline execution failed"}), 500
            
        campaign_id = os.path.basename(campaign_dir)
        metadata["campaign_id"] = campaign_id
        
        logger.info(f"Campaign generated successfully: {campaign_id}")
        return jsonify({
            "success": True,
            "campaign_id": campaign_id,
            "metadata": metadata
        })
        
    except Exception as e:
        logger.error(f"Error occurred during campaign generation: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/campaigns", methods=["GET"])
def list_campaigns():
    """
    Scan the output directory and return metadata of all previous campaigns.
    Ordered by newest timestamp first.
    """
    campaigns = []
    output_dir = "output"
    
    if not os.path.exists(output_dir):
        return jsonify([])
        
    # List all subdirectories
    for folder in os.listdir(output_dir):
        # Ignore system folders and the 'latest' folder
        if folder == "latest" or not folder.startswith("campaign_"):
            continue
            
        # Security validation for safe folders
        if not is_safe_campaign_id(folder):
            logger.warning(f"Detected unsafe folder name in output: {folder}. Skipping.")
            continue
            
        folder_path = os.path.join(output_dir, folder)
        if os.path.isdir(folder_path):
            metadata_path = os.path.join(folder_path, "metadata.json")
            if os.path.exists(metadata_path):
                try:
                    with open(metadata_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    meta["campaign_id"] = folder
                    campaigns.append(meta)
                except Exception as e:
                    logger.warning(f"Failed to read metadata in {folder}: {e}")
                    
    # Sort campaigns by timestamp (newest first)
    campaigns.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return jsonify(campaigns)

@app.route("/api/campaigns/<campaign_id>", methods=["DELETE"])
def delete_campaign(campaign_id):
    """Delete a generated campaign and all its files from history."""
    if not is_safe_campaign_id(campaign_id):
        logger.warning(f"Attempted deletion with unsafe campaign_id: {campaign_id}")
        return jsonify({"success": False, "error": "Invalid Campaign ID format"}), 400
        
    campaign_dir = os.path.join("output", campaign_id)
    if not os.path.exists(campaign_dir) or not os.path.isdir(campaign_dir):
        return jsonify({"success": False, "error": "Campaign not found"}), 404
        
    try:
        logger.info(f"Deleting campaign folder: {campaign_dir}")
        shutil.rmtree(campaign_dir)
        return jsonify({"success": True, "message": f"Campaign '{campaign_id}' deleted successfully."})
    except Exception as e:
        logger.error(f"Failed to delete campaign {campaign_id}: {e}")
        return jsonify({"success": False, "error": f"Failed to delete files: {str(e)}"}), 500

@app.route("/api/campaigns/<campaign_id>/image")
def get_image(campaign_id):
    """Serve the marketing image of a specific campaign."""
    if not is_safe_campaign_id(campaign_id):
        return "Invalid Campaign ID", 400
        
    directory = os.path.join("output", campaign_id)
    if os.path.exists(os.path.join(directory, "marketing_image.png")):
        return send_from_directory(directory, "marketing_image.png")
    return "Image not found", 404

@app.route("/api/campaigns/<campaign_id>/files/<filename>")
def get_file(campaign_id, filename):
    """Serve other campaign files (caption, prompt, scraped text)."""
    if not is_safe_campaign_id(campaign_id):
        return "Invalid Campaign ID", 400
        
    # Prevent filename path traversal
    if filename not in ["caption.txt", "image_prompt.txt", "scraped_content.txt", "metadata.json"]:
        return "File not found", 404
        
    directory = os.path.join("output", campaign_id)
    return send_from_directory(directory, filename)

if __name__ == "__main__":
    # Start local development server
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"AUTO-MARKETER APP LAUNCHED AT: http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=True)
