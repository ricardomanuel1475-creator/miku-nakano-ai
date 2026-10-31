from flask import (
    Flask, render_template_string, request,
    jsonify, session, redirect, url_for
)
from werkzeug.middleware.proxy_fix import ProxyFix
from groq import Groq
from authlib.integrations.flask_client import OAuth
from duckduckgo_search import DDGS
import os
import requests
import re

# ==========================================
# CONFIGURACIÓN GENERAL
# ==========================================

app = Flask(__name__)

app.wsgi_app = ProxyFix(
    app.wsgi_app,
    x_for=1,
    x_proto=1,
    x_host=1
)

# Clave secreta para las sesiones (fija para que no se pierda el login)
app.secret_key = "MikuNakanoEsLaMejorAsistente2026"

app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# ==========================================
# CONFIGURACIÓN DE GOOGLE
# ==========================================

GOOGLE_CLIENT_ID = "183518295635-devpot1v7r6v8902r0d53vdqqatjeu7a.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET = "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"

oauth = OAuth(app)

oauth.register(
    name="google",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url=(
        "https://accounts.google.com/"
        ".well-known/openid-configuration"
    ),
    client_kwargs={
        "scope": "openid email profile"
    }
)

# ==========================================
# CONFIGURACIÓN DE GROQ
# ==========================================

GROQ_API_KEY = "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"

cliente = Groq(api_key=GROQ_API_KEY)

# ==========================================
# CONFIGURACIÓN DE CLOUDFLARE
# ==========================================

CLOUDFLARE_ACCOUNT_ID = "b5cc836dcfc39c9e98b583f5269357df"

CLOUDFLARE_API_TOKEN = "cfut_MlI6z8COp7EtGYfFui6MbNxQN2hj7wnzGoZXMORwd779d413"

MODELO_IMAGEN = "@cf/black-forest-labs/flux-1-schnell"


# ==========================================
# GENERADOR DE IMÁGENES
# ==========================================

def generar_imagen(prompt):

    if not CLOUDFLARE_ACCOUNT_ID:
        print("ERROR: Falta CLOUDFLARE_ACCOUNT_ID")
        return None

    if not CLOUDFLARE_API_TOKEN:
        print("ERROR: Falta CLOUDFLARE_API_TOKEN")
        return None

    url = (
        "https://api.cloudflare.com/client/v4/accounts/"
        + CLOUDFLARE_ACCOUNT_ID
        + "/ai/run/"
        + MODELO_IMAGEN
    )

    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json"
    }

    prompt = prompt.strip()[:1800]

    payload = {
        "prompt": (
            prompt
            + ", high quality, detailed composition, "
              "beautiful lighting, carefully rendered details"
        ),
        "steps": 4
    }

    try:

        print("Enviando solicitud a Cloudflare...")

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=120
        )

        if not response.ok:
            print("ERROR HTTP:", response.status_code)
            print("RESPUESTA:", response.text)
            return None

        data = response.json()

        if not data.get("success", False):
            print("ERROR DE CLOUDFLARE:", data.get("errors"))
            return None

        resultado = data.get("result", {})

        imagen_base64 = resultado.get("image")

        if not imagen_base64:
            print("ERROR: Cloudflare no devolvió una imagen.")
            print(data)
            return None

        print("Imagen generada correctamente.")

        return "data:image/jpeg;base64," + imagen_base64

    except requests.exceptions.Timeout:
        print("ERROR: Cloudflare tardó demasiado en responder.")
        return None

    except requests.exceptions.RequestException as e:
        print("ERROR DE CONEXIÓN:", str(e))
        return None

    except Exception as e:
        print("ERROR GENERANDO IMAGEN:", str(e))
        return None


# ==========================================
# HISTORIAL DE CONVERSACIONES
# ==========================================

historiales = {}


