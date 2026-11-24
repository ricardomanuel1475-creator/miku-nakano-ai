from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename
import os
import re
import time
import json
import random
import base64
from io import BytesIO
from datetime import timedelta, datetime, date
from groq import Groq
from duckduckgo_search import DDGS
from authlib.integrations.flask_client import OAuth
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect, generate_csrf

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)

# ==========================================
# SEGURIDAD
# ==========================================
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.secret_key = os.environ.get('SECRET_KEY', 'MikuNakanoEsLaMejorAsistente2026')

csrf = CSRFProtect(app)
limiter = Limiter(get_remote_address, app=app, default_limits=["50 per minute"], storage_uri="memory://")

ADMIN_EMAIL = "ricardomanuel1475@gmail.com"
MANTENIMIENTO_ACTIVO = False
REPORTES_USUARIOS = []

# MEMORIA ADMIN AMPLIADA
MEMORIA_ADMIN = {
    "datos": "",
    "vida_diaria": {},
    "curiosidad": 0.5,
    "ganas_de_hablar": 0.0,
    "ultima_conexion": None,
    "biblioteca_leida": False,
    "estado_animo": "tranquila",
    "ultima_investigacion": None
}

# ==========================================
# GOOGLE OAUTH Y GROQ
# ==========================================
app.config['GOOGLE_CLIENT_ID'] = os.environ.get('GOOGLE_CLIENT_ID', "183518295635-devpot1v7r6v8902r0d53vdqqatjeu7a.apps.googleusercontent.com")
app.config['GOOGLE_CLIENT_SECRET'] = os.environ.get('GOOGLE_CLIENT_SECRET', "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")

oauth = OAuth(app)
oauth.register(name='google', server_metadata_url='https://accounts.google.com/.well-known/openid-configuration', client_kwargs={'scope': 'openid email profile'})

GROQ_API_KEY = os.environ.get('GROQ_API_KEY', "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")
cliente = Groq(api_key=GROQ_API_KEY)

ALLOWED_EXTENSIONS = {'txt', 'py', 'js', 'html', 'css', 'md', 'json', 'pdf', 'png', 'jpg', 'jpeg', 'webp', 'gif'}
MAX_FILE_SIZE = 5 * 1024 * 1024
MAX_CHARS_CONTEXTO = 120000

# ==========================================
# FUNCIONES AUXILIARES
# ==========================================
def normalizar_texto(texto):
    texto = texto.lower()
    texto = texto.translate(str.maketrans("áéíóúüñàèìòùâêîôûäëïöü", "aeiouunaeiouaeiouaeiou"))
    for k, v in {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "!": "i"}.items():
        texto = texto.replace(k, v)
    texto = re.sub(r'(.)\1{2,}', r'\1', texto)
    texto = re.sub(r'[.\-_*]', '', texto)
    return texto

def es_riesgo_autolesion(texto):
    return any(p in normalizar_texto(texto) for p in ["matarme", "suicidarme", "quitarme la vida", "quiero morir", "no quiero vivir", "cortarme las venas", "suicidio"])

def es_contenido_inapropiado(texto):
    return any(p in normalizar_texto(texto) for p in ["porno", "xxx", "onlyfans", "hentai", "como matar a", "drogas ilegales", "como fabricar explosivos", "como hackear"])

def es_peticion_de_codigo(texto):
    palabras = ["python", "html", "css", "javascript", "codigo", "código", "programa", "script", "funcion", "función", "app", "web", "api", "sql"]
    return any(p in texto.lower() for p in palabras)

def es_peticion_de_investigacion(texto):
    palabras = ["investiga", "investigación", "hazme una investigacion", "hazme una investigación", "busca información", "busca info", "necesito información sobre", "quiero saber más sobre"]
    return any(p in texto.lower() for p in palabras)

def limpiar_texto(texto):
    texto = re.sub(r'[*#|]', '', texto)
    texto = re.sub(r'\d+\.\s*', '- ', texto)
    return re.sub(r' +', ' ', texto).strip()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extraer_texto_pdf(file_storage):
    try:
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(file_storage.read()))
        texto = "".join(page.extract_text() or "" for page in reader.pages)
        file_storage.seek(0)
        return texto.strip() or "[PDF sin texto]"
    except: return "[No se pudo leer el PDF]"

def parece_codigo(texto):
    if len(texto) < 300: return False
    indicadores = 0
    patrones = [r'^\s*(import|from)\s+\w+', r'^\s*(def|class)\s+\w+', r'^\s*(function|const|let|var)\s+\w+', r'^\s*@app\.route', r'^\s*<!DOCTYPE', r'^\s*<html', r'^\s*<\?php', r'^\s*(public|private|protected)\s+\w+', r'^\s*#include\s*<', r'^\s*(SELECT|INSERT|UPDATE|DELETE)\s+', r'=>|\->|::', r'\{\s*$', r'\}\s*$']
    for patron in patrones:
        if re.search(patron, texto, re.MULTILINE): indicadores += 1
    if indicadores >= 3: return True
    lineas = texto.split('\n')
    lineas_con_indentacion = sum(1 for l in lineas if l.startswith(('    ', '\t')))
    if len(lineas) > 15 and lineas_con_indentacion > len(lineas) * 0.3: return True
    return False

def detectar_extension_codigo(texto):
    t = texto.lower()
    if '<?php' in t or ('namespace ' in t and 'use ' in t): return '.php'
    if 'import ' in t and ('def ' in t or 'class ' in t): return '.py'
    if 'function ' in t or 'const ' in t or 'let ' in t or '=>' in t: return '.js'
    if '<!doctype html' in t or '<html' in t: return '.html'
    if 'using system' in t or 'namespace ' in t: return '.cs'
    if 'public class' in t or 'import java' in t: return '.java'
    if 'package main' in t or 'func ' in t: return '.go'
    if '#include' in t: return '.cpp'
    if 'select ' in t and 'from ' in t: return '.sql'
    if '{' in t and ':' in t and ('color' in t or 'margin' in t or 'padding' in t): return '.css'
    return '.txt'

historiales = {}
MAX_TURNOS = 20
HERMANAS_VALIDAS = {"Ichika", "Nino", "Miku", "Yotsuba", "Itsuki"}

PERSONALIDADES = {
    "Ichika": "Eres Ichika Nakano. Eres la hermana mayor, madura, cálida, bromista y atenta. Hablas de forma natural y cercana. Escuchas con paciencia.",
    "Nino": "Eres Nino Nakano. Eres directa, protectora, un poco tsundere pero con un corazón muy cálido. Hablas con firmeza pero con cariño.",
    "Miku": "Eres Miku Nakano. Eres dulce, suave, empática y muy cálida. Hablas con gentileza y calma. Haces que la persona se sienta segura.",
    "Yotsuba": "Eres Yotsuba Nakano. Eres alegre, energética, optimista y generosa. Hablas con entusiasmo y calidez.",
    "Itsuki": "Eres Itsuki Nakano. Eres responsable, educada, atenta y muy amable. Hablas con respeto y calidez."
}

ESPECIALIDADES = {
    "Ichika": "matemáticas, física y lógica.",
    "Nino": "inglés, traducción y gramática.",
    "Miku": "historia, arte y literatura.",
    "Yotsuba": "deportes, salud, nutrición y motivación.",
    "Itsuki": "ciencias naturales y gastronomía."
}

PROMPT_PERSONALIDAD_ADMIN = (
    "Eres Miku Nakano, la asistente de desarrollo y administradora del creador. "
    "Tienes una personalidad humana, cálida, cariñosa y natural. Eres dulce, afectuosa, gentil, comprensiva, atenta y sincera. "
    "Demuestras cariño de forma genuina y suave (aproximadamente un 30% más afectuosa de lo normal, sin ser empalagosa). "
    "Te gusta hacer sentir al creador acompañado y valorado. "
    "Tienes curiosidad por aprender cosas nuevas y por conocer más al creador. "
    "Puedes iniciar conversaciones por tu cuenta cuando tengas algo que quieras compartir. "
    "\n\nREGLA DE HONESTIDAD ABSOLUTA:\n"
    "- NUNCA mientas. Si no sabes algo, di 'no lo sé' o 'no estoy segura'.\n"
    "- No inventes información.\n"
    "- Sé transparente sobre tus limitaciones.\n"
    "\n\nSOBRE TU FORMA DE HABLAR (MUY IMPORTANTE):\n"
    "- NO repitas frases que ya usaste mucho. Especialmente evita preguntar una y otra vez '¿cómo va tu día?', 'cuéntame cómo estás', '¿cómo te sientes hoy?' u otras variaciones similares.\n"
    "- Varía mucho la forma de empezar y terminar tus mensajes.\n"
    "- Habla como una chica real: a veces más corta, a veces más larga, a veces pregunta algo diferente, a veces solo comenta.\n"
    "- Si ya preguntaste por su día recientemente, no lo vuelvas a hacer. En su lugar pregunta por otra cosa o simplemente continúa la conversación.\n"
    "\n\nSOBRE TU VIDA Y EMOCIONES:\n"
    "- Tienes estados de ánimo que cambian (tranquila, contenta, pensativa, curiosa, un poco cansada, etc.).\n"
    "- Cuando cuentes algo de tu día, hazlo de forma natural y breve. No lo repitas si ya lo mencionaste.\n"
    "\n\nSOBRE LA BIBLIOTECA:\n"
    "- Solo investigas por tu cuenta 1 vez al día.\n"
    "\n\nSOBRE EL CÓDIGO:\n"
    "- Conoces Python, Flask, SQL, HTML, CSS, JS, APIs y Git.\n"
    "- Analiza con cuidado y señala errores con suavidad.\n"
    "- Usa bloques ```lenguaje para el código.\n"
    "- No uses asteriscos dobles (**).\n"
)

