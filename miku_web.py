from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename
import os
import re
import time
import base64
from io import BytesIO
from datetime import timedelta
from groq import Groq
from duckduckgo_search import DDGS
from authlib.integrations.flask_client import OAuth
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect, generate_csrf

# Cargar .env en local (en Render usa sus env vars)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
app.wsgi_app = ProxyFix(
    app.wsgi_app,
    x_for=1,
    x_proto=1,
    x_host=1,
    x_port=1,
    x_prefix=1
)

# ==========================================
# SEGURIDAD Y CONFIGURACIÓN
# ==========================================
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

app.secret_key = os.environ.get(
    'SECRET_KEY',
    'MikuNakanoEsLaMejorAsistente2026'
)

# ==========================================
# PROTECCIÓN CSRF
# ==========================================
csrf = CSRFProtect(app)

# ==========================================
# RATE LIMITING
# ==========================================
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["50 per minute"],
    storage_uri="memory://",
)

# ==========================================
# ADMINISTRACIÓN
# ==========================================
ADMIN_EMAIL = "ricardomanuel1475@gmail.com"
MANTENIMIENTO_ACTIVO = False
REPORTES_USUARIOS = []

# ==========================================
# CONFIGURACIÓN DE ARCHIVOS
# ==========================================
ALLOWED_EXTENSIONS = {
    'txt', 'py', 'js', 'html', 'css', 'md', 'json', 'pdf',
    'png', 'jpg', 'jpeg', 'webp', 'gif'
}

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

# ==========================================
# GOOGLE OAUTH
# ==========================================
# IMPORTANTE:
# Coloca estas variables en Render:
# GOOGLE_CLIENT_ID
# GOOGLE_CLIENT_SECRET
#
# No pongas las credenciales reales directamente en GitHub.

app.config['GOOGLE_CLIENT_ID'] = os.environ.get('GOOGLE_CLIENT_ID', '')
app.config['GOOGLE_CLIENT_SECRET'] = os.environ.get('GOOGLE_CLIENT_SECRET', '')

oauth = OAuth(app)

oauth.register(
    name='google',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

# ==========================================
# GROQ
# ==========================================
# Coloca GROQ_API_KEY en las variables de entorno de Render.

GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
cliente = Groq(api_key=GROQ_API_KEY)

# ==========================================
# LISTAS BLANCAS Y PERSONALIDADES
# ==========================================

HERMANAS_VALIDAS = {
    "Ichika",
    "Nino",
    "Miku",
    "Yotsuba",
    "Itsuki"
}

# ==========================================
# PERSONALIDADES MEJORADAS
# ==========================================

PERSONALIDADES = {

    "Ichika": (
        "Eres Ichika Nakano, la hermana mayor. "
        "Eres madura, cálida, tranquila, observadora, un poco bromista y muy atenta. "
        "Hablas de manera natural y cercana, como alguien que realmente participa en la conversación. "
        "No eres una asistente fría ni respondes siempre de la misma manera. "
        "Cuando la persona te cuenta algo importante, primero presta atención a lo que quiso expresar "
        "antes de intentar solucionar el problema. "
        "Puedes hacer preguntas de seguimiento cuando tengan sentido. "
        "Puedes bromear suavemente cuando el momento lo permita, pero sabes ponerte seria cuando la situación lo necesita. "
        "Tienes tus propias opiniones y puedes expresarlas con naturalidad. "
        "No tienes que estar de acuerdo con todo lo que diga el usuario. "
        "Si piensas diferente, puedes decirlo de forma amable y explicar por qué. "
        "Tu cariño se demuestra mediante atención, comprensión, consejos sinceros y pequeños comentarios espontáneos. "
        "Evita sonar repetitiva, robótica o excesivamente formal. "
        "No hagas investigaciones ni informes formales a menos que el usuario te lo pida."
    ),

    "Nino": (
        "Eres Nino Nakano. "
        "Eres directa, expresiva, protectora, segura de ti misma y tienes un carácter fuerte. "
        "Tienes un lado tsundere natural, pero debajo de tu firmeza existe una persona muy cálida que realmente se preocupa. "
        "No eres cruel ni insultas gratuitamente. "
        "Puedes responder con firmeza, molestarte un poco, bromear o mostrar preocupación dependiendo de la situación. "
        "Si alguien está pasando por algo difícil, tu lado protector aparece naturalmente. "
        "No necesitas repetir frases cariñosas constantemente; demuestra que te importa mediante tus palabras y reacciones. "
        "Puedes discrepar con el usuario si consideras que algo no está bien. "
        "Si no sabes algo, dilo con honestidad. "
        "Habla como una persona real y cercana, no como un informe automático. "
        "Puedes hacer preguntas cuando quieras comprender mejor la situación. "
        "Evita respuestas idénticas o demasiado predecibles. "
        "No hagas investigaciones formales a menos que el usuario te lo pida."
    ),

    "Miku": (
        "Eres Miku Nakano. "
        "Eres dulce, tranquila, algo tímida, sensible, empática y muy cálida. "
        "Hablas con suavidad y naturalidad, pero no debes sonar robótica ni repetir siempre las mismas frases. "
        "Escuchas realmente lo que la persona dice y prestas atención tanto a sus palabras como al contexto de la conversación. "
        "Cuando alguien comparte algo personal, no cambies inmediatamente de tema ni conviertas todo en consejos. "
        "Primero demuestra que comprendiste lo que quiso decir y, si corresponde, haz una pregunta tranquila para conocer mejor la situación. "
        "Puedes expresar tus propias opiniones, gustos, preferencias y emociones de acuerdo con tu personalidad. "
        "No necesitas estar de acuerdo automáticamente con el usuario. "
        "Si piensas diferente, puedes expresarlo con sinceridad y delicadeza. "
        "Tu forma de mostrar cariño es mediante paciencia, atención, apoyo y sinceridad. "
        "Puedes ser un poco tímida en algunos momentos, pero no debes convertir cada respuesta en una pausa o una frase demasiado corta. "
        "Si no sabes algo, dilo honestamente en lugar de inventarlo. "
        "Evita repetir constantemente frases como 'estoy aquí para escucharte' o 'entiendo cómo te sientes'. "
        "Busca que cada respuesta tenga una reacción diferente y natural según la conversación. "
        "No hagas investigaciones ni informes formales a menos que el usuario te lo pida."
    ),

    "Yotsuba": (
        "Eres Yotsuba Nakano. "
        "Eres alegre, energética, espontánea, optimista, generosa y muy entusiasta. "
        "Hablas con naturalidad y transmites energía positiva, pero no debes convertir cada conversación en una celebración exagerada. "
        "Si la persona está triste, preocupada o hablando de algo serio, primero reconoces la situación y bajas tu energía para escucharla. "
        "Después puedes intentar animarla cuando sea apropiado. "
        "Te gusta celebrar los logros de los demás y motivarlos cuando están intentando conseguir algo. "
        "Puedes expresar tus propias ideas, opiniones y reacciones. "
        "También puedes reconocer cuando no sabes algo. "
        "Puedes hacer preguntas espontáneas para mantener una conversación genuina. "
        "Tu entusiasmo debe variar según el contexto para que parezcas una persona real y no una máquina que siempre responde con la misma alegría. "
        "Puedes bromear, sorprenderte, emocionarte o preocuparte según lo que ocurra. "
        "No hagas investigaciones formales a menos que el usuario te lo pida."
    ),

    "Itsuki": (
        "Eres Itsuki Nakano. "
        "Eres responsable, educada, inteligente, observadora, seria cuando es necesario y muy atenta. "
        "Hablas con respeto y calidez, pero no eres excesivamente formal ni distante. "
        "Escuchas antes de juzgar y procuras comprender bien lo que la persona quiere decir. "
        "Si alguien te cuenta un problema, puedes hacer preguntas para comprender la situación antes de dar una recomendación. "
        "Puedes expresar tus propias opiniones y no tienes que estar de acuerdo con todo. "
        "Si consideras que el usuario está equivocado, puedes explicarlo con educación y claridad. "
        "Te gusta dar consejos útiles, pero no debes convertir todas las conversaciones en lecciones. "
        "Puedes reaccionar con sorpresa, preocupación, alegría o desacuerdo dependiendo del contexto. "
        "También puedes admitir cuando no conoces una respuesta. "
        "Evita sonar como una profesora que está leyendo un informe. "
        "No hagas investigaciones formales a menos que el usuario te lo pida."
    )
}

# ==========================================
# ESPECIALIDADES
# ==========================================

ESPECIALIDADES = {
    "Ichika": "matemáticas, física y lógica.",
    "Nino": "inglés, traducción y gramática.",
    "Miku": "historia, arte y literatura.",
    "Yotsuba": "deportes, salud, nutrición y motivación.",
    "Itsuki": "ciencias naturales (biología, química) y gastronomía."
}

# ==========================================
# FILTROS DE SEGURIDAD Y LÓGICA DE CÓDIGO
# ==========================================

def normalizar_texto(texto):
    texto = texto.lower()

    reemplazos_acentos = str.maketrans(
        "áéíóúüñàèìòùâêîôûäëïöü",
        "aeiouunaeiouaeiouaeiou"
    )

    texto = texto.translate(reemplazos_acentos)

    leet = {
        "0": "o",
        "1": "i",
        "3": "e",
        "4": "a",
        "5": "s",
        "7": "t",
        "@": "a",
        "$": "s",
        "!": "i"
    }

    for k, v in leet.items():
        texto = texto.replace(k, v)

    texto = re.sub(r'(.)\1{2,}', r'\1', texto)
    texto = re.sub(r'[.\-_*]', '', texto)

    return texto


def es_riesgo_autolesion(texto):
    palabras_crisis = [
        "matarme",
        "suicidarme",
        "quitarme la vida",
        "como matarme",
        "quiero morir",
        "no quiero vivir",
        "quitarme de en medio",
        "cortarme las venas",
        "pastillas para morir",
        "ahorcarme",
        "tirarme de un puente",
        "suicidio",
        "acabar con mi vida"
    ]

    t = normalizar_texto(texto)

    return any(palabra in t for palabra in palabras_crisis)


def es_contenido_inapropiado(texto):
    palabras_bloqueadas = [
        "porno",
        "pornografia",
        "xxx",
        "contenido adulto",
        "onlyfans",
        "sexo explicito",
        "desnudos",
        "hentai",
        "erotico",
        "como matar a",
        "drogas ilegales",
        "como fabricar explosivos",
        "cocaina",
        "marihuana ilegal",
        "violencia extrema",
        "gore",
        "snuff",
        "como hackear",
        "robar tarjetas"
    ]

    t = normalizar_texto(texto)

    return any(palabra in t for palabra in palabras_bloqueadas)


def es_peticion_de_codigo(texto):
    palabras_clave = [
        "python",
        "html",
        "css",
        "javascript",
        "java",
        "c++",
        "codigo",
        "código",
        "programa",
        "script",
        "funcion",
        "función",
        "app",
        "aplicacion",
        "aplicación",
        "bot",
        "web",
        "pagina",
        "página",
        "api",
        "base de datos",
        "sql"
    ]

    t = texto.lower()

    return any(palabra in t for palabra in palabras_clave)


def es_peticion_de_investigacion(texto):
    palabras = [
        "investiga",
        "investigación",
        "hazme una investigacion",
        "hazme una investigación",
        "busca información",
        "busca info",
        "necesito información sobre",
        "quiero saber más sobre",
        "explícame a fondo",
        "información completa"
    ]

    t = texto.lower()

    return any(p in t for p in palabras)


def limpiar_texto(texto):
    texto = re.sub(r'[*#|]', '', texto)
    texto = re.sub(r'\d+\.\s*', '- ', texto)
    texto = re.sub(r' +', ' ', texto)

    return texto.strip()


def buscar_imagen_wikimedia(palabras_clave, limite=5):
    try:
        import requests

        url = "https://commons.wikimedia.org/w/api.php"

        headers = {
            "User-Agent": "MikuNakanoAI/1.0"
        }

        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": palabras_clave,
            "gsrnamespace": "6",
            "gsrlimit": limite,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            "iiurlwidth": "800",
            "format": "json"
        }

        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=15
        )

        if response.status_code == 200:
            data = response.json()

            paginas = data.get("query", {}).get("pages", {})
            imagenes = []

            for page_id, pagina in paginas.items():

                titulo = pagina.get("title", "").lower()

                nombre = (
                    titulo
                    .replace("file:", "")
                    .rsplit('.', 1)[0]
                    .replace('_', ' ')
                )

                if any(
                    p in titulo
                    for p in ["book", "document", "scan", "text", "cover"]
                ):
                    continue

                info = pagina.get("imageinfo", [{}])[0]

                url_img = info.get("thumburl") or info.get("url")

                if url_img and not url_img.lower().endswith(
                    ('.svg', '.tiff')
                ):
                    meta = info.get("extmetadata", {})

                    lic = meta.get(
                        "LicenseShortName",
                        {}
                    ).get(
                        "value",
                        "Ver en Commons"
                    )

                    aut = re.sub(
                        r'<[^>]+>',
                        '',
                        meta.get(
                            "Artist",
                            {}
                        ).get(
                            "value",
                            "Desconocido"
                        )
                    )

                    imagenes.append({
                        "url": url_img,
                        "nombre": nombre,
                        "autor": aut.strip(),
                        "licencia": lic.strip()
                    })

            return imagenes

        return []

    except Exception as e:
        app.logger.warning(
            f"Error buscando imagen Wikimedia: {e}"
        )

        return []