def obtener_historial(user_id):

    if user_id not in historiales:

        historiales[user_id] = [
            {
                "role": "system",
                "content": (
                    "Eres Miku Nakano. "
                    "Tu personalidad es dulce, amable, "
                    "tranquila, inteligente y un poco tímida. "
                    "Responde en español de manera natural. "
                    "No utilices apelativos forzados. "
                    "Tus respuestas deben ser claras y útiles."
                )
            }
        ]

    return historiales[user_id]


# ==========================================
# DETECTAR SOLICITUDES DE IMÁGENES
# ==========================================

def es_solicitud_imagen(mensaje):

    patrones = [
        r"genera una imagen",
        r"generar una imagen",
        r"crea una imagen",
        r"crear una imagen",
        r"haz una imagen",
        r"hazme una imagen",
        r"dibujame",
        r"dibújame",
        r"dibuja",
        r"quiero una imagen",
        r"imagen de",
        r"hazme un dibujo",
        r"crea un dibujo",
        r"generame una imagen",
        r"genérame una imagen"
    ]

    mensaje = mensaje.lower()

    return any(
        re.search(patron, mensaje)
        for patron in patrones
    )


def extraer_prompt(mensaje):

    patrones = [
        r"genera una imagen",
        r"generar una imagen",
        r"crea una imagen",
        r"crear una imagen",
        r"haz una imagen",
        r"hazme una imagen",
        r"dibujame",
        r"dibújame",
        r"dibuja",
        r"quiero una imagen",
        r"imagen de",
        r"hazme un dibujo",
        r"crea un dibujo",
        r"generame una imagen",
        r"genérame una imagen"
    ]

    prompt = mensaje.strip()

    for patron in patrones:
        prompt = re.sub(
            patron,
            "",
            prompt,
            flags=re.IGNORECASE
        )

    prompt = prompt.strip(" :,-")

    return prompt


# ==========================================
# INTERFAZ WEB
# ==========================================

