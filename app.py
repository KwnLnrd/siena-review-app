import os
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
CORS(app, origins=os.getenv('ALLOWED_ORIGINS', '*'), supports_credentials=True)

# --- SÉCURITÉ ---
# Pas de Rate Limiter pour l'instant pour simplifier le débogage
# Talisman est désactivé pour éviter les conflits avec les CDN
# Talisman(app, content_security_policy=False)

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
class Server(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)

# (Les autres modèles restent inchangés)

# --- INITIALISATION AUTOMATIQUE DE LA DB ---
with app.app_context():
    db.create_all()

# --- DÉCORATEURS ---
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

# (Les autres routes de gestion restent similaires)

# --- ROUTES API PUBLIQUES (AVEC ANTI-CACHE) ---
@app.route('/api/public/options')
@no_cache
def get_public_options():
    # ... (le code reste le même)
    pass

# (Le reste du fichier reste inchangé)
