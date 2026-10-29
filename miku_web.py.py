from flask import Flask, render_template_string, request, jsonify
from groq import Groq

app = Flask(__name__)

# ==========================================
# CONFIGURACIÓN DE LA IA
# PEGA TU CLAVE DE GROQ AQUÍ ABAJO (la que empieza con gsk_)
# ==========================================
import os
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "TU_CLAVE_AQUI")

cliente = Groq(api_key=GROQ_API_KEY)

# Historial de la conversación
historial_chat = [{"role": "system", "content": "Eres Miku Nakano, una asistente dulce, amable y precisa. Responde en español de forma concisa y útil."}]

# --- LA INTERFAZ WEB (HTML/CSS) ---
HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Miku Nakano AI</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Segoe UI', Arial, sans-serif; background-color: #f0f7ff; display: flex; height: 100vh; overflow: hidden; }
        
        /* Panel izquierdo: Imagen de Miku */
        .sidebar { width: 300px; background: linear-gradient(180deg, #dff5ff 0%, #b3e0ff 100%); display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 20px; border-right: 2px solid #b3d9ff; }
        .sidebar img { width: 100%; max-width: 250px; border-radius: 20px; box-shadow: 0 10px 20px rgba(0,0,0,0.1); }
        .sidebar h2 { margin-top: 20px; color: #2a6f97; text-align: center; font-size: 1.5rem; }
        
        /* Panel derecho: Chat */
        .main-chat { flex: 1; display: flex; flex-direction: column; background: #ffffff; }
        .chat-header { padding: 20px; border-bottom: 1px solid #eee; color: #2a6f97; font-weight: bold; font-size: 1.2rem; display: flex; align-items: center; gap: 10px; }
        
        /* Historial de mensajes */
        #chat { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 15px; }
        .mensaje { max-width: 80%; padding: 12px 16px; border-radius: 15px; line-height: 1.5; font-size: 0.95rem; }
        .mensaje-usuario { align-self: flex-end; background: #4aa3df; color: white; border-bottom-right-radius: 2px; }
        .mensaje-miku { align-self: flex-start; background: #f0f7ff; color: #1b3a4b; border-bottom-left-radius: 2px; border: 1px solid #dff5ff; }
        .mensaje-miku b { color: #2a6f97; }
        
        /* Barra de entrada */
        .input-area { padding: 20px; border-top: 1px solid #eee; display: flex; gap: 10px; background: #fafafa; }
        input { flex: 1; padding: 15px; border-radius: 30px; border: 1px solid #ddd; outline: none; font-size: 1rem; transition: 0.3s; }
        input:focus { border-color: #4aa3df; box-shadow: 0 0 0 3px rgba(74, 163, 223, 0.2); }
        button { padding: 15px 30px; background: #4aa3df; color: white; border: none; border-radius: 30px; cursor: pointer; font-weight: bold; transition: 0.3s; }
        button:hover { background: #2a6f97; }
        
        /* Para celulares */
        @media (max-width: 768px) {
            body { flex-direction: column; }
            .sidebar { width: 100%; height: 200px; flex-direction: row; padding: 10px; }
            .sidebar img { max-width: 120px; }
            .sidebar h2 { font-size: 1.2rem; margin-top: 0; margin-left: 15px; }
        }
    </style>
</head>
<body>
    <!-- Panel Izquierdo: Imagen -->
    <div class="sidebar">
        <img src="/static/fondo_miku.png.jpg" alt="Miku Nakano">
        <h2>Miku Nakano AI 💙🎧</h2>
    </div>

    <!-- Panel Derecho: Chat -->
    <div class="main-chat">
        <div class="chat-header">💬 Conversación con Miku</div>
        <div id="chat">
            <div class="mensaje mensaje-miku"><b>Miku:</b> ¡Hola, Director! 💙 Me alegra mucho verte por aquí. ¿En qué puedo ayudarte hoy?</div>
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

            // Agregar mensaje del usuario
            chat.innerHTML += `<div class="mensaje mensaje-usuario"><b>Tú:</b> ${mensaje}</div>`;
            input.value = '';
            chat.scrollTop = chat.scrollHeight;

            // Mostrar que Miku está pensando
            const idPensando = 'pensando-' + Date.now();
            chat.innerHTML += `<div class="mensaje mensaje-miku" id="${idPensando}"><b>Miku:</b> Pensando... 💭</div>`;
            chat.scrollTop = chat.scrollHeight;

            // Petición a la IA
            const response = await fetch('/responder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mensaje: mensaje })
            });
            const data = await response.json();
            
            // Reemplazar "Pensando..." con la respuesta real
            document.getElementById(idPensando).innerHTML = `<b>Miku:</b> ${data.respuesta}`;
            chat.scrollTop = chat.scrollHeight;
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/responder', methods=['POST'])
def responder():
    data = request.get_json()
    mensaje = data.get('mensaje')
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