import os
import time
import requests
import urllib3
import logging
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

# Set up logging for this module
logger = logging.getLogger("automarketer.image_generator")

# Suppress insecure request warnings for environment fallback (e.g. self-signed cert blocks)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

HF_TOKEN = os.getenv("HF_API_TOKEN")

# Available SD models to fall back
MODEL_URLS = [
    "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0",
    "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-2-1",
    "https://api-inference.huggingface.co/models/runwayml/stable-diffusion-v1-5"
]

def ensure_local_fonts(fonts_dir="fonts"):
    """
    Downloads premium Google Fonts (Outfit Bold, Roboto Medium, Roboto Regular)
    to the local directory to ensure platform-independent premium typography.
    """
    os.makedirs(fonts_dir, exist_ok=True)
    # Direct URLs to raw TTFs in verified official GitHub source repositories
    font_urls = {
        "Outfit-Bold.ttf": "https://github.com/Outfitio/Outfit-Fonts/raw/main/fonts/ttf/Outfit-Bold.ttf",
        "Roboto-Medium.ttf": "https://github.com/googlefonts/roboto-2/raw/main/src/hinted/Roboto-Medium.ttf",
        "Roboto-Regular.ttf": "https://github.com/googlefonts/roboto-2/raw/main/src/hinted/Roboto-Regular.ttf"
    }
    
    downloaded_paths = {}
    
    for filename, url in font_urls.items():
        dest_path = os.path.join(fonts_dir, filename)
        # Check if font already exists and is not empty
        if os.path.exists(dest_path) and os.path.getsize(dest_path) > 1000:
            downloaded_paths[filename] = dest_path
            continue
            
        logger.info(f"Downloading Google Font: {filename} from Github Fonts repository...")
        try:
            # Add timeout to avoid hanging
            response = requests.get(url, timeout=15, verify=True)
            if response.status_code == 200:
                with open(dest_path, "wb") as f:
                    f.write(response.content)
                downloaded_paths[filename] = dest_path
                logger.info(f"Font {filename} downloaded successfully to {dest_path}")
            else:
                logger.warning(f"Failed to download font {filename} (HTTP {response.status_code}).")
        except Exception as e:
            logger.warning(f"Could not download font {filename}: {e}.")
            
    return downloaded_paths