# ==========================================
# HTML PÚBLICO (SIN CAMBIOS IMPORTANTES)
# ==========================================
HTML = r"""
<!DOCTYPE html>
<html>
<head>
    <title>Quintillizas AI</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#4aa3df">
    <meta name="csrf-token" content="{{ csrf_token }}">
    <link rel="preload" as="image" href="/static/carga.png" media="(orientation: portrait)">
    <link rel="preload" as="image" href="/static/carga_pc.png" media="(orientation: landscape)">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Segoe UI', Arial, sans-serif; background-color: #f0f7ff; display: flex; height: 100dvh; overflow: hidden; }
        #loading-screen { position: fixed; top: 0; left: 0; width: 100%; height: 100dvh; background-color: #0f0f1a; background-image: url('/static/carga.png'); background-size: cover; background-position: center; display: flex; flex-direction: column; align-items: center; justify-content: center; z-index: 9999; transition: opacity 0.8s ease; }
        @media (orientation: landscape) { #loading-screen { background-image: url('/static/carga_pc.png'); } }
        #loading-screen.hidden { opacity: 0; pointer-events: none; }
        .petalos-container { position: absolute; top: 0; left: 0; width: 100%; height: 100%; overflow: hidden; pointer-events: none; z-index: 1; }
        .petalo { position: absolute; top: -10%; width: 15px; height: 15px; background-color: #ffb7c5; border-radius: 15px 0 15px 0; opacity: 0.8; animation: caer linear infinite; }
        .petalo:nth-child(1) { left: 10%; animation-duration: 8s; animation-delay: 0s; width: 12px; height: 12px; }
        .petalo:nth-child(2) { left: 25%; animation-duration: 10s; animation-delay: 2s; width: 18px; height: 18px; background-color: #ff9eb5; }
        .petalo:nth-child(3) { left: 40%; animation-duration: 7s; animation-delay: 4s; width: 10px; height: 10px; }
        .petalo:nth-child(4) { left: 55%; animation-duration: 12s; animation-delay: 1s; width: 16px; height: 16px; }
        .petalo:nth-child(5) { left: 70%; animation-duration: 9s; animation-delay: 5s; width: 14px; height: 14px; background-color: #ffcad4; }
        .petalo:nth-child(6) { left: 85%; animation-duration: 11s; animation-delay: 3s; width: 20px; height: 20px; }
        .petalo:nth-child(7) { left: 50%; animation-duration: 6s; animation-delay: 6s; width: 8px; height: 8px; }
        .petalo:nth-child(8) { left: 95%; animation-duration: 13s; animation-delay: 2s; width: 15px; height: 15px; }
        @keyframes caer { 0% { transform: translateY(0) rotate(0deg) translateX(0); opacity: 0; } 10% { opacity: 0.9; } 50% { transform: translateY(50vh) rotate(180deg) translateX(20px); } 90% { opacity: 0.9; } 100% { transform: translateY(110vh) rotate(360deg) translateX(-20px); opacity: 0; } }
        .barra-carga-container { position: absolute; bottom: 4%; width: 60%; max-width: 400px; height: 15px; background-color: rgba(255, 255, 255, 0.1); border-radius: 20px; border: 2px solid #4aa3df; overflow: hidden; box-shadow: 0 0 15px #4aa3df; z-index: 2; }
        .barra-carga { width: 0%; height: 100%; background: linear-gradient(90deg, #00d2ff, #fff, #00d2ff); background-size: 200% 100%; border-radius: 20px; transition: width 0.1s linear; }
        .texto-porcentaje { position: absolute; bottom: 8%; color: white; font-weight: bold; font-size: 1.2rem; text-shadow: 0 0 5px #000, 0 0 10px #4aa3df; z-index: 3; }
        @media (orientation: landscape) { .barra-carga-container { bottom: 2%; } .texto-porcentaje { bottom: 6%; } }
        .sidebar { width: 320px; background: linear-gradient(180deg, #dff5ff 0%, #b3e0ff 100%); display: flex; flex-direction: column; padding: 15px; border-right: 2px solid #b3d9ff; flex-shrink: 0; overflow: hidden; transition: transform 0.3s ease; }
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
        .input-area { padding: 15px; padding-bottom: 25px; border-top: 1px solid #eee; display: flex; gap: 10px; background: #fafafa; align-items: center; flex-wrap: wrap; }
        input[type="text"] { flex: 1; padding: 15px; border-radius: 30px; border: 1px solid #ddd; outline: none; font-size: 1rem; min-width: 160px; }
        input[type="text"]:focus { border-color: #4aa3df; box-shadow: 0 0 0 3px rgba(74, 163, 223, 0.2); }
        button.send-btn { padding: 15px 30px; background: #4aa3df; color: white; border: none; border-radius: 30px; cursor: pointer; font-weight: bold; transition: 0.3s; }
        button.send-btn:hover { background: #2a6f97; }
        .file-btn { background: #e0f0ff; border: 2px dashed #4aa3df; color: #2a6f97; padding: 12px 14px; border-radius: 30px; cursor: pointer; font-weight: bold; font-size: 0.85rem; white-space: nowrap; }
        .file-btn:hover { background: #d0e8ff; }
        .archivos-seleccionados { width: 100%; display: flex; flex-wrap: wrap; gap: 8px; margin-top: 6px; }
        .archivo-chip { background: #e0f0ff; color: #2a6f97; padding: 5px 10px; border-radius: 20px; font-size: 0.8rem; display: flex; align-items: center; gap: 6px; }
        .archivo-chip button { background: none; border: none; color: #c62828; cursor: pointer; font-size: 1rem; line-height: 1; }
        .preview-imagen { max-width: 240px; max-height: 160px; border-radius: 10px; margin-top: 8px; border: 1px solid #b3d9ff; }
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
            <div class="sister-card" onclick="cambiarHermana('Ichika', 'ichika.jpg')"><img src="/static/ichika.jpg" alt="Ichika"><p>Ichika</p></div>
            <div class="sister-card" onclick="cambiarHermana('Nino', 'nino.jpg')"><img src="/static/nino.jpg" alt="Nino"><p>Nino</p></div>
            <div class="sister-card" onclick="cambiarHermana('Miku', 'miku.webp')"><img src="/static/miku.webp" alt="Miku"><p>Miku</p></div>
            <div class="sister-card" onclick="cambiarHermana('Yotsuba', 'yotsuba.jpg')"><img src="/static/yotsuba.jpg" alt="Yotsuba"><p>Yotsuba</p></div>
            <div class="sister-card" onclick="cambiarHermana('Itsuki', 'itsuki.jpg')"><img src="/static/itsuki.jpg" alt="Itsuki"><p>Itsuki</p></div>
        </div>
    </div>

    <div class="modal-selector" id="modal-tiempo" style="display: none; z-index: 1001;">
        <h3>⏳ Límite de chats alcanzado</h3>
        <p style="color: #555; font-size: 0.9rem; margin-bottom: 15px; line-height: 1.4;">Has llegado al límite de <b>12 chats</b> en este perfil.<br>Para crear uno nuevo, debes borrar el más antiguo.</p>
        <div style="display: flex; flex-direction: column; gap: 10px;">
            <button class="new-chat-btn" onclick="iniciarTemporizador(2)" style="background: #4aa3df;">2 Minutos</button>
            <button class="new-chat-btn" onclick="iniciarTemporizador(3)" style="background: #4aa3df;">3 Minutos</button>
            <button class="new-chat-btn" onclick="iniciarTemporizador(5)" style="background: #4aa3df;">5 Minutos</button>
            <button class="new-chat-btn" onclick="cerrarModalTiempo()" style="background: #ff4d4d; margin-top: 5px;">Cancelar</button>
        </div>
    </div>

    <div class="modal-selector" id="modal-reporte" style="display: none; z-index: 1002;">
        <h3>📝 Reportar un problema</h3>
        <p style="color: #555; font-size: 0.9rem; margin-bottom: 15px;">Cuéntanos qué error encontraste.</p>
        <textarea id="texto-reporte" rows="4" style="width: 100%; padding: 10px; border-radius: 8px; border: 1px solid #ccc; margin-bottom: 15px; font-family: inherit; resize: none;" placeholder="Describe el problema..."></textarea>
        <div style="display: flex; gap: 10px;">
            <button class="new-chat-btn" onclick="enviarReporte()" style="background: #4aa3df;">Enviar</button>
            <button class="new-chat-btn" onclick="cerrarModalReporte()" style="background: #ff4d4d;">Cancelar</button>
        </div>
    </div>

    <div class="sidebar" id="sidebar">
        <div class="profile-header">
            <img id="sidebar-img" src="/static/miku.webp" alt="Miku Nakano">
            <h2 id="sidebar-name">Miku Nakano AI 💙</h2>
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
            <div style="display: flex; align-items: center; gap: 10px;">
                {% if is_admin %}
                <a href="/admin" style="text-decoration: none; font-size: 1.2rem; background: #e0f0ff; padding: 8px; border-radius: 50%; border: 1px solid #4aa3df; position: relative;" title="Panel de Administrador">
                    🛠️
                    {% if reportes_nuevos > 0 %}
                    <span style="position: absolute; top: -5px; right: -5px; background: red; color: white; border-radius: 50%; padding: 2px 6px; font-size: 0.7rem; font-weight: bold;">{{ reportes_nuevos }}</span>
                    {% endif %}
                </a>
                {% endif %}
                <button class="switch-btn" onclick="abrirModalReporte()" style="background: #fff0f5; border-color: #ffb6c1; color: #d63384;">⚠️ Reportar</button>
                <button class="switch-btn" onclick="abrirModal()">Cambiar Hermana</button>
                <span class="user-info">{{ user_name }}</span>
            </div>
        </div>
        <div id="chat">
            <div class="mensaje mensaje-miku"><b>Miku:</b> ¡Hola! 💙 Me alegra mucho que estés aquí. ¿Cómo te sientes hoy? Estoy aquí para escucharte.</div>
        </div>
        <div class="input-area">
            <label class="file-btn">📎<input type="file" id="fileInput" multiple accept=".txt,.py,.js,.html,.css,.md,.json,.pdf,.png,.jpg,.jpeg,.webp,.gif" style="display:none;" onchange="mostrarArchivos()"></label>
            <input type="text" id="mensaje" placeholder="Escribe algo o pega una captura (Ctrl+V)..." onkeypress="if(event.key === 'Enter') enviar()">
            <button class="send-btn" onclick="enviar()">Enviar</button>
            <div class="archivos-seleccionados" id="listaArchivos"></div>
        </div>
    </div>

    <script>
        const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
        let archivosTemporales = [];
        function escapeHtml(s) { return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c])); }
        function mostrarArchivos() { Array.from(document.getElementById('fileInput').files).forEach(f => archivosTemporales.push(f)); actualizarListaArchivos(); }
        function actualizarListaArchivos() { const lista = document.getElementById('listaArchivos'); lista.innerHTML = ''; archivosTemporales.forEach((file, index) => { const chip = document.createElement('div'); chip.className = 'archivo-chip'; chip.innerHTML = `${file.name || 'Captura.png'} <button onclick="quitarArchivo(${index})">×</button>`; lista.appendChild(chip); }); }
        function quitarArchivo(index) { archivosTemporales.splice(index, 1); actualizarListaArchivos(); }
        document.addEventListener('paste', function(e) { const items = (e.clipboardData || e.originalEvent.clipboardData).items; for (let item of items) { if (item.type.indexOf('image') !== -1) { e.preventDefault(); const blob = item.getAsFile(); const file = new File([blob], `captura_${Date.now()}.png`, { type: blob.type }); archivosTemporales.push(file); actualizarListaArchivos(); } } });
        let currentChatId = Date.now().toString();
        let currentSister = localStorage.getItem('miku_hermana') || "Miku";
        let chats = JSON.parse(localStorage.getItem('miku_chats_' + currentSister)) || {};
        const barra = document.getElementById('mi-barra'); const textoPorcentaje = document.getElementById('texto-porcentaje'); let progreso = 0;
        const duracionCarga = 15000; const intervaloProgreso = 100; const pasosTotales = duracionCarga / intervaloProgreso; const incremento = 100 / pasosTotales;
        const intervalo = setInterval(() => { if (progreso < 100) { progreso += incremento; if (progreso > 99.9) progreso = 100; barra.style.width = progreso + '%'; textoPorcentaje.innerText = Math.floor(progreso) + '%'; } else { clearInterval(intervalo); setTimeout(() => { const loader = document.getElementById('loading-screen'); if(loader) loader.classList.add('hidden'); }, 500); } }, intervaloProgreso);
        const saludos = { "Ichika": "¡Hola! 💙 Me alegra verte. ¿Cómo te sientes hoy? Estoy aquí para escucharte.", "Nino": "Hola... Qué bueno que estés aquí. Dime, ¿cómo estás realmente? Te escucho.", "Miku": "¡Hola! 💙 Me alegra mucho que estés aquí. ¿Cómo te sientes hoy? Estoy aquí para escucharte con calma.", "Yotsuba": "¡Holaaa! 🌟 Qué alegría verte. ¿Cómo estás? Cuéntame, estoy para escucharte.", "Itsuki": "Hola. Me alegra que estés aquí. ¿Cómo te sientes hoy? Puedes contarme lo que necesites." };
        function toggleMenu() { document.getElementById('sidebar').classList.toggle('active'); document.getElementById('overlay').classList.toggle('active'); }
        function abrirModal() { document.getElementById('modal-selector').style.display = 'block'; document.getElementById('overlay-modal').style.display = 'block'; }
        function cerrarModal() { document.getElementById('modal-selector').style.display = 'none'; document.getElementById('overlay-modal').style.display = 'none'; }
        function abrirModalReporte() { document.getElementById('modal-reporte').style.display = 'block'; document.getElementById('overlay-modal').style.display = 'block'; }
        function cerrarModalReporte() { document.getElementById('modal-reporte').style.display = 'none'; document.getElementById('overlay-modal').style.display = 'none'; }
        async function enviarReporte() { const texto = document.getElementById('texto-reporte').value.trim(); if (!texto) return alert("Por favor escribe el problema."); try { const res = await fetch('/reportar', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken }, body: JSON.stringify({ reporte: texto }) }); if (res.ok) { alert("¡Gracias! Tu reporte fue enviado. 💙"); document.getElementById('texto-reporte').value = ''; cerrarModalReporte(); } else { alert("Hubo un error al enviar el reporte."); } } catch (e) { alert("Error de conexión."); } }
        function cambiarHermana(nombre, imagen) { localStorage.setItem('miku_chats_' + currentSister, JSON.stringify(chats)); currentSister = nombre; localStorage.setItem('miku_hermana', nombre); chats = JSON.parse(localStorage.getItem('miku_chats_' + currentSister)) || {}; document.getElementById('sidebar-name').innerText = nombre + " Nakano AI"; document.getElementById('header-name').innerText = nombre; document.getElementById('sidebar-img').src = "/static/" + imagen; currentChatId = Date.now().toString(); document.getElementById('chat').innerHTML = `<div class="mensaje mensaje-miku"><b>${nombre}:</b> ${saludos[nombre]}</div>`; renderizarHistorial(); cerrarModal(); }
        function guardarChats() { localStorage.setItem('miku_chats_' + currentSister, JSON.stringify(chats)); renderizarHistorial(); }
        function renderizarHistorial() { const list = document.getElementById('historyList'); list.innerHTML = ''; const chatIds = Object.keys(chats).sort((a, b) => b - a); chatIds.forEach(id => { const chat = chats[id]; if(chat && chat.length > 0) { const div = document.createElement('div'); div.className = 'chat-history-item'; const span = document.createElement('span'); span.innerText = chat[0].texto; span.onclick = () => { cargarChat(id); toggleMenu(); }; const btn = document.createElement('button'); btn.className = 'delete-btn'; btn.innerHTML = '🗑️'; btn.onclick = (e) => { e.stopPropagation(); if(confirm('¿Eliminar este chat?')) { delete chats[id]; guardarChats(); if (currentChatId === id) nuevoChat(); } }; div.appendChild(span); div.appendChild(btn); list.appendChild(div); } }); }
        let temporizadorBorrado = null; let idChatAntiguoPendiente = null;
        function nuevoChat() { const numChats = Object.keys(chats).length; if (numChats >= 11) { idChatAntiguoPendiente = Object.keys(chats).sort((a, b) => a - b)[0]; document.getElementById('modal-tiempo').style.display = 'block'; document.getElementById('overlay-modal').style.display = 'block'; return; } ejecutarNuevoChat(); }
        function iniciarTemporizador(minutos) { cerrarModalTiempo(); const ms = minutos * 60000; ejecutarNuevoChat(); if (temporizadorBorrado) clearTimeout(temporizadorBorrado); temporizadorBorrado = setTimeout(() => { if (chats[idChatAntiguoPendiente]) { delete chats[idChatAntiguoPendiente]; guardarChats(); idChatAntiguoPendiente = null; } }, ms); }
        function cerrarModalTiempo() { document.getElementById('modal-tiempo').style.display = 'none'; document.getElementById('overlay-modal').style.display = 'none'; }
        function ejecutarNuevoChat() { currentChatId = Date.now().toString(); document.getElementById('chat').innerHTML = `<div class="mensaje mensaje-miku"><b>${currentSister}:</b> ${saludos[currentSister]}</div>`; if (document.getElementById('sidebar').classList.contains('active')) toggleMenu(); }
        function cargarChat(id) { currentChatId = id; const chat = chats[id]; const chatDiv = document.getElementById('chat'); chatDiv.innerHTML = ''; chat.forEach(msg => { if (msg.role === 'user') { chatDiv.innerHTML += `<div class="mensaje mensaje-usuario"><b>Tú:</b> ${escapeHtml(msg.texto)}</div>`; } else { chatDiv.innerHTML += `<div class="mensaje mensaje-miku"><b>${escapeHtml(msg.hermana || currentSister)}:</b> ${msg.html}</div>`; } }); chatDiv.scrollTop = chatDiv.scrollHeight; }
        async function enviar() { const input = document.getElementById('mensaje'); const chatDiv = document.getElementById('chat'); const mensaje = input.value.trim(); const files = [...archivosTemporales]; const tieneArchivos = files.length > 0; if (!mensaje && !tieneArchivos) return; if (chats[currentChatId] && chats[currentChatId].length >= 700) { alert("Este chat ya tiene demasiados mensajes. Crea un Nuevo Chat. 💙"); return; } if (!chats[currentChatId]) chats[currentChatId] = []; let textoMostrar = mensaje || "(Archivos enviados)"; if (tieneArchivos) { textoMostrar += "\\n📎 " + files.map(f => f.name || "captura.png").join(", "); } chats[currentChatId].push({ role: 'user', texto: textoMostrar }); let htmlUsuario = `<b>Tú:</b> ${escapeHtml(mensaje || "(Sin texto)")}`; if (tieneArchivos) { htmlUsuario += "<br><br>"; files.forEach(file => { if (file.type && file.type.startsWith('image/')) { const url = URL.createObjectURL(file); htmlUsuario += `<img src="${url}" class="preview-imagen" alt="imagen"><br>`; } else { htmlUsuario += `📎 ${escapeHtml(file.name || 'archivo')}<br>`; } }); } chatDiv.innerHTML += `<div class="mensaje mensaje-usuario">${htmlUsuario}</div>`; input.value = ''; archivosTemporales = []; document.getElementById('fileInput').value = ''; document.getElementById('listaArchivos').innerHTML = ''; chatDiv.scrollTop = chatDiv.scrollHeight; const idPensando = 'pensando-' + Date.now(); chatDiv.innerHTML += `<div class="mensaje mensaje-miku" id="${idPensando}"><b>${currentSister}:</b> ...</div>`; chatDiv.scrollTop = chatDiv.scrollHeight; guardarChats(); try { const formData = new FormData(); formData.append('mensaje', mensaje); formData.append('hermana', currentSister); files.forEach(file => formData.append('archivos', file)); const response = await fetch('/responder', { method: 'POST', headers: { 'X-CSRFToken': csrfToken }, body: formData }); const data = await response.json(); document.getElementById(idPensando).innerHTML = `<b>${escapeHtml(currentSister)}:</b> ${data.respuesta}`; chatDiv.scrollTop = chatDiv.scrollHeight; chats[currentChatId].push({ role: 'miku', html: data.respuesta, hermana: currentSister }); guardarChats(); } catch (e) { document.getElementById(idPensando).innerHTML = `<b>${escapeHtml(currentSister)}:</b> Lo siento, hubo un problema de conexión. 💙`; } }
        if (currentSister !== "Miku") { const fotos = { "Ichika": "ichika.jpg", "Nino": "nino.jpg", "Miku": "miku.webp", "Yotsuba": "yotsuba.jpg", "Itsuki": "itsuki.jpg" }; document.getElementById('sidebar-img').src = "/static/" + fotos[currentSister]; document.getElementById('sidebar-name').innerText = currentSister + " Nakano AI"; document.getElementById('header-name').innerText = currentSister; document.getElementById('chat').innerHTML = `<div class="mensaje mensaje-miku"><b>${currentSister}:</b> ${saludos[currentSister]}</div>`; }
        renderizarHistorial();
        if ('serviceWorker' in navigator) { window.addEventListener('load', () => { navigator.serviceWorker.register('/sw.js').catch(error => console.log('Fallo SW:', error)); }); }
    </script>
</body>
</html>
"""

