import os
import json
from datetime import datetime
from flask import Flask, request, render_template, jsonify
from openai import OpenAI
from google.cloud import vision
from dotenv import load_dotenv
import markdown

# Cargar variables de entorno
load_dotenv()

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Inicializar clientes
client_openai = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'clave_google.json'
client_vision = vision.ImageAnnotatorClient()

HISTORIAL_FILE = 'historial.json'
ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg'}

def allowed_file(filename):
    return os.path.splitext(filename.lower())[1] in ALLOWED_EXTENSIONS

def guardar_registro(usuario, alimento, info, imagen_rel_path):
    fecha = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    nuevo = {
        'usuario': usuario,
        'alimento': alimento,
        'info': info,
        'fecha': fecha,
        'imagen': imagen_rel_path
    }
    try:
        with open(HISTORIAL_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = []
    data.append(nuevo)
    with open(HISTORIAL_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def generar_ficha(alimento):
    prompt = f"""
    Genera una ficha nutricional breve y clara sobre {alimento} en formato Markdown.
    Debe incluir exactamente estos apartados, usando ** para negritas:
    - **Alimento:** nombre del alimento
    - **Calorías (por 100g):** valor aproximado
    - **Nutrientes destacados:** lista breve
    - **Beneficios:** lista breve
    - **Dato curioso:** 1 frase interesante

    El texto debe ser conciso, educativo y fácil de leer.
    """
    try:
        response = client_openai.chat.completions.create(
            model='gpt-3.5-turbo',
            messages=[
                {'role': 'system', 'content': 'Eres un experto en nutrición y presentas la información de forma clara y atractiva.'},
                {'role': 'user', 'content': prompt}
            ],
            max_tokens=250
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f'Error con ChatGPT: {e}'

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    usuario = request.form.get('usuario')
    imagen = request.files.get('imagen')

    if not usuario or not imagen:
        return jsonify({'error': 'Faltan datos: usuario o imagen.'}), 400

    if not allowed_file(imagen.filename):
        return jsonify({'error': 'Formato de imagen no permitido.'}), 400

    filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{imagen.filename}"
    imagen_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    imagen.save(imagen_path)

    try:
        with open(imagen_path, 'rb') as img_file:
            content = img_file.read()
        image = vision.Image(content=content)
        response = client_vision.label_detection(image=image)
        if not response.label_annotations:
            return jsonify({'error': 'No se detectó ningún alimento.'}), 404
        alimento = response.label_annotations[0].description
    except Exception as e:
        return jsonify({'error': f'Error con Google Vision: {e}'}), 500

    ficha_raw = generar_ficha(alimento)
    ficha_html = markdown.markdown(ficha_raw)
    imagen_rel_path = os.path.join('static', 'uploads', filename)
    guardar_registro(usuario, alimento, ficha_raw, imagen_rel_path)

    return render_template('result.html', usuario=usuario, alimento=alimento, info=ficha_html, imagen=imagen_rel_path)

@app.route('/history')
def history():
    try:
        with open(HISTORIAL_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = []
    return render_template('history.html', historial=data)

if __name__ == '__main__':
    app.run(debug=True)
