from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for
from flask_basicauth import BasicAuth
import json
import os
import io
from PIL import Image, ImageDraw, ImageFont, ImageOps
import requests

app = Flask(__name__)

# ==========================================
# SECURITY SETUP (Admin Login)
# ==========================================
app.config['BASIC_AUTH_USERNAME'] = 'realgyjs@gmail.com'
app.config['BASIC_AUTH_PASSWORD'] = 'Livetopimo'
basic_auth = BasicAuth(app)

# ==========================================
# CONFIGURATION
# ==========================================
CONFIG_FILE = "rank_configs.json"
DEFAULT_BG_FILE = "default_bg.png"  # The default background image file
FONT_PATH = "arial.ttf"

# Load user configurations
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, 'r') as f:
        configs = json.load(f)
else:
    configs = {}

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

@app.route('/get_card/<user_id>')
def get_card(user_id):
    try:
        # Get data from the URL parameters
        name = request.args.get('name', f'User {user_id[:4]}')
        current_xp = int(request.args.get('xp', 0))
        next_level_xp = int(request.args.get('next_xp', 1000))
        progress = float(request.args.get('progress', 0.0))

        # Get User Config
        config = configs.get(user_id, {
            "bg_color": "#2f3136",
            "bar_color": "#5865F2",
            "opacity": 100,
            "font_color": "#ffffff"
        })

        # Decide what background to use
        if os.path.exists(DEFAULT_BG_FILE):
            # Load the default background uploaded by the Admin
            bg_img = Image.open(DEFAULT_BG_FILE).convert("RGB").resize((1000, 300))
        else:
            # Fallback to plain color if no image uploaded
            bg_img = Image.new('RGB', (1000, 300), color=config.get('bg_color', '#2f3136'))

        img = bg_img.copy()
        draw = ImageDraw.Draw(img)

        # 3. Fetch the user's avatar
        avatar_url = f"https://cdn.discordapp.com/avatars/{user_id}/{user_id}.png?size=512"
        avatar_img = None
        try:
            resp = requests.get(avatar_url, timeout=5)
            if resp.status_code == 200:
                avatar_img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
                mask = Image.new('L', avatar_img.size, 0)
                draw_mask = ImageDraw.Draw(mask)
                draw_mask.ellipse((0, 0, avatar_img.size[0], avatar_img.size[1]), fill=255)
                avatar_img = ImageOps.fit(avatar_img, (120, 120), Image.LANCZOS)
                mask = mask.resize((120, 120), Image.LANCZOS)
                avatar_img.putalpha(mask)
            else:
                avatar_img = None
        except:
            avatar_img = None

        # 4. Draw the Avatar
        if avatar_img:
            img.paste(avatar_img, (60, 90), avatar_img)

        # 5. Load Fonts
        try:
            font_large = ImageFont.truetype(FONT_PATH, 40)
            font_medium = ImageFont.truetype(FONT_PATH, 28)
            font_small = ImageFont.truetype(FONT_PATH, 22)
        except:
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_small = ImageFont.load_default()

        # 6. Draw Username
        font_color = config.get('font_color', '#ffffff')
        draw.text((220, 95), name, fill=font_color, font=font_large)

        # 7. Draw XP Text
        xp_text = f"XP: {current_xp:,} / {next_level_xp:,}"
        draw.text((220, 150), xp_text, fill="#b9bbbe", font=font_small)

        # 8. Draw XP Bar
        bar_x = 220
        bar_y = 190
        bar_width = 720
        bar_height = 35
        radius = 18
        draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], radius=radius, fill="#40444b")
        
        filled_width = bar_width * progress
        if filled_width > 0:
            draw.rounded_rectangle([bar_x, bar_y, bar_x + filled_width, bar_y + bar_height], radius=radius, fill=config.get('bar_color', '#5865F2'))

        # Return the image
        img_io = io.BytesIO()
        img.save(img_io, 'PNG')
        img_io.seek(0)
        return send_file(img_io, mimetype='image/png')
    except Exception as e:
        print(f"❌ ERROR in /get_card: {e}")
        return f"❌ Image generation failed: {e}", 500

# ==========================================
# SECURE ADMIN ROUTES (Owner Only)
# ==========================================

@app.route('/admin', methods=['GET', 'POST'])
@basic_auth.required
def admin_panel():
    """Admin panel to upload the default background image."""
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
                message = f"✅ Default background image uploaded successfully! (Size: 1000x300 recommended)"
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Panel - Default Rank Card</title>
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
            <p>Upload a 1000x300 default background image for all rank cards.</p>
            <form method="POST" enctype="multipart/form-data">
                <input type="file" name="bg_image" accept="image/png, image/jpeg">
                <br>
                <button type="submit">Upload Default Background</button>
            </form>
            <div class="msg">{message}</div>
        </div>
    </body>
    </html>
    '''

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
