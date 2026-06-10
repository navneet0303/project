import os
import json
import time
import re
import logging
from dotenv import load_dotenv
import google.generativeai as genai

# Set up logging for this module
logger = logging.getLogger("automarketer.llm")

load_dotenv()

# Initialize Gemini API
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)
    # Use gemini-2.5-flash as default fast model
    model = genai.GenerativeModel("gemini-2.5-flash")
    logger.info("Gemini generative model initialized successfully with gemini-2.5-flash.")
else:
    model = None
    logger.warning("GEMINI_API_KEY not found in environment. Utilizing local rule-based fallback campaigns.")

def sanitize_json_response(text):
    """
    Cleans up any markdown fences and whitespace from a JSON response string
    to ensure it is ready to be loaded by json.loads.
    """
    if not text:
        return ""
    text = text.strip()
    # Strip markdown code blocks if present
    # Matches ```json <content> ``` or ``` <content> ```
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    return text

def extract_keys_via_regex(text):
    """
    Fallback parser using regular expressions to extract JSON keys from malformed strings.
    """
    keys = ["tone", "caption", "cta", "image_prompt"]
    data = {}
    for key in keys:
        # Match string value inside quotes
        pattern = rf'"{key}"\s*:\s*"(.*?)"'
        match = re.search(pattern, text, re.DOTALL)
        if match:
            # Clean up escape characters
            val = match.group(1).replace('\\"', '"').replace('\\n', '\n')
            data[key] = val.strip()
    return data

def generate_fallback_campaign(title, domain, content):
    """
    Rule-based campaign generator when Gemini API is unavailable.
    """
    clean_title = title.replace(" - Fallback", "").strip()
    words = clean_title.split()
    subject = words[0] if words else "Product"
    
    # Construct a high-quality default caption
    caption = f"Discover the future of {subject} today. Experience premium quality, innovative features, and unmatched service tailored to your needs!"
    cta = f"Visit {domain} to learn more and get started!"
    
    # Construct a high-quality default image prompt
    image_prompt = (
        f"A clean, modern commercial banner for {clean_title}. "
        f"Featuring a premium product display, sleek minimal aesthetic, "
        f"professional studio lighting, smooth color gradients, "
        f"depth of field, high-end commercial style, 8k resolution, photorealistic."
    )
    
    return {
        "tone": "Professional & Clean (Fallback)",
        "caption": f"{caption} {cta}",
        "image_prompt": image_prompt
    }

def generate_campaign_data(scraped_data):
    """
    Analyze brand tone, synthesize a 2-sentence caption + CTA, 
    and translate it into an image generation prompt.
    """
    title = scraped_data.get("title", "Modern Brand")
    content = scraped_data.get("content", "")
    domain = scraped_data.get("domain", "website")
    
    # Check if Gemini model is available
    if not model or not api_key:
        logger.info("Gemini API not configured. Triggering rule-based fallback campaign.")
        return generate_fallback_campaign(title, domain, content)
        
    prompt = f"""
You are an elite digital marketing specialist and creative art director.
Analyze the following scraped website data (Title, Domain, Content):

Title: {title}
Domain: {domain}
Content: {content[:3000]}

Generate a structured JSON output with the following keys:
1. "tone": Briefly describe the brand's tone (e.g. "Sleek, minimalist, luxurious" or "Vibrant, friendly, energetic").
2. "caption": Create a punchy, engaging 2-sentence marketing caption. Make it sound native to professional ads and match the brand's tone.
3. "cta": A strong call-to-action (e.g., "Elevate your workspace today at domain.com").
4. "image_prompt": A highly detailed prompt for an Image Generation AI (like Stable Diffusion) to create a matching marketing graphic. Avoid text/logos in the image prompt, and focus on physical objects, composition, colors, mood, lighting, and textures that match the tone.

Return raw JSON only, fitting this schema:
{{
  "tone": "string",
  "caption": "string",
  "cta": "string",
  "image_prompt": "string"
}}
"""

    # Retry logic for API calls
    for attempt in range(3):
        try:
            logger.info(f"Invoking Gemini API (Attempt {attempt + 1}/3)...")
            # Set response schema to JSON
            response = model.generate_content(
                prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.7
                }
            )
            
            # Sanitize and Parse response text
            clean_text = sanitize_json_response(response.text)
            
            try:
                data = json.loads(clean_text)
            except json.JSONDecodeError as json_err:
                logger.warning(f"Failed to parse JSON directly: {json_err}. Trying regex extraction fallback.")
                data = extract_keys_via_regex(clean_text)
                if not data or not all(k in data for k in ["tone", "caption", "image_prompt"]):
                    raise ValueError("Could not extract necessary keys via regex fallback.")
            
            # Combine caption and CTA if separated
            caption_text = data.get("caption", "").strip()
            cta_text = data.get("cta", "").strip()
            if cta_text and cta_text not in caption_text:
                full_caption = f"{caption_text} {cta_text}"
            else:
                full_caption = caption_text
                
            logger.info("Gemini campaign synthesis succeeded.")
            return {
                "tone": data.get("tone", "Professional & Clean"),
                "caption": full_caption,
                "image_prompt": data.get("image_prompt", "")
            }
            
        except Exception as e:
            logger.warning(f"Gemini API attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                time.sleep(2 ** attempt)  # Exponential backoff
            
    logger.error("All Gemini API attempts failed. Falling back to rule-based generation.")
    return generate_fallback_campaign(title, domain, content)