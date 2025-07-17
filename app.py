import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from datetime import datetime
from functools import wraps

# --- CONFIGURATION INITIALE ---
load_dotenv()
app = Flask(__name__)
CORS(app) 

# --- CONFIGURATION DE LA BASE DE DONNÉES ---
database_url = os.getenv('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///reviews.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
DASHBOARD_PASSWORD = os.getenv('DASHBOARD_PASSWORD', 'default_password')
db = SQLAlchemy(app)

# --- MODÈLES DE LA BASE DE DONNÉES ---
class GeneratedReview(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    server_name = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

# NOUVEAU : Modèle pour les serveurs
class Server(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)

# --- SÉCURISATION ---
def password_protected(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth = request.authorization
        if not auth or not (auth.username == 'admin' and auth.password == DASHBOARD_PASSWORD):
            return 'Could not verify your access level.', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'}
        return f(*args, **kwargs)
    return decorated_function

# --- COMMANDE D'INITIALISATION DB ---
@app.cli.command("init-db")
def init_db_command():
    with app.app_context():
        db.create_all()
    print("Base de données initialisée.")

# --- ROUTES API POUR LA GESTION DES SERVEURS (PROTÉGÉES) ---
@app.route('/api/servers', methods=['GET'])
@password_protected
def get_servers():
    servers = Server.query.order_by(Server.name).all()
    return jsonify([{"id": server.id, "name": server.name} for server in servers])

@app.route('/api/servers', methods=['POST'])
@password_protected
def add_server():
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({"error": "Le nom du serveur est manquant."}), 400
    
    new_server_name = data['name'].strip().title()
    if Server.query.filter_by(name=new_server_name).first():
        return jsonify({"error": "Ce serveur existe déjà."}), 409

    new_server = Server(name=new_server_name)
    db.session.add(new_server)
    db.session.commit()
    return jsonify({"id": new_server.id, "name": new_server.name}), 201

@app.route('/api/servers/<int:server_id>', methods=['DELETE'])
@password_protected
def delete_server(server_id):
    server = Server.query.get(server_id)
    if not server:
        return jsonify({"error": "Serveur non trouvé."}), 404
    
    db.session.delete(server)
    db.session.commit()
    return jsonify({"success": True})

# --- NOUVELLE ROUTE PUBLIQUE POUR LES PAGES D'AVIS ---
@app.route('/api/public/servers', methods=['GET'])
def get_public_servers():
    try:
        servers = Server.query.order_by(Server.name).all()
        return jsonify([{"id": server.id, "name": server.name} for server in servers])
    except Exception as e:
        # Si la DB n'est pas prête, on renvoie une liste par défaut pour ne pas bloquer le client
        print(f"Erreur DB sur route publique, renvoi de la liste par défaut: {e}")
        default_servers = [{"id": 1, "name": "Kewan"}, {"id": 2, "name": "Léa"}]
        return jsonify(default_servers)

# --- ROUTE DE GÉNÉRATION D'AVIS (inchangée) ---
@app.route('/generate-review', methods=['POST'])
def generate_review():
    # ... (le code de cette fonction reste exactement le même)
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    except Exception as e: return jsonify({"error": "Clé API OpenAI non valide."}), 500
    data = request.get_json()
    if not data: return jsonify({"error": "Données invalides."}), 400
    lang = data.get('lang', 'fr')
    selected_tags = data.get('tags', [])
    prenom_serveur = "notre serveur(se)"
    service_qualities = []
    event = "une simple visite"
    liked_dishes = []
    atmosphere_notes = []
    for tag in selected_tags:
        category = tag.get('category')
        value = tag.get('value')
        if category == 'server_name': prenom_serveur = value
        elif category == 'service_qualities': service_qualities.append(value)
        elif category == 'reason_for_visit': event = value
        elif category == 'birthday_details': event += f" ({value})"
        elif category == 'liked_dishes': liked_dishes.append(value)
        elif category == 'atmosphere': atmosphere_notes.append(value)
    if prenom_serveur != "notre serveur(se)":
        try:
            new_review_record = GeneratedReview(server_name=prenom_serveur)
            db.session.add(new_review_record)
            db.session.commit()
        except Exception as e: print(f"Erreur DB: {e}"); db.session.rollback()
    prompt_details = "Points que le client a aimés : "
    if service_qualities: prompt_details += f"- Le service de {prenom_serveur} était : {', '.join(service_qualities)}. "
    if liked_dishes: prompt_details += f"- Plats préférés : {', '.join(liked_dishes)}. "
    if atmosphere_notes: prompt_details += f"- Ambiance : {', '.join(atmosphere_notes)}. "
    system_prompt = f"""Tu es un client du restaurant italien chic Siena Paris... Mentionne impérativement le super service de "{prenom_serveur}"..."""
    user_prompt = f"Contexte de la visite : {event}. Points appréciés : {prompt_details}"
    try:
        completion = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], temperature=0.8, max_tokens=150)
        return jsonify({"review": completion.choices[0].message.content})
    except Exception as e: print(f"Erreur OpenAI: {e}"); return jsonify({"error": "Erreur lors de la génération de l'avis."}), 500

# --- ROUTE DU TABLEAU DE BORD (inchangée) ---
@app.route('/dashboard')
@password_protected
def dashboard():
    try:
        server_counts = db.session.query(GeneratedReview.server_name, func.count(GeneratedReview.server_name).label('review_count')).group_by(GeneratedReview.server_name).order_by(func.count(GeneratedReview.server_name).desc()).all()
        results = [{"server": name, "count": count} for name, count in server_counts]
        return jsonify(results)
    except Exception as e: return jsonify({"error": f"Erreur de récupération des données : {e}"}), 500

if __name__ == '__main__':
    with app.app_context(): db.create_all() 
    app.run(port=5000, debug=True)
