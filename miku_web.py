from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
import os
from groq import Groq
from duckduckgo_search import DDGS
from authlib.integrations.flask_client import OAuth
import uuid
import requests
import urllib.parse
import base64
import time

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.secret_key = os.environ.get("FLASK_SECRET_KEY")

# ==========================================
# CONFIGURACIÓN DE GOOGLE (AUTH)
# ==========================================
app.config['GOOGLE_CLIENT_ID'] = "183518295635-devpot1v7r6v8902r0d53vdqqatjeu7a.apps.googleusercontent.com"
app.config['GOOGLE_CLIENT_SECRET'] = "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"

oauth = OAuth(app)
oauth.register(
    name='google',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# ==========================================
# CONFIGURACIÓN DE LA IA
# ==========================================
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "TU_CLAVE_AQUI")
cliente = Groq(api_key=GROQ_API_KEY)

# ==========================================
# FUNCIÓN PARA MEJORAR EL PROMPT (RESPETANDO LA PETICIÓN)
# ==========================================
def mejorar_prompt(prompt_usuario):
    # Le pedimos a Groq que expanda la petición del usuario, pero SIN inventar cosas que no pidió
    instrucciones = f"""
    Eres un experto en "Prompt Engineering" para modelos de generación de imágenes.
    El usuario ha pedido: "{prompt_usuario}"
    
    Tu tarea es reescribir esta petición en un prompt en inglés, ultra-detallado, que respete EXACTAMENTE lo que el usuario pidió.
    NO añadas elementos que el usuario no haya mencionado (por ejemplo, si pide un gato, NO le pongas traje de astronauta).
    
    Debes incluir:
    1. El sujeto principal (ej. un gato, una chica, un paisaje).
    2. La acción o pose (ej. sentado, sonriendo, corriendo).
    3. La vestimenta o accesorios (SOLO si el usuario lo menciona).
    4. El entorno o fondo (SOLO si el usuario lo menciona).
    5. La iluminación y estilo (ej. luz cinematográfica, hiperrealista, 8k, lente de 85mm).
    
    Devuelve SOLO el prompt en inglés, sin explicaciones, listo para ser usado en una IA de imágenes.
    """
    
    try:
        completion = cliente.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": instrucciones}],
            temperature=0.7,
            max_tokens=300
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error mejorando prompt: {e}")
        # Si falla Groq, usamos el prompt original con palabras clave de calidad
        return f"Professional photography of {prompt_usuario}, hyperrealistic, 8k, highly detailed, cinematic lighting, masterpiece"

def generar_imagen(prompt_usuario):
    # 1. Mejoramos el prompt usando Groq (respetando la petición)
    prompt_maestro = mejorar_prompt(prompt_usuario)
    
    # 2. Codificamos el prompt y llamamos a Pollinations
    prompt_encoded = urllib.parse.quote(prompt_maestro)
    url = f"https://image.pollinations.ai/prompt/{prompt_encoded}?width=1024&height=1024&nologo=true&model=flux-realism"
    
    try:
        response = requests.get(url, timeout=60)
        if response.status_code == 200:
            b64_imagen = base64.b64encode(response.content).decode('utf-8')
            return f"data:image/jpeg;base64,{b64_imagen}"
        else:
            print(f"Error de Pollinations: {response.status_code}")
            return None
    except Exception as e:
        print(f"Error generando imagen: {e}")
        return None

historiales = {}

