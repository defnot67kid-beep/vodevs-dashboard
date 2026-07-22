from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, session
from flask_basicauth import BasicAuth
import pymongo
import os
import json
import io
from PIL import Image, ImageDraw, ImageFont, ImageOps
import requests
import traceback

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
# DISCORD OAUTH2 SETUP
# ==========================================
CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "https://vodevs-dashboard-production.up.railway.app")

# ==========================================
# MONGODB SETUP (USES ENVIRONMENT VARIABLE)
# ==========================================
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    print("⚠️ CRITICAL WARNING: MONGO_URI environment variable is missing!")
    print("⚠️ The leaderboard and XP data will not load!")
else:
    client = pymongo.MongoClient(MONGO_URI)
    db = client["vodevs_bot_data"]
    levels_collection = db["levels"]
    invites_collection = db["admin_invites"]
    admins_collection = db["admins"]     # <--- ADDED THIS
    configs_collection = db["config"]

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
    redirect_uri = f"https://vodevs-dashboard-production.up.railway.app/authorize"
    oauth_url = (
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope=identify"
        # REMOVED &state={token} HERE - It is not needed for standard login
    )
    return redirect(oauth_url)

@app.route('/authorize')
def authorize():
    code = request.args.get('code')
    if not code:
        return "❌ No authorization code received.", 400

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
        
        user_resp = requests.get("https://discord.com/api/v10/users/@me", headers={"Authorization": f"Bearer {access_token}"})
        user_info = user_resp.json()
        
        session['user_id'] = user_info['id']
        
        return redirect(url_for('dashboard', guild_id="0", user_id=user_info['id']))
    except Exception as e:
        return f"❌ Login failed: {e}"

