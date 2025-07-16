import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv

# Charger les variables d'environnement (votre clé API depuis le fichier .env)
load_dotenv()

# Initialiser l'application Flask et configurer CORS pour autoriser la communication
app = Flask(__name__)
CORS(app)

# Initialiser le client OpenAI avec la clé API
try:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception as e:
    print(f"--- ERREUR CRITIQUE ---")
    print(f"La clé API OpenAI n'a pas pu être chargée. Vérifiez votre fichier .env.")
    print(f"Détail de l'erreur: {e}")
    print(f"-----------------------")
    client = None

@app.route('/generate-review', methods=['POST'])
def generate_review():
    if not client:
        return jsonify({"error": "Le service de génération n'est pas disponible car la clé API n'est pas valide."}), 500

    data = request.get_json()
    if not data:
        return jsonify({"error": "Données invalides envoyées par le navigateur."}), 400

    # Étape 1 : On récupère la langue et les tags depuis la requête
    lang = data.get('lang', 'fr') # 'fr' par défaut si la langue n'est pas fournie
    selected_tags = data.get('tags', [])

    # Étape 2 : Construire l'instruction (le "prompt") pour l'IA
    prenom_serveur = "Kewan"
    
    prompt_details = "Voici les points que le client a aimés : "
    event = "une simple visite"

    for tag in selected_tags:
        if "motif de ma visite" in tag['category'] or "reason for my visit" in tag['category'] or "motivo de mi visita" in tag['category']:
            event = tag['value']
        else:
            prompt_details += f"- {tag['category']}: {tag['value']}. "

    # L'instruction principale qui définit le rôle et le ton de l'IA
    system_prompt = f"""
    Tu es un client du restaurant italien chic Siena Paris, très satisfait.
    Rédige un avis court (2-4 phrases), chaleureux et authentique.
    IMPORTANT : Tu dois impérativement répondre dans la langue suivante : {lang}.
    
    L'avis doit inclure une mention positive du service de "{prenom_serveur}".
    Il doit aussi intégrer de manière fluide les points que le client a aimés.
    Si une occasion spéciale est mentionnée, intègre-la naturellement à l'avis.
    Varie la formulation de chaque avis pour qu'il soit unique.
    """
    
    user_prompt = f"Contexte de la visite : {event}. Points appréciés : {prompt_details}"
    
    # Étape 3 : Appeler l'API d'OpenAI et renvoyer le résultat
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.8,
            max_tokens=150
        )
        
        generated_text = completion.choices[0].message.content
        return jsonify({"review": generated_text})

    except Exception as e:
        print(f"--- ERREUR LORS DE L'APPEL A OPENAI ---")
        print(e)
        print(f"------------------------------------")
        return jsonify({"error": "Une erreur est survenue lors de la communication avec le service de génération."}), 500

if __name__ == '__main__':
    app.run(port=5000, debug=True)