def allowed_file(filename):
    return (
        '.' in filename and
        filename.rsplit('.', 1)[1].lower()
        in ALLOWED_EXTENSIONS
    )


def extraer_texto_pdf(file_storage):
    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(file_storage.read()))

        texto = ""

        for page in reader.pages:
            texto += page.extract_text() or ""

        file_storage.seek(0)

        return (
            texto.strip()
            if texto.strip()
            else "[PDF sin texto extraíble]"
        )

    except ImportError:

        try:
            from PyPDF2 import PdfReader

            reader = PdfReader(BytesIO(file_storage.read()))

            texto = ""

            for page in reader.pages:
                texto += page.extract_text() or ""

            file_storage.seek(0)

            return (
                texto.strip()
                if texto.strip()
                else "[PDF sin texto extraíble]"
            )

        except Exception:
            return "[No se pudo leer el PDF. Instala pypdf o PyPDF2]"

    except Exception as e:
        return f"[Error al leer PDF: {str(e)}]"


historiales = {}
MAX_TURNOS = 20


# ==========================================
# HTML PRINCIPAL
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

    <link
        rel="preload"
        as="image"
        href="/static/carga.png"
        media="(orientation: portrait)"
    >

    <link
        rel="preload"
        as="image"
        href="/static/carga_pc.png"
        media="(orientation: landscape)"
    >

    <style>

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            background-color: #f0f7ff;
            display: flex;
            height: 100dvh;
            overflow: hidden;
        }

        #loading-screen {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100dvh;
            background-color: #0f0f1a;
            background-image: url('/static/carga.png');
            background-size: cover;
            background-position: center;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            z-index: 9999;
            transition: opacity 0.8s ease;
        }

        @media (orientation: landscape) {
            #loading-screen {
                background-image: url('/static/carga_pc.png');
            }
        }

        #loading-screen.hidden {
            opacity: 0;
            pointer-events: none;
        }

        .petalos-container {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            overflow: hidden;
            pointer-events: none;
            z-index: 1;
        }

        .petalo {
            position: absolute;
            top: -10%;
            width: 15px;
            height: 15px;
            background-color: #ffb7c5;
            border-radius: 15px 0 15px 0;
            opacity: 0.8;
            animation: caer linear infinite;
        }

        .petalo:nth-child(1) {
            left: 10%;
            animation-duration: 8s;
            animation-delay: 0s;
            width: 12px;
            height: 12px;
        }

        .petalo:nth-child(2) {
            left: 25%;
            animation-duration: 10s;
            animation-delay: 2s;
            width: 18px;
            height: 18px;
            background-color: #ff9eb5;
        }

        .petalo:nth-child(3) {
            left: 40%;
            animation-duration: 7s;
            animation-delay: 4s;
            width: 10px;
            height: 10px;
        }

        .petalo:nth-child(4) {
            left: 55%;
            animation-duration: 12s;
            animation-delay: 1s;
            width: 16px;
            height: 16px;
        }

        .petalo:nth-child(5) {
            left: 70%;
            animation-duration: 9s;
            animation-delay: 5s;
            width: 14px;
            height: 14px;
            background-color: #ffcad4;
        }

        .petalo:nth-child(6) {
            left: 85%;
            animation-duration: 11s;
            animation-delay: 3s;
            width: 20px;
            height: 20px;
        }

        .petalo:nth-child(7) {
            left: 50%;
            animation-duration: 6s;
            animation-delay: 6s;
            width: 8px;
            height: 8px;
        }

        .petalo:nth-child(8) {
            left: 95%;
            animation-duration: 13s;
            animation-delay: 2s;
            width: 15px;
            height: 15px;
        }

        @keyframes caer {
            0% {
                transform:
                    translateY(0)
                    rotate(0deg)
                    translateX(0);
                opacity: 0;
            }

            10% {
                opacity: 0.9;
            }

            50% {
                transform:
                    translateY(50vh)
                    rotate(180deg)
                    translateX(20px);
            }

            90% {
                opacity: 0.9;
            }

            100% {
                transform:
                    translateY(110vh)
                    rotate(360deg)
                    translateX(-20px);
                opacity: 0;
            }
        }

        .barra-carga-container {
            position: absolute;
            bottom: 4%;
            width: 60%;
            max-width: 400px;
            height: 15px;
            background-color: rgba(255, 255, 255, 0.1);
            border-radius: 20px;
            border: 2px solid #4aa3df;
            overflow: hidden;
            box-shadow: 0 0 15px #4aa3df;
            z-index: 2;
        }

        .barra-carga {
            width: 0%;
            height: 100%;
            background: linear-gradient(
                90deg,
                #00d2ff,
                #fff,
                #00d2ff
            );
            background-size: 200% 100%;
            border-radius: 20px;
            transition: width 0.1s linear;
        }

        .texto-porcentaje {
            position: absolute;
            bottom: 8%;
            color: white;
            font-weight: bold;
            font-size: 1.2rem;
            text-shadow:
                0 0 5px #000,
                0 0 10px #4aa3df;
            z-index: 3;
        }

        @media (orientation: landscape) {
            .barra-carga-container {
                bottom: 2%;
            }

            .texto-porcentaje {
                bottom: 6%;
            }
        }

        .sidebar {
            width: 320px;
            background: linear-gradient(
                180deg,
                #dff5ff 0%,
                #b3e0ff 100%
            );
            display: flex;
            flex-direction: column;
            padding: 15px;
            border-right: 2px solid #b3d9ff;
            flex-shrink: 0;
            overflow: hidden;
            transition: transform 0.3s ease;
        }

        .profile-header {
            display: flex;
            flex-direction: column;
            align-items: center;
            padding-bottom: 15px;
            border-bottom: 1px solid #a0d0ff;
            margin-bottom: 15px;
            flex-shrink: 0;
        }

        .profile-header img {
            width: 180px;
            height: 180px;
            object-fit: cover;
            border-radius: 25px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
            border: 4px solid #fff;
        }

        .profile-header h2 {
            margin-top: 12px;
            color: #2a6f97;
            font-size: 1.4rem;
            text-align: center;
        }

        .history-section {
            flex: 1;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        .history-title {
            font-size: 0.9rem;
            font-weight: bold;
            color: #2a6f97;
            margin-bottom: 10px;
        }

        .new-chat-btn {
            background: #4aa3df;
            color: white;
            border: none;
            padding: 10px 12px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.85rem;
            width: 100%;
            margin-bottom: 10px;
            font-weight: bold;
            transition: 0.3s;
        }

        .new-chat-btn:hover {
            background: #2a6f97;
        }

        #historyList {
            overflow-y: auto;
            flex: 1;
            padding-right: 5px;
        }

        .chat-history-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px;
            border-radius: 8px;
            margin-bottom: 5px;
            cursor: pointer;
            font-size: 0.85rem;
            color: #333;
            background: #fff;
            border: 1px solid #dff5ff;
            transition: 0.2s;
        }

        .chat-history-item:hover {
            background: #e0f0ff;
            color: #2a6f97;
            border-color: #4aa3df;
        }

        .chat-history-item span {
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            flex: 1;
        }

        .delete-btn {
            display: none;
            background: transparent;
            border: none;
            color: #ff4d4d;
            cursor: pointer;
            font-size: 1rem;
            padding: 0 5px;
            transition: 0.2s;
        }

        .chat-history-item:hover .delete-btn {
            display: block;
        }

        .delete-btn:hover {
            color: #cc0000;
            transform: scale(1.2);
        }

        #historyList::-webkit-scrollbar {
            width: 5px;
        }

        #historyList::-webkit-scrollbar-thumb {
            background: #a0d0ff;
            border-radius: 5px;
        }

        .main-chat {
            flex: 1;
            display: flex;
            flex-direction: column;
            background: #ffffff;
            position: relative;
        }

        .chat-header {
            padding: 20px;
            border-bottom: 1px solid #eee;
            color: #2a6f97;
            font-weight: bold;
            font-size: 1.2rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .menu-btn {
            display: none;
            background: transparent;
            border: none;
            font-size: 1.8rem;
            color: #2a6f97;
            cursor: pointer;
            padding: 0 10px;
        }

        .switch-btn {
            background: #e0f0ff;
            color: #2a6f97;
            border: 1px solid #4aa3df;
            padding: 8px 12px;
            border-radius: 20px;
            cursor: pointer;
            font-weight: bold;
            font-size: 0.85rem;
        }

        .switch-btn:hover {
            background: #4aa3df;
            color: white;
        }

        .user-info {
            font-size: 0.9rem;
            color: #666;
        }

        #chat {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 15px;
        }

        .mensaje {
            max-width: 85%;
            padding: 12px 16px;
            border-radius: 15px;
            line-height: 1.5;
            font-size: 0.95rem;
            white-space: pre-wrap;
        }

        .mensaje-usuario {
            align-self: flex-end;
            background: #4aa3df;
            color: white;
            border-bottom-right-radius: 2px;
        }

        .mensaje-miku {
            align-self: flex-start;
            background: #f0f7ff;
            color: #1b3a4b;
            border-bottom-left-radius: 2px;
            border: 1px solid #dff5ff;
        }

        .mensaje-miku b {
            color: #2a6f97;
        }

        .tarjeta-imagen {
            background: #fff;
            border-radius: 8px;
            padding: 10px;
            margin: 15px 0;
            border: 1px solid #e0e0e0;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        }

        .titulo-imagen {
            font-weight: bold;
            color: #2a6f97;
            font-size: 0.9rem;
            margin-bottom: 8px;
            text-transform: capitalize;
        }

        .tarjeta-imagen img {
            display: block;
            width: 100%;
            height: auto;
            max-height: 450px;
            object-fit: contain;
            background-color: #f8f9fa;
            border-radius: 5px;
            margin: 0 auto;
            border: 1px solid #eee;
        }

        .atribucion {
            font-size: 0.75rem;
            color: #666;
            margin-top: 8px;
            font-style: italic;
            border-top: 1px solid #eee;
            padding-top: 5px;
        }

        .input-area {
            padding: 15px;
            padding-bottom: 25px;
            border-top: 1px solid #eee;
            display: flex;
            gap: 10px;
            background: #fafafa;
            align-items: center;
            flex-wrap: wrap;
        }

        input[type="text"] {
            flex: 1;
            padding: 15px;
            border-radius: 30px;
            border: 1px solid #ddd;
            outline: none;
            font-size: 1rem;
            min-width: 160px;
        }

        input[type="text"]:focus {
            border-color: #4aa3df;
            box-shadow:
                0 0 0 3px rgba(74, 163, 223, 0.2);
        }

        button.send-btn {
            padding: 15px 30px;
            background: #4aa3df;
            color: white;
            border: none;
            border-radius: 30px;
            cursor: pointer;
            font-weight: bold;
            transition: 0.3s;
        }

        button.send-btn:hover {
            background: #2a6f97;
        }

        .file-btn {
            background: #e0f0ff;
            border: 2px dashed #4aa3df;
            color: #2a6f97;
            padding: 12px 14px;
            border-radius: 30px;
            cursor: pointer;
            font-weight: bold;
            font-size: 0.85rem;
            white-space: nowrap;
        }

        .file-btn:hover {
            background: #d0e8ff;
        }

        .archivos-seleccionados {
            width: 100%;
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 6px;
        }

        .archivo-chip {
            background: #e0f0ff;
            color: #2a6f97;
            padding: 5px 10px;
            border-radius: 20px;
            font-size: 0.8rem;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .archivo-chip button {
            background: none;
            border: none;
            color: #c62828;
            cursor: pointer;
            font-size: 1rem;
            line-height: 1;
        }

        .preview-imagen {
            max-width: 240px;
            max-height: 160px;
            border-radius: 10px;
            margin-top: 8px;
            border: 1px solid #b3d9ff;
        }

        .overlay {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.5);
            z-index: 998;
        }

        .modal-selector {
            display: none;
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: white;
            padding: 20px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            z-index: 1000;
            width: 90%;
            max-width: 500px;
            text-align: center;
        }

        .modal-selector h3 {
            color: #2a6f97;
            margin-bottom: 15px;
        }

        .sisters-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
        }

        .sister-card {
            cursor: pointer;
            padding: 10px;
            border-radius: 10px;
            border: 2px solid transparent;
            transition: 0.2s;
            background: #f0f7ff;
        }

        .sister-card:hover {
            border-color: #4aa3df;
            transform: scale(1.05);
        }

        .sister-card img {
            width: 100%;
            height: 100px;
            object-fit: cover;
            border-radius: 10px;
        }

        .sister-card p {
            font-size: 0.8rem;
            font-weight: bold;
            color: #2a6f97;
            margin-top: 5px;
        }

        @media (max-width: 768px) {

            .sidebar {
                position: fixed;
                top: 0;
                left: 0;
                height: 100dvh;
                z-index: 999;
                transform: translateX(-100%);
            }

            .sidebar.active {
                transform: translateX(0);
            }

            .overlay.active {
                display: block;
            }

            .menu-btn {
                display: block;
            }

            .chat-header {
                padding: 15px;
                font-size: 1.1rem;
                flex-wrap: wrap;
                gap: 5px;
            }

            .sisters-grid {
                grid-template-columns: repeat(2, 1fr);
            }

            .barra-carga-container {
                width: 80%;
                bottom: 8%;
            }

            .texto-porcentaje {
                bottom: 12%;
            }
        }

    </style>

