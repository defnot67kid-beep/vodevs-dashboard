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
    admin_config = {
        "default_font": "Inter",
        "default_font_size": 64,
        "default_bar_color": "#5865F2",
        "default_font_color": "#ffffff",
        "default_stats_color": "#b9bbbe",
        "default_opacity": 100
    }

# ==========================================
# HELPER: Format numbers to K format (e.g., 1,200 -> 1.2K)
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
    
    # Save user-specific background
    filepath = os.path.join(USER_BG_FOLDER, f"{user_id}.png")
    img = Image.open(file.stream).convert("RGB")
    img = img.resize((1000, 300)) # Force correct size
    img.save(filepath)
    return "Uploaded", 200

@app.route('/get_card/<user_id>')
def get_card(user_id):
    try:
        # 1. Get data from URL parameters
        name = request.args.get('name', f'User')
        current_xp = int(request.args.get('xp', 0))
        next_level_xp = int(request.args.get('next_xp', 1000))
        progress = float(request.args.get('progress', 0.0))
        avatar_url = request.args.get('avatar')
        rank = request.args.get('rank', '?')

        # 2. Load User Config (Fallback to Admin Defaults!)
        user_conf = configs.get(user_id, {})
        
        config = {
            "bg_color": user_conf.get('bg_color', "#2f3136"),
            "bar_color": user_conf.get('bar_color', admin_config['default_bar_color']),
            "opacity": user_conf.get('opacity', admin_config['default_opacity']),
            "font_color": user_conf.get('font_color', admin_config['default_font_color']),
            "stats_color": user_conf.get('stats_color', admin_config['default_stats_color']),
            "font_family": user_conf.get('font_family', admin_config['default_font']),
            "font_size": user_conf.get('font_size', admin_config['default_font_size'])
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

        # Apply Overlay (Opacity)
        overlay_strength = int(config.get('opacity', 100))
        if overlay_strength > 0:
            overlay = Image.new('RGBA', (1000, 300), (0, 0, 0, overlay_strength))
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
                    img.paste(avatar_img, (45, 95), avatar_img)
            except Exception as e:
                print(f"⚠️ Avatar error: {e}")

        # 5. Load Font
        font_name = config.get('font_family', admin_config['default_font'])
        font_path_map = {
            "Inter": "Inter-Regular.ttf",
            "Roboto": "Roboto-Regular.ttf",
            "Open Sans": "OpenSans-Regular.ttf",
            "Montserrat": "Montserrat-Regular.ttf"
        }
        font_file = font_path_map.get(font_name, "Inter-Regular.ttf")
        
        font_size_large = int(config.get('font_size', admin_config['default_font_size']))
        font_size_medium = int(font_size_large * 0.6)

        try:
            font_large = ImageFont.truetype(font_file, font_size_large)
            font_medium = ImageFont.truetype(font_file, font_size_medium)
        except:
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()

        # 6. Draw Text (Arcane Style!)
        font_color = config.get('font_color', admin_config['default_font_color'])
        stats_color = config.get('stats_color', admin_config['default_stats_color'])
        
        # Username
        draw.text((185, 70), f"@{name}", fill=font_color, font=font_large)

        # Red Accent Line directly under the username
        # Measure text to get exact width
        bbox = draw.textbbox((0, 0), f"@{name}", font=font_large)
        text_width = bbox[2] - bbox[0]
        line_y = 70 + font_size_large + 5
        draw.line([(185, line_y), (185 + text_width, line_y)], fill=config.get('bar_color', admin_config['default_bar_color']), width=4)

        # Stats Text (Using K format!)
        formatted_current = format_k(current_xp)
        formatted_next = format_k(next_level_xp)
        stats_text = f"Level: 0  XP: {formatted_current} / {formatted_next}  Rank: #{rank}"
        draw.text((185, 120), stats_text, fill=stats_color, font=font_medium)

        # 7. Draw Progress Bar (Clean White & Colored)
        bar_x = 185
        bar_y = 170
        bar_width = 780
        bar_height = 28
        radius = 14

        draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], radius=radius, fill="#ffffff")
        
        filled_width = bar_width * progress
        if filled_width > 0:
            draw.rounded_rectangle([bar_x, bar_y, bar_x + filled_width, bar_y + bar_height], radius=radius, fill=config.get('bar_color', admin_config['default_bar_color']))

        img_io = io.BytesIO()
        img.save(img_io, 'PNG')
        img_io.seek(0)
        return send_file(img_io, mimetype='image/png')
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return f"❌ Image generation failed", 500

# ==========================================
# SECURE ADMIN ROUTES
# ==========================================