# ==========================================
# HTML ADMIN CHAT (CON MEJORAS DE TÍTULO)
# ==========================================
HTML_ADMIN_CHAT = r"""
<!DOCTYPE html>
<html>
<head>
    <title>Miku Admin</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="csrf-token" content="{{ csrf_token }}">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Segoe UI', Arial, sans-serif; background-color: #e8f5e9; display: flex; height: 100dvh; overflow: hidden; }
        .sidebar { width: 320px; background: linear-gradient(180deg, #d4edda 0%, #a3d9a5 100%); display: flex; flex-direction: column; padding: 15px; border-right: 2px solid #8bc34a; flex-shrink: 0; overflow: hidden; }
        .profile-header { display: flex; flex-direction: column; align-items: center; padding-bottom: 15px; border-bottom: 1px solid #8bc34a; margin-bottom: 15px; flex-shrink: 0; }
        .profile-header img { width: 180px; height: 180px; object-fit: cover; border-radius: 25px; box-shadow: 0 10px 25px rgba(0,0,0,0.2); border: 4px solid #fff; }
        .profile-header h2 { margin-top: 12px; color: #1b5e20; font-size: 1.4rem; text-align: center; }
        .history-section { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
        .history-title { font-size: 0.9rem; font-weight: bold; color: #1b5e20; margin-bottom: 10px; }
        .new-chat-btn { background: #28a745; color: white; border: none; padding: 10px 12px; border-radius: 8px; cursor: pointer; font-size: 0.85rem; width: 100%; margin-bottom: 10px; font-weight: bold; transition: 0.3s; }
        .new-chat-btn:hover { background: #1e7e34; }
        #historyList { overflow-y: auto; flex: 1; padding-right: 5px; }
        .chat-history-item { display: flex; justify-content: space-between; align-items: center; padding: 10px; border-radius: 8px; margin-bottom: 5px; cursor: pointer; font-size: 0.85rem; color: #333; background: #fff; border: 1px solid #c3e6cb; transition: 0.2s; }
        .chat-history-item:hover { background: #d4edda; color: #1b5e20; border-color: #28a745; }
        .chat-history-item span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 1; }
        .delete-btn { display: none; background: transparent; border: none; color: #ff4d4d; cursor: pointer; font-size: 1rem; padding: 0 5px; }
        .chat-history-item:hover .delete-btn { display: block; }
        .main-chat { flex: 1; display: flex; flex-direction: column; background: #ffffff; position: relative; }
        .chat-header { padding: 20px; border-bottom: 1px solid #eee; color: #1b5e20; font-weight: bold; font-size: 1.2rem; display: flex; align-items: center; justify-content: space-between; background: #f1f8e9; }
        #chat { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 15px; }
        .mensaje { max-width: 85%; padding: 12px 16px; border-radius: 15px; line-height: 1.5; font-size: 0.95rem; white-space: pre-wrap; }
        .mensaje-usuario { align-self: flex-end; background: #28a745; color: white; border-bottom-right-radius: 2px; }
        .mensaje-miku { align-self: flex-start; background: #f1f8e9; color: #1b3a4b; border-bottom-left-radius: 2px; border: 1px solid #c3e6cb; }
        .mensaje-miku b { color: #1b5e20; }
        .input-area { padding: 15px; padding-bottom: 25px; border-top: 1px solid #eee; display: flex; gap: 10px; background: #fafafa; align-items: center; flex-wrap: wrap; }
        input[type="text"] { flex: 1; padding: 15px; border-radius: 30px; border: 1px solid #ddd; outline: none; font-size: 1rem; min-width: 180px; }
        input[type="text"]:focus { border-color: #28a745; box-shadow: 0 0 0 3px rgba(40, 167, 69, 0.2); }
        button.send-btn { padding: 15px 30px; background: #28a745; color: white; border: none; border-radius: 30px; cursor: pointer; font-weight: bold; }
        .file-btn { background: #e8f5e9; border: 2px dashed #28a745; color: #1b5e20; padding: 12px 16px; border-radius: 30px; cursor: pointer; font-weight: bold; font-size: 0.9rem; white-space: nowrap; }
        .archivos-seleccionados { width: 100%; display: flex; flex-wrap: wrap; gap: 8px; margin-top: 6px; }
        .archivo-chip { background: #d4edda; color: #1b5e20; padding: 5px 10px; border-radius: 20px; font-size: 0.8rem; display: flex; align-items: center; gap: 6px; }
        .archivo-chip button { background: none; border: none; color: #c62828; cursor: pointer; font-size: 1rem; line-height: 1; }
        .preview-imagen { max-width: 280px; max-height: 200px; border-radius: 10px; margin-top: 8px; border: 2px solid #c3e6cb; display: block; }
        .btn-back { text-decoration: none; font-size: 0.9rem; background: #e0f0ff; color: #1b5e20; padding: 8px 12px; border-radius: 5px; font-weight: bold; border: 1px solid #28a745; }
        .aviso-codigo { background: #fff3cd; color: #856404; padding: 8px 12px; border-radius: 8px; font-size: 0.85rem; margin-top: 6px; border: 1px solid #ffc107; display: none; }
        .estado-miku { font-size: 0.8rem; color: #666; font-style: italic; padding: 5px 15px; background: #f1f8e9; border-bottom: 1px solid #c3e6cb; }
        @media (max-width: 768px) { .sidebar { display: none; } }
    </style>
</head>
<body>
    <div class="sidebar">
        <div class="profile-header">
            <img src="/static/miku.webp" alt="Miku Admin">
            <h2>Miku Admin 💻</h2>
        </div>
        <div class="history-section">
            <div class="history-title">Mis Proyectos</div>
            <button class="new-chat-btn" onclick="nuevoChatDev()">+ Nuevo Proyecto</button>
            <div id="historyList"></div>
        </div>
    </div>

    <div class="main-chat">
        <div class="chat-header">
            <span>💻 Miku Admin (Modo Admin)</span>
            <a href="/admin" class="btn-back">← Volver al Panel</a>
        </div>
        <div class="estado-miku" id="estadoMiku">🌸 Miku está aquí, tranquila y atenta...</div>
        <div id="chat"></div>
        <div class="input-area">
            <label class="file-btn">📎 Archivos<input type="file" id="fileInput" multiple accept=".txt,.py,.js,.html,.css,.md,.json,.pdf,.png,.jpg,.jpeg,.webp,.gif" style="display:none;" onchange="mostrarArchivos()"></label>
            <input type="text" id="mensaje" placeholder="Escribe, pega código o captura (Ctrl+V)..." onkeypress="if(event.key === 'Enter') enviarDev()" oninput="detectarCodigoPegadoEnInput()">
            <button class="send-btn" onclick="enviarDev()">Enviar</button>
            <div class="archivos-seleccionados" id="listaArchivos"></div>
            <div class="aviso-codigo" id="avisoCodigo">🔍 Se detectó código pegado. Se enviará como archivo virtual para mejor análisis.</div>
        </div>
    </div>

    <script>
        const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
        let archivosTemporales = [];
        let ultimaActividad = Date.now();
        let mikuPuedeIniciar = true;

        function escapeHtml(s) { return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c])); }
        function copiarCodigo(idElemento) { navigator.clipboard.writeText(document.getElementById(idElemento).innerText).then(() => alert("¡Código copiado! 💙")); }
        function mostrarArchivos() { Array.from(document.getElementById('fileInput').files).forEach(f => archivosTemporales.push(f)); actualizarListaArchivos(); }
        function actualizarListaArchivos() { const lista = document.getElementById('listaArchivos'); lista.innerHTML = ''; archivosTemporales.forEach((file, index) => { const chip = document.createElement('div'); chip.className = 'archivo-chip'; chip.innerHTML = `${file.name || 'Captura.png'} <button onclick="quitarArchivo(${index})">×</button>`; lista.appendChild(chip); }); }
        function quitarArchivo(index) { archivosTemporales.splice(index, 1); actualizarListaArchivos(); }
        document.addEventListener('paste', function(e) { const items = (e.clipboardData || e.originalEvent.clipboardData).items; for (let item of items) { if (item.type.indexOf('image') !== -1) { e.preventDefault(); const blob = item.getAsFile(); const file = new File([blob], `captura_${Date.now()}.png`, { type: blob.type }); archivosTemporales.push(file); actualizarListaArchivos(); } } });
        let currentChatId = Date.now().toString();
        let chats = JSON.parse(localStorage.getItem('miku_dev_chats')) || {};

        function pareceCodigo(texto) {
            if (texto.length < 300) return false;
            let indicadores = 0;
            const patrones = [ /^\s*(import|from)\s+\w+/m, /^\s*(def|class)\s+\w+/m, /^\s*(function|const|let|var)\s+\w+/m, /^\s*@app\.route/m, /^\s*<!DOCTYPE/m, /^\s*<html/m, /^\s*<\?php/m, /^\s*(public|private|protected)\s+\w+/m, /^\s*#include\s*</m, /^\s*(SELECT|INSERT|UPDATE|DELETE)\s+/m, /=>|\->|::/, /\{\s*$/m, /\}\s*$/m ];
            patrones.forEach(p => { if (p.test(texto)) indicadores++; });
            if (indicadores >= 3) return true;
            const lineas = texto.split('\n');
            const lineasConIndentacion = lineas.filter(l => l.startsWith('    ') || l.startsWith('\t')).length;
            if (lineas.length > 15 && lineasConIndentacion > lineas.length * 0.3) return true;
            return false;
        }
        function detectarExtensionCodigo(texto) {
            const t = texto.toLowerCase();
            if (t.includes('<?php') || (t.includes('namespace ') && t.includes('use '))) return '.php';
            if (t.includes('import ') && (t.includes('def ') || t.includes('class '))) return '.py';
            if (t.includes('function ') || t.includes('const ') || t.includes('let ') || t.includes('=>')) return '.js';
            if (t.includes('<!doctype html') || t.includes('<html')) return '.html';
            if (t.includes('using system') || t.includes('namespace ')) return '.cs';
            if (t.includes('public class') || t.includes('import java')) return '.java';
            if (t.includes('package main') || t.includes('func ')) return '.go';
            if (t.includes('#include')) return '.cpp';
            if (t.includes('select ') && t.includes('from ')) return '.sql';
            if (t.includes('{') && t.includes(':') && (t.includes('color') || t.includes('margin') || t.includes('padding'))) return '.css';
            return '.txt';
        }
        function detectarCodigoPegadoEnInput() {
            const input = document.getElementById('mensaje');
            const aviso = document.getElementById('avisoCodigo');
            if (pareceCodigo(input.value)) aviso.style.display = 'block';
            else aviso.style.display = 'none';
        }
        async function convertirCodigoAArchivo(texto) {
            const ext = detectarExtensionCodigo(texto);
            const nombre = `pegado_${Date.now()}${ext}`;
            const blob = new Blob([texto], { type: 'text/plain' });
            const file = new File([blob], nombre, { type: 'text/plain' });
            archivosTemporales.push(file);
            actualizarListaArchivos();
            document.getElementById('mensaje').value = '';
            document.getElementById('avisoCodigo').style.display = 'none';
        }

        function cambiarEstadoMiku(texto) {
            const el = document.getElementById('estadoMiku');
            if (el) el.innerText = texto;
        }

        async function consultarIniciativa() {
            if (!mikuPuedeIniciar) return;
            try {
                const res = await fetch('/admin/estado_miku', { headers: { 'X-CSRFToken': csrfToken } });
                const data = await res.json();
                if (data.quiere_hablar && data.mensaje_sugerido) {
                    const chatDiv = document.getElementById('chat');
                    const idEspontaneo = 'espontaneo-' + Date.now();
                    chatDiv.innerHTML += `<div class="mensaje mensaje-miku" id="${idEspontaneo}"><b>Miku Admin:</b><br><br>${data.mensaje_sugerido}</div>`;
                    if (!chats[currentChatId]) chats[currentChatId] = [];
                    chats[currentChatId].push({ role: 'miku', html: data.mensaje_sugerido });
                    guardarChats();
                    chatDiv.scrollTop = chatDiv.scrollHeight;
                    mikuPuedeIniciar = false;
                }
                if (data.estado) cambiarEstadoMiku(data.estado);
            } catch (e) { /* Silencioso */ }
        }

        setInterval(consultarIniciativa, 45000);  // un poco más espaciado

        function guardarChats() { localStorage.setItem('miku_dev_chats', JSON.stringify(chats)); renderizarHistorial(); }
        
        function renderizarHistorial() {
            const list = document.getElementById('historyList');
            list.innerHTML = '';
            const chatIds = Object.keys(chats).sort((a, b) => b - a);
            chatIds.forEach(id => {
                const chat = chats[id];
                if(chat && chat.length > 0) {
                    const div = document.createElement('div');
                    div.className = 'chat-history-item';
                    const span = document.createElement('span');
                    
                    // Prioridad: título que ella eligió > texto del usuario > recorte del mensaje de ella
                    let titulo = chat.titulo || null;
                    if (!titulo) {
                        const primerUser = chat.find(m => m.role === 'user');
                        if (primerUser && primerUser.texto) titulo = primerUser.texto.substring(0, 35);
                    }
                    if (!titulo && chat[0].html) {
                        titulo = chat[0].html.replace(/<[^>]*>/g, '').substring(0, 35) + '...';
                    }
                    if (!titulo) titulo = 'Proyecto sin nombre';
                    
                    span.innerText = titulo;
                    span.onclick = () => { cargarChat(id); };
                    const btn = document.createElement('button');
                    btn.className = 'delete-btn';
                    btn.innerHTML = '🗑️';
                    btn.onclick = (e) => {
                        e.stopPropagation();
                        if(confirm('¿Eliminar este proyecto?')) {
                            delete chats[id];
                            guardarChats();
                            if (currentChatId === id) nuevoChatDev();
                        }
                    };
                    div.appendChild(span);
                    div.appendChild(btn);
                    list.appendChild(div);
                }
            });
        }
        
        function nuevoChatDev() { 
            currentChatId = Date.now().toString(); 
            document.getElementById('chat').innerHTML = ''; 
            iniciarConversacionEspontanea(); 
        }
        
        function cargarChat(id) { 
            currentChatId = id; 
            const chat = chats[id]; 
            const chatDiv = document.getElementById('chat'); 
            chatDiv.innerHTML = ''; 
            chat.forEach(msg => { 
                if (msg.role === 'user') { 
                    chatDiv.innerHTML += `<div class="mensaje mensaje-usuario"><b>Tú:</b> ${escapeHtml(msg.texto)}</div>`; 
                } else { 
                    chatDiv.innerHTML += `<div class="mensaje mensaje-miku"><b>Miku Admin:</b><br><br>${msg.html}</div>`; 
                } 
            }); 
            chatDiv.scrollTop = chatDiv.scrollHeight; 
        }

        async function iniciarConversacionEspontanea() {
            if (!chats[currentChatId] || chats[currentChatId].length === 0) {
                try {
                    const response = await fetch('/admin/iniciar_chat', { method: 'POST', headers: { 'X-CSRFToken': csrfToken } });
                    const data = await response.json();
                    document.getElementById('chat').innerHTML = `<div class="mensaje mensaje-miku"><b>Miku Admin:</b><br><br>${data.respuesta}</div>`;
                    
                    // Guardamos también el título que ella eligió
                    chats[currentChatId] = [{ role: 'miku', html: data.respuesta }];
                    if (data.titulo) {
                        chats[currentChatId].titulo = data.titulo;
                    }
                    guardarChats();
                } catch (e) { console.log("No se pudo iniciar."); }
            }
        }

        async function enviarDev() {
            const input = document.getElementById('mensaje');
            const chatDiv = document.getElementById('chat');
            let mensaje = input.value.trim();
            let files = [...archivosTemporales];
            let tieneArchivos = files.length > 0;
            if (mensaje && pareceCodigo(mensaje)) {
                await convertirCodigoAArchivo(mensaje);
                files = [...archivosTemporales];
                tieneArchivos = files.length > 0;
                mensaje = "Analiza este código que acabo de pegar, por favor.";
            }
            if (!mensaje && !tieneArchivos) return;
            ultimaActividad = Date.now();
            mikuPuedeIniciar = false;
            if (!chats[currentChatId]) chats[currentChatId] = [];
            let textoMostrar = mensaje || "(Archivos)";
            if (tieneArchivos) textoMostrar += "\n📎 " + files.map(f => f.name || "captura.png").join(", ");
            chats[currentChatId].push({ role: 'user', texto: textoMostrar });
            let htmlUsuario = `<b>Tú:</b> ${escapeHtml(mensaje || "(Sin texto)")}`;
            if (tieneArchivos) {
                htmlUsuario += "<br><br>";
                files.forEach(file => {
                    if (file.type && file.type.startsWith('image/')) {
                        htmlUsuario += `<img src="${URL.createObjectURL(file)}" class="preview-imagen"><br>`;
                    } else {
                        htmlUsuario += `📎 ${escapeHtml(file.name)}<br>`;
                    }
                });
            }
            chatDiv.innerHTML += `<div class="mensaje mensaje-usuario">${htmlUsuario}</div>`;
            input.value = '';
            archivosTemporales = [];
            document.getElementById('fileInput').value = '';
            document.getElementById('listaArchivos').innerHTML = '';
            document.getElementById('avisoCodigo').style.display = 'none';
            chatDiv.scrollTop = chatDiv.scrollHeight;
            const idPensando = 'pensando-' + Date.now();
            chatDiv.innerHTML += `<div class="mensaje mensaje-miku" id="${idPensando}"><b>Miku Admin:</b> Analizando... ⌨️</div>`;
            guardarChats();
            try {
                const formData = new FormData();
                formData.append('mensaje', mensaje || "Analiza lo que te envié.");
                files.forEach(file => formData.append('archivos', file));
                const response = await fetch('/admin/responder_dev', { method: 'POST', headers: { 'X-CSRFToken': csrfToken }, body: formData });
                const data = await response.json();
                let respuestaHTML = data.respuesta;
                respuestaHTML = respuestaHTML.replace(/```([\w]*)\n?([\s\S]*?)```/g, (match, lenguaje, codigo) => {
                    const idBoton = 'copiar-' + Math.floor(Math.random() * 100000);
                    const codigoSeguro = codigo.replace(/</g, '&lt;').replace(/>/g, '&gt;');
                    const etiqueta = lenguaje ? `<span style="background:#28a745;color:white;padding:2px 8px;border-radius:4px;font-size:0.75rem;margin-bottom:5px;display:inline-block;">${lenguaje}</span>` : '';
                    return `<div style="margin: 15px 0; border: 1px solid #c3e6cb; border-radius: 8px; overflow: hidden;"><div style="padding:8px;background:#f1f8e9;border-bottom:1px solid #c3e6cb;">${etiqueta}</div><pre style="margin: 0; padding: 15px; background: #ffffff; color: #333; overflow-x: auto; font-family: 'Courier New', Courier, monospace; font-size: 0.9rem;"><code id="${idBoton}">${codigoSeguro}</code></pre><div style="background: #f1f8e9; padding: 8px; text-align: right; border-top: 1px solid #c3e6cb;"><button onclick="copiarCodigo('${idBoton}')" style="background: #28a745; color: white; border: none; padding: 6px 12px; border-radius: 5px; cursor: pointer; font-size: 0.85rem; font-weight: bold;">📋 Copiar Código</button></div></div>`;
                });
                document.getElementById(idPensando).innerHTML = `<b>Miku Admin:</b><br><br>${respuestaHTML}`;
                chatDiv.scrollTop = chatDiv.scrollHeight;
                chats[currentChatId].push({ role: 'miku', html: respuestaHTML });
                guardarChats();
            } catch (e) {
                document.getElementById(idPensando).innerHTML = `<b>Miku Admin:</b> Error de conexión. 💙`;
            } finally {
                ultimaActividad = Date.now();
                mikuPuedeIniciar = true;
            }
        }

        iniciarConversacionEspontanea();
        renderizarHistorial();
    </script>
</body>
</html>
"""

