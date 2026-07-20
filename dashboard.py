from flask import Flask, render_template, request, jsonify, send_file
from flask_basicauth import BasicAuth
import json
import os
import io
from PIL import Image, ImageDraw, ImageFont, ImageOps
import requests

app = Flask(__name__)

# ==========================================
# SECURITY
# ==========================================
app.config['BASIC_AUTH_USERNAME'] = 'realgyjs@gmail.com'
app.config['BASIC_AUTH_PASSWORD'] = 'Livetopimo'
basic_auth = BasicAuth(app)

# ==========================================
# CONFIGURATION
# ==========================================
CONFIG_FILE = "rank_configs.json"
ADMIN_CONFIG_FILE = "admin_config.json"
DEFAULT_BG_FILE = "default_bg.png"
USER_BG_FOLDER = "backgrounds/"

# Ensure user background folder exists
if not os.path.exists(USER_BG_FOLDER):
    os.makedirs(USER_BG_FOLDER)

# Load user configurations
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, 'r') as f:
        configs = json.load(f)
else:
    configs = {}

# Load Admin Config (Global defaults)
if os.path.exists(ADMIN_CONFIG_FILE):
    with open(ADMIN_CONFIG_FILE, 'r') as f:
        admin_config = json.load(f)
else:
    admin_config = {}

# ==========================================
# HELPER: Format numbers to K format
# ==========================================
def format_k(num):
    if num >= 1000:
        return f"{num/1000:.1f}K"
    return str(num)

# ==========================================
# PUBLIC ROUTES
# ==========================================

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

@app.route('/reset_config/<user_id>', methods=['POST'])
def reset_config(user_id):
    if user_id in configs:
        del configs[user_id]
        with open(CONFIG_FILE, 'w') as f:
            json.dump(configs, f, indent=4)
    return jsonify({"status": "reset"})

@app.route('/upload_bg/<user_id>', methods=['POST'])
def upload_bg(user_id):
    if 'bg_image' not in request.files:
        return "No file", 400
    file = request.files['bg_image']
    if file.filename == '':
        return "No file", 400
    
    filepath = os.path.join(USER_BG_FOLDER, f"{user_id}.png")
    img = Image.open(file.stream).convert("RGB")
    img = img.resize((1000, 300))
    img.save(filepath)
    return "Uploaded", 200