HTML = """
<!DOCTYPE html>
<html lang="es">

<head>

<meta charset="UTF-8">

<title>Miku Nakano AI</title>

<meta name="viewport"
content="width=device-width, initial-scale=1.0">

<style>

* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    font-family: 'Segoe UI', Arial, sans-serif;
    background: #f0f7ff;
    display: flex;
    height: 100dvh;
    overflow: hidden;
}

.sidebar {
    width: 300px;
    background: linear-gradient(
        180deg,
        #dff5ff 0%,
        #b3e0ff 100%
    );
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 20px;
    border-right: 2px solid #b3d9ff;
}

.sidebar img {
    width: 100%;
    max-width: 250px;
    border-radius: 20px;
    box-shadow: 0 10px 20px rgba(0,0,0,0.1);
}

.sidebar h2 {
    margin-top: 20px;
    color: #2a6f97;
    text-align: center;
    font-size: 1.5rem;
}

.main-chat {
    flex: 1;
    display: flex;
    flex-direction: column;
    background: white;
    min-width: 0;
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
    gap: 10px;
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
    max-width: 80%;
    padding: 12px 16px;
    border-radius: 15px;
    line-height: 1.5;
    font-size: 0.95rem;
    overflow-wrap: anywhere;
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

.mensaje img {
    display: block;
    max-width: 100%;
    height: auto;
    border-radius: 10px;
    margin-top: 10px;
}

.input-area {
    padding: 15px;
    padding-bottom: 25px;
    border-top: 1px solid #eee;
    display: flex;
    gap: 10px;
    background: #fafafa;
}

input {
    flex: 1;
    min-width: 0;
    padding: 15px;
    border-radius: 30px;
    border: 1px solid #ddd;
    outline: none;
    font-size: 1rem;
}

input:focus {
    border-color: #4aa3df;
}

button {
    padding: 15px 30px;
    background: #4aa3df;
    color: white;
    border: none;
    border-radius: 30px;
    cursor: pointer;
    font-weight: bold;
}

button:hover {
    background: #2a6f97;
}

button:disabled {
    opacity: 0.6;
    cursor: wait;
}

@media (max-width: 768px) {

    body {
        flex-direction: column;
    }

    .sidebar {
        width: 100%;
        height: 140px;
        flex-direction: row;
        padding: 10px;
    }

    .sidebar img {
        max-width: 100px;
        max-height: 120px;
        object-fit: cover;
    }

    .sidebar h2 {
        font-size: 1.2rem;
        margin-top: 0;
        margin-left: 15px;
    }

    .mensaje {
        max-width: 92%;
    }

    .input-area {
        padding: 10px;
    }

    button {
        padding: 12px 18px;
    }

}

</style>

</head>

<body>

<div class="sidebar">

    <img src="/static/fondo_miku.png.jpg"
         alt="Miku Nakano">

    <h2>Miku Nakano AI 💙🎧</h2>

</div>

<div class="main-chat">

    <div class="chat-header">

        <span>💬 Conversación con Miku</span>

        <span class="user-info">{{ user_name }}</span>

    </div>

    <div id="chat">

        <div class="mensaje mensaje-miku">
            <b>Miku:</b>
            ¡Hola! 💙 ¿En qué puedo ayudarte hoy?
        </div>

    </div>

    <div class="input-area">

        <input
            type="text"
            id="mensaje"
            placeholder="Escribe algo..."
            autocomplete="off"
        >

        <button id="botonEnviar" onclick="enviar()">
            Enviar
        </button>

    </div>

</div>

<script>

const input = document.getElementById("mensaje");
const chat = document.getElementById("chat");
const boton = document.getElementById("botonEnviar");

function agregarMensaje(texto, clase) {

    const div = document.createElement("div");

    div.className = "mensaje " + clase;

    const titulo = document.createElement("b");

    titulo.textContent =
        clase === "mensaje-usuario" ? "Tú: " : "Miku: ";

    div.appendChild(titulo);

    const contenido = document.createElement("span");

    contenido.textContent = texto;

    div.appendChild(contenido);

    chat.appendChild(div);

    chat.scrollTop = chat.scrollHeight;

    return div;
}


async function enviar() {

    const mensaje = input.value.trim();

    if (!mensaje || boton.disabled) {
        return;
    }

    agregarMensaje(mensaje, "mensaje-usuario");

    input.value = "";

    boton.disabled = true;

    const pensando = agregarMensaje(
        "Estoy pensando... 💙",
        "mensaje-miku"
    );

    try {

        const response = await fetch("/responder", {

            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify({
                mensaje: mensaje
            })

        });

        const data = await response.json();

        pensando.textContent = "";

        const titulo = document.createElement("b");
        titulo.textContent = "Miku: ";

        pensando.appendChild(titulo);

        const texto = document.createElement("span");

        texto.textContent = data.respuesta || "No recibí una respuesta.";

        pensando.appendChild(texto);

        if (data.imagen) {

            const imagen = document.createElement("img");

            imagen.src = data.imagen;

            imagen.alt = "Imagen generada por Miku";

            pensando.appendChild(imagen);

        }

    } catch (error) {

        pensando.textContent =
            "Miku: Ocurrió un error de conexión. Inténtalo otra vez.";

        console.error(error);

    }

    boton.disabled = false;

    input.focus();

    chat.scrollTop = chat.scrollHeight;

}


input.addEventListener("keydown", function(event) {

    if (event.key === "Enter") {
        enviar();
    }

});

</script>

</body>
</html>
"""


# ==========================================
# PÁGINA PRINCIPAL
# ==========================================

@app.route("/")
def index():

    if "user" not in session:
        return redirect(url_for("login"))

    user_name = session["user"].get(
        "name",
        "Usuario"
    )

    return render_template_string(
        HTML,
        user_name=user_name
    )


# ==========================================
# INICIAR SESIÓN
# ==========================================

@app.route("/login")
def login():

    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return "Falta configurar Google OAuth en Render.", 500

    redirect_uri = url_for(
        "authorize",
        _external=True
    )

    return oauth.google.authorize_redirect(
        redirect_uri
    )