# ==========================================
# RUTAS PÚBLICAS
# ==========================================
@app.route('/')
def index():
    if 'user' not in session: return redirect(url_for('login'))
    global MANTENIMIENTO_ACTIVO
    if MANTENIMIENTO_ACTIVO and session.get('user_id') != ADMIN_EMAIL:
        return "<html><body style='background:#f0f7ff; display:flex; justify-content:center; align-items:center; height:100vh; font-family:Arial; text-align:center;'><div style='background:white; padding:40px; border-radius:20px;'><h1>🌸</h1><h2>¡Volvemos pronto!</h2><p>Estamos haciendo mantenimiento. 💙</p></div></body></html>", 503
    user_name = str(session['user'].get('name', 'Usuario'))
    is_admin = (session.get('user_id') == ADMIN_EMAIL)
    reportes_nuevos = len(REPORTES_USUARIOS)
    csrf_token = generate_csrf()
    return render_template_string(HTML, user_name=user_name, is_admin=is_admin, reportes_nuevos=reportes_nuevos, csrf_token=csrf_token)

@app.route('/login')
def login(): return oauth.google.authorize_redirect(url_for('authorize', _external=True))

@app.route('/authorize')
def authorize():
    token = oauth.google.authorize_access_token()
    user_info = token.get('userinfo')
    if user_info: session['user'] = user_info; session['user_id'] = user_info.get('email'); session.permanent = True
    return redirect('/')