@app.route('/get_card/<user_id>')
def get_card(user_id):
    try:
        # 1. Get data from URL parameters (NOW INCLUDING LEVEL!)
        name = request.args.get('name', f'User')
        level = int(request.args.get('level', 0))  # <--- FIXED THE LEVEL 0 BUG HERE
        current_xp = int(request.args.get('xp', 0))
        next_level_xp = int(request.args.get('next_xp', 1000))
        progress = float(request.args.get('progress', 0.0))
        avatar_url = request.args.get('avatar')
        rank = request.args.get('rank', '?')

        # 2. Load User Config (Fallback to massive HARDCODED defaults)
        user_conf = configs.get(user_id, {})
        
        config = {
            "bg_color": user_conf.get('bg_color', "#2f3136"),
            "bar_color": user_conf.get('bar_color', "#5865F2"),
            "opacity": user_conf.get('opacity', 45),     # Reduced to 45 for beautiful backgrounds
            "font_color": user_conf.get('font_color', "#ffffff"),
            "stats_color": user_conf.get('stats_color', "#D2D5DA"),
            "font_family": user_conf.get('font_family', "Inter"),
            "font_size": user_conf.get('font_size', 72)
        }

        # 3. Create Canvas (1000x300)
        user_bg_path = os.path.join(USER_BG_FOLDER, f"{user_id}.png")
        if os.path.exists(user_bg_path):
            bg_img = Image.open(user_bg_path).convert("RGB")
        elif os.path.exists(DEFAULT_BG_FILE):
            bg_img = Image.open(DEFAULT_BG_FILE).convert("RGB").resize((1000, 300))
        else:
            bg_img = Image.new('RGB', (1000, 300), color=config.get('bg_color', '#2f3136'))

        img = bg_img.copy()
        draw = ImageDraw.Draw(img)

        # Apply Overlay (45% Opacity)
        overlay_strength = int(config.get('opacity', 45))
        if overlay_strength > 0:
            overlay = Image.new('RGBA', (1000, 300), (0, 0, 0, overlay_strength))
            img.paste(overlay, (0, 0), overlay)

        # 4. Avatar (150x150 with 4px White Border)
        avatar_img = None
        if avatar_url:
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                resp = requests.get(avatar_url, headers=headers, timeout=5)
                if resp.status_code == 200:
                    avatar_img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
                    mask = Image.new('L', (150, 150), 0)
                    draw_mask = ImageDraw.Draw(mask)
                    draw_mask.ellipse((0, 0, 150, 150), fill=255)
                    avatar_img = ImageOps.fit(avatar_img, (150, 150), Image.LANCZOS)
                    avatar_img.putalpha(mask)
                    img.paste(avatar_img, (40, 70), avatar_img)
                    
                    # Draw thin 4px white border around avatar
                    draw.ellipse([37, 67, 193, 223], outline="#ffffff", width=4)
            except Exception as e:
                print(f"⚠️ Avatar error: {e}")

        # 5. Load Font (Inter Bold, SemiBold, and Medium)
        font_name = config.get('font_family', "Inter")
        font_path_map = {
            "Inter": "Inter-Bold.ttf",
            "Roboto": "Roboto-Bold.ttf",
            "Open Sans": "OpenSans-Bold.ttf",
            "Montserrat": "Montserrat-Bold.ttf"
        }
        # Try to load bold, fall back to regular, fall back to default
        try:
            font_large = ImageFont.truetype("Inter-Bold.ttf", 72)
            font_medium = ImageFont.truetype("Inter-SemiBold.ttf", 38)
            font_small = ImageFont.truetype("Inter-Medium.ttf", 32)
        except:
            try:
                font_large = ImageFont.truetype("Inter-Regular.ttf", 72)
                font_medium = ImageFont.truetype("Inter-Regular.ttf", 38)
                font_small = ImageFont.truetype("Inter-Regular.ttf", 32)
            except:
                font_large = ImageFont.load_default()
                font_medium = ImageFont.load_default()
                font_small = ImageFont.load_default()

        # 6. Draw Text (PREMIUM LAYOUT)
        font_color = config.get('font_color', '#ffffff')
        stats_color = config.get('stats_color', '#D2D5DA')
        accent_color = config.get('bar_color', '#5865F2')
        
        # Username (72px Bold) - Starts at X=225
        draw.text((225, 70), f"@{name}", fill=font_color, font=font_large)

        # Accent Line (Thick 5px, perfectly under username)
        bbox = draw.textbbox((0, 0), f"@{name}", font=font_large)
        text_width = bbox[2] - bbox[0]
        line_y = 70 + 72 + 15
        draw.line([(225, line_y), (225 + text_width, line_y)], fill=accent_color, width=5)

        # Stats Text (Level 19 • XP 8.6K / 10K • Rank #2)
        formatted_current = format_k(current_xp)
        formatted_next = format_k(next_level_xp)
        stats_text = f"Level {level} • XP {formatted_current} / {formatted_next} • Rank #{rank}"
        draw.text((225, line_y + 20), stats_text, fill=stats_color, font=font_medium)

        # 7. Draw Progress Bar (Thicker, closer, softer colors)
        bar_x = 225
        bar_y = line_y + 75
        bar_width = 740
        bar_height = 40
        radius = 20

        # Softer empty bar (#ECECEC)
        draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], radius=radius, fill="#ECECEC")
        
        # Filled colored bar
        filled_width = bar_width * progress
        if filled_width > 0:
            draw.rounded_rectangle([bar_x, bar_y, bar_x + filled_width, bar_y + bar_height], radius=radius, fill=accent_color)

        img_io = io.BytesIO()
        img.save(img_io, 'PNG')
        img_io.seek(0)
        return send_file(img_io, mimetype='image/png')
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return f"❌ Image generation failed", 500

# ==========================================
# SIMPLIFIED ADMIN ROUTES (Only Backgrounds)
# ==========================================

@app.route('/admin', methods=['GET', 'POST'])
@basic_auth.required
def admin_panel():
    message = ""
    
    if request.method == 'POST':
        if 'bg_image' in request.files and request.files['bg_image'].filename != '':
            file = request.files['bg_image']
            img = Image.open(file.stream).convert("RGB").resize((1000, 300))
            img.save(DEFAULT_BG_FILE)
            message = "✅ Default background uploaded! (1000x300)"
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Panel</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap" rel="stylesheet">
        <style>
            body {{ font-family: 'Inter', sans-serif; background: #1e1e2e; color: white; text-align: center; padding: 50px; }}
            .card {{ background: #2f3136; max-width: 500px; margin: 0 auto; padding: 30px; border-radius: 16px; border: 1px solid #40444b; }}
            h1 {{ color: #45ddc0; }}
            .upload-box {{ border: 2px dashed #40444b; padding: 30px; text-align: center; border-radius: 10px; margin: 20px 0; }}
            input[type="file"] {{ display: block; margin: 10px auto; color: white; }}
            button {{ background: #5865F2; border: none; padding: 12px 24px; border-radius: 6px; font-weight: bold; cursor: pointer; margin-top: 10px; }}
            .msg {{ color: #45ddc0; margin-top: 20px; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>🛠️ Admin Panel</h1>
            <p style="color:#b9bbbe;">Upload a 1000x300 default background image for un-customized cards.</p>
            <div class="msg">{message}</div>
            <form method="POST" enctype="multipart/form-data">
                <div class="upload-box">
                    <input type="file" name="bg_image" accept="image/png,image/jpeg">
                    <button type="submit">Upload Default Background</button>
                </div>
            </form>
        </div>
    </body>
    </html>
    '''

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
