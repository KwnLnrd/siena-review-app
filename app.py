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

    # On utilise maintenant des identifiants simples pour plus de robustesse
    prenom_serveur = "Kewan"
    prompt_details = ""
    event = "une simple visite"
    
    # Dictionnaires pour recréer de jolies catégories pour l'IA
    category_map = {
        "service_kewan": f"Le service de {prenom_serveur}",
        "liked_dishes": "Les plats appréciés",
        "atmosphere": "L'ambiance"
    }

    for tag in selected_tags:
        category_key = tag.get('category')
        if category_key == 'reason_for_visit':
            event = tag['value']
        # On ignore la catégorie si elle n'est pas dans notre dictionnaire
        elif category_key in category_map:
            pretty_category = category_map[category_key]
            prompt_details += f"- {pretty_category}: {tag['value']}. "

    system_prompt = f"""
    Tu es un client du restaurant italien chic Siena Paris, très satisfait, qui rédige un avis sur Google.
    Rédige un avis court (2-4 phrases), chaleureux et authentique.
    IMPORTANT : Tu dois impérativement répondre dans la langue suivante : {lang}.
    
    L'avis doit inclure une mention positive du service de "{prenom_serveur}".
    Intègre de manière fluide les points que le client a aimés, qui te sont fournis.
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