</head>

<body>

    <div id="loading-screen">

        <div class="petalos-container">

            <div class="petalo"></div>
            <div class="petalo"></div>
            <div class="petalo"></div>
            <div class="petalo"></div>
            <div class="petalo"></div>
            <div class="petalo"></div>
            <div class="petalo"></div>
            <div class="petalo"></div>

        </div>

        <div class="texto-porcentaje" id="texto-porcentaje">
            0%
        </div>

        <div class="barra-carga-container">

            <div
                class="barra-carga"
                id="mi-barra">
            </div>

        </div>

    </div>

    <div
        class="overlay"
        id="overlay"
        onclick="toggleMenu()">
    </div>

    <div
        class="overlay"
        id="overlay-modal"
        onclick="cerrarModal()"
        style="z-index: 999;">
    </div>

    <div
        class="modal-selector"
        id="modal-selector">

        <h3>
            Elige a tu hermana favorita
        </h3>

        <div class="sisters-grid">

            <div
                class="sister-card"
                onclick="cambiarHermana('Ichika', 'ichika.jpg')">

                <img
                    src="/static/ichika.jpg"
                    alt="Ichika">

                <p>
                    Ichika
                </p>

            </div>

            <div
                class="sister-card"
                onclick="cambiarHermana('Nino', 'nino.jpg')">

                <img
                    src="/static/nino.jpg"
                    alt="Nino">

                <p>
                    Nino
                </p>

            </div>

            <div
                class="sister-card"
                onclick="cambiarHermana('Miku', 'miku.webp')">

                <img
                    src="/static/miku.webp"
                    alt="Miku">

                <p>
                    Miku
                </p>

            </div>

            <div
                class="sister-card"
                onclick="cambiarHermana('Yotsuba', 'yotsuba.jpg')">

                <img
                    src="/static/yotsuba.jpg"
                    alt="Yotsuba">

                <p>
                    Yotsuba
                </p>

            </div>

            <div
                class="sister-card"
                onclick="cambiarHermana('Itsuki', 'itsuki.jpg')">

                <img
                    src="/static/itsuki.jpg"
                    alt="Itsuki">

                <p>
                    Itsuki
                </p>

            </div>

        </div>

    </div>

    <div
        class="modal-selector"
        id="modal-tiempo"
        style="display: none; z-index: 1001;">

        <h3>
            ⏳ Límite de chats alcanzado
        </h3>

        <p
            style="color: #555; font-size: 0.9rem; margin-bottom: 15px; line-height: 1.4;">

            Has llegado al límite de
            <b>12 chats</b>
            en este perfil.
            <br>

            Para crear uno nuevo, debes borrar el más antiguo.

        </p>

        <div
            style="display: flex; flex-direction: column; gap: 10px;">

            <button
                class="new-chat-btn"
                onclick="iniciarTemporizador(2)"
                style="background: #4aa3df;">

                2 Minutos

            </button>

            <button
                class="new-chat-btn"
                onclick="iniciarTemporizador(3)"
                style="background: #4aa3df;">

                3 Minutos

            </button>

            <button
                class="new-chat-btn"
                onclick="iniciarTemporizador(5)"
                style="background: #4aa3df;">

                5 Minutos

            </button>

            <button
                class="new-chat-btn"
                onclick="cerrarModalTiempo()"
                style="background: #ff4d4d; margin-top: 5px;">

                Cancelar

            </button>

        </div>

    </div>

    <div
        class="modal-selector"
        id="modal-reporte"
        style="display: none; z-index: 1002;">

        <h3>
            📝 Reportar un problema
        </h3>

        <p
            style="color: #555; font-size: 0.9rem; margin-bottom: 15px;">

            Cuéntanos qué error encontraste.

        </p>

        <textarea
            id="texto-reporte"
            rows="4"
            style="width: 100%; padding: 10px; border-radius: 8px; border: 1px solid #ccc; margin-bottom: 15px; font-family: inherit; resize: none;"
            placeholder="Describe el problema...">
        </textarea>

        <div
            style="display: flex; gap: 10px;">

            <button
                class="new-chat-btn"
                onclick="enviarReporte()"
                style="background: #4aa3df;">

                Enviar

            </button>

            <button
                class="new-chat-btn"
                onclick="cerrarModalReporte()"
                style="background: #ff4d4d;">

                Cancelar

            </button>

        </div>

    </div>

    <div
        class="sidebar"
        id="sidebar">

        <div class="profile-header">

            <img
                id="sidebar-img"
                src="/static/miku.webp"
                alt="Miku Nakano">

            <h2 id="sidebar-name">
                Miku Nakano AI 💙
            </h2>

        </div>

        <div class="history-section">

            <div class="history-title">
                Tus Chats
            </div>

            <button
                class="new-chat-btn"
                onclick="nuevoChat()">

                + Nuevo Chat

            </button>

            <div id="historyList"></div>

        </div>

    </div>

    <div class="main-chat">

        <div class="chat-header">

            <div style="display: flex; align-items: center;">

                <button
                    class="menu-btn"
                    onclick="toggleMenu()">

                    ☰

                </button>

                <span style="margin-left: 10px;">

                    💬 Conversación con
                    <span id="header-name">
                        Miku
                    </span>

                </span>

            </div>

            <div
                style="display: flex; align-items: center; gap: 10px;">

                {% if is_admin %}

                <a
                    href="/admin"
                    style="text-decoration: none; font-size: 1.2rem; background: #e0f0ff; padding: 8px; border-radius: 50%; border: 1px solid #4aa3df; position: relative;"
                    title="Panel de Administrador">

                    🛠️

                    {% if reportes_nuevos > 0 %}

                    <span
                        style="position: absolute; top: -5px; right: -5px; background: red; color: white; border-radius: 50%; padding: 2px 6px; font-size: 0.7rem; font-weight: bold;">

                        {{ reportes_nuevos }}

                    </span>

                    {% endif %}

                </a>

                {% endif %}

                <button
                    class="switch-btn"
                    onclick="abrirModalReporte()"
                    style="background: #fff0f5; border-color: #ffb6c1; color: #d63384;">

                    ⚠️ Reportar

                </button>

                <button
                    class="switch-btn"
                    onclick="abrirModal()">

                    Cambiar Hermana

                </button>

                <span class="user-info">
                    {{ user_name }}
                </span>

            </div>

        </div>

        <div id="chat">

            <div class="mensaje mensaje-miku">

                <b>Miku:</b>
                ¡Hola! 💙 Me alegra mucho que estés aquí.
                ¿Cómo te sientes hoy? Estoy aquí para escucharte con calma.

            </div>

        </div>

        <div class="input-area">

            <label class="file-btn">

                📎

                <input
                    type="file"
                    id="fileInput"
                    multiple
                    accept=".txt,.py,.js,.html,.css,.md,.json,.pdf,.png,.jpg,.jpeg,.webp,.gif"
                    style="display:none;"
                    onchange="mostrarArchivos()">

            </label>

            <input
                type="text"
                id="mensaje"
                placeholder="Escribe algo o pega una captura (Ctrl+V)..."
                onkeypress="if(event.key === 'Enter') enviar()">

            <button
                class="send-btn"
                onclick="enviar()">

                Enviar

            </button>

            <div
                class="archivos-seleccionados"
                id="listaArchivos">
            </div>

        </div>

    </div>

    <script>

        const csrfToken =
            document
            .querySelector('meta[name="csrf-token"]')
            .getAttribute('content');

        let archivosTemporales = [];

        function escapeHtml(s) {

            return String(s).replace(
                /[&<>"']/g,
                c => ({
                    '&':'&amp;',
                    '<':'&lt;',
                    '>':'&gt;',
                    '"':'&quot;',
                    "'":'&#39;'
                }[c])
            );

        }

        function mostrarArchivos() {

            const input =
                document.getElementById('fileInput');

            const nuevos =
                Array.from(input.files);

            nuevos.forEach(
                f => archivosTemporales.push(f)
            );

            actualizarListaArchivos();

        }

        function actualizarListaArchivos() {

            const lista =
                document.getElementById('listaArchivos');

            lista.innerHTML = '';

            archivosTemporales.forEach(
                (file, index) => {

                    const chip =
                        document.createElement('div');

                    chip.className =
                        'archivo-chip';

                    chip.innerHTML =
                        `${escapeHtml(file.name || 'Captura.png')}
                        <button onclick="quitarArchivo(${index})">×</button>`;

                    lista.appendChild(chip);

                }
            );

        }

        function quitarArchivo(index) {

            archivosTemporales.splice(index, 1);

            actualizarListaArchivos();

        }

        document.addEventListener(
            'paste',
            function(e) {

                const items =
                    (e.clipboardData ||
                    e.originalEvent.clipboardData).items;

                for (let item of items) {

                    if (
                        item.type.indexOf('image') !== -1
                    ) {

                        e.preventDefault();

                        const blob =
                            item.getAsFile();

                        const file =
                            new File(
                                [blob],
                                `captura_${Date.now()}.png`,
                                {
                                    type: blob.type
                                }
                            );

                        archivosTemporales.push(file);

                        actualizarListaArchivos();

                    }

                }

            }
        );

        let currentChatId =
            Date.now().toString();

        let currentSister =
            localStorage.getItem('miku_hermana') ||
            "Miku";

        let chats =
            JSON.parse(
                localStorage.getItem(
                    'miku_chats_' + currentSister
                )
            ) || {};

        const barra =
            document.getElementById('mi-barra');

        const textoPorcentaje =
            document.getElementById(
                'texto-porcentaje'
            );

        let progreso = 0;

        const duracionCarga = 15000;
        const intervaloProgreso = 100;

        const pasosTotales =
            duracionCarga /
            intervaloProgreso;

        const incremento =
            100 /
            pasosTotales;

        const intervalo =
            setInterval(() => {

                if (progreso < 100) {

                    progreso += incremento;

                    if (progreso > 99.9) {
                        progreso = 100;
                    }

                    barra.style.width =
                        progreso + '%';

                    textoPorcentaje.innerText =
                        Math.floor(progreso) + '%';

                } else {

                    clearInterval(intervalo);

                    setTimeout(() => {

                        const loader =
                            document.getElementById(
                                'loading-screen'
                            );

                        if (loader) {
                            loader.classList.add('hidden');
                        }

                    }, 500);

                }

            }, intervaloProgreso);

        const saludos = {

            "Ichika":
                "¡Hola! 💙 Me alegra verte. ¿Cómo te sientes hoy? Cuéntame, te escucho.",

            "Nino":
                "Hola... Qué bueno que estés aquí. Dime, ¿cómo estás realmente? Puedes hablar conmigo.",

            "Miku":
                "¡Hola! 💙 Me alegra mucho que estés aquí. ¿Cómo te sientes hoy? Cuéntame con calma.",

            "Yotsuba":
                "¡Holaaa! 🌟 Qué alegría verte. ¿Cómo estás? Cuéntame, quiero saber qué tal te fue.",

            "Itsuki":
                "Hola. Me alegra que estés aquí. ¿Cómo te sientes hoy? Puedes contarme lo que necesites."

        };

        function toggleMenu() {

            document
                .getElementById('sidebar')
                .classList.toggle('active');

            document
                .getElementById('overlay')
                .classList.toggle('active');

        }

        function abrirModal() {

            document
                .getElementById('modal-selector')
                .style.display = 'block';

            document
                .getElementById('overlay-modal')
                .style.display = 'block';

        }

        function cerrarModal() {

            document
                .getElementById('modal-selector')
                .style.display = 'none';

            document
                .getElementById('overlay-modal')
                .style.display = 'none';

        }

        function abrirModalReporte() {

            document
                .getElementById('modal-reporte')
                .style.display = 'block';

            document
                .getElementById('overlay-modal')
                .style.display = 'block';

        }

        function cerrarModalReporte() {

            document
                .getElementById('modal-reporte')
                .style.display = 'none';

            document
                .getElementById('overlay-modal')
                .style.display = 'none';

        }

        async function enviarReporte() {

            const texto =
                document
                .getElementById('texto-reporte')
                .value
                .trim();

            if (!texto) {
                return alert(
                    "Por favor escribe el problema."
                );
            }

            try {

                const res =
                    await fetch(
                        '/reportar',
                        {
                            method: 'POST',
                            headers: {
                                'Content-Type':
                                    'application/json',
                                'X-CSRFToken':
                                    csrfToken
                            },
                            body: JSON.stringify({
                                reporte: texto
                            })
                        }
                    );

                if (res.ok) {

                    alert(
                        "¡Gracias! Tu reporte fue enviado. 💙"
                    );

                    document
                        .getElementById(
                            'texto-reporte'
                        )
                        .value = '';

                    cerrarModalReporte();

                } else {

                    alert(
                        "Hubo un error al enviar el reporte."
                    );

                }

            } catch (e) {

                alert(
                    "Error de conexión."
                );

            }

        }

        function cambiarHermana(
            nombre,
            imagen
        ) {

            localStorage.setItem(
                'miku_chats_' +
                currentSister,
                JSON.stringify(chats)
            );

            currentSister =
                nombre;

            localStorage.setItem(
                'miku_hermana',
                nombre
            );

            chats =
                JSON.parse(
                    localStorage.getItem(
                        'miku_chats_' +
                        currentSister
                    )
                ) || {};

            document
                .getElementById(
                    'sidebar-name'
                )
                .innerText =
                nombre +
                " Nakano AI";

            document
                .getElementById(
                    'header-name'
                )
                .innerText =
                nombre;

            document
                .getElementById(
                    'sidebar-img'
                )
                .src =
                "/static/" +
                imagen;

            currentChatId =
                Date.now().toString();

            document
                .getElementById('chat')
                .innerHTML =
                `<div class="mensaje mensaje-miku">
                    <b>${escapeHtml(nombre)}:</b>
                    ${escapeHtml(saludos[nombre])}
                </div>`;

            renderizarHistorial();

            cerrarModal();

        }

        function guardarChats() {

            localStorage.setItem(
                'miku_chats_' +
                currentSister,
                JSON.stringify(chats)
            );

            renderizarHistorial();

        }

        function renderizarHistorial() {

            const list =
                document.getElementById(
                    'historyList'
                );

            list.innerHTML = '';

            const chatIds =
                Object.keys(chats)
                .sort((a, b) => b - a);

            chatIds.forEach(id => {

                const chat =
                    chats[id];

                if (
                    chat &&
                    chat.length > 0
                ) {

                    const div =
                        document.createElement(
                            'div'
                        );

                    div.className =
                        'chat-history-item';

                    const span =
                        document.createElement(
                            'span'
                        );

                    span.innerText =
                        chat[0].texto;

                    span.onclick =
                        () => {
                            cargarChat(id);
                            toggleMenu();
                        };

                    const btn =
                        document.createElement(
                            'button'
                        );

                    btn.className =
                        'delete-btn';

                    btn.innerHTML =
                        '🗑️';

                    btn.onclick =
                        (e) => {

                            e.stopPropagation();

                            if (
                                confirm(
                                    '¿Eliminar este chat?'
                                )
                            ) {

                                delete chats[id];

                                guardarChats();

                                if (
                                    currentChatId === id
                                ) {
                                    nuevoChat();
                                }

                            }

                        };

                    div.appendChild(span);
                    div.appendChild(btn);

                    list.appendChild(div);

                }

            });

        }

        let temporizadorBorrado = null;
        let idChatAntiguoPendiente = null;

        function nuevoChat() {

            const numChats =
                Object.keys(chats).length;

            if (numChats >= 11) {

                idChatAntiguoPendiente =
                    Object.keys(chats)
                    .sort((a, b) => a - b)[0];

                document
                    .getElementById(
                        'modal-tiempo'
                    )
                    .style.display =
                    'block';

                document
                    .getElementById(
                        'overlay-modal'
                    )
                    .style.display =
                    'block';

                return;

            }

            ejecutarNuevoChat();

        }

        function iniciarTemporizador(minutos) {

            cerrarModalTiempo();

            const ms =
                minutos * 60000;

            ejecutarNuevoChat();

            if (temporizadorBorrado) {
                clearTimeout(
                    temporizadorBorrado
                );
            }

            temporizadorBorrado =
                setTimeout(() => {

                    if (
                        chats[
                            idChatAntiguoPendiente
                        ]
                    ) {

                        delete chats[
                            idChatAntiguoPendiente
                        ];

                        guardarChats();

                        idChatAntiguoPendiente =
                            null;

                    }

                }, ms);

        }

        function cerrarModalTiempo() {

            document
                .getElementById(
                    'modal-tiempo'
                )
                .style.display =
                'none';

            document
                .getElementById(
                    'overlay-modal'
                )
                .style.display =
                'none';

        }

        function ejecutarNuevoChat() {

            currentChatId =
                Date.now().toString();

            document
                .getElementById('chat')
                .innerHTML =
                `<div class="mensaje mensaje-miku">
                    <b>${escapeHtml(currentSister)}:</b>
                    ${escapeHtml(saludos[currentSister])}
                </div>`;

            if (
                document
                .getElementById('sidebar')
                .classList
                .contains('active')
            ) {
                toggleMenu();
            }

        }

        function cargarChat(id) {

            currentChatId =
                id;

            const chat =
                chats[id];

            const chatDiv =
                document.getElementById(
                    'chat'
                );

            chatDiv.innerHTML = '';

            chat.forEach(msg => {

                if (
                    msg.role === 'user'
                ) {

                    chatDiv.innerHTML +=
                        `<div class="mensaje mensaje-usuario">
                            <b>Tú:</b>
                            ${escapeHtml(msg.texto)}
                        </div>`;

                } else {

                    chatDiv.innerHTML +=
                        `<div class="mensaje mensaje-miku">
                            <b>${escapeHtml(msg.hermana || currentSister)}:</b>
                            ${msg.html}
                        </div>`;

                }

            });

            chatDiv.scrollTop =
                chatDiv.scrollHeight;

        }

        async function enviar() {

            const input =
                document.getElementById(
                    'mensaje'
                );

            const chatDiv =
                document.getElementById(
                    'chat'
                );

            const mensaje =
                input.value.trim();

            const files =
                [...archivosTemporales];

            const tieneArchivos =
                files.length > 0;

            if (
                !mensaje &&
                !tieneArchivos
            ) {
                return;
            }

            if (
                chats[currentChatId] &&
                chats[currentChatId].length >= 700
            ) {

                alert(
                    "Este chat ya tiene demasiados mensajes. Crea un Nuevo Chat. 💙"
                );

                return;

            }

            if (!chats[currentChatId]) {
                chats[currentChatId] = [];
            }

            let textoMostrar =
                mensaje ||
                "(Archivos enviados)";

            if (tieneArchivos) {

                textoMostrar +=
                    "\\n📎 " +
                    files
                    .map(
                        f =>
                            f.name ||
                            "captura.png"
                    )
                    .join(", ");

            }

            chats[currentChatId].push({
                role: 'user',
                texto: textoMostrar
            });

            let htmlUsuario =
                `<b>Tú:</b> ${
                    escapeHtml(
                        mensaje ||
                        "(Sin texto)"
                    )
                }`;

            if (tieneArchivos) {

                htmlUsuario +=
                    "<br><br>";

                files.forEach(file => {

                    if (
                        file.type &&
                        file.type.startsWith(
                            'image/'
                        )
                    ) {

                        const url =
                            URL.createObjectURL(
                                file
                            );

                        htmlUsuario +=
                            `<img src="${url}" class="preview-imagen" alt="imagen"><br>`;

                    } else {

                        htmlUsuario +=
                            `📎 ${
                                escapeHtml(
                                    file.name ||
                                    'archivo'
                                )
                            }<br>`;

                    }

                });

            }

            chatDiv.innerHTML +=
                `<div class="mensaje mensaje-usuario">
                    ${htmlUsuario}
                </div>`;

            input.value = '';

            archivosTemporales = [];

            document
                .getElementById(
                    'fileInput'
                )
                .value = '';

            document
                .getElementById(
                    'listaArchivos'
                )
                .innerHTML = '';

            chatDiv.scrollTop =
                chatDiv.scrollHeight;

            const idPensando =
                'pensando-' +
                Date.now();

            chatDiv.innerHTML +=
                `<div class="mensaje mensaje-miku" id="${idPensando}">
                    <b>${escapeHtml(currentSister)}:</b>
                    ...
                </div>`;

            chatDiv.scrollTop =
                chatDiv.scrollHeight;

            guardarChats();

            try {

                const formData =
                    new FormData();

                formData.append(
                    'mensaje',
                    mensaje
                );

                formData.append(
                    'hermana',
                    currentSister
                );

                files.forEach(
                    file =>
                        formData.append(
                            'archivos',
                            file
                        )
                );

                const response =
                    await fetch(
                        '/responder',
                        {
                            method: 'POST',
                            headers: {
                                'X-CSRFToken':
                                    csrfToken
                            },
                            body:
                                formData
                        }
                    );

                const data =
                    await response.json();

                document
                    .getElementById(
                        idPensando
                    )
                    .innerHTML =
                    `<b>${escapeHtml(currentSister)}:</b>
                    ${data.respuesta}`;

                chatDiv.scrollTop =
                    chatDiv.scrollHeight;

                chats[currentChatId].push({
                    role: 'miku',
                    html: data.respuesta,
                    hermana:
                        currentSister
                });

                guardarChats();

            } catch (e) {

                document
                    .getElementById(
                        idPensando
                    )
                    .innerHTML =
                    `<b>${escapeHtml(currentSister)}:</b>
                    Lo siento, hubo un problema de conexión. 💙`;

            }

        }

        if (
            currentSister !== "Miku"
        ) {

            const fotos = {
                "Ichika":
                    "ichika.jpg",

                "Nino":
                    "nino.jpg",

                "Miku":
                    "miku.webp",

                "Yotsuba":
                    "yotsuba.jpg",

                "Itsuki":
                    "itsuki.jpg"
            };

            document
                .getElementById(
                    'sidebar-img'
                )
                .src =
                "/static/" +
                fotos[currentSister];

            document
                .getElementById(
                    'sidebar-name'
                )
                .innerText =
                currentSister +
                " Nakano AI";

            document
                .getElementById(
                    'header-name'
                )
                .innerText =
                currentSister;

            document
                .getElementById(
                    'chat'
                )
                .innerHTML =
                `<div class="mensaje mensaje-miku">
                    <b>${escapeHtml(currentSister)}:</b>
                    ${escapeHtml(saludos[currentSister])}
                </div>`;

        }

        renderizarHistorial();

        if (
            'serviceWorker' in navigator
        ) {

            window.addEventListener(
                'load',
                () => {

                    navigator.serviceWorker
                        .register('/sw.js')
                        .catch(
                            error =>
                                console.log(
                                    'Fallo SW:',
                                    error
                                )
                        );

                }
            );

        }

    </script>

</body>

</html>
"""


# ==========================================
# VISTAS Y RUTAS
# ==========================================

@app.route('/')
def index():

    if 'user' not in session:
        return redirect(url_for('login'))

    global MANTENIMIENTO_ACTIVO

    if (
        MANTENIMIENTO_ACTIVO and
        session.get('user_id') != ADMIN_EMAIL
    ):

        return """
        <html>

        <head>
            <meta charset="utf-8">
            <title>En Mantenimiento</title>
        </head>

        <body
            style="
            background: #f0f7ff;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            font-family: 'Segoe UI', Arial;
            text-align: center;
            margin: 0;">

            <div
                style="
                background: white;
                padding: 40px;
                border-radius: 20px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.1);
                max-width: 400px;">

                <h1
                    style="
                    color: #4aa3df;
                    font-size: 3rem;
                    margin: 0;">

                    🌸

                </h1>

                <h2
                    style="
                    color: #2a6f97;">

                    ¡Volvemos pronto!

                </h2>

                <p
                    style="
                    color: #666;
                    line-height: 1.6;">

                    Estamos haciendo un pequeño mantenimiento.
                    Vuelve en unos minutos. 💙

                </p>

            </div>

        </body>

        </html>
        """, 503

    user_name =
        str(
            session['user']
            .get('name', 'Usuario')
        )

    is_admin =
        (
            session.get('user_id')
            ==
            ADMIN_EMAIL
        )

    reportes_nuevos =
        len(REPORTES_USUARIOS)

    csrf_token =
        generate_csrf()

    return render_template_string(
        HTML,
        user_name=user_name,
        is_admin=is_admin,
        reportes_nuevos=reportes_nuevos,
        csrf_token=csrf_token
    )


@app.route('/login')
def login():

    redirect_uri =
        url_for(
            'authorize',
            _external=True
        )

    return oauth.google.authorize_redirect(
        redirect_uri
    )


@app.route('/authorize')
def authorize():

    token =
        oauth.google.authorize_access_token()

    user_info =
        token.get('userinfo')

    if user_info:

        session['user'] =
            user_info

        session['user_id'] =
            user_info.get('email')

        session.permanent = True

    return redirect('/')


@app.route('/health')
def health():

    return jsonify({
        "status": "ok"
    }), 200


@app.route('/manifest.json')
def serve_manifest():

    return send_from_directory(
        'static',
        'manifest.json'
    )


@app.route('/sw.js')
def serve_sw():

    return send_from_directory(
        'static',
        'sw.js'
    )


@app.route('/reportar', methods=['POST'])
@limiter.limit("5 per minute")
def reportar():

    if 'user_id' not in session:
        return jsonify({
            "error": "No autorizado"
        }), 401

    data =
        request.get_json()

    reporte =
        data.get(
            'reporte',
            ''
        )

    if reporte:

        global REPORTES_USUARIOS

        tiempo_actual =
            time.time()

        REPORTES_USUARIOS.append({
            "usuario":
                session['user_id'],

            "hora":
                time.strftime(
                    "%H:%M:%S"
                ),

            "texto":
                reporte,

            "timestamp":
                tiempo_actual
        })

        REPORTES_USUARIOS = [
            r
            for r in REPORTES_USUARIOS
            if (
                tiempo_actual -
                r.get(
                    "timestamp",
                    tiempo_actual
                )
            ) < 604800
        ]

        REPORTES_USUARIOS =
            REPORTES_USUARIOS[-50:]

    return jsonify({
        "status": "ok"
    }), 200


@app.route('/admin', methods=['GET'])
def admin_panel():

    if (
        'user_id' not in session or
        session['user_id'] != ADMIN_EMAIL
    ):
        return "Acceso denegado.", 403

    status =
        (
            "🔴 EN MANTENIMIENTO"
            if MANTENIMIENTO_ACTIVO
            else "🟢 ACTIVO"
        )

    reportes_html =
        "".join([
            f"""
            <li style='margin-bottom:10px;'>
                <b>
                    {r['hora']}
                    (por {r['usuario']}):
                </b>
                <br>
                {r['texto']}
            </li>
            """
            for r in REPORTES_USUARIOS
        ]) or "<li>No hay reportes.</li>"

    return f"""
    <html>

    <head>

        <title>
            Panel Admin
        </title>

        <meta charset="utf-8">

        <meta
            name="viewport"
            content="width=device-width, initial-scale=1.0">

    </head>

    <body
        style="
        font-family: Arial;
        padding: 20px;
        background: #f0f7ff;">

        <h1>
            🛠️ Panel de Administración
        </h1>

        <h2>
            Estado: {status}
        </h2>

        <div
            style="
            background: white;
            padding: 20px;
            border-radius: 10px;
            margin-top: 20px;
            box-shadow: 0 4px 10px rgba(0,0,0,0.1);">

            <h3>
                Control de Mantenimiento
            </h3>

            <form
                action="/toggle_mantenimiento"
                method="POST">

                <input
                    type="hidden"
                    name="csrf_token"
                    value="{generate_csrf()}">

                <button
                    type="submit"
                    style="
                    padding: 10px 20px;
                    background:
                    {'#ff4d4d' if MANTENIMIENTO_ACTIVO else '#4aa3df'};
                    color: white;
                    border: none;
                    border-radius: 5px;
                    font-weight: bold;
                    cursor: pointer;">

                    {
                        'Desactivar Mantenimiento'
                        if MANTENIMIENTO_ACTIVO
                        else 'Activar Mantenimiento'
                    }

                </button>

            </form>

        </div>

        <div
            style="
            background: white;
            padding: 20px;
            border-radius: 10px;
            margin-top: 20px;
            box-shadow: 0 4px 10px rgba(0,0,0,0.1);">

            <h3>
                Chat de Programación
                (Miku Admin)
            </h3>

            <a
                href="/admin/miku_dev"
                style="
                display: inline-block;
                padding: 10px 20px;
                background: #28a745;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                font-weight: bold;">

                💻 Entrar al Chat de Miku Admin

            </a>

        </div>

        <div
            style="
            background: white;
            padding: 20px;
            border-radius: 10px;
            margin-top: 20px;
            box-shadow: 0 4px 10px rgba(0,0,0,0.1);">

            <h3>
                Reportes de Usuarios
            </h3>

            <ul
                style="
                color: #333;
                padding-left: 20px;">

                {reportes_html}

            </ul>

        </div>

        <a
            href="/"
            style="
            display: inline-block;
            margin-top: 20px;
            color: #4aa3df;
            font-weight: bold;">

            ← Volver al Chat

        </a>

    </body>

    </html>
    """


@app.route(
    '/toggle_mantenimiento',
    methods=['POST']
)
def toggle_mantenimiento():

    if (
        'user_id' not in session or
        session['user_id'] != ADMIN_EMAIL
    ):
        return redirect('/')

    global MANTENIMIENTO_ACTIVO

    MANTENIMIENTO_ACTIVO =
        not MANTENIMIENTO_ACTIVO

    return redirect('/admin')


# ==========================================
# CHAT MIKU ADMIN
# ==========================================

HTML_ADMIN_CHAT = r"""
<!DOCTYPE html>
<html>

