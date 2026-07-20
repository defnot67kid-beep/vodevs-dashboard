from flask import Flask, render_template, request, jsonify, send_file
import json
import os
import io
from PIL import Image, ImageDraw, ImageFont, ImageOps
import requests

app = Flask(__name__)

CONFIG_FILE = "rank_configs.json"
DATA_FILE = "level_data.json"
FONT_PATH = "arial.ttf"  # Make sure this file is in your root folder!

# Load user configurations
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, 'r') as f:
        configs = json.load(f)
else:
    configs = {}

@app.route('/')
def home():
    return "✅ Rank Card Dashboard is online!"

@app.route('/dashboard/<user_id>')
def dashboard(user_id):
    user_config = configs.get(user_id, {})
    return render_template('dashboard.html', user_id=user_id, config=user_config)

@app.route('/save_config/<user_id>', methods=['POST'])
def save_config(user_id):
    data = request.json
    configs[user_id] = data
    with open(CONFIG_FILE, 'w') as f:
        json.dump(configs, f, indent=4)
    return jsonify({"status": "saved"})

@app.route('/get_card/<user_id>')
def get_card(user_id):
    try:
        # 1. Get the user's config (or defaults)
        config = configs.get(user_id, {
            "bg_color": "#2f3136",
            "bar_color": "#5865F2",
            "opacity": 100,
            "font_color": "#ffffff"
        })

        # 2. Get XP and Progress from the URL parameters
        # Example: /get_card/123?xp=1287&progress=0.50
        xp = int(request.args.get('xp', 0))
        progress = float(request.args.get('progress', 0.0))

        # 3. Fetch the user's avatar from Discord
        avatar_url = f"https://cdn.discordapp.com/avatars/{user_id}/{user_id}.png?size=512"
        avatar_img = None
        try:
            resp = requests.get(avatar_url, timeout=5)
            if resp.status_code == 200:
                avatar_img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
                # Crop to a circle
                mask = Image.new('L', avatar_img.size, 0)
                draw_mask = ImageDraw.Draw(mask)
                draw_mask.ellipse((0, 0, avatar_img.size[0], avatar_img.size[1]), fill=255)
                avatar_img = ImageOps.fit(avatar_img, (100, 100), Image.LANCZOS)
                mask = mask.resize((100, 100), Image.LANCZOS)
                avatar_img.putalpha(mask)
            else:
                avatar_img = None
        except:
            avatar_img = None

        # 4. Create the card background (800x200)
        img = Image.new('RGB', (800, 200), color=config.get('bg_color', '#2f3136'))
        draw = ImageDraw.Draw(img)

        # 5. Draw the Avatar
        if avatar_img:
            img.paste(avatar_img, (50, 50), avatar_img)

        # 6. Load Fonts
        try:
            font_large = ImageFont.truetype(FONT_PATH, 36)
            font_medium = ImageFont.truetype(FONT_PATH, 24)
            font_small = ImageFont.truetype(FONT_PATH, 18)
        except:
            # Fallback to default if font file is missing
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_small = ImageFont.load_default()

        # 7. Draw Username
        font_color = config.get('font_color', '#ffffff')
        draw.text((170, 55), f"@{user_id[:10]}", fill=font_color, font=font_large)

        # 8. Draw XP Bar
        bar_x = 170
        bar_y = 120
        bar_width = 580
        bar_height = 25
        radius = 12

        # Draw background of bar (gray)
        draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], radius=radius, fill="#2c2f33")
        
        # Draw filled progress bar (color)
        filled_width = bar_width * progress
        draw.rounded_rectangle([bar_x, bar_y, bar_x + filled_width, bar_y + bar_height], radius=radius, fill=config.get('bar_color', '#5865F2'))

        # 9. Draw XP Text inside/under the bar
        draw.text((bar_x + 10, bar_y + 5), f"XP: {xp:,}", fill="#ffffff", font=font_small)

        # Return the image
        img_io = io.BytesIO()
        img.save(img_io, 'PNG')
        img_io.seek(0)
        return send_file(img_io, mimetype='image/png')
    except Exception as e:
        print(f"❌ ERROR in /get_card: {e}")
        return f"❌ Image generation failed: {e}", 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
