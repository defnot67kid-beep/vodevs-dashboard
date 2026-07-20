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
DEFAULT_BG_FILE = "default_bg.png"

# Load user configurations
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, 'r') as f:
        configs = json.load(f)
else:
    configs = {}

# ==========================================
# ROUTES
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

@app.route('/get_card/<user_id>')
def get_card(user_id):
    try:
        # 1. Get data from URL parameters
        name = request.args.get('name', f'User')
        current_xp = int(request.args.get('xp', 0))
        next_level_xp = int(request.args.get('next_xp', 1000))
        progress = float(request.args.get('progress', 0.0))
        avatar_url = request.args.get('avatar')

        # 2. Load User Config (or defaults)
        # We also read the 6 new customization settings
        config = configs.get(user_id, {
            "bg_color": "#2f3136",
            "bar_color": "#5865F2",
            "opacity": 100,
            "font_color": "#ffffff",
            "stats_color": "#b9bbbe",
            "font_family": "Inter"
        })

        # 3. Create Canvas (900x250)
        if os.path.exists(DEFAULT_BG_FILE):
            bg_img = Image.open(DEFAULT_BG_FILE).convert("RGB").resize((900, 250))
        else:
            bg_img = Image.new('RGB', (900, 250), color=config.get('bg_color', '#2f3136'))

        img = bg_img.copy()
        draw = ImageDraw.Draw(img)

        # Apply Overlay (Opacity)
        overlay_strength = int(config.get('opacity', 100))
        if overlay_strength > 0:
            overlay = Image.new('RGBA', (900, 250), (0, 0, 0, overlay_strength))
            img.paste(overlay, (0, 0), overlay)

        # 4. Avatar
        avatar_img = None
        if avatar_url:
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                resp = requests.get(avatar_url, headers=headers, timeout=5)
                if resp.status_code == 200:
                    avatar_img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
                    mask = Image.new('L', (110, 110), 0)
                    draw_mask = ImageDraw.Draw(mask)
                    draw_mask.ellipse((0, 0, 110, 110), fill=255)
                    avatar_img = ImageOps.fit(avatar_img, (110, 110), Image.LANCZOS)
                    avatar_img.putalpha(mask)
                    img.paste(avatar_img, (30, 70), avatar_img)
            except Exception as e:
                print(f"⚠️ Avatar error: {e}")

        # 5. Load Font (Dynamic based on user choice!)
        font_name = config.get('font_family', 'Inter')
        font_path_map = {
            "Inter": "Inter-Regular.ttf",
            "Roboto": "Roboto-Regular.ttf",
            "Open Sans": "OpenSans-Regular.ttf",
            "Montserrat": "Montserrat-Regular.ttf"
        }
        font_file = font_path_map.get(font_name, "Inter-Regular.ttf")
        
        try:
            font_large = ImageFont.truetype(font_file, 36)
            font_medium = ImageFont.truetype(font_file, 22)
        except:
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()

        # 6. Draw Text
        font_color = config.get('font_color', '#ffffff')
        stats_color = config.get('stats_color', '#b9bbbe')
        
        draw.text((170, 65), f"@{name}", fill=font_color, font=font_large)
        status_text = f"Level: 0  XP: {current_xp:,} / {next_level_xp:,}"
        draw.text((170, 110), status_text, fill=stats_color, font=font_medium)

        # 7. Draw Progress Bar
        bar_x = 170
        bar_y = 150
        bar_width = 700
        bar_height = 25
        radius = 20

        draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], radius=radius, fill="#ffffff")
        
        filled_width = bar_width * progress
        if filled_width > 0:
            draw.rounded_rectangle([bar_x, bar_y, bar_x + filled_width, bar_y + bar_height], radius=radius, fill=config.get('bar_color', '#5865F2'))

        img_io = io.BytesIO()
        img.save(img_io, 'PNG')
        img_io.seek(0)
        return send_file(img_io, mimetype='image/png')
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return f"❌ Image generation failed", 500

# ==========================================
# ADMIN ROUTES
# ==========================================

@app.route('/admin', methods=['GET', 'POST'])
@basic_auth.required
def admin_panel():
    message = ""
    if request.method == 'POST':
        if 'bg_image' not in request.files:
            message = "No file uploaded."
        else:
            file = request.files['bg_image']
            if file.filename == '':
                message = "No file selected."
            else:
                file.save(DEFAULT_BG_FILE)
                message = f"✅ Default background uploaded! (900x250 recommended)"
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Panel</title>
        <style>
            body {{ font-family: sans-serif; background: #1e1e2e; color: white; text-align: center; padding: 50px; }}
            .card {{ background: #2f3136; max-width: 500px; margin: 0 auto; padding: 30px; border-radius: 12px; }}
            h1 {{ color: #45ddc0; }}
            input[type="file"] {{ margin: 20px 0; padding: 10px; color: white; }}
            button {{ background: #45ddc0; border: none; padding: 12px 24px; border-radius: 6px; font-weight: bold; cursor: pointer; }}
            .msg {{ color: #45ddc0; margin-top: 20px; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>🛠️ Admin Panel</h1>
            <p>Upload a 900x250 default background image.</p>
            <form method="POST" enctype="multipart/form-data">
                <input type="file" name="bg_image" accept="image/png, image/jpeg">
                <br>
                <button type="submit">Upload Background</button>
            </form>
            <div class="msg">{message}</div>
        </div>
    </body>
    </html>
    '''

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
