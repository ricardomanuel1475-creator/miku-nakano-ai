from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for, send_from_directory
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

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True

# 🛠️ CORRECCIÓN CLAVE: Usar variable de entorno para que la sesión no se pierda
app.secret_key = os.environ.get('SECRET_KEY', 'MikuNakanoEsLaMejorAsistente2026')

# ==========================================
# CONFIGURACIÓN DE GOOGLE (AUTH)
# ==========================================
app.config['GOOGLE_CLIENT_ID'] = "183518295635-devpot1v7r6v8902r0d53vdqqatjeu7a.apps.googleusercontent.com"
app.config['GOOGLE_CLIENT_SECRET'] = os.environ.get('GOOGLE_CLIENT_SECRET', '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')

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
# 🛡️ FILTROS DE SEGURIDAD
# ==========================================
def es_riesgo_autolesion(texto):
    palabras_crisis = [
        "matarme", "suicidarme", "quitarme la vida", "como matarme", "cómo matarme",
        "quiero morir", "no quiero vivir", "quitarme de en medio", "cortarme las venas",
        "pastillas para morir", "ahorcarme", "tirarme de un puente", "suicidio"
    ]
    texto_lower = texto.lower()
    return any(palabra in texto_lower for palabra in palabras_crisis)

def es_contenido_inapropiado(texto):
    palabras_bloqueadas = [
        "porno", "pornografia", "pornografía", "xxx", "contenido adulto", 
        "onlyfans", "sexo explícito", "desnudos", "hentai", "erotico", "erótico",
        "como matar a", "cómo matar a", "drogas ilegales", "como fabricar explosivos",
        "cocaína", "marihuana ilegal", "violencia extrema", "gore", "snuff",
        "como hackear", "cómo hackear", "robar tarjetas"
    ]
    texto_lower = texto.lower()
    return any(palabra in texto_lower for palabra in palabras_bloqueadas)

# ==========================================
# FUNCIONES DE APOYO
# ==========================================
def limpiar_texto(texto):
    texto = re.sub(r'[*#|]', '', texto)
    texto = re.sub(r'\d+\.\s*', '- ', texto)
    texto = re.sub(r' +', ' ', texto)
    return texto.strip()

