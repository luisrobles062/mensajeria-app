import os
from flask import Flask, render_template, request, redirect, url_for, flash
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.utils import secure_filename
import pandas as pd

app = Flask(__name__)
app.secret_key = 'tu_clave_super_secreta'

# --- Conexión a la base de datos ---
def get_db_connection():
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("La variable de entorno DATABASE_URL no está definida")
    # Eliminar channel_binding=require si está presente para evitar error en Neon
    if 'channel_binding=require' in database_url:
        database_url = database_url.replace('&channel_binding=require', '')
        database_url = database_url.replace('?channel_binding=require', '')
    conn = psycopg2.connect(database_url)
    return conn

# --- Creación de tablas si no existen ---
def crear_tablas():
    conn = get_db_connection()
    cur = conn.cursor()
    # Tabla zonas
    cur.execute('''
        CREATE TABLE IF NOT EXISTS zonas (
            nombre VARCHAR(100) PRIMARY KEY,
            tarifa NUMERIC(10, 2) NOT NULL
        )
    ''')
    # Tabla mensajeros
    cur.execute('''
        CREATE TABLE IF NOT EXISTS mensajeros (
            nombre VARCHAR(100) PRIMARY KEY,
            zona VARCHAR(100),
            FOREIGN KEY (zona) REFERENCES zonas(nombre)
        )
    ''')
    # Tabla guias
    cur.execute('''
        CREATE TABLE IF NOT EXISTS guias (
            numero VARCHAR(50) PRIMARY KEY,
            remitente VARCHAR(100),
            destinatario VARCHAR(100),
            direccion VARCHAR(200),
            ciudad VARCHAR(100),
            zona VARCHAR(100),
            estado VARCHAR(50) DEFAULT 'Cargada',
            mensajero VARCHAR(100),
            fecha_despacho DATE,
            fecha_entrega DATE,
            observacion TEXT,
            FOREIGN KEY (zona) REFERENCES zonas(nombre),
            FOREIGN KEY (mensajero) REFERENCES mensajeros(nombre)
        )
    ''')
    # Tabla recogidas
    cur.execute('''
        CREATE TABLE IF NOT EXISTS recogidas (
            id SERIAL PRIMARY KEY,
            numero_guia VARCHAR(50),
            fecha DATE,
            observacion TEXT,
            FOREIGN KEY (numero_guia) REFERENCES guias(numero)
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()

crear_tablas()

# --- Rutas ---

@app.route('/')
def index():
    return render_template('index.html')

# Cargar base de guías desde Excel
@app.route('/cargar_base', methods=['GET', 'POST'])
def cargar_base():
    if request.method == 'POST':
        file = request.files.get('file')
        if not file:
            flash('No se seleccionó ningún archivo', 'error')
            return redirect(request.url)
        filename = secure_filename(file.filename)
        if not filename.endswith(('.xls', '.xlsx')):
            flash('Solo se permiten archivos Excel', 'error')
            return redirect(request.url)
        df = pd.read_excel(file)
        required_columns = {'numero', 'remitente', 'destinatario', 'direccion', 'ciudad', 'zona'}
        if not required_columns.issubset(set(df.columns.str.lower())):
            flash(f'Faltan columnas obligatorias: {required_columns}', 'error')
            return redirect(request.url)
        # Insertar o actualizar guías en la BD
        conn = get_db_connection()
        cur = conn.cursor()
        for _, row in df.iterrows():
            numero = str(row.get('numero')).strip()
            remitente = str(row.get('remitente')).strip()
            destinatario = str(row.get('destinatario')).strip()
            direccion = str(row.get('direccion')).strip()
            ciudad = str(row.get('ciudad')).strip()
            zona = str(row.get('zona')).strip()
            # Insertar o actualizar
            cur.execute('''
                INSERT INTO guias (numero, remitente, destinatario, direccion, ciudad, zona)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (numero) DO UPDATE SET
                    remitente = EXCLUDED.remitente,
                    destinatario = EXCLUDED.destinatario,
                    direccion = EXCLUDED.direccion,
                    ciudad = EXCLUDED.ciudad,
                    zona = EXCLUDED.zona
            ''', (numero, remitente, destinatario, direccion, ciudad, zona))
        conn.commit()
        cur.close()
        conn.close()
        flash('Base de guías cargada correctamente', 'success')
        return redirect(url_for('index'))
    return render_template('cargar_base.html')

# Listar zonas
@app.route('/zonas')
def listar_zonas():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT * FROM zonas ORDER BY nombre')
    zonas = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('zonas.html', zonas=zonas)

# Nueva zona
@app.route('/zonas/nueva', methods=['GET', 'POST'])
def nueva_zona():
    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        tarifa = request.form['tarifa'].strip()
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute('INSERT INTO zonas (nombre, tarifa) VALUES (%s, %s)', (nombre, tarifa))
            conn.commit()
            flash('Zona creada correctamente', 'success')
            return redirect(url_for('listar_zonas'))
        except psycopg2.IntegrityError:
            conn.rollback()
            flash('La zona ya existe', 'error')
        finally:
            cur.close()
            conn.close()
    return render_template('nueva_zona.html')

# Listar mensajeros
@app.route('/mensajeros')
def listar_mensajeros():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT * FROM mensajeros ORDER BY nombre')
    mensajeros = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('mensajeros.html', mensajeros=mensajeros)

# Nuevo mensajero
@app.route('/mensajeros/nuevo', methods=['GET', 'POST'])
def nuevo_mensajero():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT nombre FROM zonas ORDER BY nombre')
    zonas = cur.fetchall()
    cur.close()
    conn.close()

    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        zona = request.form['zona'].strip()
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute('INSERT INTO mensajeros (nombre, zona) VALUES (%s, %s)', (nombre, zona))
            conn.commit()
            flash('Mensajero creado correctamente', 'success')
            return redirect(url_for('listar_mensajeros'))
        except psycopg2.IntegrityError:
            conn.rollback()
            flash('El mensajero ya existe', 'error')
        finally:
            cur.close()
            conn.close()
    return render_template('nuevo_mensajero.html', zonas=zonas)

# Despachar guías (asignar mensajero a guía y fecha despacho)
@app.route('/despachar', methods=['GET', 'POST'])
def despachar_guias():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT numero FROM guias WHERE estado = %s ORDER BY numero', ('Cargada',))
    guias_disponibles = cur.fetchall()
    cur.execute('SELECT nombre FROM mensajeros ORDER BY nombre')
    mensajeros = cur.fetchall()
    cur.close()
    conn.close()

    if request.method == 'POST':
        numero_guia = request.form['numero_guia'].strip()
        mensajero = request.form['mensajero'].strip()
        fecha_despacho = request.form['fecha_despacho']
        conn = get_db_connection()
        cur = conn.cursor()
        # Validar que la guía esté cargada y no despachada
        cur.execute('SELECT estado FROM guias WHERE numero = %s', (numero_guia,))
        guia = cur.fetchone()
        if not guia:
            flash('La guía no existe', 'error')
            return redirect(request.url)
        if guia[0] != 'Cargada':
            flash('La guía ya fue despachada o entregada', 'error')
            return redirect(request.url)
        # Actualizar guía con mensajero y fecha despacho
        cur.execute('''
            UPDATE guias SET mensajero = %s, fecha_despacho = %s, estado = %s WHERE numero = %s
        ''', (mensajero, fecha_despacho, 'Despachada', numero_guia))
        conn.commit()
        cur.close()
        conn.close()
        flash('Guía despachada correctamente', 'success')
        return redirect(url_for('index'))

    return render_template('despachar.html', guias=guias_disponibles, mensajeros=mensajeros)

# Consultar estado guía
@app.route('/consulta', methods=['GET', 'POST'])
def consultar_guia():
    guia_info = None
    if request.method == 'POST':
        numero_guia = request.form['numero_guia'].strip()
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('SELECT * FROM guias WHERE numero = %s', (numero_guia,))
        guia_info = cur.fetchone()
        cur.close()
        conn.close()
        if not guia_info:
            flash('Guía no encontrada', 'error')
    return render_template('consulta.html', guia=guia_info)

# Registrar recepción
@app.route('/recepcion', methods=['GET', 'POST'])
def registrar_recepcion():
    if request.method == 'POST':
        numero_guia = request.form['numero_guia'].strip()
        estado = request.form['estado']
        fecha_entrega = request.form['fecha_entrega']
        observacion = request.form['observacion'].strip()
        conn = get_db_connection()
        cur = conn.cursor()
        # Verificar existencia guía
        cur.execute('SELECT estado FROM guias WHERE numero = %s', (numero_guia,))
        guia = cur.fetchone()
        if not guia:
            flash('Guía no existe', 'error')
            return redirect(request.url)
        # Actualizar estado y fecha entrega
        cur.execute('''
            UPDATE guias SET estado = %s, fecha_entrega = %s, observacion = %s WHERE numero = %s
        ''', (estado, fecha_entrega, observacion, numero_guia))
        conn.commit()
        cur.close()
        conn.close()
        flash('Recepción registrada correctamente', 'success')
        return redirect(url_for('index'))
    return render_template('recepcion.html')

# Registrar recogida
@app.route('/recogidas/registrar', methods=['GET', 'POST'])
def registrar_recogida():
    if request.method == 'POST':
        numero_guia = request.form['numero_guia'].strip()
        fecha = request.form['fecha']
        observacion = request.form['observacion'].strip()
        conn = get_db_connection()
        cur = conn.cursor()
        # Verificar que la guía exista
        cur.execute('SELECT numero FROM guias WHERE numero = %s', (numero_guia,))
        if not cur.fetchone():
            flash('La guía no existe', 'error')
            cur.close()
            conn.close()
            return redirect(request.url)
        # Insertar recogida
        cur.execute('INSERT INTO recogidas (numero_guia, fecha, observacion) VALUES (%s, %s, %s)', (numero_guia, fecha, observacion))
        conn.commit()
        cur.close()
        conn.close()
        flash('Recogida registrada', 'success')
        return redirect(url_for('index'))
    return render_template('registrar_recogida.html')

# Ver recogidas
@app.route('/recogidas')
def ver_recogidas():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT * FROM recogidas ORDER BY fecha DESC')
    recogidas = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('ver_recogidas.html', recogidas=recogidas)

if __name__ == '__main__':
    app.run(debug=True)
