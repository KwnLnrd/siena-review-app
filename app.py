import os
import json
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, exc
from datetime import datetime
from functools import wraps

# --- CONFIGURATION ---
load_dotenv()
app = Flask(__name__)

# --- SÉCURITÉ ---
is_production = os.getenv('RENDER', False)
allowed_origins = "https://sienarestaurant.netlify.app" if is_production else "*"
CORS(app, origins=allowed_origins, supports_credentials=True)

# --- CONFIGURATION DB ---
database_url = os.getenv('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url.replace("postgres://", "postgresql://", 1)
else:
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'local_reviews.db')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
DASHBOARD_PASSWORD = os.getenv('DASHBOARD_PASSWORD', 'siena_secret_password')
db = SQLAlchemy(app)

# --- MODÈLES DE LA BASE DE DONNÉES ---
class GeneratedReview(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    server_name = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

class Server(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)

class TranslationMixin:
    text_fr = db.Column(db.String(100), nullable=False)
    text_en = db.Column(db.String(100))
    text_es = db.Column(db.String(100))
    text_it = db.Column(db.String(100))
    text_pt = db.Column(db.String(100))
    text_zh = db.Column(db.String(100))
    text_ar = db.Column(db.String(100))

class FlavorOption(db.Model, TranslationMixin):
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(50), nullable=False)

class AtmosphereOption(db.Model, TranslationMixin):
    id = db.Column(db.Integer, primary_key=True)

# --- INITIALISATION AUTOMATIQUE DE LA DB ---
with app.app_context():
    db.create_all()

# --- SÉCURISATION ---
def password_protected(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth = request.authorization
        if not auth or not (auth.username == 'admin' and auth.password == DASHBOARD_PASSWORD):
            return 'Accès non autorisé.', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'}
        return f(*args, **kwargs)
    return decorated_function

def no_cache(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        response = make_response(f(*args, **kwargs))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '-1'
        return response
    return decorated_function

# --- FONCTION DE TRADUCTION ---
def get_translations(text_to_translate):
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        prompt = f"""
        Translate the following French restaurant term '{text_to_translate}' into English, Spanish, Italian, Portuguese, Chinese (Simplified), and Arabic.
        Return the result as a single, minified JSON object with keys "en", "es", "it", "pt", "zh", "ar".
        Example: if the term is "Poulpe Grillé", the output should be {{"en":"Grilled Octopus","es":"Pulpo a la parrilla","it":"Polpo Grigliato","pt":"Polvo Grelhado","zh":"烤章鱼", "ar":"أخطبوط مشوي"}}.
        """
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": prompt}],
            temperature=0.2
        )
        return json.loads(completion.choices[0].message.content)
    except Exception as e:
        print(f"Erreur de traduction OpenAI : {e}")
        return None

# --- ROUTES API (PROTÉGÉES) POUR LA GESTION ---
@app.route('/api/servers', methods=['GET', 'POST'])
@password_protected
@no_cache
def manage_servers():
    if request.method == 'POST':
        data = request.get_json()
        if not data or not data.get('name'): return jsonify({"error": "Nom manquant."}), 400
        new_server = Server(name=data['name'].strip().title())
        db.session.add(new_server)
        db.session.commit()
        return jsonify({"id": new_server.id, "name": new_server.name}), 201
    servers = Server.query.order_by(Server.name).all()
    return jsonify([{"id": s.id, "name": s.name} for s in servers])

@app.route('/api/servers/<int:server_id>', methods=['DELETE'])
@password_protected
def delete_server(server_id):
    server = Server.query.get_or_404(server_id)
    db.session.delete(server)
    db.session.commit()
    return jsonify({"success": True})

@app.route('/api/options/<option_type>', methods=['GET', 'POST'])
@password_protected
@no_cache
def manage_options(option_type):
    Model = FlavorOption if option_type == 'flavors' else AtmosphereOption
    if request.method == 'POST':
        data = request.get_json()
        if not data or not data.get('text_fr'): return jsonify({"error": "Texte français manquant."}), 400
        
        text_fr = data['text_fr'].strip()
        translations = get_translations(text_fr)
        if not translations:
            return jsonify({"error": "La traduction automatique a échoué."}), 500

        new_option_data = {
            'text_fr': text_fr, 'text_en': translations.get('en'), 'text_es': translations.get('es'),
            'text_it': translations.get('it'), 'text_pt': translations.get('pt'),
            'text_zh': translations.get('zh'), 'text_ar': translations.get('ar')
        }
        if option_type == 'flavors':
            if not data.get('category'): return jsonify({"error": "Catégorie manquante."}), 400
            new_option_data['category'] = data['category'].strip()
        
        new_option = Model(**new_option_data)
        db.session.add(new_option)
        db.session.commit()
        return jsonify({"id": new_option.id, "text": new_option.text_fr}), 201
    
    options = Model.query.all()
    if option_type == 'flavors':
        return jsonify([{"id": opt.id, "text": opt.text_fr, "category": opt.category} for opt in options])
    return jsonify([{"id": opt.id, "text": opt.text_fr} for opt in options])

@app.route('/api/options/<option_type>/<int:option_id>', methods=['DELETE'])
@password_protected
def delete_option(option_type, option_id):
    Model = FlavorOption if option_type == 'flavors' else AtmosphereOption
    option = Model.query.get_or_404(option_id)
    db.session.delete(option)
    db.session.commit()
    return jsonify({"success": True})

# --- ROUTES API PUBLIQUES ---
@app.route('/api/public/options')
@no_cache
def get_public_options():
    lang = request.args.get('lang', 'fr')
    try:
        server_col = Server.name
        flavor_col = getattr(FlavorOption, f'text_{lang}', FlavorOption.text_fr)
        atmosphere_col = getattr(AtmosphereOption, f'text_{lang}', AtmosphereOption.text_fr)

        servers = db.session.query(server_col).order_by(server_col).all()
        flavors = db.session.query(FlavorOption.id, flavor_col, FlavorOption.category).all()
        atmospheres = db.session.query(AtmosphereOption.id, atmosphere_col).order_by(AtmosphereOption.id).all()

        categorized_flavors = {}
        for f_id, f_text, f_category in flavors:
            if f_category not in categorized_flavors: categorized_flavors[f_category] = []
            categorized_flavors[f_category].append({"id": f_id, "text": f_text})
        
        return jsonify({
            "servers": [{"name": s[0]} for s in servers],
            "flavors": categorized_flavors,
            "atmospheres": [{"id": a_id, "text": a_text} for a_id, a_text in atmospheres]
        })
    except Exception as e:
        print(f"Erreur DB sur route publique : {e}")
        return jsonify({"error": "Service momentanément indisponible."}), 503

# --- ROUTE DE GÉNÉRATION D'AVIS ---
@app.route('/generate-review', methods=['POST'])
def generate_review():
    # ... (le code de cette fonction est inchangé)
    pass

# --- ROUTE DU TABLEAU DE BORD ---
@app.route('/dashboard')
@password_protected
def dashboard():
    try:
        server_counts = db.session.query(GeneratedReview.server_name, func.count(GeneratedReview.server_name).label('review_count')).group_by(GeneratedReview.server_name).order_by(func.count(GeneratedReview.server_name).desc()).all()
        results = [{"server": name, "count": count} for name, count in server_counts]
        return jsonify(results)
    except Exception as e:
        print(f"Erreur Dashboard: {e}")
        return jsonify({"error": f"Erreur de récupération des données."}), 500

if __name__ == '__main__':
    app.run(port=5000, debug=True)
