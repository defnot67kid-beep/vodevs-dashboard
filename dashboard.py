from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, session
from flask_basicauth import BasicAuth
import json
import os
import io
import sqlite3
import traceback
from PIL import Image, ImageDraw, ImageFont, ImageOps
import requests

app = Flask(__name__)

# ==========================================
# SESSION CONFIG (Fixed for Railway)
# ==========================================
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_FILE_DIR'] = './flask_session/'

# ==========================================
# DISCORD OAUTH2 SETUP (Manual URL Build)
# ==========================================
CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "https://vodevs-dashboard-production.up.railway.app")

# ==========================================
# SECURITY (Admin Login)
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
FONTS_FOLDER = "fonts/"
DB_FILE = os.getenv("DB_PATH", "level_data.db")


if not os.path.exists(USER_BG_FOLDER):
    os.makedirs(USER_BG_FOLDER)
if not os.path.exists(FONTS_FOLDER):
    os.makedirs(FONTS_FOLDER)

if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, 'r') as f:
        configs = json.load(f)
else:
    configs = {}

if os.path.exists(ADMIN_CONFIG_FILE):
    with open(ADMIN_CONFIG_FILE, 'r') as f:
        admin_config = json.load(f)
else:
    admin_config = {
        "default_font": "Inter",
        "default_font_size": 48,
        "default_bar_color": "#5865F2",
        "default_font_color": "#ffffff",
        "default_stats_color": "#b9bbbe",
        "default_opacity": 0
    }

# ==========================================
# PUBLIC ROUTES
# ==========================================

@app.route('/')
def home():
    return "✅ Rank Card Dashboard is online!"

@app.route('/dashboard')
def dashboard_redirect():
    return redirect(url_for('login'))

@app.route('/login')
def login():
    # MANUAL URL GENERATION (Eliminates mismatching_state error)
    redirect_uri = f"https://vodevs-dashboard-production.up.railway.app/authorize"
    oauth_url = (
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope=identify"
    )
    return redirect(oauth_url)

@app.route('/authorize')
def authorize():
    code = request.args.get('code')
    if not code:
        return "❌ No authorization code received.", 400

    # Exchange the code for a token manually
    token_url = "https://discord.com/api/oauth2/token"
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": "https://vodevs-dashboard-production.up.railway.app/authorize"
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    
    try:
        token_resp = requests.post(token_url, data=data, headers=headers)
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        
        # Fetch user info
        user_resp = requests.get("https://discord.com/api/v10/users/@me", headers={"Authorization": f"Bearer {access_token}"})
        user_info = user_resp.json()
        
        # Store user ID in session
        session['user_id'] = user_info['id']
        
        # Redirect to dashboard
        return redirect(url_for('dashboard', guild_id="0", user_id=user_info['id']))
    except Exception as e:
        return f"❌ Login failed: {e}"

@app.route('/dashboard/<guild_id>/<user_id>')
def dashboard(guild_id, user_id):
    # SECURITY CHECK: Ensure the logged-in user is accessing their own card
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # If the user accesses a different user's ID, redirect them to their OWN dashboard
    if session['user_id'] != user_id:
        return redirect(url_for('dashboard', guild_id=guild_id, user_id=session['user_id']))
    
    font_files = [f[:-4] for f in os.listdir(FONTS_FOLDER) if f.endswith('.ttf')]
    if not font_files:
        font_files = ["Inter"]
    
    config_key = f"{guild_id}_{user_id}"
    user_config = configs.get(config_key, {})
    
    return render_template('dashboard.html', guild_id=guild_id, user_id=user_id, config=user_config, fonts=font_files)

@app.route('/save_config/<guild_id>/<user_id>', methods=['POST'])
def save_config(guild_id, user_id):
    if 'user_id' not in session or session['user_id'] != user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    data = request.json
    config_key = f"{guild_id}_{user_id}"
    configs[config_key] = data
    with open(CONFIG_FILE, 'w') as f:
        json.dump(configs, f, indent=4)
    return jsonify({"status": "saved"})

@app.route('/reset_config/<guild_id>/<user_id>', methods=['POST'])
def reset_config(guild_id, user_id):
    if 'user_id' not in session or session['user_id'] != user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    config_key = f"{guild_id}_{user_id}"
    if config_key in configs:
        del configs[config_key]
        with open(CONFIG_FILE, 'w') as f:
            json.dump(configs, f, indent=4)
    return jsonify({"status": "reset"})

