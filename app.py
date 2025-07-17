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

# --- CONFIGURATION INTELLIGENTE DE LA BASE DE DONNÉES ---
database_url = os.getenv('DATABASE_URL')

if database_url:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///reviews.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
DASHBOARD_PASSWORD = os.getenv('DASHBOARD_PASSWORD', 'default_password')

db = SQLAlchemy(app)

# --- MODÈLE DE LA BASE DE DONNÉES ---
class GeneratedReview(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    server_name = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f'<Review for {self.server_name}>'

# --- NOUVELLE COMMANDE POUR INITIALISER LA BASE DE DONNÉES ---
@app.cli.command("init-db")
def init_db_command():
    """Crée les tables de la base de données."""
    with app.app_context():
        db.create_all()
    print("Base de données initialisée avec succès.")

# --- SÉCURISATION DU TABLEAU DE BORD ---
def password_protected(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth = request.authorization
        if not auth or not (auth.username == 'admin' and auth.password == DASHBOARD_PASSWORD):
            return 'Could not verify your access level for that URL.\n' \
                   'You have to login with proper credentials', 401, \
                   {'WWW-Authenticate': 'Basic realm="Login Required"'}
        return f(*args, **kwargs)
    return decorated_function

# --- ROUTE DE GÉNÉRATION D'AVIS ---
@app.route('/generate-review', methods=['POST'])
def generate_review():
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    except Exception as e:
        return jsonify({"error": "Clé API OpenAI non valide."}), 500
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
        except Exception as e:
            print(f"Erreur lors de l'enregistrement en base de données : {e}")
            db.session.rollback()

    prompt_details = "Points que le client a aimés : "
    if service_qualities: prompt_details += f"- Le service de {prenom_serveur} était : {', '.join(service_qualities)}. "
    if liked_dishes: prompt_details += f"- Plats préférés : {', '.join(liked_dishes)}. "
    if atmosphere_notes: prompt_details += f"- Ambiance : {', '.join(atmosphere_notes)}. "
    
    system_prompt = f"""
    Tu es un client du restaurant italien chic Siena Paris, très satisfait, qui rédige un avis sur Google.
    Rédige un avis court (2-4 phrases), chaleureux et authentique.
    IMPORTANT : Tu dois impérativement répondre dans la langue suivante : {lang}.
    Mentionne impérativement le super service de "{prenom_serveur}".
    Intègre de manière fluide les points que le client a aimés.
    Si une occasion spéciale est mentionnée, intègre-la naturellement dans l'avis.
    Varie la formulation de chaque avis pour qu'il soit unique.
    """
    user_prompt = f"Contexte de la visite : {event}. Points appréciés : {prompt_details}"
    try:
        completion = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], temperature=0.8, max_tokens=150)
        return jsonify({"review": completion.choices[0].message.content})
    except Exception as e:
        print(f"Erreur lors de l'appel à OpenAI: {e}")
        return jsonify({"error": "Erreur lors de la génération de l'avis."}), 500

# --- ROUTE DU TABLEAU DE BORD ---
@app.route('/dashboard')
@password_protected
def dashboard():
    try:
        server_counts = db.session.query(GeneratedReview.server_name, func.count(GeneratedReview.server_name).label('review_count')).group_by(GeneratedReview.server_name).order_by(func.count(GeneratedReview.server_name).desc()).all()
        results = [{"server": name, "count": count} for name, count in server_counts]
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": f"Erreur lors de la récupération des données : {e}"}), 500

# --- Lancement de l'application ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all() 
    app.run(port=5000, debug=True)