@app.route('/admin', methods=['GET', 'POST'])
@basic_auth.required
def admin_panel():
    global admin_config
    message = ""
    
    if request.method == 'POST':
        if 'bg_image' in request.files and request.files['bg_image'].filename != '':
            file = request.files['bg_image']
            img = Image.open(file.stream).convert("RGB").resize((1000, 300))
            img.save(DEFAULT_BG_FILE)
            message = "✅ Default background uploaded! (1000x300)"
        
        elif 'action' in request.form and request.form['action'] == 'save_settings':
            admin_config['default_font'] = request.form.get('default_font', 'Inter')
            admin_config['default_font_size'] = int(request.form.get('default_font_size', 42))
            admin_config['default_bar_color'] = request.form.get('default_bar_color', '#5865F2')
            admin_config['default_font_color'] = request.form.get('default_font_color', '#ffffff')
            admin_config['default_stats_color'] = request.form.get('default_stats_color', '#b9bbbe')
            admin_config['default_opacity'] = int(request.form.get('default_opacity', 100))
            
            with open(ADMIN_CONFIG_FILE, 'w') as f:
                json.dump(admin_config, f, indent=4)
            message = "✅ Admin settings updated successfully!"
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Panel</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap" rel="stylesheet">
        <style>
            body {{ font-family: 'Inter', sans-serif; background: #1e1e2e; color: white; padding: 20px; text-align: center; }}
            .card {{ background: #2f3136; max-width: 700px; margin: 20px auto; padding: 30px; border-radius: 16px; border: 1px solid #40444b; text-align: left; }}
            h1, h2 {{ color: #45ddc0; }}
            label {{ display: block; margin-top: 15px; font-weight: 600; color: #b9bbbe; }}
            select, input, button {{ width: 100%; padding: 10px; margin-top: 5px; border-radius: 6px; border: 1px solid #40444b; background: #202225; color: white; font-size: 16px; box-sizing: border-box; }}
            input[type="color"] {{ height: 50px; padding: 0; cursor: pointer; }}
            input[type="number"] {{ width: 100px; }}
            button {{ background: #5865F2; border: none; font-weight: bold; cursor: pointer; transition: 0.2s; }}
            button:hover {{ background: #4752c4; }}
            .msg {{ color: #45ddc0; margin-top: 20px; text-align: center; font-weight: bold; }}
            .upload-box {{ border: 2px dashed #40444b; padding: 20px; text-align: center; border-radius: 10px; margin-top: 10px; }}
            .row {{ display: flex; gap: 15px; align-items: center; flex-wrap: wrap; }}
        </style>
    </head>
    <body>
        <h1>🛠️ Admin Control Panel</h1>
        <div class="msg">{message}</div>

        <div class="card">
            <h2>📷 Default Background</h2>
            <p style="color:#b9bbbe;">Upload a 1000x300 background image.</p>
            <form method="POST" enctype="multipart/form-data">
                <div class="upload-box">
                    <input type="file" name="bg_image" accept="image/png,image/jpeg" style="width:auto; display:inline-block;">
                    <button type="submit" style="width:auto; padding: 10px 20px; margin-left:10px;">Upload</button>
                </div>
            </form>
        </div>

        <div class="card">
            <h2>⚙️ Global Default Settings</h2>
            <p style="color:#b9bbbe;">These settings apply to all users.</p>
            <form method="POST">
                <input type="hidden" name="action" value="save_settings">
                
                <label>Default Font Family</label>
                <select name="default_font">
                    <option value="Inter" {"selected" if admin_config['default_font'] == 'Inter' else ""}>Inter</option>
                    <option value="Roboto" {"selected" if admin_config['default_font'] == 'Roboto' else ""}>Roboto</option>
                    <option value="Open Sans" {"selected" if admin_config['default_font'] == 'Open Sans' else ""}>Open Sans</option>
                    <option value="Montserrat" {"selected" if admin_config['default_font'] == 'Montserrat' else ""}>Montserrat</option>
                </select>

                <label>Default Font Size (px)</label>
                <input type="number" name="default_font_size" value="{admin_config['default_font_size']}" min="20" max="100">

                <label>Default Username Color</label>
                <input type="color" name="default_font_color" value="{admin_config['default_font_color']}">

                <label>Default Stats Color</label>
                <input type="color" name="default_stats_color" value="{admin_config['default_stats_color']}">

                <label>Default Progress Bar Color</label>
                <input type="color" name="default_bar_color" value="{admin_config['default_bar_color']}">

                <label>Default Background Overlay (Darkness)</label>
                <input type="number" name="default_opacity" value="{admin_config['default_opacity']}" min="0" max="180">

                <button type="submit" style="margin-top: 25px;">Save Global Settings</button>
            </form>
        </div>
    </body>
    </html>
    '''

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
