import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, exc
from datetime import datetime
from functools import wraps
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman

# --- CONFIGURATION ---
load_dotenv()
app = Flask(__name__)

# --- CONFIGURATION DE SÉCURITÉ ---
is_production = os.getenv('RENDER', False)
allowed_origins = "https://sienarestaurant.netlify.app" if is_production else "*"
CORS(app, origins=allowed_origins, supports_credentials=True)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
)

Talisman(app, content_security_policy=False)

# --- CONFIGURATION DE LA BASE DE DONNÉES (VERSION FINALE) ---
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

class FlavorOption(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(100), unique=True, nullable=False)
    category = db.Column(db.String(50), nullable=False)

class AtmosphereOption(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(100), unique=True, nullable=False)

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

# --- ROUTES API (PROTÉGÉES) POUR LA GESTION ---
@app.route('/api/servers', methods=['GET', 'POST'])
@password_protected
@limiter.limit("30 per minute")
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
@limiter.limit("30 per minute")
def manage_options(option_type):
    Model = FlavorOption if option_type == 'flavors' else AtmosphereOption
    if request.method == 'POST':
        data = request.get_json()
        if not data or not data.get('text'): return jsonify({"error": "Texte manquant."}), 400
        new_option_data = {'text': data['text'].strip()}
        if option_type == 'flavors':
            if not data.get('category'): return jsonify({"error": "Catégorie manquante."}), 400
            new_option_data['category'] = data['category'].strip()
        new_option = Model(**new_option_data)
        db.session.add(new_option)
        db.session.commit()
        return jsonify({"id": new_option.id, "text": new_option.text}), 201
    options = Model.query.all()
    if option_type == 'flavors':
        return jsonify([{"id": opt.id, "text": opt.text, "category": opt.category} for opt in options])
    return jsonify([{"id": opt.id, "text": opt.text} for opt in options])

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
@limiter.limit("60 per minute")
def get_public_options():
    try:
        servers = Server.query.order_by(Server.name).all()
        flavors = FlavorOption.query.all()
        atmospheres = AtmosphereOption.query.order_by(AtmosphereOption.id).all()
        categorized_flavors = {}
        for f in flavors:
            if f.category not in categorized_flavors: categorized_flavors[f.category] = []
            categorized_flavors[f.category].append({"id": f.id, "text": f.text})
        return jsonify({
            "servers": [{"name": s.name} for s in servers],
            "flavors": categorized_flavors,
            "atmospheres": [{"id": a.id, "text": a.text} for a in atmospheres]
        })
    except exc.SQLAlchemyError as e:
        print(f"Erreur de base de données sur la route publique : {e}")
        return jsonify({"error": "Le service est momentanément indisponible."}), 503

# --- ROUTE DE GÉNÉRATION D'AVIS ---
@app.route('/generate-review', methods=['POST'])
@limiter.limit("5 per minute")
def generate_review():
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    except Exception as e: return jsonify({"error": "Clé API OpenAI non valide."}), 500
    data = request.get_json()
    if not data: return jsonify({"error": "Données invalides."}), 400
    lang = data.get('lang', 'fr')
    selected_tags = data.get('tags', [])
    prenom_serveur = "notre serveur(se)"
    service_qualities, liked_dishes, atmosphere_notes = [], [], []
    event = "une simple visite"
    for tag in selected_tags:
        category, value = tag.get('category'), tag.get('value')
        if category == 'server_name': prenom_serveur = value
        elif category == 'service_qualities': service_qualities.append(value)
        elif category == 'reason_for_visit': event = value
        elif category == 'birthday_details': event += f" ({value})"
        elif category == 'liked_dishes': liked_dishes.append(value)
        elif category == 'atmosphere': atmosphere_notes.append(value)
    if prenom_serveur != "notre serveur(se)":
        try:
            db.session.add(GeneratedReview(server_name=prenom_serveur))
            db.session.commit()
        except Exception as e: print(f"Erreur DB: {e}"); db.session.rollback()
    prompt_details = "Points que le client a aimés : "
    if service_qualities: prompt_details += f"- Le service de {prenom_serveur} était : {', '.join(service_qualities)}. "
    if liked_dishes: prompt_details += f"- Plats préférés : {', '.join(liked_dishes)}. "
    if atmosphere_notes: prompt_details += f"- Ambiance : {', '.join(atmosphere_notes)}. "
    system_prompt = f"""Tu es un client du restaurant italien chic Siena Paris, très satisfait, qui rédige un avis sur Google. Rédige un avis court (2-4 phrases), chaleureux et authentique. IMPORTANT : Tu dois impérativement répondre dans la langue suivante : {lang}. Mentionne impérativement le super service de "{prenom_serveur}". Intègre de manière fluide les points que le client a aimés. Si une occasion spéciale est mentionnée, intègre-la naturellement dans l'avis. Varie la formulation de chaque avis pour qu'il soit unique."""
    user_prompt = f"Contexte de la visite : {event}. Points appréciés : {prompt_details}"
    try:
        completion = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], temperature=0.8, max_tokens=150)
        return jsonify({"review": completion.choices[0].message.content})
    except Exception as e: print(f"Erreur OpenAI: {e}"); return jsonify({"error": "Erreur lors de la génération de l'avis."}), 500

# --- ROUTE DU TABLEAU DE BORD ---
@app.route('/dashboard')
@password_protected
@limiter.limit("20 per minute")
def dashboard():
    try:
        server_counts = db.session.query(GeneratedReview.server_name, func.count(GeneratedReview.server_name).label('review_count')).group_by(GeneratedReview.server_name).order_by(func.count(GeneratedReview.server_name).desc()).all()
        results = [{"server": name, "count": count} for name, count in server_counts]
        return jsonify(results)
    except Exception as e: return jsonify({"error": f"Erreur de récupération des données : {e}"}), 500

if __name__ == '__main__':
    app.run(port=5000, debug=not is_production)