def generate_local_fallback_image(caption, title, output_path):
    """
    Programmatically creates a premium-looking marketing graphic
    using a curated gradient background and clean glassmorphic typography card.
    Ensure zero-dependency offline rendering capability with Google Fonts fallbacks.
    """
    logger.info("Generating a local premium graphic fallback using Pillow...")
    
    # Ensure fonts are downloaded
    local_fonts = {}
    try:
        local_fonts = ensure_local_fonts()
    except Exception as e:
        logger.warning(f"Font pre-download failed: {e}. Falling back to system fonts.")
    
    width, height = 1024, 1024
    
    # 1. Create base gradient background (Vibrant Indigo to Deep Night-blue)
    base = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(base)
    
    # Draw soft vertical gradient
    for y in range(height):
        # Interpolate between Deep Navy (15, 23, 42) and Neon Indigo (80, 50, 230)
        ratio = y / height
        r = int(15 + (80 - 15) * ratio)
        g = int(23 + (50 - 23) * ratio)
        b = int(42 + (230 - 42) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
        
    # Draw decorative modern glowing accent orbs
    overlay_orb = Image.new("RGBA", base.size, (0, 0, 0, 0))
    orb_draw = ImageDraw.Draw(overlay_orb)
    # Draw neon pink glow orb top-right
    orb_draw.ellipse([600, -100, 1150, 450], fill=(236, 72, 153, 35))
    # Draw neon cyan glow orb bottom-left
    orb_draw.ellipse([-150, 650, 400, 1200], fill=(6, 182, 212, 35))
    
    # 2. Draw glassmorphic card overlay
    # White card in center with semi-transparency and thin border
    card_margin_x = 100
    card_margin_y = 150
    card_box = [card_margin_x, card_margin_y, width - card_margin_x, height - card_margin_y]
    orb_draw.rounded_rectangle(
        card_box,
        radius=40,
        fill=(255, 255, 255, 12),       # Translucent white
        outline=(255, 255, 255, 45),     # Semi-transparent border
        width=2
    )
    
    # Blend base and orb overlay
    img = Image.alpha_composite(base.convert("RGBA"), overlay_orb)
    final_draw = ImageDraw.Draw(img)
    
    # 3. Font Loading Strategy
    # Setup Font paths prioritizing local Google Fonts
    title_font_path = local_fonts.get("Outfit-Bold.ttf")
    body_font_path = local_fonts.get("Roboto-Medium.ttf") or local_fonts.get("Roboto-Regular.ttf")
    
    # System fallbacks if local download fails
    system_bold_fonts = [
        "C:\\Windows\\Fonts\\SegoeUIb.ttf",
        "C:\\Windows\\Fonts\\Arialbd.ttf",
        "C:\\Windows\\Fonts\\Calibrib.ttf"
    ]
    system_reg_fonts = [
        "C:\\Windows\\Fonts\\SegoeUI.ttf",
        "C:\\Windows\\Fonts\\Arial.ttf",
        "C:\\Windows\\Fonts\\Calibri.ttf"
    ]
    
    if not title_font_path:
        for p in system_bold_fonts:
            if os.path.exists(p):
                title_font_path = p
                break
                
    if not body_font_path:
        for p in system_reg_fonts:
            if os.path.exists(p):
                body_font_path = p
                break

    # Helpers for text metrics (compatible with old/new Pillow)
    def get_text_width(text, font):
        if hasattr(font, "getlength"):
            return font.getlength(text)
        elif hasattr(font, "getsize"):
            return font.getsize(text)[0]
        return len(text) * 10
        
    def get_text_height(text, font):
        if hasattr(font, "getbbox"):
            bbox = font.getbbox(text)
            return bbox[3] - bbox[1] if bbox else 24
        elif hasattr(font, "getsize"):
            return font.getsize(text)[1]
        return 24

    # 4. Draw Header/Title with Dynamic Font Scaling to prevent overflow
    title_text = title.upper().strip()
    title_size = 46
    max_title_width = width - (card_margin_x * 2) - 100
    
    # Dynamically scale down title font size to fit on one line
    while title_size >= 24:
        if title_font_path:
            try:
                title_font = ImageFont.truetype(title_font_path, title_size)
            except Exception:
                title_font = ImageFont.load_default()
        else:
            title_font = ImageFont.load_default()
            
        title_w = get_text_width(title_text, title_font)
        if title_w <= max_title_width or title_font == ImageFont.load_default():
            break
        title_size -= 2
        
    # Fallback title wrap if it still exceeds and we hit the minimum size
    if title_w > max_title_width:
        title_text = title_text[:32] + "..."
        title_w = get_text_width(title_text, title_font)
        
    title_x = (width - title_w) // 2
    final_draw.text((title_x, card_margin_y + 60), title_text, fill=(255, 255, 255, 255), font=title_font)
    
    # Draw decorative thin accent line below title
    line_y = card_margin_y + 130
    final_draw.line([(width // 2 - 120, line_y), (width // 2 + 120, line_y)], fill=(255, 255, 255, 100), width=2)
    
    # 5. Draw CTA Pill Button at Bottom of Card
    cta_text = "LEARN MORE"
    cta_size = 26
    if body_font_path:
        try:
            cta_font = ImageFont.truetype(body_font_path, cta_size)
        except Exception:
            cta_font = ImageFont.load_default()
    else:
        cta_font = ImageFont.load_default()
        
    cta_w = get_text_width(cta_text, cta_font)
    cta_h = get_text_height(cta_text, cta_font)
    
    btn_w = cta_w + 60
    btn_h = cta_h + 30
    btn_x0 = (width - btn_w) // 2
    btn_y0 = height - card_margin_y - 120
    
    # Draw CTA button box
    final_draw.rounded_rectangle(
        [btn_x0, btn_y0, btn_x0 + btn_w, btn_y0 + btn_h],
        radius=16,
        fill=(6, 182, 212, 220),  # Bright Cyan highlight
        outline=(255, 255, 255, 240),
        width=1
    )
    
    btn_text_x = btn_x0 + (btn_w - cta_w) // 2
    btn_text_y = btn_y0 + (btn_h - cta_h) // 2 - 2
    final_draw.text((btn_text_x, btn_text_y), cta_text, fill=(255, 255, 255, 255), font=cta_font)
    
    # 6. Wrap and Draw Caption (Body Text) with Dynamic Font Size Scaling
    # Fits text neatly in the vertical space between the title line and the CTA button
    start_y = card_margin_y + 180
    max_text_height = btn_y0 - start_y - 40
    max_text_width = width - (card_margin_x * 2) - 80
    
    body_size = 32
    wrapped_lines = []
    line_h = 32
    line_spacing = 14
    
    words = caption.split()
    
    # Scale down body text font size until the paragraph fits in the card
    while body_size >= 16:
        if body_font_path:
            try:
                body_font = ImageFont.truetype(body_font_path, body_size)
            except Exception:
                body_font = ImageFont.load_default()
        else:
            body_font = ImageFont.load_default()
            
        # Wrap words
        wrapped_lines = []
        current_line = []
        
        for word in words:
            # Handle exceptionally long words
            word_w = get_text_width(word, body_font)
            if word_w > max_text_width:
                # Force wrap long word characters
                if current_line:
                    wrapped_lines.append(" ".join(current_line))
                    current_line = []
                # Split word characters
                chunk = ""
                for char in word:
                    test_chunk = chunk + char
                    if get_text_width(test_chunk, body_font) <= max_text_width:
                        chunk = test_chunk
                    else:
                        wrapped_lines.append(chunk)
                        chunk = char
                if chunk:
                    current_line = [chunk]
                continue
                
            test_line = " ".join(current_line + [word])
            if get_text_width(test_line, body_font) <= max_text_width:
                current_line.append(word)
            else:
                if current_line:
                    wrapped_lines.append(" ".join(current_line))
                current_line = [word]
        if current_line:
            wrapped_lines.append(" ".join(current_line))
            
        # Measure total height
        line_h = get_text_height("Aqy", body_font)
        total_h = len(wrapped_lines) * (line_h + line_spacing) - line_spacing
        
        # Check if it fits
        if total_h <= max_text_height or body_font == ImageFont.load_default():
            break
            
        body_size -= 2
        
    # Draw body text lines centered vertically in the available space
    total_h = len(wrapped_lines) * (line_h + line_spacing) - line_spacing
    vertical_offset = (max_text_height - total_h) // 2
    draw_y = start_y + max(0, vertical_offset)
    
    for line in wrapped_lines:
        line_w = get_text_width(line, body_font)
        x = (width - line_w) // 2
        final_draw.text((x, draw_y), line, fill=(243, 244, 246, 245), font=body_font)
        draw_y += line_h + line_spacing
        
    # Save image to file system
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.convert("RGB").save(output_path, "PNG")
    logger.info(f"Local premium graphic fallback saved successfully to {output_path}")
    return output_path

def _post_request_with_ssl_fallback(url, headers, json_data, timeout):
    """
    Tries requests.post normally. If it fails with an SSL verification error,
    retries with verify=False.
    """
    try:
        return requests.post(url, headers=headers, json=json_data, timeout=timeout)
    except requests.exceptions.SSLError:
        logger.warning("SSL Verification failed. Retrying request with verify=False...")
        return requests.post(url, headers=headers, json=json_data, timeout=timeout, verify=False)

def generate_image(prompt, caption, title, output_path="output/marketing_image.png"):
    """
    Generate an image from prompt using Hugging Face Stable Diffusion,
    supporting loading retry logic, multiple model failover, and PIL local fallback.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    if not HF_TOKEN:
        logger.warning("HF_API_TOKEN not found in environment. Utilizing local graphic generator.")
        return generate_local_fallback_image(caption, title, output_path)

    # Iterate through models for fallback
    for model_idx, api_url in enumerate(MODEL_URLS):
        model_name = api_url.split("/models/")[-1]
        logger.info(f"Attempting image generation with model {model_idx + 1}/{len(MODEL_URLS)}: {model_name}...")
        
        headers = {
            "Authorization": f"Bearer {HF_TOKEN}"
        }
        
        # Retry loop for model loading (HTTP 503)
        max_retries = 4
        for attempt in range(max_retries):
            try:
                response = _post_request_with_ssl_fallback(
                    api_url,
                    headers=headers,
                    json_data={"inputs": prompt},
                    timeout=45
                )
                
                # Check status code
                if response.status_code == 200:
                    # Validate content is actually a valid image format (PNG/JPEG)
                    content_type = response.headers.get("Content-Type", "").lower()
                    is_image_header = content_type.startswith("image/")
                    
                    # Check magic bytes for JPEG (FF D8) or PNG (89 50 4E 47)
                    has_magic_bytes = (
                        response.content.startswith(b"\x89PNG") or 
                        response.content.startswith(b"\xff\xd8")
                    )
                    
                    if not (is_image_header or has_magic_bytes):
                        logger.warning(f"Model {model_name} returned non-image content (headers: {content_type}). Likely blocked or network filtered.")
                        break  # Break retry loop to try next model or fall back
                        
                    with open(output_path, "wb") as f:
                        f.write(response.content)
                    logger.info(f"Image successfully generated and saved via HF model {model_name}!")
                    return output_path
                    
                elif response.status_code == 503:
                    # Model is loading on Hugging Face
                    try:
                        error_data = response.json()
                        estimated_time = error_data.get("estimated_time", 15.0)
                    except Exception:
                        estimated_time = 15.0
                        
                    wait_time = min(estimated_time, 20.0)
                    logger.info(f"HF Model is loading. Attempt {attempt + 1}/{max_retries}. Waiting {wait_time}s...")
                    time.sleep(wait_time)
                    
                else:
                    logger.warning(f"Model {model_name} failed with HTTP status {response.status_code}.")
                    logger.warning(response.text[:200])
                    break  # Break retry loop to try next model
                    
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request exception for model {model_name}: {e}")
                time.sleep(2)
                
    # If all API attempts fail, trigger local premium graphic rendering
    logger.error("All Hugging Face image generation models failed or timed out. Triggering Pillow fallback.")
    return generate_local_fallback_image(caption, title, output_path)