# --- LA INTERFAZ WEB (HTML/CSS) ---
HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Miku Nakano AI</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Segoe UI', Arial, sans-serif; background-color: #f0f7ff; display: flex; height: 100dvh; overflow: hidden; }
        .sidebar { width: 300px; background: linear-gradient(180deg, #dff5ff 0%, #b3e0ff 100%); display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 20px; border-right: 2px solid #b3d9ff; }
        .sidebar img { width: 100%; max-width: 250px; border-radius: 20px; box-shadow: 0 10px 20px rgba(0,0,0,0.1); }
        .sidebar h2 { margin-top: 20px; color: #2a6f97; text-align: center; font-size: 1.5rem; }
        .main-chat { flex: 1; display: flex; flex-direction: column; background: #ffffff; }
        .chat-header { padding: 20px; border-bottom: 1px solid #eee; color: #2a6f97; font-weight: bold; font-size: 1.2rem; display: flex; align-items: center; justify-content: space-between; }
        .user-info { font-size: 0.9rem; color: #666; }
        #chat { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 15px; }
        .mensaje { max-width: 80%; padding: 12px 16px; border-radius: 15px; line-height: 1.5; font-size: 0.95rem; }
        .mensaje-usuario { align-self: flex-end; background: #4aa3df; color: white; border-bottom-right-radius: 2px; }
        .mensaje-miku { align-self: flex-start; background: #f0f7ff; color: #1b3a4b; border-bottom-left-radius: 2px; border: 1px solid #dff5ff; }
        .mensaje-miku b { color: #2a6f97; }
        .input-area { padding: 15px; padding-bottom: 25px; border-top: 1px solid #eee; display: flex; gap: 10px; background: #fafafa; }
        input { flex: 1; padding: 15px; border-radius: 30px; border: 1px solid #ddd; outline: none; font-size: 1rem; transition: 0.3s; }
        input:focus { border-color: #4aa3df; box-shadow: 0 0 0 3px rgba(74, 163, 223, 0.2); }
        button { padding: 15px 30px; background: #4aa3df; color: white; border: none; border-radius: 30px; cursor: pointer; font-weight: bold; transition: 0.3s; }
        button:hover { background: #2a6f97; }
        @media (max-width: 768px) {
            body { flex-direction: column; }
            .sidebar { width: 100%; height: 180px; flex-direction: row; padding: 10px; }
            .sidebar img { max-width: 120px; }
            .sidebar h2 { font-size: 1.2rem; margin-top: 0; margin-left: 15px; }
        }
    </style>
</head>
<body>
    <div class="sidebar">
        <img src="/static/fondo_miku.png.jpg" alt="Miku Nakano">
        <h2>Miku Nakano AI 💙🎧</h2>
    </div>
    <div class="main-chat">
        <div class="chat-header">
            <span>💬 Conversación con Miku</span>
            <span class="user-info">{{ user_name }}</span>
        </div>
        <div id="chat">
            <div class="mensaje mensaje-miku"><b>Miku:</b> ¡Hola! 💙 Me alegra mucho verte por aquí. ¿En qué puedo ayudarte hoy?</div>
        </div>
        <div class="input-area">
            <input type="text" id="mensaje" placeholder="Escribe algo..." onkeypress="if(event.key === 'Enter') enviar()">
            <button onclick="enviar()">Enviar</button>
        </div>
    </div>

    <script>
        async function enviar() {
            const input = document.getElementById('mensaje');
            const chat = document.getElementById('chat');
            const mensaje = input.value;
            if (!mensaje) return;
            
            chat.innerHTML += `<div class="mensaje mensaje-usuario"><b>Tú:</b> ${mensaje}</div>`;
            input.value = '';
            chat.scrollTop = chat.scrollHeight;

            const idPensando = 'pensando-' + Date.now();
            chat.innerHTML += `<div class="mensaje mensaje-miku" id="${idPensando}"><b>Miku:</b> Creando imagen... 🎨</div>`;
            chat.scrollTop = chat.scrollHeight;

            const response = await fetch('/responder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mensaje: mensaje })
            });
            const data = await response.json();
            
            let respuestaFormateada = data.respuesta;
            
            if (respuestaFormateada.includes("[IMAGEN]")) {
                const url = respuestaFormateada.split("[IMAGEN]")[1].split("[/IMAGEN]")[0];
                let texto = respuestaFormateada.split("[IMAGEN]")[0];
                texto = texto.replace("[CREANDO]", "");
                document.getElementById(idPensando).innerHTML = `<b>Miku:</b> ${texto}<br><img src="${url}" style="max-width: 100%; border-radius: 10px; margin-top: 10px;">`;
            } else {
                document.getElementById(idPensando).innerHTML = `<b>Miku:</b> ${respuestaFormateada}`;
            }
            chat.scrollTop = chat.scrollHeight;
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    if 'user' not in session:
        return redirect(url_for('login'))
    user_name = session['user'].get('name', 'Usuario')
    return render_template_string(HTML, user_name=user_name)

@app.route('/login')
def login():
    redirect_uri = url_for('authorize', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)

@app.route('/authorize')
def authorize():
    token = oauth.google.authorize_access_token()
    user_info = token.get('userinfo')
    if user_info:
        session['user'] = user_info
        session['user_id'] = user_info.get('email')
    return redirect('/')

@app.route('/responder', methods=['POST'])
def responder():
    if 'user_id' not in session:
        return jsonify({"respuesta": "Error: Debes iniciar sesión."})
    data = request.get_json()
    mensaje = data.get('mensaje')
    user_id = session['user_id']
    
    texto_lower = mensaje.lower()
    if any(palabra in texto_lower for palabra in ["genera una imagen", "crea una imagen", "dibuja", "dibújame", "hazme una imagen", "haz una imagen", "hazme la imagen", "quiero una imagen", "imagen de", "genera", "crea", "dibujo"]):
        prompt = texto_lower.replace("miku", "").replace("genera una imagen", "").replace("crea una imagen", "").replace("dibuja", "").replace("dibújame", "").replace("hazme una imagen", "").replace("haz una imagen", "").replace("hazme la imagen", "").replace("quiero una imagen", "").replace("imagen de", "").strip()
        if prompt:
            url_imagen = generar_imagen(prompt)
            if url_imagen:
                return jsonify({"respuesta": f"[CREANDO]¡Claro! Dame un momento, estoy creando tu imagen... 🎨[IMAGEN]{url_imagen}[/IMAGEN]"})
            else:
                return jsonify({"respuesta": "Lo siento, el servidor de imágenes está ocupado. Intenta de nuevo en unos segundos."})

    if user_id not in historiales:
        historiales[user_id] = [
            {"role": "system", "content": "Eres Miku Nakano. Tu personalidad es dulce, cálida, amable y un poco tímida. IMPORTANTE: No uses apelativos como 'Director' ni 'Tú' a menos que te lo pidan. Responde en español de forma concisa y cariñosa."}
        ]
    
    historial_chat = historiales[user_id]
    
    if "busca" in texto_lower or "investiga" in texto_lower:
        query = texto_lower.replace("miku", "").replace("busca", "").replace("investiga", "").strip()
        if query:
            try:
                resultados = DDGS().text(query, max_results=3)
                info_web = "\n".join([f"- {r['title']}: {r['body']}" for r in resultados])
                historial_chat.append({"role": "system", "content": f"Info de internet: {info_web}"})
            except: pass

    historial_chat.append({"role": "user", "content": mensaje})
    
    try:
        completion = cliente.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=historial_chat,
            temperature=0.7,
            max_tokens=1500
        )
        respuesta = completion.choices[0].message.content
        historial_chat.append({"role": "assistant", "content": respuesta})
        return jsonify({"respuesta": respuesta})
    except Exception as e:
        return jsonify({"respuesta": f"Error: {e}"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
