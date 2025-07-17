import os
from flask import Flask, request, jsonify, render_template_string
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
# L'URL de votre base de données Render sera chargée depuis les variables d'environnement
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Le mot de passe pour votre tableau de bord
DASHBOARD_PASSWORD = os.getenv('DASHBOARD_PASSWORD', 'default_password')

db = SQLAlchemy(app)

# --- MODÈLE DE LA BASE DE DONNÉES ---
# Définit la structure de notre table pour stocker les avis
class GeneratedReview(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    server_name = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f'<Review for {self.server_name}>'

# --- SÉCURISATION DU TABLEAU DE BORD ---
# "Décorateur" pour protéger une page par mot de passe
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

# --- INITIALISATION DE LA BASE DE DONNÉES ---
# Une route à appeler une seule fois pour créer les tables
@app.route('/init_db')
@password_protected
def init_db():
    with app.app_context():
        db.create_all()
    return "Base de données initialisée avec succès !"

# --- ROUTE PRINCIPALE DE GÉNÉRATION D'AVIS (AMÉLIORÉE) ---
@app.route('/generate-review', methods=['POST'])
def generate_review():
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    except Exception as e:
        return jsonify({"error": "Clé API OpenAI non valide."}), 500

    data = request.get_json()
    if not data:
        return jsonify({"error": "Données invalides."}), 400

    lang = data.get('lang', 'fr')
    selected_tags = data.get('tags', [])
    
    prenom_serveur = "notre serveur(se)"
    # ... (La logique pour extraire les détails reste la même)
    prompt_details = "Points que le client a aimés : "
    event = "une simple visite"
    for tag in selected_tags:
        category = tag.get('category')
        if category == 'server_name':
            prenom_serveur = tag.get('value')
        # ... (etc.)

    # --- LOGIQUE D'ENREGISTREMENT DANS LA BASE DE DONNÉES ---
    if prenom_serveur != "notre serveur(se)": # On n'enregistre que si un serveur est choisi
        try:
            new_review_record = GeneratedReview(server_name=prenom_serveur)
            db.session.add(new_review_record)
            db.session.commit()
        except Exception as e:
            print(f"Erreur lors de l'enregistrement en base de données : {e}")
            db.session.rollback()

    # Le reste de la logique OpenAI reste inchangé...
    system_prompt = f"""
    Tu es un client du restaurant italien chic Siena Paris...
    Mentionne impérativement le super service de "{prenom_serveur}".
    ...
    """
    user_prompt = f"Contexte de la visite : {event}. Points appréciés : {prompt_details}"
    
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.8, max_tokens=150
        )
        generated_text = completion.choices[0].message.content
        return jsonify({"review": generated_text})
    except Exception as e:
        print(f"Erreur lors de l'appel à OpenAI: {e}")
        return jsonify({"error": "Erreur lors de la génération de l'avis."}), 500

# --- NOUVELLE ROUTE POUR LE TABLEAU DE BORD ---
@app.route('/dashboard')
@password_protected
def dashboard():
    try:
        # Requête pour compter les avis par serveur et les classer
        server_counts = db.session.query(
            GeneratedReview.server_name, 
            func.count(GeneratedReview.server_name).label('review_count')
        ).group_by(GeneratedReview.server_name).order_by(func.count(GeneratedReview.server_name).desc()).all()
        
        # Formate les données pour le JSON
        results = [{"server": name, "count": count} for name, count in server_counts]
        
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": f"Erreur lors de la récupération des données : {e}"}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all() # Crée les tables si elles n'existent pas au démarrage local
    app.run(port=5000, debug=True)