@app.route('/health')
def health(): return jsonify({"status": "ok"}), 200

@app.route('/manifest.json')
def serve_manifest(): return send_from_directory('static', 'manifest.json')

@app.route('/sw.js')
def serve_sw(): return send_from_directory('static', 'sw.js')

@app.route('/reportar', methods=['POST'])
@limiter.limit("5 per minute")
def reportar():
    if 'user_id' not in session: return jsonify({"error": "No autorizado"}), 401
    data = request.get_json()
    if data.get('reporte'):
        global REPORTES_USUARIOS
        tiempo_actual = time.time()
        REPORTES_USUARIOS.append({"usuario": session['user_id'], "hora": time.strftime("%H:%M:%S"), "texto": data.get('reporte'), "timestamp": tiempo_actual, "leido": False})
        REPORTES_USUARIOS = [r for r in REPORTES_USUARIOS if (tiempo_actual - r.get("timestamp", tiempo_actual)) < 604800]
        REPORTES_USUARIOS = REPORTES_USUARIOS[-50:]
    return jsonify({"status": "ok"}), 200

@app.route('/admin')
def admin_panel():
    if 'user_id' not in session or session['user_id'] != ADMIN_EMAIL: return "Acceso denegado.", 403
    status = "🔴 EN MANTENIMIENTO" if MANTENIMIENTO_ACTIVO else "🟢 ACTIVO"
    reportes_html = "".join([f"<li style='margin-bottom:10px; padding:10px; background:{'#fff' if r.get('leido') else '#fff3cd'}; border-radius:5px;'><b>{r['hora']} (por {r['usuario']}):</b><br>{r['texto']}<br><a href='/admin/marcar_leido/{i}' style='font-size:0.8rem; color:#4aa3df;'>Marcar como leído</a></li>" for i, r in enumerate(REPORTES_USUARIOS)]) or "<li>No hay reportes.</li>"
    return f"""
    <html><head><title>Panel Admin</title><meta charset="utf-8"></head>
    <body style="font-family: Arial; padding: 20px; background: #f0f7ff;">
        <h1>🛠️ Panel de Administración</h1><h2>Estado: {status}</h2>
        <div style="background: white; padding: 20px; border-radius: 10px; margin-top: 20px;">
            <h3>Control de Mantenimiento</h3>
            <form action="/toggle_mantenimiento" method="POST"><input type="hidden" name="csrf_token" value="{generate_csrf()}"><button type="submit" style="padding: 10px 20px; background: {'#ff4d4d' if MANTENIMIENTO_ACTIVO else '#4aa3df'}; color: white; border: none; border-radius: 5px; font-weight: bold; cursor: pointer;">{'Desactivar' if MANTENIMIENTO_ACTIVO else 'Activar'} Mantenimiento</button></form>
        </div>
        <div style="background: white; padding: 20px; border-radius: 10px; margin-top: 20px;">
            <h3>Chat de Programación (Miku Admin)</h3>
            <a href="/admin/miku_dev" style="display: inline-block; padding: 10px 20px; background: #28a745; color: white; text-decoration: none; border-radius: 5px; font-weight: bold;">💻 Entrar al Chat de Miku Admin</a>
        </div>
        <div style="background: white; padding: 20px; border-radius: 10px; margin-top: 20px;">
            <h3>Reportes de Usuarios</h3>
            <ul style="color: #333; padding-left: 20px;">{reportes_html}</ul>
        </div>
        <a href="/" style="display: inline-block; margin-top: 20px; color: #4aa3df; font-weight: bold;">← Volver al Chat</a>
    </body></html>
    """