@app.route('/upload_bg/<guild_id>/<user_id>', methods=['POST'])
def upload_bg(guild_id, user_id):
    if 'user_id' not in session or session['user_id'] != user_id:
        return "Unauthorized", 403

    if 'bg_image' not in request.files:
        return "No file", 400
    file = request.files['bg_image']
    if file.filename == '':
        return "No file", 400
    
    filepath = os.path.join(USER_BG_FOLDER, f"{guild_id}_{user_id}.png")
    img = Image.open(file.stream).convert("RGB")
    img = img.resize((900, 250))
    img.save(filepath)
    return "Uploaded", 200

@app.route('/remove_bg/<guild_id>/<user_id>', methods=['POST'])
def remove_bg(guild_id, user_id):
    if 'user_id' not in session or session['user_id'] != user_id:
        return "Unauthorized", 403

    filepath = os.path.join(USER_BG_FOLDER, f"{guild_id}_{user_id}.png")
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
            return "Removed", 200
        except:
            return "Failed to remove", 500
    return "No file found", 200

@app.route('/get_card/<guild_id>/<user_id>')
def get_card(guild_id, user_id):
    try:
        name = request.args.get('name', f'User')
        level = int(request.args.get('level', 0))
        rank = int(request.args.get('rank', 0))
        current_xp = int(request.args.get('xp', 0))
        next_level_xp = int(request.args.get('next_xp', 1000))
        progress = float(request.args.get('progress', 0.0))
        avatar_url = request.args.get('avatar')

        config_key = f"{guild_id}_{user_id}"
        user_conf = configs.get(config_key, {})
        
        config = {
            "bar_color": user_conf.get('bar_color', admin_config['default_bar_color']),
            "font_color": user_conf.get('font_color', admin_config['default_font_color']),
            "stats_color": user_conf.get('stats_color', admin_config['default_stats_color']),
            "font_family": user_conf.get('font_family', admin_config['default_font']),
            "font_size": user_conf.get('font_size', admin_config['default_font_size'])
        }

        user_bg_path = os.path.join(USER_BG_FOLDER, f"{guild_id}_{user_id}.png")
        if os.path.exists(user_bg_path):
            bg_img = Image.open(user_bg_path).convert("RGB").resize((900, 250))
        elif os.path.exists(DEFAULT_BG_FILE):
            bg_img = Image.open(DEFAULT_BG_FILE).convert("RGB").resize((900, 250))
        else:
            bg_img = Image.new('RGB', (900, 250), color='#2f3136')

        img = bg_img.copy()
        draw = ImageDraw.Draw(img)

        box_padding = 20
        box_x, box_y = box_padding, box_padding
        box_w, box_h = 900 - (box_padding * 2), 250 - (box_padding * 2)
        draw.rounded_rectangle([box_x, box_y, box_x + box_w, box_y + box_h], radius=20, fill="#ffffff")

        avatar_img = None
        if avatar_url:
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                resp = requests.get(avatar_url, headers=headers, timeout=5)
                if resp.status_code == 200:
                    avatar_img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
                    mask = Image.new('L', (80, 80), 0)
                    draw_mask = ImageDraw.Draw(mask)
                    draw_mask.ellipse((0, 0, 80, 80), fill=255)
                    avatar_img = ImageOps.fit(avatar_img, (80, 80), Image.LANCZOS)
                    avatar_img.putalpha(mask)
                    img.paste(avatar_img, (box_x + 20, box_y + 20), avatar_img)
            except Exception as e:
                print(f"⚠️ Avatar error: {e}")

        font_name = config.get('font_family', admin_config['default_font'])
        font_file_path = os.path.join(FONTS_FOLDER, f"{font_name}.ttf")
        font_size_large = int(config.get('font_size', admin_config['default_font_size'])) - 6
        font_size_medium = int(font_size_large * 0.55)

        try:
            font_large = ImageFont.truetype(font_file_path, font_size_large)
            font_medium = ImageFont.truetype(font_file_path, font_size_medium)
        except:
            fallback_path = os.path.join(FONTS_FOLDER, "Inter.ttf")
            try:
                font_large = ImageFont.truetype(fallback_path, font_size_large)
                font_medium = ImageFont.truetype(fallback_path, font_size_medium)
            except:
                font_large = ImageFont.load_default()
                font_medium = ImageFont.load_default()

        # 6. Draw Text
        text_color = "#000000"
        stats_color = "#3d3d3d"
        center_x = box_x + (box_w / 2) - 10
        center_y_name = 75

        draw.text((center_x, center_y_name), f"@{name}", fill=text_color, font=font_large, anchor="mm")
        
        # Level and XP line
        stats_line1 = f"Level: {level}   XP: {current_xp:,} / {next_level_xp:,}"
        draw.text((center_x, center_y_name + 42), stats_line1, fill=stats_color, font=font_medium, anchor="mm")
        
        # Rank line (underneath)
        if rank > 0:
            stats_line2 = f"Rank: #{rank}"
            draw.text((center_x, center_y_name + 72), stats_line2, fill=stats_color, font=font_medium, anchor="mm")

        bar_x = box_x + 30
        bar_y = box_y + box_h - 30
        bar_width = box_w - 60
        bar_height = 20
        radius = 12

        draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], radius=radius, fill="#e0e0e0")
        
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
# WEB LEADERBOARD (FIXED: Returns friendly error messages)
# ==========================================

