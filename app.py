import os
import json
from datetime import datetime
from flask import Flask, request, render_template, jsonify
from flask import send_from_directory
from openai import OpenAI
from google.cloud import vision
from dotenv import load_dotenv
import markdown

# Cargar variables de entorno
load_dotenv()

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

FICHAS_FOLDER = 'fichas'
os.makedirs(FICHAS_FOLDER, exist_ok=True)

# Inicializar clientes

client_openai = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

google_credentials_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
if google_credentials_path:
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = google_credentials_path
else:
    raise EnvironmentError("La variable GOOGLE_APPLICATION_CREDENTIALS no está definida en el entorno.")

client_vision = vision.ImageAnnotatorClient()


HISTORIAL_FILE = 'historial.json'
ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg'}

def allowed_file(filename):
    return os.path.splitext(filename.lower())[1] in ALLOWED_EXTENSIONS

def detectar_alimento(imagen_path):
    try:
        with open(imagen_path, 'rb') as img_file:
            content = img_file.read()
        image = vision.Image(content=content)
        response = client_vision.label_detection(image=image)
        etiquetas = response.label_annotations

        # Verifica si hay etiquetas relevantes con alta confianza
        etiquetas_validas = [label for label in etiquetas if label.description in {"Food", "Fruit"} and label.score >= 0.80]

        if not etiquetas_validas:
            return None  # No se detectó alimento válido

        # Filtra etiquetas genéricas
        ignorar = {"Food", "Dish", "Cuisine", "Ingredient", "Recipe", "Produce"}
        etiquetas_filtradas = [label.description for label in etiquetas if label.description not in ignorar]

        return etiquetas_filtradas[0] if etiquetas_filtradas else etiquetas[0].description
    except Exception as e:
        return f"Error: {e}"


def guardar_registro(usuario, alimento, info, imagen_rel_path):
    fecha = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ficha_id = datetime.now().strftime('%Y%m%d%H%M%S')
    ficha_filename = f"ficha_{ficha_id}.txt"
    ficha_path = os.path.join(FICHAS_FOLDER, ficha_filename)

    with open(ficha_path, 'w', encoding='utf-8') as f:
        f.write(info)

    nuevo = {
        'id': ficha_id,
        'usuario': usuario,
        'alimento': alimento,
        'ficha_file': ficha_filename,
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

    return ficha_filename  # ✅ Retorna el nombre del archivo

def generar_ficha(alimento):
    prompt = f"""
    Actúa como un nutricionista profesional especializado en divulgación educativa. 
    Tu tarea es generar una ficha nutricional breve y clara sobre el alimento "{alimento}" en formato Markdown, destinada a usuarios curiosos que desean aprender sobre nutrición de forma accesible.

    Antes de comenzar, determina si el alimento es un platillo compuesto (por ejemplo: ensalada, hamburguesa, pasta, etc.).  
    Si lo es, incluye una lista estimada de ingredientes comunes que lo componen. Si no lo es, omite esta sección.

    Si detectas que el alimento esta en muy mal estado, deci si es o no es recomendable ingerir ese mismo alimento.
    
    La ficha debe incluir los siguientes apartados, usando ** para negritas:

    - **Alimento:** nombre común del alimento  
    - **Estado:** estado del alimento
    - **Ingredientes estimados:** (solo si es un platillo) lista breve de componentes típicos  
    - **Calorías (por 100g):** valor aproximado según preparación estándar  
    - **Nutrientes destacados:** lista breve con 3 a 5 componentes clave  
    - **Beneficios para la salud:** 2 a 3 beneficios concretos y comprensibles  
    - **Dato curioso:** una frase interesante o cultural sobre el alimento  

    Requisitos adicionales:  
    - Usa lenguaje claro, sin tecnicismos excesivos.  
    - Evita repetir el nombre del alimento en cada sección.  
    - No incluyas advertencias ni contraindicaciones.  
    - Organiza el contenido en párrafos breves.  
    - No uses encabezados ni listas con guiones.  
    - Mantén el texto dentro de 150 palabras.
    """
    try:
        response = client_openai.chat.completions.create(
            model='gpt-3.5-turbo',
            messages=[
                {'role': 'system', 'content': 'Eres un experto en nutrición con enfoque educativo.'},
                {'role': 'user', 'content': prompt}
            ],
            max_tokens=350
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

    alimento = detectar_alimento(imagen_path)
    ficha_raw = generar_ficha(alimento)
    ficha_html = markdown.markdown(ficha_raw)
    imagen_rel_path = os.path.join('static', 'uploads', filename)
    ficha_filename = guardar_registro(usuario, alimento, ficha_raw, imagen_rel_path)

    return render_template('result.html',
                       usuario=usuario,
                       alimento=alimento,
                       info=ficha_html,
                       imagen=imagen_rel_path,
                       ficha_file=ficha_filename)


@app.route('/history')
def history():
    try:
        with open(HISTORIAL_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        for item in data:
            ficha_path = os.path.join(FICHAS_FOLDER, item['ficha_file'])
            if os.path.exists(ficha_path):
                with open(ficha_path, 'r', encoding='utf-8') as f_txt:
                    ficha_raw = f_txt.read()
                item['info'] = markdown.markdown(ficha_raw)
            else:
                item['info'] = "<p><em>Ficha no disponible</em></p>"

    except FileNotFoundError:
        data = []

    return render_template('history.html', historial=data)

@app.route('/descargar/<filename>')
def descargar_ficha(filename):
    try:
        return send_from_directory(FICHAS_FOLDER, filename, as_attachment=True)
    except FileNotFoundError:
        return "Archivo no encontrado", 404

if __name__ == '__main__':
    app.run(debug=True)

