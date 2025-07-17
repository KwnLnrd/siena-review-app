import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
CORS(app) 

try:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception as e:
    print(f"ERREUR CRITIQUE: La clé API OpenAI n'a pas pu être chargée. {e}")
    client = None

@app.route('/generate-review', methods=['POST'])
def generate_review():
    if not client:
        return jsonify({"error": "Service non disponible (clé API invalide)."}), 500

    data = request.get_json()
    if not data:
        return jsonify({"error": "Données invalides."}), 400

    lang = data.get('lang', 'fr')
    selected_tags = data.get('tags', [])

    # --- NOUVELLE LOGIQUE AMÉLIORÉE ---
    prenom_serveur = ""
    service_qualities = []
    event = "une simple visite"
    liked_dishes = []
    atmosphere_notes = []

    # On trie toutes les informations reçues
    for tag in selected_tags:
        category = tag.get('category')
        value = tag.get('value')
        
        if category == 'server_name':
            prenom_serveur = value
        elif category == 'service_qualities':
            service_qualities.append(value)
        elif category == 'reason_for_visit':
            event = value
        elif category == 'birthday_details':
            event += f" ({value})"
        elif category == 'liked_dishes':
            liked_dishes.append(value)
        elif category == 'atmosphere':
            atmosphere_notes.append(value)

    # On construit le message pour l'IA
    prompt_details = "Points que le client a aimés : "
    if service_qualities:
        prompt_details += f"- Le service de {prenom_serveur} était : {', '.join(service_qualities)}. "
    if liked_dishes:
        prompt_details += f"- Plats préférés : {', '.join(liked_dishes)}. "
    if atmosphere_notes:
        prompt_details += f"- Ambiance : {', '.join(atmosphere_notes)}. "
    
    # Le prompt système reste le même, il utilise le nom du serveur dynamiquement
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
        print(f"ERREUR LORS DE L'APPEL A OPENAI: {e}")
        return jsonify({"error": "Erreur lors de la génération de l'avis."}), 500

if __name__ == '__main__':
    app.run(port=5000, debug=True)