@app.route('/leaderboard/<server_id>')
def web_leaderboard(server_id):
    try:
        # If the database file doesn't exist
        if not os.path.exists(DB_FILE):
            return "The bot hasn't generated a database yet. Wait for members to chat or run `!level`.", 404
            
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # Check if this specific server has data
        c.execute("SELECT COUNT(*) FROM levels WHERE guild_id = ?", (server_id,))
        count = c.fetchone()[0]
        
        if count == 0:
            conn.close()
            return f"No members found in database for server {server_id}. Members must chat to appear.", 404
        
        # Get all users for this guild
        c.execute("SELECT user_id, xp FROM levels WHERE guild_id = ? ORDER BY xp DESC LIMIT 100", (server_id,))
        sorted_users = c.fetchall()
        conn.close()
        
        formatted_users = []
        
        def format_xp(xp):
            if xp >= 1000000: return f"{xp/1000000:.1f}M"
            elif xp >= 1000: return f"{xp/1000:.1f}K"
            else: return str(xp)
                
        def get_level_from_xp(xp):
            level = 0
            while int(1000 * ((level + 1) ** 1.5)) <= xp:
                level += 1
            return level
        
        for user_id, xp in sorted_users:
            level = get_level_from_xp(xp)
            xp_formatted = format_xp(xp)
            
            # Placeholder for user avatar URL
            avatar_url = f"https://cdn.discordapp.com/avatars/{user_id}/{user_id}.png"
            
            formatted_users.append({
                "username": f"User {user_id[:4]}",
                "avatar_url": avatar_url,
                "level": level,
                "xp_formatted": xp_formatted
            })
            
        return render_template('leaderboard.html', server_name=f"Server {server_id[:4]}", users=formatted_users)
    except Exception as e:
        # This will print the exact Python error to your Railway logs!
        print("🔥 LEADERBOARD CRASHED WITH ERROR:")
        traceback.print_exc()
        return f"❌ Internal Server Error: {e}", 500

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
            img = Image.open(file.stream).convert("RGB").resize((900, 250))
            img.save(DEFAULT_BG_FILE)
            message = "✅ Default background uploaded! (900x250)"
        
        elif 'font_file' in request.files and request.files['font_file'].filename != '':
            file = request.files['font_file']
            if file.filename.endswith('.ttf'):
                filepath = os.path.join(FONTS_FOLDER, file.filename)
                file.save(filepath)
                message = f"✅ Font '{file.filename}' uploaded successfully!"
            else:
                message = "❌ Invalid file type. Please upload a .ttf file."

        elif 'action' in request.form and request.form['action'] == 'save_settings':
            admin_config['default_font'] = request.form.get('default_font', 'Inter')
            admin_config['default_font_size'] = int(request.form.get('default_font_size', 42))
            admin_config['default_bar_color'] = request.form.get('default_bar_color', '#5865F2')
            admin_config['default_font_color'] = request.form.get('default_font_color', '#ffffff')
            admin_config['default_stats_color'] = request.form.get('default_stats_color', '#b9bbbe')
            admin_config['default_opacity'] = int(request.form.get('default_opacity', 0))
            
            with open(ADMIN_CONFIG_FILE, 'w') as f:
                json.dump(admin_config, f, indent=4)
            message = "✅ Admin settings updated successfully!"
    
    font_files = [f[:-4] for f in os.listdir(FONTS_FOLDER) if f.endswith('.ttf')]
    
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
            
            .upload-zone {{
                border: 2px dashed #40444b;
                padding: 30px;
                text-align: center;
                border-radius: 10px;
                margin-top: 10px;
                transition: all 0.3s;
                cursor: pointer;
                position: relative;
            }}
            .upload-zone.dragover {{
                border-color: #5865F2;
                background: rgba(88, 101, 242, 0.1);
                transform: scale(1.02);
            }}
            .upload-zone input {{
                position: absolute;
                width: 100%;
                height: 100%;
                top: 0;
                left: 0;
                opacity: 0;
                cursor: pointer;
            }}
            .upload-zone p {{ margin: 0; color: #b9bbbe; }}
        </style>
    </head>
    <body>
        <h1>🛠️ Admin Control Panel</h1>
        <div class="msg">{message}</div>

        <div class="card">
            <h2>📷 Default Background</h2>
            <p style="color:#b9bbbe;">Upload a 900x250 background image.</p>
            <div class="upload-zone">
                <p>📁 Drag & Drop or Click to Upload Background</p>
                <form method="POST" enctype="multipart/form-data">
                    <input type="file" name="bg_image" accept="image/png,image/jpeg">
                </form>
            </div>
        </div>

        <div class="card">
            <h2>📁 Font Manager (Drag & Drop)</h2>
            <p style="color:#b9bbbe;">Drag & Drop .ttf files here. They will immediately appear in the user dashboard.</p>
            <div class="upload-zone" id="fontDropZone">
                <p>📁 Drag & Drop .ttf Fonts Here or Click</p>
                <form method="POST" enctype="multipart/form-data">
                    <input type="file" name="font_file" accept=".ttf" id="fontInput">
                </form>
            </div>
            <div style="margin-top:15px; font-size:14px; color:#b9bbbe;">
                <strong>Installed Fonts:</strong> {', '.join(font_files) if font_files else 'None uploaded yet.'}
            </div>
        </div>

        <div class="card">
            <h2>⚙️ Global Default Settings</h2>
            <p style="color:#b9bbbe;">These settings apply to all users who haven't customized them yet.</p>
            <form method="POST">
                <input type="hidden" name="action" value="save_settings">
                
                <label>Default Font Family</label>
                <select name="default_font">
                    {"".join([f'<option value="{f}" {"selected" if admin_config["default_font"] == f else ""}>{f}</option>' for f in font_files])}
                    <option value="Inter" {"selected" if admin_config['default_font'] == 'Inter' else ""}>Inter (Fallback)</option>
                </select>

                <label>Default Font Size (px)</label>
                <input type="number" name="default_font_size" value="{admin_config['default_font_size']}" min="20" max="100">

                <label>Default Username Color</label>
                <input type="color" name="default_font_color" value="{admin_config['default_font_color']}">

                <label>Default Stats Color</label>
                <input type="color" name="default_stats_color" value="{admin_config['default_stats_color']}">

                <label>Default Progress Bar Color</label>
                <input type="color" name="default_bar_color" value="{admin_config['default_bar_color']}">

                <button type="submit" style="margin-top: 25px;">Save Global Settings</button>
            </form>
        </div>

        <script>
            const dropZones = document.querySelectorAll('.upload-zone');
            dropZones.forEach(zone => {{
                ['dragenter', 'dragover'].forEach(eventName => {{
                    zone.addEventListener(eventName, (e) => {{
                        e.preventDefault();
                        e.stopPropagation();
                        zone.classList.add('dragover');
                    }}, false);
                }});

                ['dragleave', 'drop'].forEach(eventName => {{
                    zone.addEventListener(eventName, (e) => {{
                        e.preventDefault();
                        e.stopPropagation();
                        zone.classList.remove('dragover');
                    }}, false);
                }});
            }});

            document.querySelectorAll('.upload-zone input[type="file"]').forEach(input => {{
                input.addEventListener('change', function() {{
                    if(this.files.length > 0) {{
                        this.closest('form').submit();
                    }}
                }});
            }});
        </script>
    </body>
    </html>
    '''

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