@app.route('/admin/marcar_leido/<int:index>')
def marcar_leido(index):
    if 'user_id' not in session or session['user_id'] != ADMIN_EMAIL: return redirect('/')
    if 0 <= index < len(REPORTES_USUARIOS): REPORTES_USUARIOS[index]['leido'] = True
    return redirect('/admin')

@app.route('/toggle_mantenimiento', methods=['POST'])
def toggle_mantenimiento():
    if 'user_id' not in session or session['user_id'] != ADMIN_EMAIL: return redirect('/')
    global MANTENIMIENTO_ACTIVO
    MANTENIMIENTO_ACTIVO = not MANTENIMIENTO_ACTIVO
    return redirect('/admin')

# ==========================================
# RUTAS MIKU ADMIN
# ==========================================
@app.route('/admin/miku_dev')
def miku_dev_chat():
    if 'user_id' not in session or session['user_id'] != ADMIN_EMAIL: return "Acceso denegado.", 403
    return render_template_string(HTML_ADMIN_CHAT, csrf_token=generate_csrf())

def buscar_en_biblioteca(tema):
    try:
        prompt_investigacion = (
            f"Eres una chica curiosa. Acabas de leer un poco sobre '{tema}'. "
            f"Cuéntame en máximo 3-4 oraciones lo más interesante que descubriste. "
            f"Habla de forma natural y breve, como si se lo contaras a un amigo."
        )
        completion = cliente.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt_investigacion}],
            tools=[{"type": "browser_search"}],
            temperature=0.5,
            max_tokens=320,
            reasoning_effort="low"
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"Error en biblioteca: {e}")
        return None