@app.route("/authorize")
def authorize():

    try:

        token = oauth.google.authorize_access_token()

        user_info = token.get("userinfo")

        if not user_info:
            return "No se pudo obtener la información de Google.", 400

        session["user"] = user_info

        session["user_id"] = user_info.get("email")

        return redirect("/")

    except Exception as e:

        print("ERROR GOOGLE LOGIN:", str(e))

        return "Error al iniciar sesión con Google.", 500


# ==========================================
# CERRAR SESIÓN
# ==========================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))


# ==========================================
# RESPONDER MENSAJES
# ==========================================

@app.route("/responder", methods=["POST"])
def responder():

    if "user_id" not in session:
        return jsonify({
            "respuesta": "Debes iniciar sesión."
        }), 401

    data = request.get_json(silent=True) or {}

    mensaje = data.get("mensaje", "").strip()

    if not mensaje:
        return jsonify({
            "respuesta": "Escribe un mensaje."
        }), 400

    if len(mensaje) > 3000:
        return jsonify({
            "respuesta": "El mensaje es demasiado largo."
        }), 400

    user_id = session["user_id"]

    texto_lower = mensaje.lower()

    # ======================================
    # GENERACIÓN DE IMÁGENES
    # ======================================

    if es_solicitud_imagen(mensaje):

        prompt = extraer_prompt(mensaje)

        if not prompt:

            return jsonify({
                "respuesta": (
                    "¡Claro! 💙 Dime qué imagen quieres que cree."
                )
            })

        imagen = generar_imagen(prompt)

        if imagen:

            return jsonify({
                "respuesta": "¡Aquí tienes tu imagen! 💙🎨",
                "imagen": imagen
            })

        return jsonify({
            "respuesta": (
                "Lo siento, hubo un problema al generar la imagen. "
                "Revisa los registros de Render para conocer el error."
            )
        })

    # ======================================
    # CONVERSACIÓN CON GROQ
    # ======================================

    if not cliente:

        return jsonify({
            "respuesta": "Falta configurar GROQ_API_KEY en Render."
        }), 500

    historial_chat = obtener_historial(user_id)

    # ======================================
    # BÚSQUEDA EN INTERNET
    # ======================================

    if "busca" in texto_lower or "investiga" in texto_lower:

        query = re.sub(
            r"miku|busca|investiga",
            "",
            mensaje,
            flags=re.IGNORECASE
        ).strip()

        if query:

            try:

                resultados = DDGS().text(
                    query,
                    max_results=3
                )

                info_web = "\n".join([
                    f"- {r['title']}: {r['body']}"
                    for r in resultados
                ])

                if info_web:

                    historial_chat.append({
                        "role": "system",
                        "content": (
                            "Información encontrada en internet. "
                            "Úsala como referencia y verifica su "
                            "relevancia para la pregunta:\n"
                            + info_web
                        )
                    })

            except Exception as e:

                print("ERROR DE BÚSQUEDA:", str(e))

    historial_chat.append({
        "role": "user",
        "content": mensaje
    })

    try:

        completion = cliente.chat.completions.create(

            model="openai/gpt-oss-120b",

            messages=historial_chat,

            temperature=0.7,

            max_tokens=1500

        )

        respuesta = completion.choices[0].message.content

        historial_chat.append({
            "role": "assistant",
            "content": respuesta
        })

        # Limitar el tamaño del historial
        if len(historial_chat) > 21:

            historiales[user_id] = (
                historial_chat[:1] + historial_chat[-20:]
            )

        return jsonify({
            "respuesta": respuesta
        })

    except Exception as e:

        print("ERROR GROQ:", str(e))

        return jsonify({
            "respuesta": (
                "Ocurrió un problema al responder. "
                "Inténtalo nuevamente."
            )
        }), 500


# ==========================================
# INICIAR SERVIDOR
# ==========================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )
