from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
import os
from groq import Groq
from duckduckgo_search import DDGS
from authlib.integrations.flask_client import OAuth
import uuid
import requests
import re
import time
import json
import urllib.parse

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.secret_key = "MikuNakanoEsLaMejorAsistente2026"

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
# CONFIGURACIÓN DE LA IA (GROQ)
# ==========================================
GROQ_API_KEY = "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"
cliente = Groq(api_key=GROQ_API_KEY)

# ==========================================
# FUNCIÓN PARA LIMPIAR EL TEXTO
# ==========================================
def limpiar_texto(texto):
    texto = re.sub(r'[*#|]', '', texto)
    texto = re.sub(r'\d+\.\s*', '- ', texto)
    texto = re.sub(r' +', ' ', texto)
    return texto.strip()

# ==========================================
# FUNCIÓN PARA BUSCAR IMÁGENES EN WIKIMEDIA COMMONS
# ==========================================
def buscar_imagen_wikimedia(palabras_clave, limite=5):
    try:
        url = "https://commons.wikimedia.org/w/api.php"
        headers = {
            "User-Agent": "MikuNakanoAI/1.0 (https://miku-nakano-ai.onrender.com; contacto@ejemplo.com)"
        }
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": palabras_clave,
            "gsrnamespace": "6",
            "gsrlimit": limite, # Pedimos 5 opciones para saltarnos basura
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata",
            "iiurlwidth": "800",
            "format": "json"
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            paginas = data.get("query", {}).get("pages", {})
            
            imagenes_encontradas = []
            for page_id, pagina in paginas.items():
                titulo_archivo = pagina.get("title", "").lower()
                nombre_limpio = titulo_archivo.replace("file:", "").rsplit('.', 1)[0].replace('_', ' ')
                
                info = pagina.get("imageinfo", [{}])[0]
                url_imagen = info.get("thumburl") or info.get("url")
                ancho_original = info.get("width", 0)
                
                if not url_imagen: continue

                # FILTRO ANTI-BASURA: Evitar libros, textos y escaneos
                es_formato_valido = url_imagen.lower().endswith(('.jpg', '.jpeg', '.png'))
                es_alta_resolucion = ancho_original >= 500
                palabras_basura = ["book", "document", "scan", "text", "cover", "signature", "graph", "chart", "page"]
                es_basura = any(palabra in titulo_archivo for palabra in palabras_basura)

                if es_formato_valido and es_alta_resolucion and not es_basura:
                    metadatos = info.get("extmetadata", {})
                    licencia = metadatos.get("LicenseShortName", {}).get("value", "Ver en Commons")
                    autor = metadatos.get("Artist", {}).get("value", "Desconocido")
                    autor = re.sub(r'<[^>]+>', '', autor)
                    
                    imagenes_encontradas.append({
                        "url": url_imagen,
                        "nombre": nombre_limpio,
                        "autor": autor.strip(),
                        "licencia": licencia.strip()
                    })
            return imagenes_encontradas
        return []
    except Exception as e:
        print(f"Error buscando imagen en Wikimedia Commons: {e}")
        return []

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
        .mensaje { max-width: 85%; padding: 12px 16px; border-radius: 15px; line-height: 1.5; font-size: 0.95rem; white-space: pre-wrap; }
        .mensaje-usuario { align-self: flex-end; background: #4aa3df; color: white; border-bottom-right-radius: 2px; }
        .mensaje-miku { align-self: flex-start; background: #f0f7ff; color: #1b3a4b; border-bottom-left-radius: 2px; border: 1px solid #dff5ff; width: auto; max-width: 90%; }
        .mensaje-miku b { color: #2a6f97; }
        
        .tarjeta-imagen { background: #fff; border-radius: 8px; padding: 10px; margin: 15px 0; border: 1px solid #e0e0e0; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
        .titulo-imagen { font-weight: bold; color: #2a6f97; font-size: 0.9rem; margin-bottom: 8px; text-transform: capitalize; }
        
        .tarjeta-imagen img { 
            display: block; width: 100%; height: auto; max-height: 450px; 
            object-fit: contain; background-color: #f8f9fa; border-radius: 5px; 
            margin: 0 auto; border: 1px solid #eee;
        }
        
        .atribucion { font-size: 0.75rem; color: #666; margin-top: 8px; font-style: italic; border-top: 1px solid #eee; padding-top: 5px; }
        
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
            .mensaje { max-width: 95%; }
            .mensaje-miku { max-width: 100%; }
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
            chat.innerHTML += `<div class="mensaje mensaje-miku" id="${idPensando}"><b>Miku:</b> Investigando y decidiendo dónde colocar las imágenes... 🔍</div>`;
            chat.scrollTop = chat.scrollHeight;

            const response = await fetch('/responder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mensaje: mensaje })
            });
            const data = await response.json();
            
            document.getElementById(idPensando).innerHTML = `<b>Miku:</b> ${data.respuesta}`;
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
    
    if user_id not in historiales:
        historiales[user_id] = [
            {"role": "system", "content": "Eres Miku Nakano. Tu personalidad es dulce, cálida, amable y un poco tímida. Responde en español de forma clara y útil. Cuando te pidan una investigación o resumen, sé muy detallada y estructurada. Usa texto plano y viñetas simples."}
        ]
    
    historial_chat = historiales[user_id]
    query = ""
    
    if "busca" in texto_lower or "investiga" in texto_lower or "resumen" in texto_lower or "quien" in texto_lower:
        query = texto_lower.replace("miku", "").replace("busca", "").replace("investiga", "").replace("resumen", "").replace("hazme", "").replace("de", "").replace("sobre", "").replace("la", "").replace("el", "").replace("quien", "").replace("era", "").replace("es", "").strip()
        if query:
            try:
                resultados = DDGS().text(query, max_results=3)
                info_web = "\n".join([f"- {r['title']}: {r['body']}" for r in resultados])
                historial_chat.append({"role": "system", "content": f"Info de internet: {info_web}"})
            except: pass

    # PROMPT MAESTRO: La IA decide cuántas imágenes poner, dónde ponerlas y qué buscar
    instruccion_imagenes = (
        "INSTRUCCIÓN DE IMÁGENES: Mientras escribes tu respuesta, decide de forma inteligente dónde colocar imágenes "
        "para que la investigación se vea profesional. "
        "Debes insertar entre 2 y 4 imágenes dependiendo de lo que necesite el texto. "
        "Usa el formato exacto: [IMG: palabras clave en inglés]. "
        "Coloca la etiqueta JUSTO DESPUÉS del párrafo al que hace referencia la imagen. "
        "Si hablas de un personaje, usa su nombre + 'portrait'. "
        "Si hablas de un lugar o batalla, usa 'map' para un mapa o 'landscape' para una foto del lugar. "
        "NUNCA uses palabras como 'book', 'document' o 'scan'. "
        "Usa palabras clave muy específicas en inglés."
    )
    historial_chat.append({"role": "system", "content": instruccion_imagenes})
    historial_chat.append({"role": "user", "content": mensaje})
    
    try:
        completion = cliente.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=historial_chat,
            temperature=0.7,
            max_tokens=4000
        )
        respuesta_cruda = completion.choices[0].message.content
        
        patron = r'\[IMG:\s*(.*?)\]'
        partes = re.split(patron, respuesta_cruda)
        
        respuesta_final = ""
        imagenes_insertadas_urls = []
        
        for i, parte in enumerate(partes):
            if i % 2 == 0:
                # Es texto normal
                respuesta_final += limpiar_texto(parte) + "\n"
            else:
                # Es una etiqueta [IMG: ...] que la IA colocó
                palabras_clave = parte.strip()
                # Buscamos hasta 5 imágenes para saltar los libros
                imagenes = buscar_imagen_wikimedia(palabras_clave, limite=5)
                
                for img in imagenes:
                    if img["url"] not in imagenes_insertadas_urls:
                        tarjeta = f'''
                        <div class="tarjeta-imagen">
                            <div class="titulo-imagen">📷 {img["nombre"]}</div>
                            <img src="{img["url"]}" alt="{palabras_clave}">
                            <div class="atribucion">Fuente: Wikimedia Commons | Autor: {img["autor"]} | Licencia: {img["licencia"]}</div>
                        </div>
                        '''
                        respuesta_final += tarjeta + "\n"
                        imagenes_insertadas_urls.append(img["url"])
                        break # Ponemos la primera imagen bonita que encontremos
                        
        # Si la IA olvidó poner imágenes en una investigación, forzamos 1 al final
        if len(imagenes_insertadas_urls) == 0 and ("investiga" in texto_lower or "resumen" in texto_lower) and query:
            img_rescate = buscar_imagen_wikimedia(f"{query} portrait", limite=5)
            if img_rescate:
                img = img_rescate[0]
                tarjeta = f'''
                <div class="tarjeta-imagen">
                    <div class="titulo-imagen">📷 {img["nombre"]}</div>
                    <img src="{img["url"]}" alt="{query}">
                    <div class="atribucion">Fuente: Wikimedia Commons | Autor: {img["autor"]} | Licencia: {img["licencia"]}</div>
                </div>
                '''
                respuesta_final += tarjeta + "\n"

        historial_chat.append({"role": "assistant", "content": respuesta_final})
        
        return jsonify({"respuesta": respuesta_final})
    except Exception as e:
        return jsonify({"respuesta": f"Error: {e}"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