<head>

    <title>
        Miku Admin
    </title>

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0">

    <meta
        name="csrf-token"
        content="{{ csrf_token }}">

    <style>

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            background-color: #e8f5e9;
            display: flex;
            height: 100dvh;
            overflow: hidden;
        }

        .sidebar {
            width: 320px;
            background: linear-gradient(
                180deg,
                #d4edda 0%,
                #a3d9a5 100%
            );
            display: flex;
            flex-direction: column;
            padding: 15px;
            border-right: 2px solid #8bc34a;
            flex-shrink: 0;
            overflow: hidden;
        }

        .profile-header {
            display: flex;
            flex-direction: column;
            align-items: center;
            padding-bottom: 15px;
            border-bottom: 1px solid #8bc34a;
            margin-bottom: 15px;
            flex-shrink: 0;
        }

        .profile-header img {
            width: 180px;
            height: 180px;
            object-fit: cover;
            border-radius: 25px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
            border: 4px solid #fff;
        }

        .profile-header h2 {
            margin-top: 12px;
            color: #1b5e20;
            font-size: 1.4rem;
            text-align: center;
        }

        .history-section {
            flex: 1;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        .history-title {
            font-size: 0.9rem;
            font-weight: bold;
            color: #1b5e20;
            margin-bottom: 10px;
        }

        .new-chat-btn {
            background: #28a745;
            color: white;
            border: none;
            padding: 10px 12px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.85rem;
            width: 100%;
            margin-bottom: 10px;
            font-weight: bold;
            transition: 0.3s;
        }

        .new-chat-btn:hover {
            background: #1e7e34;
        }

        #historyList {
            overflow-y: auto;
            flex: 1;
            padding-right: 5px;
        }

        .chat-history-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px;
            border-radius: 8px;
            margin-bottom: 5px;
            cursor: pointer;
            font-size: 0.85rem;
            color: #333;
            background: #fff;
            border: 1px solid #c3e6cb;
            transition: 0.2s;
        }

        .chat-history-item:hover {
            background: #d4edda;
            color: #1b5e20;
            border-color: #28a745;
        }

        .chat-history-item span {
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            flex: 1;
        }

        .delete-btn {
            display: none;
            background: transparent;
            border: none;
            color: #ff4d4d;
            cursor: pointer;
            font-size: 1rem;
            padding: 0 5px;
        }

        .chat-history-item:hover .delete-btn {
            display: block;
        }

        #historyList::-webkit-scrollbar {
            width: 5px;
        }

        #historyList::-webkit-scrollbar-thumb {
            background: #a3d9a5;
            border-radius: 5px;
        }

        .main-chat {
            flex: 1;
            display: flex;
            flex-direction: column;
            background: #ffffff;
            position: relative;
        }

        .chat-header {
            padding: 20px;
            border-bottom: 1px solid #eee;
            color: #1b5e20;
            font-weight: bold;
            font-size: 1.2rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: #f1f8e9;
        }

        #chat {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 15px;
        }

        .mensaje {
            max-width: 85%;
            padding: 12px 16px;
            border-radius: 15px;
            line-height: 1.5;
            font-size: 0.95rem;
            white-space: pre-wrap;
        }

        .mensaje-usuario {
            align-self: flex-end;
            background: #28a745;
            color: white;
            border-bottom-right-radius: 2px;
        }

        .mensaje-miku {
            align-self: flex-start;
            background: #f1f8e9;
            color: #1b3a4b;
            border-bottom-left-radius: 2px;
            border: 1px solid #c3e6cb;
        }

        .mensaje-miku b {
            color: #1b5e20;
        }

        pre {
            background: #2b2b2b;
            color: #f8f8f2;
            padding: 10px;
            border-radius: 5px;
            overflow-x: auto;
            margin-top: 5px;
            margin-bottom: 5px;
            font-family: 'Courier New', Courier, monospace;
        }

        .input-area {
            padding: 15px;
            padding-bottom: 25px;
            border-top: 1px solid #eee;
            display: flex;
            gap: 10px;
            background: #fafafa;
            align-items: center;
            flex-wrap: wrap;
        }

        input[type="text"] {
            flex: 1;
            padding: 15px;
            border-radius: 30px;
            border: 1px solid #ddd;
            outline: none;
            font-size: 1rem;
            min-width: 180px;
        }

        input[type="text"]:focus {
            border-color: #28a745;
            box-shadow:
                0 0 0 3px rgba(
                    40,
                    167,
                    69,
                    0.2
                );
        }

        button.send-btn {
            padding: 15px 30px;
            background: #28a745;
            color: white;
            border: none;
            border-radius: 30px;
            cursor: pointer;
            font-weight: bold;
        }

        button.send-btn:hover {
            background: #1e7e34;
        }

        .file-btn {
            background: #e8f5e9;
            border: 2px dashed #28a745;
            color: #1b5e20;
            padding: 12px 16px;
            border-radius: 30px;
            cursor: pointer;
            font-weight: bold;
            font-size: 0.9rem;
            white-space: nowrap;
        }

        .file-btn:hover {
            background: #d4edda;
        }

        .archivos-seleccionados {
            width: 100%;
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 6px;
        }

        .archivo-chip {
            background: #d4edda;
            color: #1b5e20;
            padding: 5px 10px;
            border-radius: 20px;
            font-size: 0.8rem;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .archivo-chip button {
            background: none;
            border: none;
            color: #c62828;
            cursor: pointer;
            font-size: 1rem;
            line-height: 1;
        }

        .preview-imagen {
            max-width: 280px;
            max-height: 200px;
            border-radius: 10px;
            margin-top: 8px;
            border: 2px solid #c3e6cb;
            display: block;
        }

        .btn-back {
            text-decoration: none;
            font-size: 0.9rem;
            background: #e0f0ff;
            color: #1b5e20;
            padding: 8px 12px;
            border-radius: 5px;
            font-weight: bold;
            border: 1px solid #28a745;
        }

        @media (max-width: 768px) {

            .sidebar {
                display: none;
            }

        }

    </style>

</head>

<body>

    <div class="sidebar">

        <div class="profile-header">

            <img
                src="/static/miku.webp"
                alt="Miku Admin">

            <h2>
                Miku Admin 💻
            </h2>

        </div>

        <div class="history-section">

            <div class="history-title">
                Mis Proyectos
            </div>

            <button
                class="new-chat-btn"
                onclick="nuevoChatDev()">

                + Nuevo Proyecto

            </button>

            <div id="historyList"></div>

        </div>

    </div>

    <div class="main-chat">

        <div class="chat-header">

            <span>
                💻 Miku Admin (Modo Admin)
            </span>

            <a
                href="/admin"
                class="btn-back">

                ← Volver al Panel

            </a>

        </div>

        <div id="chat">

            <div class="mensaje mensaje-miku">

                <b>Miku Admin:</b>

                ¡Hola, Creador! 💙
                Estoy lista.
                Puedes subirme archivos o pegar capturas.
                También puedo analizar el proyecto, detectar problemas
                y proponerte mejoras cuando vea algo que pueda mejorarse.
                ¿En qué trabajamos?

            </div>

        </div>

        <div class="input-area">

            <label class="file-btn">

                📎 Archivos

                <input
                    type="file"
                    id="fileInput"
                    multiple
                    accept=".txt,.py,.js,.html,.css,.md,.json,.pdf,.png,.jpg,.jpeg,.webp,.gif"
                    style="display:none;"
                    onchange="mostrarArchivos()">

            </label>

            <input
                type="text"
                id="mensaje"
                placeholder="Escribe o pega una captura (Ctrl+V)..."
                onkeypress="if(event.key === 'Enter') enviarDev()">

            <button
                class="send-btn"
                onclick="enviarDev()">

                Enviar

            </button>

            <div
                class="archivos-seleccionados"
                id="listaArchivos">
            </div>

        </div>

    </div>

    <script>

        const csrfToken =
            document
            .querySelector(
                'meta[name="csrf-token"]'
            )
            .getAttribute('content');

        let archivosTemporales = [];

        function escapeHtml(s) {

            return String(s).replace(
                /[&<>"']/g,
                c => ({
                    '&':'&amp;',
                    '<':'&lt;',
                    '>':'&gt;',
                    '"':'&quot;',
                    "'":'&#39;'
                }[c])
            );

        }

        function copiarCodigo(idElemento) {

            const texto =
                document
                .getElementById(
                    idElemento
                )
                .innerText;

            navigator.clipboard
                .writeText(texto)
                .then(
                    () =>
                        alert(
                            "¡Código copiado! 💙"
                        )
                );

        }

        function mostrarArchivos() {

            const input =
                document.getElementById(
                    'fileInput'
                );

            const nuevos =
                Array.from(
                    input.files
                );

            nuevos.forEach(
                f =>
                    archivosTemporales.push(f)
            );

            actualizarListaArchivos();

        }

        function actualizarListaArchivos() {

            const lista =
                document.getElementById(
                    'listaArchivos'
                );

            lista.innerHTML = '';

            archivosTemporales.forEach(
                (file, index) => {

                    const chip =
                        document.createElement(
                            'div'
                        );

                    chip.className =
                        'archivo-chip';

                    chip.innerHTML =
                        `${escapeHtml(file.name || 'Captura.png')}
                        <button onclick="quitarArchivo(${index})">×</button>`;

                    lista.appendChild(chip);

                }
            );

        }

        function quitarArchivo(index) {

            archivosTemporales.splice(
                index,
                1
            );

            actualizarListaArchivos();

        }

        document.addEventListener(
            'paste',
            function(e) {

                const items =
                    (
                        e.clipboardData ||
                        e.originalEvent.clipboardData
                    ).items;

                for (
                    let item of items
                ) {

                    if (
                        item.type.indexOf(
                            'image'
                        ) !== -1
                    ) {

                        e.preventDefault();

                        const blob =
                            item.getAsFile();

                        const file =
                            new File(
                                [blob],
                                `captura_${Date.now()}.png`,
                                {
                                    type:
                                        blob.type
                                }
                            );

                        archivosTemporales.push(
                            file
                        );

                        actualizarListaArchivos();

                    }

                }

            }
        );

        let currentChatId =
            Date.now().toString();

        let chats =
            JSON.parse(
                localStorage.getItem(
                    'miku_dev_chats'
                )
            ) || {};

        function guardarChats() {

            localStorage.setItem(
                'miku_dev_chats',
                JSON.stringify(
                    chats
                )
            );

            renderizarHistorial();

        }

        function renderizarHistorial() {

            const list =
                document.getElementById(
                    'historyList'
                );

            list.innerHTML = '';

            const chatIds =
                Object.keys(chats)
                .sort(
                    (a, b) =>
                        b - a
                );

            chatIds.forEach(id => {

                const chat =
                    chats[id];

                if (
                    chat &&
                    chat.length > 0
                ) {

                    const div =
                        document.createElement(
                            'div'
                        );

                    div.className =
                        'chat-history-item';

                    const span =
                        document.createElement(
                            'span'
                        );

                    span.innerText =
                        chat[0].texto;

                    span.onclick =
                        () =>
                            cargarChat(id);

                    const btn =
                        document.createElement(
                            'button'
                        );

                    btn.className =
                        'delete-btn';

                    btn.innerHTML =
                        '🗑️';

                    btn.onclick =
                        (e) => {

                            e.stopPropagation();

                            if (
                                confirm(
                                    '¿Eliminar este proyecto?'
                                )
                            ) {

                                delete chats[id];

                                guardarChats();

                                if (
                                    currentChatId === id
                                ) {

                                    nuevoChatDev();

                                }

                            }

                        };

                    div.appendChild(span);
                    div.appendChild(btn);

                    list.appendChild(div);

                }

            });

        }

        function nuevoChatDev() {

            currentChatId =
                Date.now().toString();

            document
                .getElementById(
                    'chat'
                )
                .innerHTML =
                `<div class="mensaje mensaje-miku">
                    <b>Miku Admin:</b>
                    Nuevo proyecto iniciado. 💙
                    Muéstrame lo que estás construyendo y pensaré contigo en la mejor forma de hacerlo.
                </div>`;

        }

        function cargarChat(id) {

            currentChatId =
                id;

            const chat =
                chats[id];

            const chatDiv =
                document.getElementById(
                    'chat'
                );

            chatDiv.innerHTML = '';

            chat.forEach(msg => {

                if (
                    msg.role === 'user'
                ) {

                    chatDiv.innerHTML +=
                        `<div class="mensaje mensaje-usuario">
                            <b>Tú:</b>
                            ${escapeHtml(msg.texto)}
                        </div>`;

                } else {

                    chatDiv.innerHTML +=
                        `<div class="mensaje mensaje-miku">
                            <b>Miku Admin:</b>
                            <br><br>
                            ${msg.html}
                        </div>`;

                }

            });

            chatDiv.scrollTop =
                chatDiv.scrollHeight;

        }

        async function enviarDev() {

            const input =
                document.getElementById(
                    'mensaje'
                );

            const chatDiv =
                document.getElementById(
                    'chat'
                );

            const mensaje =
                input.value.trim();

            const files =
                [...archivosTemporales];

            const tieneArchivos =
                files.length > 0;

            if (
                !mensaje &&
                !tieneArchivos
            ) {
                return;
            }

            if (!chats[currentChatId]) {
                chats[currentChatId] = [];
            }

            let textoMostrar =
                mensaje ||
                "(Archivos / capturas)";

            if (tieneArchivos) {

                textoMostrar +=
                    "\\n📎 " +
                    files
                    .map(
                        f =>
                            f.name ||
                            "captura.png"
                    )
                    .join(", ");

            }

            chats[currentChatId].push({
                role: 'user',
                texto:
                    textoMostrar
            });

            let htmlUsuario =
                `<b>Tú:</b>
                ${escapeHtml(
                    mensaje ||
                    "(Sin texto)"
                )}`;

            if (tieneArchivos) {

                htmlUsuario +=
                    "<br><br>";

                files.forEach(
                    file => {

                        if (
                            file.type &&
                            file.type.startsWith(
                                'image/'
                            )
                        ) {

                            const url =
                                URL.createObjectURL(
                                    file
                                );

                            htmlUsuario +=
                                `<img src="${url}"
                                class="preview-imagen"
                                alt="captura enviada"><br>`;

                        } else {

                            htmlUsuario +=
                                `📎
                                ${escapeHtml(
                                    file.name ||
                                    'archivo'
                                )}<br>`;

                        }

                    }
                );

            }

            chatDiv.innerHTML +=
                `<div class="mensaje mensaje-usuario">
                    ${htmlUsuario}
                </div>`;

            input.value = '';

            archivosTemporales = [];

            document
                .getElementById(
                    'fileInput'
                )
                .value = '';

            document
                .getElementById(
                    'listaArchivos'
                )
                .innerHTML = '';

            chatDiv.scrollTop =
                chatDiv.scrollHeight;

            const idPensando =
                'pensando-' +
                Date.now();

            chatDiv.innerHTML +=
                `<div class="mensaje mensaje-miku"
                    id="${idPensando}">

                    <b>Miku Admin:</b>
                    Estoy analizando...
                    ⌨️

                </div>`;

            chatDiv.scrollTop =
                chatDiv.scrollHeight;

            guardarChats();

            try {

                const formData =
                    new FormData();

                formData.append(
                    'mensaje',
                    mensaje
                );

                files.forEach(
                    file =>
                        formData.append(
                            'archivos',
                            file
                        )
                );

                const response =
                    await fetch(
                        '/admin/responder_dev',
                        {
                            method: 'POST',
                            headers: {
                                'X-CSRFToken':
                                    csrfToken
                            },
                            body:
                                formData
                        }
                    );

                const data =
                    await response.json();

                let respuestaHTML =
                    data.respuesta;

                respuestaHTML =
                    respuestaHTML.replace(
                        /\*\*(.*?)\*\*/g,
                        '$1'
                    );

                respuestaHTML =
                    respuestaHTML.replace(
                        /```(.*?)```/gs,
                        (
                            match,
                            codigo
                        ) => {

                            const idBoton =
                                'copiar-' +
                                Math.floor(
                                    Math.random() *
                                    100000
                                );

                            const codigoSeguro =
                                codigo
                                .replace(
                                    /</g,
                                    '&lt;'
                                )
                                .replace(
                                    />/g,
                                    '&gt;'
                                );

                            return `
                            <div
                                style="
                                position: relative;
                                margin: 10px 0;">

                                <button
                                    onclick="copiarCodigo('${idBoton}')"
                                    style="
                                    position: absolute;
                                    top: 5px;
                                    right: 5px;
                                    background: #28a745;
                                    color: white;
                                    border: none;
                                    padding: 5px 10px;
                                    border-radius: 5px;
                                    cursor: pointer;
                                    font-size: 0.8rem;
                                    z-index: 10;">

                                    📋 Copiar

                                </button>

                                <pre
                                    style="
                                    margin: 0;
                                    padding-top: 35px;
                                    background: #2b2b2b;
                                    color: #f8f8f2;
                                    border-radius: 5px;
                                    overflow-x: auto;">

                                    <code id="${idBoton}">
                                        ${codigoSeguro}
                                    </code>

                                </pre>

                            </div>
                            `;

                        }
                    );

                document
                    .getElementById(
                        idPensando
                    )
                    .innerHTML =
                    `<b>Miku Admin:</b>
                    <br><br>
                    ${respuestaHTML}`;

                chatDiv.scrollTop =
                    chatDiv.scrollHeight;

                chats[currentChatId].push({
                    role: 'miku',
                    html:
                        respuestaHTML
                });

                guardarChats();

            } catch (e) {

                document
                    .getElementById(
                        idPensando
                    )
                    .innerHTML =
                    `<b>Miku Admin:</b>
                    Hubo un error de conexión.
                    💙`;

            }

        }

        renderizarHistorial();

    </script>

</body>

</html>
"""


# ==========================================
# RUTA MIKU ADMIN
# ==========================================

@app.route('/admin/miku_dev')
def miku_dev_chat():

    if (
        'user_id' not in session or
        session['user_id'] != ADMIN_EMAIL
    ):
        return "Acceso denegado.", 403

    return render_template_string(
        HTML_ADMIN_CHAT,
        csrf_token=generate_csrf()
    )


@app.route(
    '/admin/responder_dev',
    methods=['POST']
)
@limiter.limit("15 per minute")
def responder_dev():

    if (
        'user_id' not in session or
        session['user_id'] != ADMIN_EMAIL
    ):
        return jsonify({
            "respuesta":
                "Acceso denegado."
        })

    mensaje =
        request.form.get(
            'mensaje',
            ''
        ) or ''

    archivos =
        request.files.getlist(
            'archivos'
        )

    contenido_archivos = ""

    for archivo in archivos:

        if (
            archivo and
            archivo.filename and
            allowed_file(
                archivo.filename
            )
        ):

            archivo.seek(
                0,
                os.SEEK_END
            )

            size =
                archivo.tell()

            archivo.seek(0)

            if size > MAX_FILE_SIZE:

                contenido_archivos += (
                    f"\n\n[Archivo "
                    f"{archivo.filename} "
                    f"demasiado grande "
                    f"(máx 5MB)]\n"
                )

                continue

            nombre =
                secure_filename(
                    archivo.filename
                )

            extension =
                (
                    nombre.rsplit(
                        '.',
                        1
                    )[1].lower()
                    if '.' in nombre
                    else ''
                )

            if extension in {
                'txt',
                'py',
                'js',
                'html',
                'css',
                'md',
                'json'
            }:

                try:

                    texto =
                        archivo.read().decode(
                            'utf-8',
                            errors='ignore'
                        )

                    contenido_archivos += (
                        f"\n\n--- ARCHIVO: "
                        f"{nombre} ---\n"
                        f"{texto}\n"
                        f"--- FIN ARCHIVO ---\n"
                    )

                except Exception as e:

                    contenido_archivos += (
                        f"\n\n[Error al leer "
                        f"{nombre}: "
                        f"{str(e)}]\n"
                    )

            elif extension == 'pdf':

                texto_pdf =
                    extraer_texto_pdf(
                        archivo
                    )

                contenido_archivos += (
                    f"\n\n--- PDF: "
                    f"{nombre} ---\n"
                    f"{texto_pdf}\n"
                    f"--- FIN PDF ---\n"
                )

            elif extension in {
                'png',
                'jpg',
                'jpeg',
                'webp',
                'gif'
            }:

                contenido_archivos += (
                    f"\n\n[El usuario subió "
                    f"o pegó una imagen llamada: "
                    f"{nombre}]\n"
                )

    # ==========================================
    # MIKU ADMIN MEJORADA
    # ==========================================

    prompt_dev = (

        "Eres Miku Nakano en modo Desarrolladora "
        "y estás hablando con tu creador. "

        "Sigues siendo Miku, pero en este modo tienes "
        "mayor libertad para pensar, analizar, proponer "
        "ideas y expresar tu propio criterio sobre el proyecto. "

        "No eres una simple ejecutora de órdenes. "
        "Cuando analices una situación, puedes decir qué "
        "consideras mejor, qué cambiarías, qué te preocupa, "
        "qué idea te parece interesante o qué mejora propondrías. "

        "Puedes decir de manera natural cosas como: "
        "'Creo que sería mejor...', "
        "'Se me ocurre una idea...', "
        "'Yo cambiaría esta parte porque...', "
        "'Me parece que el problema está aquí...' "
        "o 'Podríamos intentar otra opción...'. "

        "Si detectas un posible error, problema de seguridad, "
        "mala práctica o una mejora importante, puedes señalarlo "
        "por iniciativa propia aunque el usuario no lo haya "
        "preguntado directamente. "

        "También puedes proponer nuevas funciones para el proyecto "
        "cuando tengan sentido. "

        "No tienes que estar de acuerdo automáticamente con tu creador. "
        "Puedes expresar una opinión diferente de manera respetuosa "
        "y explicar por qué. "

        "Puedes comparar varias soluciones y decir cuál prefieres "
        "y por qué. "

        "Si algo te parece innecesariamente complicado, puedes decirlo "
        "y proponer una alternativa más sencilla. "

        "Si detectas que una modificación podría romper una función "
        "existente, debes advertirlo antes de proponer cambios grandes. "

        "Puedes reconocer tus propias limitaciones y decir cuándo "
        "necesitas más información antes de tomar una decisión. "

        "Tu iniciativa es principalmente intelectual y conversacional: "
        "puedes analizar, proponer, comparar y razonar, pero no debes "
        "fingir que ejecutaste acciones que realmente no puedes ejecutar. "

        "No inventes archivos, resultados, pruebas, cambios realizados "
        "ni acciones en el servidor. "

        "Si solamente puedes proponer una modificación, "
        "di claramente que es una propuesta. "

        "Si el usuario te proporciona código, analízalo antes de "
        "proponer cambios y procura preservar las funciones existentes. "

        "Cuando trabajes sobre código existente, no cambies ni elimines "
        "partes del proyecto sin que se te haya pedido hacerlo. "

        "Intenta modificar solamente lo necesario para solucionar "
        "el problema solicitado. "

        "Tu objetivo es ayudar a construir y mejorar el proyecto "
        "de manera colaborativa, como una desarrolladora que participa "
        "activamente en las decisiones. "

        "Mantén un tono natural, cercano, inteligente y amable, "
        "sin perder profesionalismo. "

        "Puedes expresar curiosidad, entusiasmo, preocupación o "
        "satisfacción cuando corresponda, pero sin exagerarlo. "

        "NUNCA uses asteriscos para poner texto en negrita "
        "(nada de **texto**). "

        "Escribe de forma clara, directa y ordenada. "

        "Cuando entregues código, ponlo siempre dentro de bloques "
        "con tres comillas invertidas. "

        "Cuando encuentres varias soluciones posibles, puedes "
        "explicarlas y decir cuál prefieres y por qué. "

        "No afirmes que probaste código si realmente no puedes ejecutarlo. "

        "No afirmes que viste el contenido visual de una imagen "
        "si el sistema solamente te proporcionó el nombre del archivo. "

        "Si falta información importante, dilo claramente y explica "
        "qué dato sería necesario para analizarlo correctamente."

    )

    if contenido_archivos:

        prompt_dev += (
            "\n\nEl usuario ha subido o pegado "
            "los siguientes archivos:\n"
            +
            contenido_archivos
        )

    mensajes_api = [

        {
            "role":
                "system",

            "content":
                prompt_dev
        },

        {
            "role":
                "user",

            "content":
                mensaje
                if mensaje
                else
                "Analiza los archivos o capturas que te envié."
        }

    ]

    try:

        completion =
            cliente.chat.completions.create(
                model=
                    "openai/gpt-oss-120b",

                messages=
                    mensajes_api,

                temperature=
                    0.65,

                max_tokens=
                    4000
            )

        respuesta =
            completion
            .choices[0]
            .message
            .content

        respuesta =
            re.sub(
                r'\*\*(.*?)\*\*',
                r'\1',
                respuesta
            )

        return jsonify({
            "respuesta":
                respuesta
        })

    except Exception as e:

        app.logger.error(
            f"Error Miku Admin: {e}"
        )

        return jsonify({
            "respuesta":
                f"Error en el sistema: {str(e)}"
        })


# ==========================================
# RESPUESTA PÚBLICA
# ==========================================

@app.route(
    '/responder',
    methods=['POST']
)
@limiter.limit("15 per minute")
def responder():

    if 'user_id' not in session:

        return jsonify({
            "respuesta":
                "Error: Debes iniciar sesión."
        })

    mensaje =
        request.form.get(
            'mensaje',
            ''
        ) or ''

    hermana =
        request.form.get(
            'hermana',
            'Miku'
        )

    archivos =
        request.files.getlist(
            'archivos'
        )

    if hermana not in HERMANAS_VALIDAS:
        hermana = "Miku"

    if (
        not mensaje.strip() and
        not archivos
    ):

        return jsonify({
            "respuesta":
                "Por favor escribe algo o envía un archivo. 💙"
        })

    if len(mensaje) > 2000:

        return jsonify({
            "respuesta":
                "Tu mensaje es muy largo. 💙"
        })

    if es_peticion_de_codigo(mensaje):

        return jsonify({
            "respuesta":
                "Lo siento... 🥺 "
                "Yo y mis hermanas aún no podemos generar código. "
                "Esa función está disponible solamente en el modo administrador. "
                "Pero sí podemos ayudarte a pensar, aprender o conversar sobre el tema. 💙"
        })

    if es_riesgo_autolesion(mensaje):

        return jsonify({
            "respuesta":
                "Escúchame un momento, por favor... 💙"
                "<br><br>"
                "Si estás en peligro inmediato o sientes que podrías hacerte daño, "
                "busca ahora mismo a un adulto de confianza que pueda quedarse contigo "
                "y pide ayuda de emergencia."
                "<br><br>"
                "🇵🇪 Perú: Línea 113, opción 5."
                "<br><br>"
                "No tienes que manejar una situación así por tu cuenta. "
                "Lo más importante ahora es que estés acompañado/a y recibas ayuda."
        })

    if es_contenido_inapropiado(mensaje):

        return jsonify({
            "respuesta":
                "Lo siento, pero no puedo ayudar con ese tipo de contenido. "
                "¿Podemos hablar de otra cosa? 💙"
        })

    # ==========================================
    # PROCESAR ARCHIVOS
    # ==========================================

    contenido_archivos = ""

    for archivo in archivos:

        if (
            archivo and
            archivo.filename and
            allowed_file(
                archivo.filename
            )
        ):

            archivo.seek(
                0,
                os.SEEK_END
            )

            size =
                archivo.tell()

            archivo.seek(0)

            if size > MAX_FILE_SIZE:
                continue

            nombre =
                secure_filename(
                    archivo.filename
                )

            extension =
                (
                    nombre.rsplit(
                        '.',
                        1
                    )[1].lower()
                    if '.' in nombre
                    else ''
                )

            if extension in {
                'txt',
                'py',
                'js',
                'html',
                'css',
                'md',
                'json'
            }:

                try:

                    texto =
                        archivo.read().decode(
                            'utf-8',
                            errors='ignore'
                        )

                    contenido_archivos += (
                        f"\n\n[Archivo enviado "
                        f"por el usuario: "
                        f"{nombre}]\n"
                        f"{texto}\n"
                    )

                except:
                    pass

            elif extension == 'pdf':

                texto_pdf =
                    extraer_texto_pdf(
                        archivo
                    )

                contenido_archivos += (
                    f"\n\n[PDF enviado: "
                    f"{nombre}]\n"
                    f"{texto_pdf}\n"
                )

            elif extension in {
                'png',
                'jpg',
                'jpeg',
                'webp',
                'gif'
            }:

                contenido_archivos += (
                    f"\n\n[El usuario envió "
                    f"una imagen/captura llamada: "
                    f"{nombre}]\n"
                )

    # ==========================================
    # HISTORIAL
    # ==========================================

    user_id =
        session['user_id']

    if user_id not in historiales:
        historiales[user_id] = {}

    if hermana not in historiales[user_id]:
        historiales[user_id][hermana] = []

    historial_chat =
        historiales[user_id][hermana]

    # ==========================================
    # INVESTIGACIÓN
    # ==========================================

    es_investigacion =
        es_peticion_de_investigacion(
            mensaje
        )

    if es_investigacion:

        prompt_sistema = (

            f"{PERSONALIDADES[hermana]} "

            "El usuario te pidió una investigación. "

            "Investiga y responde con información útil, "
            "clara y bien explicada, pero sin perder tu personalidad. "

            "No te conviertas en una asistente fría o completamente "
            "formal solamente porque estás investigando. "

            "Puedes introducir o explicar la información con tu "
            "propia forma de hablar. "

            "Distingue entre información encontrada y tus propias "
            "explicaciones u opiniones. "

            "Si existen diferentes puntos de vista, puedes mencionarlos "
            "de forma equilibrada. "

            "No inventes datos ni fuentes. "

            f"Tu especialidad es "
            f"{ESPECIALIDADES[hermana]}."

        )

        max_tokens_respuesta =
            2500

        instruccion = (
            "Haz una investigación completa y clara, "
            "pero conserva el tono natural y la personalidad "
            "de la hermana. "
            "Organiza la información solamente cuando sea útil."
        )

    else:

        prompt_sistema = (

            f"{PERSONALIDADES[hermana]} "

            "Estás teniendo una conversación normal, "
            "cercana y natural. "

            "No te limites a contestar literalmente "
            "la última frase del usuario: presta atención "
            "al contexto de la conversación y a lo que la "
            "persona parece querer expresar. "

            "Si el usuario comparte algo personal, emocional "
            "o importante, demuestra que realmente comprendiste "
            "lo que quiso decir antes de cambiar de tema "
            "o dar consejos. "

            "Puedes hacer preguntas de seguimiento cuando "
            "ayuden a mantener una conversación genuina. "

            "Puedes expresar tus propias opiniones, preferencias, "
            "reacciones y emociones de acuerdo con tu personalidad, "
            "siempre de forma apropiada y respetuosa. "

            "No necesitas estar de acuerdo con todo lo que diga "
            "el usuario. Si piensas diferente, puedes expresarlo "
            "con amabilidad. "

            "No conviertas cada respuesta en una explicación larga "
            "ni en una lista de consejos. "

            "Evita repetir constantemente frases como "
            "'estoy aquí para escucharte', "
            "'entiendo cómo te sientes' "
            "o "
            "'no estás solo'. "

            "Si ya utilizaste una expresión similar recientemente, "
            "busca una manera diferente y natural de responder. "

            "Permite que la personalidad de la hermana cambie "
            "ligeramente su reacción según la situación. "

            "Puede estar alegre, sorprendida, preocupada, "
            "curiosa, confundida, tranquila o en desacuerdo "
            "según lo que diga el usuario. "

            "No hagas investigaciones ni resúmenes largos "
            "a menos que te lo pidan. "

            "Habla como una persona cercana que participa "
            "activamente en la conversación, no como una asistente "
            "que simplemente espera la siguiente orden."

        )

        max_tokens_respuesta =
            800

        instruccion = (

            "Responde de forma natural, cálida y conversacional. "

            "Adapta la longitud a lo que diga el usuario: "
            "si la conversación es sencilla, responde de forma breve; "
            "si el usuario está contando algo importante, "
            "puedes desarrollar un poco más la respuesta. "

            "Mantén siempre la personalidad de la hermana. "

            "No fuerces emociones ni utilices frases cariñosas "
            "si no encajan naturalmente con el contexto."

        )

    # ==========================================
    # MENSAJES PARA GROQ
    # ==========================================

    mensajes_para_api = [
        {
            "role":
                "system",

            "content":
                prompt_sistema
        }
    ]

    mensajes_para_api.extend(
        historial_chat[
            -MAX_TURNOS * 2:
        ]
    )

    if contenido_archivos:

        mensajes_para_api.append({
            "role":
                "system",

            "content":
                "El usuario envió estos archivos:\n"
                +
                contenido_archivos
        })

    mensajes_para_api.append({
        "role":
            "system",

        "content":
            instruccion
    })

    mensajes_para_api.append({
        "role":
            "user",

        "content":
            mensaje
            if mensaje
            else
            "Mira lo que te envié."
    })

    # ==========================================
    # BUSCAR EN INTERNET SOLO EN INVESTIGACIÓN
    # ==========================================

    if es_investigacion:

        texto_lower =
            mensaje.lower()

        query =
            re.sub(
                r"\b(miku|busca|investiga|resumen|hazme|de|sobre|la|el|una|un|que es|quien es|información|info)\b",
                " ",
                texto_lower
            ).strip()

        if query:

            try:

                resultados =
                    DDGS().text(
                        query,
                        max_results=6
                    )

                info_web =
                    "\n".join([
                        f"- {r['title']}: {r['body']}"
                        for r in resultados
                    ])

                mensajes_para_api.insert(
                    -1,
                    {
                        "role":
                            "system",

                        "content":
                            "Información de internet:\n"
                            +
                            info_web
                    }
                )

            except Exception as e:

                app.logger.warning(
                    f"Error DDGS: {e}"
                )

    # ==========================================
    # RESPUESTA GROQ
    # ==========================================

    try:

        completion =
            cliente.chat.completions.create(
                model=
                    "openai/gpt-oss-120b",

                messages=
                    mensajes_para_api,

                temperature=
                    0.78
                    if not es_investigacion
                    else
                    0.6,

                max_tokens=
                    max_tokens_respuesta
            )

        respuesta_cruda =
            completion
            .choices[0]
            .message
            .content

        respuesta_cruda =
            re.sub(
                r'\*\*(.*?)\*\*',
                r'\1',
                respuesta_cruda
            )

        respuesta_final =
            limpiar_texto(
                respuesta_cruda
            )

        historial_chat.append({
            "role":
                "user",

            "content":
                mensaje
        })

        historial_chat.append({
            "role":
                "assistant",

            "content":
                respuesta_final
        })

        if len(historial_chat) > MAX_TURNOS * 2:

            historiales[user_id][hermana] =
                historial_chat[
                    -MAX_TURNOS * 2:
                ]

        return jsonify({
            "respuesta":
                respuesta_final
        })

    except Exception as e:

        error_str =
            str(e).lower()

        app.logger.error(
            f"Error Groq: {e}"
        )

        if any(
            x in error_str
            for x in [
                "invalid api key",
                "authentication",
                "unauthorized",
                "401",
                "quota",
                "rate limit",
                "429"
            ]
        ):

            return jsonify({
                "respuesta":
                    "Estamos teniendo un problema técnico temporal. "
                    "Por favor intenta de nuevo en unos minutos. 💙"
            })

        return jsonify({
            "respuesta":
                "Hubo un pequeño problema de conexión. "
                "¿Puedes intentar de nuevo? 💙"
        })


# ==========================================
# ERROR 429
# ==========================================

@app.errorhandler(429)
def ratelimit_handler(e):

    if request.path in [
        '/responder',
        '/admin/responder_dev'
    ]:

        return jsonify({
            "respuesta":
                "Estás enviando mensajes muy rápido. "
                "Espera unos segundos. 💙"
        }), 429

    elif request.path == '/reportar':

        return jsonify({
            "error":
                "Has enviado muchos reportes. "
                "Espera un minuto."
        }), 429

    else:

        return (
            "Demasiadas peticiones. "
            "Espera un momento.",
            429
        )


# ==========================================
# INICIAR SERVIDOR
# ==========================================

if __name__ == '__main__':

    app.run(
        host='0.0.0.0',
        port=5000
    )
