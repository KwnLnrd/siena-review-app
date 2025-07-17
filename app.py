import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from datetime import datetime
from functools import wraps

# --- CONFIGURATION ---
load_dotenv()
app = Flask(__name__)
CORS(app) 

# --- CONFIGURATION DE LA BASE DE DONNÉES ---
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
# (Le code de gestion reste inchangé)

# --- ROUTES API PUBLIQUES ---
# (Le code des routes publiques reste inchangé)

# --- ROUTE DE GÉNÉRATION D'AVIS ---
# (Le code de cette fonction reste inchangé)

# --- ROUTE DU TABLEAU DE BORD (AVEC LOGGING AMÉLIORÉ) ---
@app.route('/dashboard')
@password_protected
def dashboard():
    print("Accès à la route /dashboard.")
    try:
        print("Exécution de la requête sur la base de données...")
        server_counts = db.session.query(
            GeneratedReview.server_name, 
            func.count(GeneratedReview.server_name).label('review_count')
        ).group_by(GeneratedReview.server_name).order_by(func.count(GeneratedReview.server_name).desc()).all()
        print(f"Requête réussie. {len(server_counts)} résultats trouvés.")
        
        results = [{"server": name, "count": count} for name, count in server_counts]
        print("Formatage des données réussi. Envoi de la réponse JSON.")
        
        return jsonify(results)
    except Exception as e:
        # Log détaillé de l'erreur sur le serveur Render
        print(f"---! ERREUR CRITIQUE DANS LE DASHBOARD !---")
        print(f"L'erreur est : {e}")
        print(f"-----------------------------------------")
        # Envoi d'un message d'erreur clair au frontend
        return jsonify({"error": f"Une erreur interne est survenue sur le serveur."}), 500

# --- INITIALISATION ET LANCEMENT ---
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(port=5000, debug=True)
