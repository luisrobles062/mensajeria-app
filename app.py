import os
from flask import Flask, render_template, request, redirect, url_for, flash
import psycopg2
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'secreto'

# Carpeta para subir archivos (ejemplo)
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def get_db_connection():
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("La variable de entorno DATABASE_URL no está definida")

    parsed_url = urlparse(database_url)
    query_params = parse_qs(parsed_url.query)

    # Corregir sslmode y eliminar channel_binding
    if 'sslmode' in query_params and query_params['sslmode'][0] == 'require':
        query_params['sslmode'] = ['verify-full']
    if 'channel_binding' in query_params:
        del query_params['channel_binding']

    new_query = urlencode(query_params, doseq=True)
    fixed_url = urlunparse((
        parsed_url.scheme,
        parsed_url.netloc,
        parsed_url.path,
        parsed_url.params,
        new_query,
        parsed_url.fragment
    ))

    conn = psycopg2.connect(fixed_url)
    return conn

def crear_tablas():
    conn = get_db_connection()
    cur = conn.cursor()
    # Ejemplo tabla para guías
    cur.execute('''
        CREATE TABLE IF NOT EXISTS guias (
            numero_guia TEXT PRIMARY KEY,
            remitente TEXT NOT NULL,
            destinatario TEXT NOT NULL,
            direccion TEXT NOT NULL,
            ciudad TEXT NOT NULL,
            estado TEXT DEFAULT 'pendiente'
        )
    ''')
    # Ejemplo tabla para recogidas
    cur.execute('''
        CREATE TABLE IF NOT EXISTS recogidas (
            id SERIAL PRIMARY KEY,
            numero_guia TEXT NOT NULL,
            fecha DATE NOT NULL,
            observaciones TEXT
        )
    ''')
    # Agrega aquí otras tablas necesarias para tu proyecto

    conn.commit()
    cur.close()
    conn.close()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/cargar_base', methods=['GET', 'POST'])
def cargar_base():
    if request.method == 'POST':
        if 'archivo' not in request.files:
            flash('No se seleccionó archivo')
            return redirect(request.url)
        archivo = request.files['archivo']
        if archivo.filename == '':
            flash('No se seleccionó archivo')
            return redirect(request.url)
        filename = secure_filename(archivo.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        archivo.save(filepath)
        # Aquí procesar el archivo Excel y guardar datos en DB
        flash('Archivo cargado correctamente')
        return redirect(url_for('index'))
    return render_template('cargar_base.html')

@app.route('/registrar_recogida', methods=['GET', 'POST'])
def registrar_recogida():
    if request.method == 'POST':
        numero_guia = request.form.get('numero_guia')
        fecha = request.form.get('fecha')
        observaciones = request.form.get('observaciones')
        if not numero_guia or not fecha:
            flash('Número de guía y fecha son obligatorios')
            return redirect(request.url)

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('INSERT INTO recogidas (numero_guia, fecha, observaciones) VALUES (%s, %s, %s)',
                    (numero_guia, fecha, observaciones))
        conn.commit()
        cur.close()
        conn.close()
        flash('Recogida registrada con éxito')
        return redirect(url_for('index'))
    return render_template('registrar_recogida.html')

@app.route('/ver_recogidas')
def ver_recogidas():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, numero_guia, fecha, observaciones FROM recogidas ORDER BY fecha DESC')
    recogidas = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('ver_recogidas.html', recogidas=recogidas)

# Agrega aquí más rutas necesarias con sus funciones según los templates que tengas

if __name__ == '__main__':
    crear_tablas()
    app.run(host='0.0.0.0', port=10000, debug=True)
