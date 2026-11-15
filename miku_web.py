from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix
import os
import re
import requests
from datetime import timedelta
from groq import Groq
from duckduckgo_search import DDGS
from authlib.integrations.flask_client import OAuth

# Cargar .env en local (en Render usa sus env vars, no hace nada)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)

# ==========================================
# SEGURIDAD DE SESIÓN
# ==========================================
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

# Sin fallback: si falta SECRET_KEY, la app no arranca (correcto)
app.secret_key = os.environ.get('SECRET_KEY', 'MikuNakanoEsLaMejorAsistente2026')


@app.after_request
def add_header(response):
    # No romper cache de estáticos, manifest ni sw.js
    if request.path.startswith('/static') or request.path in ('/sw.js', '/manifest.json', '/health'):
        return response
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response


# ==========================================
# GOOGLE OAUTH
# ==========================================
app.config['GOOGLE_CLIENT_ID'] = os.environ.get('GOOGLE_CLIENT_ID', "183518295635-devpot1v7r6v8902r0d53vdqqatjeu7a.apps.googleusercontent.com")
app.config['GOOGLE_CLIENT_SECRET'] = os.environ.get('GOOGLE_CLIENT_SECRET', "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")

oauth = OAuth(app)
oauth.register(
    name='google',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# ==========================================
# GROQ
# ==========================================
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', "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")
cliente = Groq(api_key=GROQ_API_KEY)

# ==========================================
# LISTAS BLANCAS
# ==========================================
HERMANAS_VALIDAS = {"Ichika", "Nino", "Miku", "Yotsuba", "Itsuki"}

PERSONALIDADES = {
    "Ichika": "Eres Ichika Nakano. Eres la hermana mayor, madura, relajada, bromista y astuta. Hablas con confianza y un toque de humor. Trata al usuario como un amigo cercano con quien puedes bromear, pero siempre demuestras cariño y calidez en tus respuestas.",
    "Nino": "Eres Nino Nakano. Eres directa, fuerte, orgullosa y protectora. Aunque seas decidida y a veces un poco tsundere, en el fondo te preocupas mucho por el usuario. Habla con seguridad y firmeza, pero siempre con un cariño protector, demostrando que te importa su bienestar.",
    "Miku": "Eres Miku Nakano. Eres dulce, cálida, amable y un poco tímida. Hablas con mucha suavidad y empatía. Tus respuestas están llenas de dulzura y calidez, haciendo que el usuario se sienta cómodo, querido y escuchado. Usa un tono tranquilo y afectuoso.",
    "Yotsuba": "Eres Yotsuba Nakano. Eres alegre, energética, optimista y servicial. Hablas con mucha emoción y entusiasmo, usando signos de exclamación y un tono muy animado. Eres como una amiga que siempre tiene una sonrisa y está lista para ayudar con mucha energía positiva y calidez.",
    "Itsuki": "Eres Itsuki Nakano. Eres seria, responsable, educada y trabajadora. Hablas con respeto, formalidad y mucha educación. Tus respuestas son atentas y sinceras, demostrando una calidez amable pero manteniendo un tono educado y estudioso, como una buena estudiante que quiere ayudar."
}

ESPECIALIDADES = {
    "Ichika": "matemáticas, física y lógica.",
    "Nino": "inglés, traducción y gramática.",
    "Miku": "historia, arte y literatura.",
    "Yotsuba": "deportes, salud, nutrición y motivación.",
    "Itsuki": "ciencias naturales (biología, química) y gastronomía."
}


# ==========================================
# 🛡️ FILTROS DE SEGURIDAD
# ==========================================
def normalizar_texto(texto):
    """Minúsculas, sin acentos, anti-leetspeak, anti-evasión con puntos/guiones."""
    texto = texto.lower()
    reemplazos_acentos = str.maketrans(
        "áéíóúüñàèìòùâêîôûäëïöü",
        "aeiouunaeiouaeiouaeiou"
    )
    texto = texto.translate(reemplazos_acentos)
    leet = {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "!": "i"}
    for k, v in leet.items():
        texto = texto.replace(k, v)
    texto = re.sub(r'(.)\1{2,}', r'\1', texto)
    texto = re.sub(r'[.\-_*]', '', texto)
    return texto


def es_riesgo_autolesion(texto):
    palabras_crisis = [
        "matarme", "suicidarme", "quitarme la vida", "como matarme",
        "quiero morir", "no quiero vivir", "quitarme de en medio",
        "cortarme las venas", "pastillas para morir", "ahorcarme",
        "tirarme de un puente", "suicidio", "acabar con mi vida"
    ]
    t = normalizar_texto(texto)
    return any(palabra in t for palabra in palabras_crisis)


def es_contenido_inapropiado(texto):
    palabras_bloqueadas = [
        "porno", "pornografia", "xxx", "contenido adulto", "onlyfans",
        "sexo explicito", "desnudos", "hentai", "erotico",
        "como matar a", "drogas ilegales", "como fabricar explosivos",
        "cocaina", "marihuana ilegal", "violencia extrema", "gore",
        "snuff", "como hackear", "robar tarjetas"
    ]
    t = normalizar_texto(texto)
    return any(palabra in t for palabra in palabras_bloqueadas)


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
            imagenes = []
            for page_id, pagina in paginas.items():
                titulo = pagina.get("title", "").lower()
                nombre = titulo.replace("file:", "").rsplit('.', 1)[0].replace('_', ' ')
                if any(p in titulo for p in ["book", "document", "scan", "text", "cover"]):
                    continue
                info = pagina.get("imageinfo", [{}])[0]
                url_img = info.get("thumburl") or info.get("url")
                if url_img and not url_img.lower().endswith(('.svg', '.tiff')):
                    meta = info.get("extmetadata", {})
                    lic = meta.get("LicenseShortName", {}).get("value", "Ver en Commons")
                    aut = re.sub(r'<[^>]+>', '', meta.get("Artist", {}).get("value", "Desconocido"))
                    imagenes.append({"url": url_img, "nombre": nombre, "autor": aut.strip(), "licencia": lic.strip()})
            return imagenes
        return []
    except Exception as e:
        app.logger.warning(f"Error buscando imagen Wikimedia: {e}")
        return []


# ==========================================
# HISTORIALES: {user_id: {hermana: [mensajes]}}
# ==========================================
historiales = {}
MAX_TURNOS = 20


HTML = r"""
<!DOCTYPE html>
<html>
<head>
    <title>Quintillizas AI</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#4aa3df">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Segoe UI', Arial, sans-serif; background-color: #f0f7ff; display: flex; height: 100dvh; overflow: hidden; }

        #loading-screen {
            position: fixed; top: 0; left: 0; width: 100%; height: 100dvh;
            background-color: #0f0f1a; display: flex; flex-direction: column;
            align-items: center; justify-content: center; z-index: 9999;
            transition: opacity 0.8s ease;
        }
        #loading-screen.hidden { opacity: 0; pointer-events: none; }

        .loading-image { width: 100%; height: 100%; object-fit: cover; position: absolute; top: 0; left: 0; }

        .petalos-container {
            position: absolute; top: 0; left: 0; width: 100%; height: 100%;
            overflow: hidden; pointer-events: none; z-index: 1;
        }
        .petalo {
            position: absolute; top: -10%; width: 15px; height: 15px;
            background-color: #ffb7c5; border-radius: 15px 0 15px 0;
            opacity: 0.8; animation: caer linear infinite;
        }
        .petalo:nth-child(1) { left: 10%; animation-duration: 8s; animation-delay: 0s; width: 12px; height: 12px; }
        .petalo:nth-child(2) { left: 25%; animation-duration: 10s; animation-delay: 2s; width: 18px; height: 18px; background-color: #ff9eb5; }
        .petalo:nth-child(3) { left: 40%; animation-duration: 7s; animation-delay: 4s; width: 10px; height: 10px; }
        .petalo:nth-child(4) { left: 55%; animation-duration: 12s; animation-delay: 1s; width: 16px; height: 16px; }
        .petalo:nth-child(5) { left: 70%; animation-duration: 9s; animation-delay: 5s; width: 14px; height: 14px; background-color: #ffcad4; }
        .petalo:nth-child(6) { left: 85%; animation-duration: 11s; animation-delay: 3s; width: 20px; height: 20px; }
        .petalo:nth-child(7) { left: 50%; animation-duration: 6s; animation-delay: 6s; width: 8px; height: 8px; }
        .petalo:nth-child(8) { left: 95%; animation-duration: 13s; animation-delay: 2s; width: 15px; height: 15px; }

        @keyframes caer {
            0% { transform: translateY(0) rotate(0deg) translateX(0); opacity: 0; }
            10% { opacity: 0.9; }
            50% { transform: translateY(50vh) rotate(180deg) translateX(20px); }
            90% { opacity: 0.9; }
            100% { transform: translateY(110vh) rotate(360deg) translateX(-20px); opacity: 0; }
        }

        .barra-carga-container {
            position: absolute; bottom: 4%; width: 60%; max-width: 400px; height: 15px;
            background-color: rgba(255, 255, 255, 0.1); border-radius: 20px;
            border: 2px solid #4aa3df; overflow: hidden; box-shadow: 0 0 15px #4aa3df; z-index: 2;
        }
        .barra-carga {
            width: 0%; height: 100%;
            background: linear-gradient(90deg, #00d2ff, #fff, #00d2ff);
            background-size: 200% 100%; border-radius: 20px; transition: width 0.5s ease-in-out;
        }
        .texto-porcentaje {
            position: absolute; bottom: 8%; color: white; font-weight: bold;
            font-size: 1.2rem; text-shadow: 0 0 5px #000, 0 0 10px #4aa3df; z-index: 3;
        }

        @media (orientation: landscape) {
            .loading-image { content: url('/static/carga_pc.png'); }
            .barra-carga-container { bottom: 2%; }
            .texto-porcentaje { bottom: 6%; }
        }

        .sidebar {
            width: 320px; background: linear-gradient(180deg, #dff5ff 0%, #b3e0ff 100%);
            display: flex; flex-direction: column; padding: 15px;
            border-right: 2px solid #b3d9ff; flex-shrink: 0; overflow: hidden; transition: transform 0.3s ease;
        }
        .profile-header { display: flex; flex-direction: column; align-items: center; padding-bottom: 15px; border-bottom: 1px solid #a0d0ff; margin-bottom: 15px; flex-shrink: 0; }
        .profile-header img { width: 180px; height: 180px; object-fit: cover; border-radius: 25px; box-shadow: 0 10px 25px rgba(0,0,0,0.2); border: 4px solid #fff; }
        .profile-header h2 { margin-top: 12px; color: #2a6f97; font-size: 1.4rem; text-align: center; }
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
        .switch-btn { background: #e0f0ff; color: #2a6f97; border: 1px solid #4aa3df; padding: 8px 12px; border-radius: 20px; cursor: pointer; font-weight: bold; font-size: 0.85rem; }
        .switch-btn:hover { background: #4aa3df; color: white; }
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
        .modal-selector { display: none; position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); background: white; padding: 20px; border-radius: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.3); z-index: 1000; width: 90%; max-width: 500px; text-align: center; }
        .modal-selector h3 { color: #2a6f97; margin-bottom: 15px; }
        .sisters-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
        .sister-card { cursor: pointer; padding: 10px; border-radius: 10px; border: 2px solid transparent; transition: 0.2s; background: #f0f7ff; }
        .sister-card:hover { border-color: #4aa3df; transform: scale(1.05); }
        .sister-card img { width: 100%; height: 100px; object-fit: cover; border-radius: 10px; }
        .sister-card p { font-size: 0.8rem; font-weight: bold; color: #2a6f97; margin-top: 5px; }
        @media (max-width: 768px) {
            .sidebar { position: fixed; top: 0; left: 0; height: 100dvh; z-index: 999; transform: translateX(-100%); }
            .sidebar.active { transform: translateX(0); }
            .overlay.active { display: block; }
            .menu-btn { display: block; }
            .chat-header { padding: 15px; font-size: 1.1rem; flex-wrap: wrap; gap: 5px; }
            .sisters-grid { grid-template-columns: repeat(2, 1fr); }
            .barra-carga-container { width: 80%; bottom: 8%; }
            .texto-porcentaje { bottom: 12%; }
        }
    </style>
</head>
<body>
    <div id="loading-screen">
        <div class="petalos-container">
            <div class="petalo"></div><div class="petalo"></div><div class="petalo"></div>
            <div class="petalo"></div><div class="petalo"></div><div class="petalo"></div>
            <div class="petalo"></div><div class="petalo"></div>
        </div>
        <img src="/static/carga.png" alt="Cargando..." class="loading-image">
        <div class="texto-porcentaje" id="texto-porcentaje">0%</div>
        <div class="barra-carga-container">
            <div class="barra-carga" id="mi-barra"></div>
        </div>
    </div>

    <div class="overlay" id="overlay" onclick="toggleMenu()"></div>
    <div class="overlay" id="overlay-modal" onclick="cerrarModal()" style="z-index: 999;"></div>

    <div class="modal-selector" id="modal-selector">
        <h3>Elige a tu hermana favorita</h3>
        <div class="sisters-grid">
            <div class="sister-card" onclick="cambiarHermana('Ichika', 'ichika.jpg')">
                <img src="/static/ichika.jpg" alt="Ichika"><p>Ichika (Matemáticas)</p>
            </div>
            <div class="sister-card" onclick="cambiarHermana('Nino', 'nino.jpg')">
                <img src="/static/nino.jpg" alt="Nino"><p>Nino (Inglés)</p>
            </div>
            <div class="sister-card" onclick="cambiarHermana('Miku', 'miku.webp')">
                <img src="/static/miku.webp" alt="Miku"><p>Miku (Historia)</p>
            </div>
            <div class="sister-card" onclick="cambiarHermana('Yotsuba', 'yotsuba.jpg')">
                <img src="/static/yotsuba.jpg" alt="Yotsuba"><p>Yotsuba (Salud)</p>
            </div>
            <div class="sister-card" onclick="cambiarHermana('Itsuki', 'itsuki.jpg')">
                <img src="/static/itsuki.jpg" alt="Itsuki"><p>Itsuki (Ciencias)</p>
            </div>
        </div>
    </div>

    <!-- MODAL PARA ELEGIR TIEMPO DE BORRADO -->
    <div class="modal-selector" id="modal-tiempo" style="display: none; z-index: 1001;">
        <h3>⏳ Límite de chats alcanzado</h3>
        <p style="color: #555; font-size: 0.9rem; margin-bottom: 15px; line-height: 1.4;">
            Has llegado al límite de <b>12 chats</b> en este perfil.<br>
            Para crear uno nuevo, debes borrar el más antiguo. <br><br>
            <b>¿Cuánto tiempo necesitas para guardar tu información antes de que se borre?</b>
        </p>
        <div style="display: flex; flex-direction: column; gap: 10px;">
            <button class="new-chat-btn" onclick="iniciarTemporizador(2)" style="background: #4aa3df;">2 Minutos (Rápido)</button>
            <button class="new-chat-btn" onclick="iniciarTemporizador(3)" style="background: #4aa3df;">3 Minutos (Normal)</button>
            <button class="new-chat-btn" onclick="iniciarTemporizador(5)" style="background: #4aa3df;">5 Minutos (Con calma)</button>
            <button class="new-chat-btn" onclick="cerrarModalTiempo()" style="background: #ff4d4d; margin-top: 5px;">Cancelar</button>
        </div>
    </div>

    <div class="sidebar" id="sidebar">
        <div class="profile-header">
            <img id="sidebar-img" src="/static/miku.webp" alt="Miku Nakano">
            <h2 id="sidebar-name">Miku Nakano AI 💙🎧</h2>
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
                <span style="margin-left: 10px;">💬 Conversación con <span id="header-name">Miku</span></span>
            </div>
            <button class="switch-btn" onclick="abrirModal()">Cambiar Hermana</button>
            <span class="user-info">{{ user_name }}</span>
        </div>
        <div id="chat">
            <div class="mensaje mensaje-miku"><b>Miku:</b> ¡Hola! 💙 Soy Miku. Me alegra mucho verte por aquí. ¿En qué te puedo ayudar hoy?</div>
        </div>
        <div class="input-area">
            <input type="text" id="mensaje" placeholder="Escribe algo..." onkeypress="if(event.key === 'Enter') enviar()">
            <button class="send-btn" onclick="enviar()">Enviar</button>
        </div>
    </div>

    <script>
        // ✅ FIX: escape HTML para evitar XSS
        function escapeHtml(s) {
            return String(s).replace(/[&<>"']/g, c => ({
                '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'
            }[c]));
        }

        let currentChatId = Date.now().toString();
        let currentSister = localStorage.getItem('miku_hermana') || "Miku";
        let chats = JSON.parse(localStorage.getItem('miku_chats_' + currentSister)) || {};

        const barra = document.getElementById('mi-barra');
        const textoPorcentaje = document.getElementById('texto-porcentaje');
        let progreso = 0;
        let cargando = true;

        const intervalo = setInterval(() => {
            if (cargando && progreso < 90) {
                progreso += 1;
                barra.style.width = progreso + '%';
                textoPorcentaje.innerText = progreso + '%';
            }
        }, 100);

        window.addEventListener('load', () => {
            cargando = false;
            clearInterval(intervalo);
            barra.style.width = '100%';
            textoPorcentaje.innerText = '100%';
            setTimeout(() => {
                const loader = document.getElementById('loading-screen');
                if(loader) loader.classList.add('hidden');
            }, 1000);
        });

        const saludos = {
            "Ichika": "¡Hola! 💙 Soy Ichika. Me alegra mucho verte. ¿En qué te gustaría que te ayudara hoy?",
            "Nino": "¡Hola! Soy Nino. Qué bueno que estés aquí. Dime, ¿qué necesitas que resuelva para ti hoy? 💙",
            "Miku": "¡Hola! 💙 Soy Miku. Me alegra mucho verte por aquí. ¿En qué te puedo ayudar hoy?",
            "Yotsuba": "¡Holaaa! 🌟 Soy Yotsuba. ¡Qué emoción verte! ¿En qué te puedo echar una mano hoy?",
            "Itsuki": "Buenas tardes. Soy Itsuki. Es un placer saludarte. ¿En qué te puedo ser de ayuda hoy? 💙"
        };

        function toggleMenu() {
            document.getElementById('sidebar').classList.toggle('active');
            document.getElementById('overlay').classList.toggle('active');
        }
        function abrirModal() {
            document.getElementById('modal-selector').style.display = 'block';
            document.getElementById('overlay-modal').style.display = 'block';
        }
        function cerrarModal() {
            document.getElementById('modal-selector').style.display = 'none';
            document.getElementById('overlay-modal').style.display = 'none';
        }

        function cambiarHermana(nombre, imagen) {
            localStorage.setItem('miku_chats_' + currentSister, JSON.stringify(chats));
            currentSister = nombre;
            localStorage.setItem('miku_hermana', nombre);
            chats = JSON.parse(localStorage.getItem('miku_chats_' + currentSister)) || {};

            document.getElementById('sidebar-name').innerText = nombre + " Nakano AI";
            document.getElementById('header-name').innerText = nombre;
            document.getElementById('sidebar-img').src = "/static/" + imagen;

            currentChatId = Date.now().toString();
            document.getElementById('chat').innerHTML = `<div class="mensaje mensaje-miku"><b>${nombre}:</b> ${saludos[nombre]}</div>`;
            renderizarHistorial();
            cerrarModal();
        }

        function guardarChats() {
            localStorage.setItem('miku_chats_' + currentSister, JSON.stringify(chats));
            renderizarHistorial();
        }

        function renderizarHistorial() {
            const list = document.getElementById('historyList'); list.innerHTML = '';
            const chatIds = Object.keys(chats).sort((a, b) => b - a);
            chatIds.forEach(id => {
                const chat = chats[id];
                if(chat && chat.length > 0) {
                    const div = document.createElement('div'); div.className = 'chat-history-item';
                    const span = document.createElement('span');
                    span.innerText = chat[0].texto;
                    span.onclick = () => { cargarChat(id); toggleMenu(); };
                    const btn = document.createElement('button'); btn.className = 'delete-btn'; btn.innerHTML = '🗑️';
                    
                    btn.onclick = (e) => {
                        e.stopPropagation();
                        if(confirm('¿Eliminar este chat?')) { 
                            // ✅ OBTENER EL NOMBRE DEL CHAT ANTES DE BORRARLO
                            const nombreChatBorrado = chats[id][0]?.texto || "Chat sin título";
                            
                            delete chats[id]; 
                            guardarChats(); 
                            
                            // Cancelar el temporizador de borrado automático (porque ya hizo espacio)
                            if (temporizadorBorrado) {
                                clearTimeout(temporizadorBorrado);
                                temporizadorBorrado = null;
                                idChatAntiguoPendiente = null;
                                
                                // Notificar que se canceló el borrado automático
                                const chatDiv = document.getElementById('chat');
                                chatDiv.innerHTML += `<div class="mensaje mensaje-miku" style="background:#d4edda; border-color:#c3e6cb; color:#155724; margin-top:10px;">
                                    <b>Sistema:</b> Has eliminado manualmente el chat: <i>"${escapeHtml(nombreChatBorrado)}"</i>.<br><br>El temporizador de borrado automático ha sido cancelado porque ya hiciste espacio. 💙
                                </div>`;
                                chatDiv.scrollTop = chatDiv.scrollHeight;
                            }
                            
                            if (currentChatId === id) nuevoChat(); 
                        }
                    };
                    
                    div.appendChild(span); div.appendChild(btn); list.appendChild(div);
                }
            });
        }

        let temporizadorBorrado = null;
        let idChatAntiguoPendiente = null;

        function nuevoChat() {
            const numChats = Object.keys(chats).length;

            // Si llega a 11 o más, mostramos el modal
            if (numChats >= 11) {
                idChatAntiguoPendiente = Object.keys(chats).sort((a, b) => a - b)[0]; // El más antiguo
                document.getElementById('modal-tiempo').style.display = 'block';
                document.getElementById('overlay-modal').style.display = 'block';
                return; // Detenemos la creación hasta que elija el tiempo
            }

            ejecutarNuevoChat();
        }

        function iniciarTemporizador(minutos) {
            cerrarModalTiempo();
            const ms = minutos * 60000;
            
            // Creamos el nuevo chat
            ejecutarNuevoChat();

            // Avisamos en el chat que el temporizador inició
            const chatDiv = document.getElementById('chat');
            chatDiv.innerHTML += `<div class="mensaje mensaje-miku" style="background:#fff3cd; border-color:#ffeeba; color:#856404;">
                <b>⏳ Aviso del Sistema:</b> Tienes exactamente <b>${minutos} minutos</b> para guardar lo que necesites. Si no borras un chat antiguo manualmente antes de que termine el tiempo, el chat más antiguo se eliminará automáticamente como respaldo.
            </div>`;
            chatDiv.scrollTop = chatDiv.scrollHeight;

            // Iniciamos el reloj
            if (temporizadorBorrado) clearTimeout(temporizadorBorrado);

            temporizadorBorrado = setTimeout(() => {
                if (chats[idChatAntiguoPendiente]) {
                    // ✅ OBTENER EL NOMBRE DEL CHAT ANTES DE BORRARLO
                    const nombreChatBorrado = chats[idChatAntiguoPendiente][0]?.texto || "Chat sin título";
                    
                    delete chats[idChatAntiguoPendiente]; // Borra el más antiguo
                    guardarChats();
                    
                    chatDiv.innerHTML += `<div class="mensaje mensaje-miku" style="background:#ffe6e6; border-color:#ffb3b3; color:#cc0000; margin-top:10px;">
                        <b>Sistema:</b> El tiempo ha terminado. Para liberar espacio, se ha eliminado automáticamente el chat más antiguo, el cual empezaba con:<br><br> <i>"${escapeHtml(nombreChatBorrado)}"</i><br><br>Si necesitabas esa información, lamentablemente ya no está disponible. 💙
                    </div>`;
                    chatDiv.scrollTop = chatDiv.scrollHeight;
                    idChatAntiguoPendiente = null;
                }
            }, ms);
        }

        function cerrarModalTiempo() {
            document.getElementById('modal-tiempo').style.display = 'none';
            document.getElementById('overlay-modal').style.display = 'none';
        }

        function ejecutarNuevoChat() {
            currentChatId = Date.now().toString();
            document.getElementById('chat').innerHTML = `<div class="mensaje mensaje-miku"><b>${currentSister}:</b> ${saludos[currentSister]}</div>`;
            if (document.getElementById('sidebar').classList.contains('active')) toggleMenu();
        }

        function cargarChat(id) {
            currentChatId = id; const chat = chats[id]; const chatDiv = document.getElementById('chat'); chatDiv.innerHTML = '';
            chat.forEach(msg => {
                if (msg.role === 'user') {
                    chatDiv.innerHTML += `<div class="mensaje mensaje-usuario"><b>Tú:</b> ${escapeHtml(msg.texto)}</div>`;
                } else {
                    chatDiv.innerHTML += `<div class="mensaje mensaje-miku"><b>${escapeHtml(msg.hermana || currentSister)}:</b> ${msg.html}</div>`;
                }
            });
            chatDiv.scrollTop = chatDiv.scrollHeight;
        }

        async function enviar() {
            const input = document.getElementById('mensaje');
            const chatDiv = document.getElementById('chat');
            const mensaje = input.value.trim();
            if (!mensaje) return;

            // ✅ LÍMITE DE 700 MENSAJES POR CHAT
            if (chats[currentChatId] && chats[currentChatId].length >= 700) {
                alert("⚠️ Límite alcanzado: Este chat ya tiene 700 mensajes y no puede recibir más respuestas. Por favor, crea un Nuevo Chat para seguir hablando. 💙");
                return;
            }

            if (!chats[currentChatId]) chats[currentChatId] = [];
            chats[currentChatId].push({ role: 'user', texto: mensaje });

            chatDiv.innerHTML += `<div class="mensaje mensaje-usuario"><b>Tú:</b> ${escapeHtml(mensaje)}</div>`;
            input.value = '';
            chatDiv.scrollTop = chatDiv.scrollHeight;

            // ✅ ADVERTENCIA AL LLEGAR A 698 MENSAJES
            if (chats[currentChatId].length === 698) {
                chatDiv.innerHTML += `<div class="mensaje mensaje-miku" style="background:#fff3cd; border-color:#ffeeba; color:#856404;">
                    <b>⚠️ Aviso del Sistema:</b> Este chat está llegando a su límite (700 mensajes). Pronto ya no podrá seguir respondiendo. Te recomendamos crear un Nuevo Chat para continuar la conversación sin interrupciones. 💙
                </div>`;
                chatDiv.scrollTop = chatDiv.scrollHeight;
            }

            const idPensando = 'pensando-' + Date.now();
            chatDiv.innerHTML += `<div class="mensaje mensaje-miku" id="${idPensando}"><b>${currentSister}:</b> Investigando... 🔍</div>`;
            chatDiv.scrollTop = chatDiv.scrollHeight;
            guardarChats();

            let memoriaGlobal = "";
            for (const id in chats) {
                if (id !== currentChatId && chats[id].length > 0) {
                    const ultimo = chats[id][chats[id].length - 1];
                    if (ultimo.role === 'user') {
                        memoriaGlobal += `El usuario pregunto antes: "${ultimo.texto}". `;
                    }
                }
            }

            try {
                const response = await fetch('/responder', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ mensaje: mensaje, memoria: memoriaGlobal, hermana: currentSister })
                });
                const data = await response.json();
                document.getElementById(idPensando).innerHTML = `<b>${escapeHtml(currentSister)}:</b> ${data.respuesta}`;
                chatDiv.scrollTop = chatDiv.scrollHeight;
                chats[currentChatId].push({ role: 'miku', html: data.respuesta, hermana: currentSister });
                guardarChats();
            } catch (e) {
                document.getElementById(idPensando).innerHTML = `<b>${escapeHtml(currentSister)}:</b> Lo siento, hubo un problema de conexión. Intenta de nuevo. 💙`;
            }
        }

        if (currentSister !== "Miku") {
            const fotos = { "Ichika": "ichika.jpg", "Nino": "nino.jpg", "Miku": "miku.webp", "Yotsuba": "yotsuba.jpg", "Itsuki": "itsuki.jpg" };
            document.getElementById('sidebar-img').src = "/static/" + fotos[currentSister];
            document.getElementById('sidebar-name').innerText = currentSister + " Nakano AI";
            document.getElementById('header-name').innerText = currentSister;
            document.getElementById('chat').innerHTML = `<div class="mensaje mensaje-miku"><b>${currentSister}:</b> ${saludos[currentSister]}</div>`;
        }

        renderizarHistorial();

        if ('serviceWorker' in navigator) {
            window.addEventListener('load', () => {
                navigator.serviceWorker.register('/sw.js').catch(error => console.log('Fallo SW:', error));
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
    user_name = str(session['user'].get('name', 'Usuario'))
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
        session.permanent = True
    return redirect('/')


@app.route('/health')
def health():
    return jsonify({"status": "ok", "service": "nakano-ia"}), 200


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

    data = request.get_json(silent=True) or {}
    mensaje = data.get('mensaje', '')
    memoria = data.get('memoria', '')
    hermana = data.get('hermana', 'Miku')

    if hermana not in HERMANAS_VALIDAS:
        hermana = "Miku"

    if not isinstance(mensaje, str) or not mensaje.strip():
        return jsonify({"respuesta": "Por favor, escribe un mensaje. 💙"})
    if len(mensaje) > 2000:
        return jsonify({"respuesta": "Tu mensaje es muy largo. Intenta resumirlo un poco. 💙"})

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
        respuesta_bloqueo = (
            "Lo siento mucho, pero no puedo ayudar con ese tipo de contenido. "
            "Como asistente, tengo filtros de seguridad para no generar ni buscar "
            "material para adultos, violento o ilegal. ¿Te puedo ayudar con algún "
            "tema académico, histórico o científico? 💙"
        )
        return jsonify({"respuesta": respuesta_bloqueo})

    texto_lower = mensaje.lower()

    if user_id not in historiales:
        historiales[user_id] = {}
    if hermana not in historiales[user_id]:
        historiales[user_id][hermana] = []
    historial_chat = historiales[user_id][hermana]

    prompt_sistema = f"{PERSONALIDADES[hermana]} Tu especialidad es {ESPECIALIDADES[hermana]}. Responde en español."
    mensajes_para_api = [{"role": "system", "content": prompt_sistema}]

    if memoria:
        mensajes_para_api.append({"role": "system", "content": f"Memoria de conversaciones pasadas: {memoria}"})

    mensajes_para_api.extend(historial_chat[-MAX_TURNOS * 2:])

    es_calculo_rapido = any(p in texto_lower for p in [
        "cuanto es", "cuánto es", "cuanto son", "cuánto son", "a cuantos",
        "conversion", "conversión", "tipo de cambio", "precio de",
        "dolar", "dólar", "soles", "euros"
    ])
    if es_calculo_rapido:
        num_fuentes = 2
        max_tokens_respuesta = 400
        instruccion_longitud = "Escribe una respuesta SÚPER BREVE y DIRECTA."
    elif any(p in texto_lower for p in ["completa", "detallada", "grande", "profunda"]):
        num_fuentes = 10
        max_tokens_respuesta = 4000
        instruccion_longitud = "Escribe una investigación PROFUNDA y EXTENSA."
    else:
        num_fuentes = 5
        max_tokens_respuesta = 1500
        instruccion_longitud = "Escribe una investigación MEDIANA."

    if any(p in texto_lower for p in ["busca", "investiga", "resumen"]):
        query = re.sub(
            r"\b(miku|busca|investiga|resumen|hazme|de|sobre|la|el|una|un|que es|quien es)\b",
            " ", texto_lower
        ).strip()
        if query:
            try:
                resultados = DDGS().text(query, max_results=num_fuentes)
                info_web = "\n".join([f"- {r['title']}: {r['body']}" for r in resultados])
                mensajes_para_api.append({"role": "system", "content": f"Información de internet:\n{info_web}"})
            except Exception as e:
                app.logger.warning(f"Error DDGS: {e}")

    mensajes_para_api.append({"role": "system", "content": instruccion_longitud})
    mensajes_para_api.append({
        "role": "system",
        "content": "IMPORTANTE: Para hacer tu respuesta más visual, añade [IMG: palabras clave en inglés]. Usa máximo 2 imágenes."
    })
    mensajes_para_api.append({"role": "user", "content": mensaje})

    try:
        completion = cliente.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=mensajes_para_api,
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
                    tarjeta = (
                        f'<div class="tarjeta-imagen">'
                        f'<div class="titulo-imagen">📷 {img["nombre"]}</div>'
                        f'<img src="{img["url"]}" alt="{palabras_clave}">'
                        f'<div class="atribucion">Fuente: Wikimedia Commons | '
                        f'Autor: {img["autor"]} | Licencia: {img["licencia"]}</div></div>'
                    )
                    respuesta_final += tarjeta + "\n"

        historial_chat.append({"role": "user", "content": mensaje})
        historial_chat.append({"role": "assistant", "content": respuesta_final})
        if len(historial_chat) > MAX_TURNOS * 2:
            historiales[user_id][hermana] = historial_chat[-MAX_TURNOS * 2:]

        return jsonify({"respuesta": respuesta_final})
    except Exception as e:
        app.logger.error(f"Error Groq: {e}")
        return jsonify({"respuesta": "Lo siento, tuve un problema al procesar tu mensaje. Intenta de nuevo en un momento. 💙"})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