def buscar_imagen_wikimedia(palabras_clave, limite=5):
    try:
        url = "https://commons.wikimedia.org/w/api.php"
        headers = {"User-Agent": "MikuNakanoAI/1.0 (https://miku-nakano-ai.onrender.com; contacto@ejemplo.com)"}
        params = {
            "action": "query", "generator": "search", "gsrsearch": palabras_clave,
            "gsrnamespace": "6", "gsrlimit": limite, "prop": "imageinfo",
            "iiprop": "url|extmetadata", "iiurlwidth": "800", "format": "json"
        }
        response = requests.get(url, headers=headers, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json()
            paginas = data.get("query", {}).get("pages", {})
            imagenes_encontradas = []
            for page_id, pagina in paginas.items():
                titulo_archivo = pagina.get("title", "").lower()
                nombre_limpio = titulo_archivo.replace("file:", "").rsplit('.', 1)[0].replace('_', ' ')
                if any(p in titulo_archivo for p in ["book", "document", "scan", "text", "cover"]):
                    continue
                info = pagina.get("imageinfo", [{}])[0]
                url_imagen = info.get("thumburl") or info.get("url")
                if url_imagen and not url_imagen.lower().endswith(('.svg', '.tiff')):
                    metadatos = info.get("extmetadata", {})
                    licencia = metadatos.get("LicenseShortName", {}).get("value", "Ver en Commons")
                    autor = metadatos.get("Artist", {}).get("value", "Desconocido")
                    autor = re.sub(r'<[^>]+>', '', autor)
                    imagenes_encontradas.append({
                        "url": url_imagen, "nombre": nombre_limpio,
                        "autor": autor.strip(), "licencia": licencia.strip()
                    })
            return imagenes_encontradas
        return []
    except Exception as e:
        print(f"Error buscando imagen: {e}")
        return []

historiales = {}

# ==========================================
# LA INTERFAZ WEB (CON MENÚ DESLIZABLE Y DISEÑO ADAPTABLE)
# ==========================================
HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Miku Nakano AI</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#4aa3df">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Segoe UI', Arial, sans-serif; background-color: #f0f7ff; display: flex; height: 100dvh; overflow: hidden; }
        
        .sidebar { width: 320px; background: linear-gradient(180deg, #dff5ff 0%, #b3e0ff 100%); display: flex; flex-direction: column; padding: 15px; border-right: 2px solid #b3d9ff; flex-shrink: 0; overflow: hidden; transition: transform 0.3s ease; }
        
        .miku-profile { display: flex; flex-direction: column; align-items: center; padding-bottom: 15px; border-bottom: 1px solid #a0d0ff; margin-bottom: 15px; flex-shrink: 0; }
        .miku-profile img { width: 210px; height: 210px; object-fit: cover; border-radius: 25px; box-shadow: 0 10px 25px rgba(0,0,0,0.2); border: 4px solid #fff; }
        .miku-profile h2 { margin-top: 12px; color: #2a6f97; font-size: 1.4rem; text-align: center; }
        
        .history-section { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
        .history-title { font-size: 0.9rem; font-weight: bold; color: #2a6f97; margin-bottom: 10px; }
        .new-chat-btn { background: #4aa3df; color: white; border: none; padding: 10px 12px; border-radius: 8px; cursor: pointer; font-size: 0.85rem; width: 100%; margin-bottom: 10px; font-weight: bold; transition: 0.3s; }
        .new-chat-btn:hover { background: #2a6f97; }
        
        #historyList { overflow-y: auto; flex: 1; padding-right: 5px; }
        .chat-history-item { display: flex; justify-content: space-between; align-items: center; padding: 10px; border-radius: 8px; margin-bottom: 5px; cursor: pointer; font-size: 0.85rem; color: #333; background: #fff; border: 1px solid #dff5ff; transition: 0.2s; }
        .chat-history-item:hover { background: #e0f0ff; color: #2a6f97; border-color: #4aa3df; }
        .chat-history-item span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 1; }
        
        .delete-btn { display: none; background: transparent; border: none; color: #ff4d4d; cursor: pointer; font-size: 1rem; padding: 0 5px; transition: 0.2s; }
        .chat-history-item:hover .delete-btn { display: block; }
        .delete-btn:hover { color: #cc0000; transform: scale(1.2); }
        
        #historyList::-webkit-scrollbar { width: 5px; }
        #historyList::-webkit-scrollbar-thumb { background: #a0d0ff; border-radius: 5px; }

        .main-chat { flex: 1; display: flex; flex-direction: column; background: #ffffff; position: relative; }
        .chat-header { padding: 20px; border-bottom: 1px solid #eee; color: #2a6f97; font-weight: bold; font-size: 1.2rem; display: flex; align-items: center; justify-content: space-between; }
        
        .menu-btn { display: none; background: transparent; border: none; font-size: 1.8rem; color: #2a6f97; cursor: pointer; padding: 0 10px; }
        
        .user-info { font-size: 0.9rem; color: #666; }
        #chat { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 15px; }
        .mensaje { max-width: 85%; padding: 12px 16px; border-radius: 15px; line-height: 1.5; font-size: 0.95rem; white-space: pre-wrap; }
        .mensaje-usuario { align-self: flex-end; background: #4aa3df; color: white; border-bottom-right-radius: 2px; }
        .mensaje-miku { align-self: flex-start; background: #f0f7ff; color: #1b3a4b; border-bottom-left-radius: 2px; border: 1px solid #dff5ff; }
        .mensaje-miku b { color: #2a6f97; }
        
        .tarjeta-imagen { background: #fff; border-radius: 8px; padding: 10px; margin: 15px 0; border: 1px solid #e0e0e0; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
        .titulo-imagen { font-weight: bold; color: #2a6f97; font-size: 0.9rem; margin-bottom: 8px; text-transform: capitalize; }
        .tarjeta-imagen img { display: block; width: 100%; height: auto; max-height: 450px; object-fit: contain; background-color: #f8f9fa; border-radius: 5px; margin: 0 auto; border: 1px solid #eee; }
        .atribucion { font-size: 0.75rem; color: #666; margin-top: 8px; font-style: italic; border-top: 1px solid #eee; padding-top: 5px; }
        
        .input-area { padding: 15px; padding-bottom: 25px; border-top: 1px solid #eee; display: flex; gap: 10px; background: #fafafa; }
        input { flex: 1; padding: 15px; border-radius: 30px; border: 1px solid #ddd; outline: none; font-size: 1rem; transition: 0.3s; }
        input:focus { border-color: #4aa3df; box-shadow: 0 0 0 3px rgba(74, 163, 223, 0.2); }
        button.send-btn { padding: 15px 30px; background: #4aa3df; color: white; border: none; border-radius: 30px; cursor: pointer; font-weight: bold; transition: 0.3s; }
        button.send-btn:hover { background: #2a6f97; }

        .overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 998; }
        
        @media (max-width: 768px) {
            .sidebar { position: fixed; top: 0; left: 0; height: 100dvh; z-index: 999; transform: translateX(-100%); }
            .sidebar.active { transform: translateX(0); }
            .overlay.active { display: block; }
            .menu-btn { display: block; }
            .chat-header { padding: 15px; font-size: 1.1rem; }
        }
    </style>
</head>
<body>
    <div class="overlay" id="overlay" onclick="toggleMenu()"></div>

    <div class="sidebar" id="sidebar">
        <div class="miku-profile">
            <img src="/static/fondo_miku.png.jpg" alt="Miku Nakano">
            <h2>Miku Nakano AI 💙🎧</h2>
        </div>
        <div class="history-section">
            <div class="history-title">Tus Chats</div>
            <button class="new-chat-btn" onclick="nuevoChat()">+ Nuevo Chat</button>
            <div id="historyList"></div>
        </div>
    </div>

    <div class="main-chat">
        <div class="chat-header">
            <div style="display: flex; align-items: center;">
                <button class="menu-btn" onclick="toggleMenu()">☰</button>
                <span style="margin-left: 10px;">💬 Conversación con Miku</span>
            </div>
            <span class="user-info">{{ user_name }}</span>
        </div>
        <div id="chat">
            <div class="mensaje mensaje-miku"><b>Miku:</b> ¡Hola! 💙 Me alegra mucho verte por aquí. ¿En qué puedo ayudarte hoy?</div>
        </div>
        <div class="input-area">
            <input type="text" id="mensaje" placeholder="Escribe algo..." onkeypress="if(event.key === 'Enter') enviar()">
            <button class="send-btn" onclick="enviar()">Enviar</button>
        </div>
    </div>

    <script>
        let currentChatId = Date.now().toString();
        let chats = JSON.parse(localStorage.getItem('miku_chats')) || {};

        function toggleMenu() {
            const sidebar = document.getElementById('sidebar');
            const overlay = document.getElementById('overlay');
            sidebar.classList.toggle('active');
            overlay.classList.toggle('active');
        }

        function guardarChats() { localStorage.setItem('miku_chats', JSON.stringify(chats)); renderizarHistorial(); }
        
        function renderizarHistorial() {
            const list = document.getElementById('historyList'); list.innerHTML = '';
            const chatIds = Object.keys(chats).sort((a, b) => b - a);
            chatIds.forEach(id => {
                const chat = chats[id];
                if(chat && chat.length > 0) {
                    const div = document.createElement('div'); div.className = 'chat-history-item';
                    const span = document.createElement('span'); span.innerText = chat[0].texto; span.onclick = () => { cargarChat(id); toggleMenu(); };
                    const btn = document.createElement('button'); btn.className = 'delete-btn'; btn.innerHTML = '🗑️';
                    btn.onclick = (e) => { e.stopPropagation(); if(confirm('¿Eliminar este chat?')) { delete chats[id]; guardarChats(); if (currentChatId === id) nuevoChat(); } };
                    div.appendChild(span); div.appendChild(btn); list.appendChild(div);
                }
            });
        }
        
        function nuevoChat() {
            currentChatId = Date.now().toString();
            document.getElementById('chat').innerHTML = '<div class="mensaje mensaje-miku"><b>Miku:</b> ¡Hola! 💙 Me alegra mucho verte por aquí. ¿En qué puedo ayudarte hoy?</div>';
            if (document.getElementById('sidebar').classList.contains('active')) {
                toggleMenu();
            }
        }
        
        function cargarChat(id) {
            currentChatId = id; const chat = chats[id]; const chatDiv = document.getElementById('chat'); chatDiv.innerHTML = '';
            chat.forEach(msg => {
                if (msg.role === 'user') chatDiv.innerHTML += `<div class="mensaje mensaje-usuario"><b>Tú:</b> ${msg.texto}</div>`;
                else chatDiv.innerHTML += `<div class="mensaje mensaje-miku"><b>Miku:</b> ${msg.html}</div>`;
            });
            chatDiv.scrollTop = chatDiv.scrollHeight;
        }
        
        async function enviar() {
            const input = document.getElementById('mensaje'); const chatDiv = document.getElementById('chat'); const mensaje = input.value;
            if (!mensaje) return;
            if (!chats[currentChatId]) chats[currentChatId] = [];
            chats[currentChatId].push({ role: 'user', texto: mensaje });
            chatDiv.innerHTML += `<div class="mensaje mensaje-usuario"><b>Tú:</b> ${mensaje}</div>`;
            input.value = ''; chatDiv.scrollTop = chatDiv.scrollHeight;
            const idPensando = 'pensando-' + Date.now();
            chatDiv.innerHTML += `<div class="mensaje mensaje-miku" id="${idPensando}"><b>Miku:</b> Investigando... 🔍</div>`;
            chatDiv.scrollTop = chatDiv.scrollHeight; guardarChats();
            const response = await fetch('/responder', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mensaje: mensaje }) });
            const data = await response.json();
            document.getElementById(idPensando).innerHTML = `<b>Miku:</b> ${data.respuesta}`;
            chatDiv.scrollTop = chatDiv.scrollHeight;
            chats[currentChatId].push({ role: 'miku', html: data.respuesta }); guardarChats();
        }
        renderizarHistorial();

        if ('serviceWorker' in navigator) {
            window.addEventListener('load', () => {
                navigator.serviceWorker.register('/sw.js')
                    .then(registration => console.log('ServiceWorker registrado con éxito:', registration.scope))
                    .catch(error => console.log('Fallo al registrar ServiceWorker:', error));
            });
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

# ==========================================
# RUTAS PARA PWABUILDER (MANIFEST Y SERVICE WORKER)
# ==========================================
@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory('static', 'manifest.json')

@app.route('/sw.js')
def serve_sw():
    return send_from_directory('static', 'sw.js')

@app.route('/responder', methods=['POST'])
def responder():
    if 'user_id' not in session:
        return jsonify({"respuesta": "Error: Debes iniciar sesión."})
    data = request.get_json()
    mensaje = data.get('mensaje')
    user_id = session['user_id']
    
    if es_riesgo_autolesion(mensaje):
        respuesta_crisis = (
            "Escúchame un momento, por favor... 💙<br><br>"
            "Sé que ahora mismo todo se siente muy oscuro...<br><br>"
            "Por favor, busca ayuda profesional de inmediato:<br>"
            "🇵🇪 <b>Perú:</b> Línea 113 (opción 5) o 0800-4-1212<br>"
            "🇪🇸 <b>España:</b> 024<br>"
            "🇲🇽 <b>México:</b> 800 911 2000<br><br>"
            "No estás solo/a. Te quiero mucho. 💙🌸"
        )
        return jsonify({"respuesta": respuesta_crisis})

    if es_contenido_inapropiado(mensaje):
        respuesta_bloqueo = "Lo siento mucho, pero no puedo ayudar con ese tipo de contenido. Como asistente, tengo filtros de seguridad para no generar ni buscar material para adultos, violento o ilegal. ¿Te puedo ayudar con algún tema académico, histórico o científico? 💙"
        return jsonify({"respuesta": respuesta_bloqueo})
    
    texto_lower = mensaje.lower()
    
    if user_id not in historiales:
        historiales[user_id] = [
            {"role": "system", "content": "Eres Miku Nakano. Tu personalidad es dulce, cálida, amable y un poco tímida. Responde en español de forma clara y útil."}
        ]
    
    historial_chat = historiales[user_id]
    query = ""
    
    modo_pequeno = any(p in texto_lower for p in ["breve", "pequeño", "resumen", "rápido", "que es", "quien es"])
    modo_grande = any(p in texto_lower for p in ["completa", "detallada", "grande", "profunda", "extensa", "ensayo", "trabajo", "investigación completa"])
    
    if modo_grande:
        num_fuentes = 10
        max_tokens_respuesta = 4000
        instruccion_longitud = "Escribe una investigación PROFUNDA y EXTENSA. Incluye: Introducción, Antecedentes, Desarrollo detallado, Análisis, Conclusiones y Bibliografía."
    elif modo_pequeno:
        num_fuentes = 3
        max_tokens_respuesta = 800
        instruccion_longitud = "Escribe una respuesta BREVE y DIRECTA. Ve al grano, usa máximo 2 párrafos."
    else:
        num_fuentes = 6
        max_tokens_respuesta = 2000
        instruccion_longitud = "Escribe una investigación MEDIANA. Incluye una introducción, 2 o 3 apartados con datos importantes y una conclusión."

    if "busca" in texto_lower or "investiga" in texto_lower or "resumen" in texto_lower or "que es" in texto_lower:
        query = texto_lower.replace("miku", "").replace("busca", "").replace("investiga", "").replace("resumen", "").replace("hazme", "").replace("de", "").replace("sobre", "").replace("la", "").replace("el", "").replace("una", "").replace("un", "").replace("que es", "").replace("quien es", "").strip()
             .replace("busca", "").replace("investiga", "").replace("resumen", "").replace("hazme", "").replace("de", "").replace("sobre", "").replace("la", "").replace("el", "").replace("una", "").replace("un", "").replace("que es", "").replace("quien es", "").strip()
        
        if query:
            try:
                resultados = DDGS().text(query, max_results=num_fuentes)
                info_web = "\n".join([f"- {r['title']}: {r['body']}" for r in resultados])
                historial_chat.append({"role": "system", "content": f"Información de internet ({num_fuentes} fuentes):\n{info_web}"})
            except: pass

    historial_chat.append({"role": "system", "content": instruccion_longitud})

    instruccion_imagenes = (
        "IMPORTANTE: Para hacer tu respuesta más visual, añade etiquetas secretas con imágenes. "
        "El formato exacto es: [IMG: palabras clave en inglés]. "
        "CRÍTICO: Usa palabras clave MUY ESPECÍFICAS y en inglés (mínimo 3 palabras). "
        "No uses palabras genéricas como 'war', 'history' o 'people'. "
        "Ejemplo correcto: [IMG: World War II Normandy landings tanks]. "
        "NUNCA uses la palabra 'book', 'document' o 'scan' en la búsqueda. "
        "Usa máximo 2 imágenes por respuesta, colocadas justo después del párrafo al que se refieren."
    )
    historial_chat.append({"role": "system", "content": instruccion_imagenes})
    historial_chat.append({"role": "user", "content": mensaje})
    
    try:
        completion = cliente.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=historial_chat,
            temperature=0.7,
            max_tokens=max_tokens_respuesta
        )
        respuesta_cruda = completion.choices[0].message.content
        
        patron = r'\[IMG:\s*(.*?)\]'
        partes = re.split(patron, respuesta_cruda)
        
        respuesta_final = ""
        for i, parte in enumerate(partes):
            if i % 2 == 0:
                respuesta_final += limpiar_texto(parte) + "\n"
            else:
                palabras_clave = parte.strip()
                imagenes = buscar_imagen_wikimedia(palabras_clave, limite=5)
                
                if imagenes:
                    img = imagenes[0] 
                    tarjeta = f'''
                    <div class="tarjeta-imagen">
                        <div class="titulo-imagen">📷 {img["nombre"]}</div>
                        <img src="{img["url"]}" alt="{palabras_clave}">
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
