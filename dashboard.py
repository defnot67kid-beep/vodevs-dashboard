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

        # 1. Create the Base Canvas (1000x300)
        if os.path.exists(DEFAULT_BG_FILE):
            bg_img = Image.open(DEFAULT_BG_FILE).convert("RGB").resize((1000, 300))
        else:
            bg_img = Image.new('RGB', (1000, 300), color=config.get('bg_color', '#2f3136'))

        # 2. Add a semi-transparent dark layer so text pops!
        img = bg_img.copy()
        draw = ImageDraw.Draw(img)
        overlay = Image.new('RGBA', (1000, 300), (0, 0, 0, 140))
        img.paste(overlay, (0, 0), overlay)

        # ==========================================
        # 3. FETCH AND DRAW AVATAR (BULLETPROOF FIX)
        # ==========================================
        avatar_img = None
        
        try:
            # Use Discord's official API to get the avatar hash. This ALWAYS works.
            api_url = f"https://discord.com/api/v10/users/{user_id}"
            headers = {'User-Agent': 'Mozilla/5.0'}
            
            # Fetch the user data from Discord API
            resp = requests.get(api_url, headers=headers, timeout=5)
            
            if resp.status_code == 200:
                user_data = resp.json()
                avatar_hash = user_data.get('avatar')
                
                if avatar_hash:
                    # Determine if the avatar is animated (GIF) or static
                    ext = "gif" if avatar_hash.startswith("a_") else "png"
                    avatar_url = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.{ext}?size=512"
                    
                    # Download the actual image
                    img_resp = requests.get(avatar_url, headers=headers, timeout=5)
                    if img_resp.status_code == 200:
                        avatar_img = Image.open(io.BytesIO(img_resp.content)).convert("RGBA")
                        
                        # Create a circular mask
                        mask = Image.new('L', (140, 140), 0)
                        draw_mask = ImageDraw.Draw(mask)
                        draw_mask.ellipse((0, 0, 140, 140), fill=255)
                        
                        # Resize and apply mask
                        avatar_img = ImageOps.fit(avatar_img, (140, 140), Image.LANCZOS)
                        avatar_img.putalpha(mask)
                        
                        # Paste the avatar onto the card
                        img.paste(avatar_img, (45, 80), avatar_img)
                    else:
                        print(f"❌ Avatar image download failed: {img_resp.status_code}")
                else:
                    print("ℹ️ User has no custom avatar (default Discord avatar).")
            else:
                print(f"❌ Discord API fetch failed: {resp.status_code}")
        except Exception as e:
            print(f"⚠️ Avatar error (Ignored): {e}")

        # ==========================================
        # 4. LOAD FONTS
        # ==========================================
        try:
            font_large = ImageFont.truetype(FONT_PATH, 52)
            font_medium = ImageFont.truetype(FONT_PATH, 36)
            font_small = ImageFont.truetype(FONT_PATH, 26)
        except:
            print("⚠️ WARNING: arial.ttf not found. Using default font.")
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_small = ImageFont.load_default()

        # 5. Draw Username
        font_color = config.get('font_color', '#ffffff')
        draw.text((230, 85), name, fill=font_color, font=font_large)

        # 6. Draw XP Text (Current / Next)
        xp_text = f"XP: {current_xp:,} / {next_level_xp:,}"
        draw.text((230, 150), xp_text, fill="#b9bbbe", font=font_medium)

        # 7. Draw XP Bar (Thick, rounded)
        bar_x = 230
        bar_y = 205
        bar_width = 720
        bar_height = 50
        radius = 25

        draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], radius=radius, fill="#2f3136")
        
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