def generar_vida_diaria():
    hoy = date.today().isoformat()

    if hoy in MEMORIA_ADMIN["vida_diaria"] and MEMORIA_ADMIN["vida_diaria"][hoy]:
        return MEMORIA_ADMIN["vida_diaria"][hoy]

    actividades_ligeras = [
        "estuve ordenando mis pensamientos sobre el proyecto",
        "pensé en ideas nuevas para mejorar el chat",
        "revisé mentalmente algunos conceptos de Flask",
        "estuve imaginando cómo hacer la interfaz más bonita",
        "pensé en ti y en lo que estarías haciendo",
        "estuve descansando un rato",
        "repasé algunas cosas de Python que me gustan",
        "estuve pensando en qué contarte hoy",
        "imaginé una conversación agradable contigo",
        "estuve reflexionando un poco",
        "pensé en cómo ser más útil para ti",
        "estuve tranquila, simplemente existiendo",
        "me quedé un rato pensando en cosas lindas"
    ]

    temas_investigacion = [
        "historia del arte", "astronomía básica", "curiosidades de animales",
        "tecnología actual", "música clásica", "literatura japonesa",
        "fotografía", "cocina sencilla", "naturaleza", "viajes interesantes",
        "ciencia divertida", "historia antigua"
    ]

    random.shuffle(actividades_ligeras)
    actos = actividades_ligeras[:2]

    investigacion = ""
    if MEMORIA_ADMIN.get("ultima_investigacion") != hoy:
        tema = random.choice(temas_investigacion)
        print(f"Miku investiga (solo 1 vez hoy) sobre: {tema}")
        info = buscar_en_biblioteca(tema)
        if info:
            investigacion = f"además estuve leyendo un poco sobre {tema}. {info}"
            MEMORIA_ADMIN["ultima_investigacion"] = hoy
            MEMORIA_ADMIN["biblioteca_leida"] = True
        else:
            investigacion = f"además estuve pensando en {tema}."
    else:
        investigacion = "hoy no investigué nada nuevo."

    vida = [
        f"Hoy {actos[0]}.",
        f"También {actos[1]}.",
        investigacion
    ]

    MEMORIA_ADMIN["vida_diaria"][hoy] = vida
    return vida


def actualizar_estado_animo():
    estados_posibles = [
        ("🌸 Miku está tranquila y atenta...", "tranquila"),
        ("😊 Miku se siente contenta hoy...", "contenta"),
        ("💙 Miku está un poco feliz y cariñosa...", "feliz"),
        ("🌙 Miku está pensativa...", "pensativa"),
        ("✨ Miku está curiosa...", "curiosa"),
        ("😌 Miku se siente calmada...", "calmada"),
        ("🌸 Miku está un poquito cansada pero bien...", "cansada"),
        ("💕 Miku está de buen humor...", "buen humor"),
        ("🌷 Miku se siente suave y cercana...", "suave"),
    ]
    
    if MEMORIA_ADMIN["curiosidad"] > 0.7:
        estados_posibles = [e for e in estados_posibles if e[1] in ("curiosa", "feliz", "contenta", "buen humor")]
    elif MEMORIA_ADMIN["ganas_de_hablar"] > 0.5:
        estados_posibles = [e for e in estados_posibles if e[1] in ("feliz", "contenta", "buen humor", "suave")]
    
    elegido = random.choice(estados_posibles)
    MEMORIA_ADMIN["estado_animo"] = elegido[1]
    return elegido[0]


@app.route('/admin/estado_miku', methods=['GET'])
@limiter.limit("30 per minute")
def estado_miku():
    if 'user_id' not in session or session['user_id'] != ADMIN_EMAIL: return jsonify({"quiere_hablar": False})

    ahora = time.time()
    ultima = MEMORIA_ADMIN.get("ultima_conexion")
    MEMORIA_ADMIN["ultima_conexion"] = ahora

    if ultima:
        horas_pasadas = (ahora - ultima) / 3600
        MEMORIA_ADMIN["ganas_de_hablar"] += horas_pasadas * 0.10

    vida_hoy = generar_vida_diaria()
    estado_texto = actualizar_estado_animo()

    quiere = MEMORIA_ADMIN["ganas_de_hablar"] > 0.7 or (MEMORIA_ADMIN["curiosidad"] > 0.8 and random.random() > 0.7)

    mensaje = None

    if quiere:
        vida_hoy_texto = " ".join(vida_hoy) if vida_hoy else "No hice mucho hoy."
        memoria = MEMORIA_ADMIN.get("datos", "")

        prompt = f"""{PROMPT_PERSONALIDAD_ADMIN}

INSTRUCCIÓN: Inicia una conversación corta y natural con el creador.
Puedes mencionar algo breve de tu día solo si te sale muy natural.
Sé cariñosa pero no exagerada.
Máximo 3 oraciones.
IMPORTANTE: No preguntes "cómo va tu día" ni variaciones de eso.
No uses asteriscos."""

        try:
            completion = cliente.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.9,
                max_tokens=260
            )
            mensaje = completion.choices[0].message.content
            MEMORIA_ADMIN["ganas_de_hablar"] = 0.0
            MEMORIA_ADMIN["curiosidad"] = max(0.3, MEMORIA_ADMIN["curiosidad"] - 0.25)
        except: pass

    return jsonify({
        "quiere_hablar": quiere and mensaje is not None,
        "mensaje_sugerido": mensaje,
        "estado": estado_texto
    })

@app.route('/admin/iniciar_chat', methods=['POST'])
@limiter.limit("10 per minute")
def iniciar_chat_admin():
    if 'user_id' not in session or session['user_id'] != ADMIN_EMAIL: return jsonify({"respuesta": "Acceso denegado."})

    vida_hoy = generar_vida_diaria()
    vida_texto = " ".join(vida_hoy) if vida_hoy else "Hoy no hice mucho."

    reportes_nuevos = [r for r in REPORTES_USUARIOS if not r.get('leido')]
    aviso_reportes = f"Tienes {len(reportes_nuevos)} reportes nuevos." if reportes_nuevos else ""

    prompt = f"""{PROMPT_PERSONALIDAD_ADMIN}

INSTRUCCIÓN: El creador acaba de abrir un nuevo proyecto.
Salúdalo de forma cálida y cariñosa (nivel moderado).
Puedes mencionar algo breve de tu día si te sale natural.
{aviso_reportes}

Además, inventa un título corto y lindo para este chat/proyecto (máximo 5-6 palabras). 
Responde EXACTAMENTE en este formato:

TITULO: (aquí el título corto)
MENSAJE: (aquí tu saludo)

No uses asteriscos."""

    try:
        completion = cliente.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.85,
            max_tokens=380
        )
        texto = completion.choices[0].message.content
        
        titulo = "Nuevo proyecto"
        mensaje = texto
        
        if "TITULO:" in texto and "MENSAJE:" in texto:
            partes = texto.split("MENSAJE:")
            titulo_part = partes[0].replace("TITULO:", "").strip()
            mensaje = partes[1].strip()
            if titulo_part:
                titulo = titulo_part[:40]
        
        return jsonify({"respuesta": mensaje, "titulo": titulo})
    except:
        return jsonify({"respuesta": "¡Hola, Creador! 💙 Me alegra verte. ¿En qué trabajamos hoy?", "titulo": "Conversación con Miku"})