@app.route('/dashboard/<guild_id>/<user_id>')
def dashboard(guild_id, user_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
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
        
        stats_line1 = f"Level: {level}   XP: {current_xp:,} / {next_level_xp:,}"
        draw.text((center_x, center_y_name + 42), stats_line1, fill=stats_color, font=font_medium, anchor="mm")
        
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
# WEB LEADERBOARD (READS DIRECTLY FROM DATABASE)
# ==========================================

@app.route('/leaderboard/<server_id>')
def web_leaderboard(server_id):
    try:
        if not MONGO_URI:
            return "MongoDB URI not configured. Please set the MONGO_URI environment variable.", 500

        results = levels_collection.find({"guild_id": server_id}).sort("xp", pymongo.DESCENDING).limit(100)
        
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
        
        has_data = False
        for doc in results:
            has_data = True
            user_id = doc["user_id"]
            xp = doc["xp"]
            
            level = get_level_from_xp(xp)
            xp_formatted = format_xp(xp)
            
            username = doc.get("username", f"User {user_id[:4]}")
            
            avatar_hash = doc.get("avatar_hash")
            if avatar_hash:
                ext = "gif" if avatar_hash.startswith("a_") else "png"
                avatar_url = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.{ext}?size=256"
            else:
                default_avatar_id = (int(user_id) >> 22) % 6
                avatar_url = f"https://cdn.discordapp.com/embed/avatars/{default_avatar_id}.png"
            
            formatted_users.append({
                "username": username,
                "avatar_url": avatar_url,
                "level": level,
                "xp_formatted": xp_formatted,
                "messages": "0",
                "voice_time": "-",
                "is_animated": avatar_hash.startswith("a_") if avatar_hash else False
            })
            
        if not has_data:
            return "No level data found for this server.", 404
            
        return render_template('leaderboard.html', server_name=f"Server {server_id[:4]}", users=formatted_users)
    except Exception as e:
        print("🔥 LEADERBOARD CRASHED WITH ERROR:")
        traceback.print_exc()
        return f"❌ Internal Server Error: {e}", 500

# ==========================================
# SECURE ADMIN ROUTES
# ==========================================

@app.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    # Check if they have a basic auth login OR an admin token
    auth = request.authorization
    if not auth:
        return "❌ Please log in with your Admin Username and Password.", 401

    # Check against admin DB
    admin = admins_collection.find_one({"username": auth.username, "password": auth.password})
    if not admin:
        return "❌ Invalid admin credentials.", 401

    # Use the existing admin panel HTML
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

# ==========================================
# SECURE ADMIN SIGNUP ROUTES
# ==========================================

@app.route('/admin/signup/<token>')
def admin_signup(token):
    """Verify the token and prove identity."""
    # Check if token exists in DB
    invite = invites_collection.find_one({"token": token, "used": False})
    if not invite:
        return "❌ Invalid or already used invite link.", 404

    # Redirect to Discord OAuth2 to prove identity
    redirect_uri = url_for('admin_authorize', _external=True, _scheme='https')
    oauth_url = (
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope=identify"
        f"&state={token}"  # <--- FIX: Added the state param so Discord returns it
    )
    return redirect(oauth_url)

@app.route('/admin/authorize')
def admin_authorize():
    """Complete OAuth2 flow and mark token as used."""
    code = request.args.get('code')
    token = request.args.get('state')
    
    if not code or not token:
        return "❌ Missing authorization code or state.", 400

    # Verify the token is valid
    invite = invites_collection.find_one({"token": token, "used": False})
    if not invite:
        return "❌ Invalid or expired invite token.", 404

    # Exchange code for token
    token_url = "https://discord.com/api/oauth2/token"
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": "https://vodevs-dashboard-production.up.railway.app/admin/authorize" # Hardcoded HTTPS for safety
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        resp = requests.post(token_url, data=data, headers=headers)
        token_data = resp.json()
        access_token = token_data.get("access_token")

        # Fetch user info from Discord
        user_resp = requests.get("https://discord.com/api/v10/users/@me", headers={"Authorization": f"Bearer {access_token}"})
        user_info = user_resp.json()
        discord_id = str(user_info["id"])

        # Check if the Discord ID matches the invite ID
        if discord_id != invite["discord_id"]:
            return "❌ This Discord account does not match the invite recipient.", 403

        # Mark invite as used
        invites_collection.update_one({"token": token}, {"$set": {"used": True}})

        # Prepare HTML signup form
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Create Admin Account</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{ font-family: 'Inter', sans-serif; background: #1e1e2e; color: white; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }}
                .card {{ background: #2f3136; padding: 40px; border-radius: 16px; border: 1px solid #40444b; max-width: 400px; width: 100%; text-align: center; }}
                h1 {{ color: #45ddc0; margin: 0 0 10px 0; font-size: 24px; }}
                p {{ color: #b9bbbe; margin: 0 0 20px 0; font-size: 14px; }}
                form {{ display: flex; flex-direction: column; gap: 15px; }}
                input {{ padding: 12px; border-radius: 8px; border: 1px solid #40444b; background: #202225; color: white; font-size: 16px; outline: none; }}
                input:focus {{ border-color: #5865F2; }}
                button {{ background: #5865F2; color: white; border: none; padding: 12px; border-radius: 8px; font-weight: bold; font-size: 16px; cursor: pointer; transition: 0.2s; }}
                button:hover {{ background: #4752c4; transform: scale(1.02); }}
            </style>
        </head>
        <body>
            <div class="card">
                <h1>🛡️ Create Admin Account</h1>
                <p>Welcome {user_info['username']}! Set up your admin credentials below.</p>
                <form method="POST" action="/admin/register/{discord_id}">
                    <input type="text" name="username" placeholder="Admin Username" required>
                    <input type="password" name="password" placeholder="Admin Password" required>
                    <button type="submit">Create Account</button>
                </form>
            </div>
        </body>
        </html>
        """
    except Exception as e:
        return f"❌ Authentication failed: {e}", 500

@app.route('/admin/register/<discord_id>', methods=['POST'])
def admin_register(discord_id):
    """Register the admin account in the database."""
    username = request.form.get('username')
    password = request.form.get('password')

    if not username or not password:
        return "❌ Username and password required.", 400

    # Check if this Discord ID already has an admin account
    existing = admins_collection.find_one({"discord_id": discord_id})
    if existing:
        return "❌ This Discord account already has an admin account created.", 400

    # Store the admin (In production, hash the password with bcrypt!)
    admins_collection.insert_one({
        "discord_id": discord_id,
        "username": username,
        "password": password  # ⚠️ HASH THIS IN PRODUCTION
    })

    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Account Created</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body { font-family: 'Inter', sans-serif; background: #1e1e2e; color: white; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
            .card { background: #2f3136; padding: 40px; border-radius: 16px; border: 1px solid #40444b; max-width: 400px; width: 100%; text-align: center; }
            h1 { color: #45ddc0; margin: 0; }
            p { color: #b9bbbe; }
            a { color: #5865F2; text-decoration: none; font-weight: bold; }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>✅ Account Created!</h1>
            <p>Your admin account has been successfully created.</p>
            <p>You can now log in at the <a href="/admin">Admin Panel</a>.</p>
        </div>
    </body>
    </html>
    """

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