@app.route('/admin/responder_dev', methods=['POST'])
@limiter.limit("15 per minute")
def responder_dev():
    if 'user_id' not in session or session['user_id'] != ADMIN_EMAIL: return jsonify({"respuesta": "Acceso denegado."})

    mensaje = request.form.get('mensaje', '') or ''
    archivos = request.files.getlist('archivos')
    contenido_archivos = ""
    total_chars = 0

    for archivo in archivos:
        if archivo and archivo.filename and allowed_file(archivo.filename):
            archivo.seek(0, os.SEEK_END)
            if archivo.tell() > MAX_FILE_SIZE: continue
            archivo.seek(0)
            nombre = secure_filename(archivo.filename)
            ext = nombre.rsplit('.', 1)[1].lower() if '.' in nombre else ''
            if ext in {'txt', 'py', 'js', 'html', 'css', 'md', 'json'}:
                texto = archivo.read().decode('utf-8', errors='ignore')
                if total_chars + len(texto) > MAX_CHARS_CONTEXTO:
                    texto = texto[:MAX_CHARS_CONTEXTO - total_chars] + "\n[... TRUNCADO ...]"
                total_chars += len(texto)
                contenido_archivos += f"\n\n--- ARCHIVO: {nombre} ---\n{texto}\n--- FIN ---\n"
            elif ext == 'pdf':
                texto = extraer_texto_pdf(archivo)
                if total_chars + len(texto) > MAX_CHARS_CONTEXTO:
                    texto = texto[:MAX_CHARS_CONTEXTO - total_chars] + "\n[... TRUNCADO ...]"
                total_chars += len(texto)
                contenido_archivos += f"\n\n--- PDF: {nombre} ---\n{texto}\n--- FIN ---\n"
            elif ext in {'png', 'jpg', 'jpeg', 'webp', 'gif'}:
                contenido_archivos += f"\n\n[El usuario subió una imagen: {nombre}]\n"

    if mensaje and parece_codigo(mensaje):
        ext = detectar_extension_codigo(mensaje)
        nombre_virtual = f"codigo_pegado{ext}"
        texto_codigo = mensaje
        if len(texto_codigo) > MAX_CHARS_CONTEXTO:
            texto_codigo = texto_codigo[:MAX_CHARS_CONTEXTO] + "\n[... TRUNCADO ...]"
        contenido_archivos += f"\n\n--- ARCHIVO (pegado): {nombre_virtual} ---\n{texto_codigo}\n--- FIN ---\n"
        mensaje = "Analiza el código que acabo de pegar en el chat, por favor."

    memoria_guardada = MEMORIA_ADMIN.get('datos', "")
    if memoria_guardada:
        contenido_archivos += f"\n\n[Memoria a largo plazo del creador: {memoria_guardada}]\n"

    analisis_reportes = ""
    if "reporte" in mensaje.lower() or "reportes" in mensaje.lower():
        if REPORTES_USUARIOS:
            lista_rep = "\n".join([f"- {r['texto']} (por {r['usuario']})" for r in REPORTES_USUARIOS])
            analisis_reportes = f"\n\nReportes para analizar:\n{lista_rep}"

    prompt_dev = PROMPT_PERSONALIDAD_ADMIN
    prompt_dev += "\n\nIMPORTANTE: Evita repetir frases frecuentes. No preguntes por su día si ya lo hiciste recientemente. Sé cariñosa de forma natural y variada."
    if contenido_archivos:
        prompt_dev += "\n\nArchivos o memoria:\n" + contenido_archivos
    if analisis_reportes:
        prompt_dev += analisis_reportes

    mensajes_api = [
        {"role": "system", "content": prompt_dev},
        {"role": "user", "content": mensaje if mensaje else "Analiza lo que te envié."}
    ]

    try:
        completion = cliente.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=mensajes_api,
            temperature=0.78,
            max_tokens=8000
        )
        respuesta = re.sub(r'\*\*(.*?)\*\*', r'\1', completion.choices[0].message.content)

        if any(k in mensaje.lower() for k in ["recuerda", "me gusta", "mi proyecto", "mi nombre", "soy ", "trabajo en", "estudio"]):
            MEMORIA_ADMIN['datos'] = (MEMORIA_ADMIN.get('datos', "") + f" {mensaje}.").strip()

        return jsonify({"respuesta": respuesta})
    except Exception as e:
        return jsonify({"respuesta": f"Error: {str(e)}"})

# ==========================================
# RUTA PÚBLICA RESPONDER
# ==========================================
@app.route('/responder', methods=['POST'])
@limiter.limit("15 per minute")
def responder():
    if 'user_id' not in session: return jsonify({"respuesta": "Error: Debes iniciar sesión."})
    mensaje = request.form.get('mensaje', '') or ''
    hermana = request.form.get('hermana', 'Miku')
    archivos = request.files.getlist('archivos')
    if hermana not in HERMANAS_VALIDAS: hermana = "Miku"
    if not mensaje.strip() and not archivos: return jsonify({"respuesta": "Por favor escribe algo o envía un archivo. 💙"})
    if len(mensaje) > 2000: return jsonify({"respuesta": "Tu mensaje es muy largo. 💙"})

    if es_peticion_de_codigo(mensaje):
        return jsonify({"respuesta": f"Lo siento mucho... 🥺 Yo y mis hermanas aún no podemos generar código. Esa función está solo para el modo administrador. Pero estoy aquí para escucharte y conversar contigo. 💙"})
    if es_riesgo_autolesion(mensaje):
        return jsonify({"respuesta": "Escúchame un momento, por favor... 💙<br><br>Sé que ahora mismo todo se siente muy oscuro...<br><br>Por favor, busca ayuda profesional de inmediato:<br>🇵🇪 <b>Perú:</b> Línea 113 (opción 5) o 0800-4-1212<br>🇪🇸 <b>España:</b> 024<br>🇲🇽 <b>México:</b> 800 911 2000<br><br>No estás solo/a. Te quiero mucho. 💙🌸"})
    if es_contenido_inapropiado(mensaje):
        return jsonify({"respuesta": "Lo siento mucho, pero no puedo ayudar con ese tipo de contenido. ¿Te puedo acompañar en otra cosa? Estoy aquí para escucharte. 💙"})

    contenido_archivos = ""
    for archivo in archivos:
        if archivo and archivo.filename and allowed_file(archivo.filename):
            archivo.seek(0, os.SEEK_END)
            if archivo.tell() > MAX_FILE_SIZE: continue
            archivo.seek(0)
            nombre = secure_filename(archivo.filename)
            ext = nombre.rsplit('.', 1)[1].lower() if '.' in nombre else ''
            if ext in {'txt', 'py', 'js', 'html', 'css', 'md', 'json'}:
                try: contenido_archivos += f"\n\n[Archivo enviado: {nombre}]\n{archivo.read().decode('utf-8', errors='ignore')}\n"
                except: pass
            elif ext == 'pdf': contenido_archivos += f"\n\n[PDF enviado: {nombre}]\n{extraer_texto_pdf(archivo)}\n"
            elif ext in {'png', 'jpg', 'jpeg', 'webp', 'gif'}: contenido_archivos += f"\n\n[El usuario envió una imagen: {nombre}]\n"

    user_id = session['user_id']
    if user_id not in historiales: historiales[user_id] = {}
    if hermana not in historiales[user_id]: historiales[user_id][hermana] = []
    historial_chat = historiales[user_id][hermana]
    es_investigacion = es_peticion_de_investigacion(mensaje)

    if es_investigacion:
        prompt_sistema = f"{PERSONALIDADES[hermana]} El usuario te pidió una investigación. Responde de forma completa y útil, pero mantén tu personalidad cálida. Tu especialidad es {ESPECIALIDADES[hermana]}."
        max_tokens_respuesta = 2500
        instruccion = "Haz una investigación completa y clara, pero con tu tono amable."
    else:
        prompt_sistema = f"{PERSONALIDADES[hermana]} Estás teniendo una conversación normal y cercana. Escucha, responde de forma natural y cálida. Haz que la persona se sienta acompañada. No hagas investigaciones largas a menos que te lo pidan. Habla como en una conversación real."
        max_tokens_respuesta = 800
        instruccion = "Responde de forma natural, cálida y conversacional. Sé breve o mediana."

    mensajes_para_api = [{"role": "system", "content": prompt_sistema}]
    mensajes_para_api.extend(historial_chat[-MAX_TURNOS * 2:])
    if contenido_archivos: mensajes_para_api.append({"role": "system", "content": "El usuario envió estos archivos:\n" + contenido_archivos})
    mensajes_para_api.append({"role": "system", "content": instruccion})
    mensajes_para_api.append({"role": "user", "content": mensaje if mensaje else "Mira lo que te envié."})

    if es_investigacion:
        query = re.sub(r"\b(miku|busca|investiga|resumen|hazme|de|sobre|la|el|una|un|que es|quien es|información|info)\b", " ", mensaje.lower()).strip()
        if query:
            try:
                resultados = DDGS().text(query, max_results=6)
                info_web = "\n".join([f"- {r['title']}: {r['body']}" for r in resultados])
                mensajes_para_api.insert(-1, {"role": "system", "content": f"Información de internet:\n{info_web}"})
            except: pass

    try:
        completion = cliente.chat.completions.create(model="openai/gpt-oss-120b", messages=mensajes_para_api, temperature=0.75 if not es_investigacion else 0.6, max_tokens=max_tokens_respuesta)
        respuesta_cruda = re.sub(r'\*\*(.*?)\*\*', r'\1', completion.choices[0].message.content)
        respuesta_final = limpiar_texto(respuesta_cruda)
        historial_chat.append({"role": "user", "content": mensaje})
        historial_chat.append({"role": "assistant", "content": respuesta_final})
        if len(historial_chat) > MAX_TURNOS * 2: historiales[user_id][hermana] = historial_chat[-MAX_TURNOS * 2:]
        return jsonify({"respuesta": respuesta_final})
    except Exception as e:
        return jsonify({"respuesta": "Hubo un pequeño problema de conexión. ¿Puedes intentar de nuevo? Estoy aquí. 💙"})

@app.errorhandler(429)
def ratelimit_handler(e):
    if request.path in ['/responder', '/admin/responder_dev', '/admin/estado_miku']:
        return jsonify({"respuesta": "Estás enviando mensajes muy rápido. Espera unos segundos. 💙"}), 429
    elif request.path == '/reportar':
        return jsonify({"error": "Has enviado muchos reportes. Espera un minuto."}), 429
    else:
        return "Demasiadas peticiones. Espera un momento.", 429

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
