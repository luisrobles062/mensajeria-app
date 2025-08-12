from flask import Flask, render_template, request, redirect, url_for, flash
import psycopg2
from psycopg2.extras import RealDictCursor
from urllib.parse import urlparse
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Configuración de conexión a Neon PostgreSQL (ajustado para evitar error sslmode)
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://neondb_owner:npg_3owpfIUOAT0a@ep-soft-bush-acv2a8v4-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require')

# Ajustar la URL para psycopg2, removiendo channel_binding si está (error común en Neon)
def get_connection():
    url = urlparse(DATABASE_URL)
    # Reconstruir DSN sin channel_binding para evitar error en psycopg2
    query = url.query.replace('channel_binding=require', '')
    dsn = f"dbname={url.path[1:]} user={url.username} password={url.password} host={url.hostname} port={url.port} sslmode=require"
    if query.strip():
        dsn += f" {query}"
    conn = psycopg2.connect(dsn)
    return conn

# Crear tablas necesarias si no existen
def crear_tablas():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS zonas (
            nombre VARCHAR PRIMARY KEY,
            tarifa NUMERIC
        );
        CREATE TABLE IF NOT EXISTS mensajeros (
            nombre VARCHAR PRIMARY KEY,
            zona VARCHAR REFERENCES zonas(nombre)
        );
        CREATE TABLE IF NOT EXISTS guias (
            numero VARCHAR PRIMARY KEY,
            remitente VARCHAR,
            destinatario VARCHAR,
            direccion TEXT,
            ciudad VARCHAR,
            zona VARCHAR REFERENCES zonas(nombre),
            estado VARCHAR DEFAULT 'pendiente'
        );
        CREATE TABLE IF NOT EXISTS despachos (
            id SERIAL PRIMARY KEY,
            guia_numero VARCHAR REFERENCES guias(numero),
            mensajero_nombre VARCHAR REFERENCES mensajeros(nombre),
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS recepciones (
            id SERIAL PRIMARY KEY,
            guia_numero VARCHAR REFERENCES guias(numero),
            estado VARCHAR,
            causal TEXT,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS recogidas (
            id SERIAL PRIMARY KEY,
            guia_numero VARCHAR,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            observaciones TEXT
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

crear_tablas()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/cargar_base', methods=['GET', 'POST'])
def cargar_base():
    if request.method == 'POST':
        # Aquí procesar archivo Excel o datos
        flash('Carga de base de guías no implementada aún.', 'info')
        return redirect(url_for('cargar_base'))
    return render_template('cargar_base.html')

@app.route('/consultar_estado', methods=['GET', 'POST'])
def consultar_estado():
    guia = None
    estado = None
    if request.method == 'POST':
        numero = request.form.get('numero_guia')
        if not numero:
            flash('Debe ingresar número de guía.', 'warning')
            return redirect(url_for('consultar_estado'))
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM guias WHERE numero = %s", (numero,))
        guia = cur.fetchone()
        if guia:
            estado = guia.get('estado', 'No disponible')
        else:
            flash('Guía no encontrada.', 'danger')
        cur.close()
        conn.close()
    return render_template('consultar_estado.html', guia=guia, estado=estado)

@app.route('/despachar_guias', methods=['GET', 'POST'])
def despachar_guias():
    if request.method == 'POST':
        # Procesar despacho
        flash('Despacho no implementado aún.', 'info')
        return redirect(url_for('despachar_guias'))
    return render_template('despachar_guias.html')

@app.route('/liquidacion')
def liquidacion():
    return render_template('liquidacion.html')

@app.route('/registrar_mensajero', methods=['GET', 'POST'])
def registrar_mensajero():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        zona = request.form.get('zona')
        if not nombre or not zona:
            flash('Nombre y zona son obligatorios.', 'warning')
            return redirect(url_for('registrar_mensajero'))
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO mensajeros (nombre, zona) VALUES (%s, %s)", (nombre, zona))
            conn.commit()
            flash('Mensajero registrado con éxito.', 'success')
        except Exception as e:
            flash(f'Error al registrar mensajero: {e}', 'danger')
        finally:
            cur.close()
            conn.close()
        return redirect(url_for('registrar_mensajero'))
    # Obtener zonas para el select
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT nombre FROM zonas")
    zonas = [r[0] for r in cur.fetchall()]
    cur.close()
    conn.close()
    return render_template('registrar_mensajero.html', zonas=zonas)

@app.route('/registrar_recepcion', methods=['GET', 'POST'])
def registrar_recepcion():
    if request.method == 'POST':
        # Procesar recepción
        flash('Registro de recepción no implementado aún.', 'info')
        return redirect(url_for('registrar_recepcion'))
    return render_template('registrar_recepcion.html')

@app.route('/registrar_recogida', methods=['GET', 'POST'])
def registrar_recogida():
    if request.method == 'POST':
        # Procesar recogida
        flash('Registro de recogida no implementado aún.', 'info')
        return redirect(url_for('registrar_recogida'))
    return render_template('registrar_recogida.html')

@app.route('/registrar_zona', methods=['GET', 'POST'])
def registrar_zona():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        tarifa = request.form.get('tarifa')
        if not nombre or not tarifa:
            flash('Nombre y tarifa son obligatorios.', 'warning')
            return redirect(url_for('registrar_zona'))
        try:
            tarifa_num = float(tarifa)
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO zonas (nombre, tarifa) VALUES (%s, %s)", (nombre, tarifa_num))
            conn.commit()
            flash('Zona registrada con éxito.', 'success')
        except Exception as e:
            flash(f'Error al registrar zona: {e}', 'danger')
        finally:
            cur.close()
            conn.close()
        return redirect(url_for('registrar_zona'))
    return render_template('registrar_zona.html')

@app.route('/ver_despacho')
def ver_despacho():
    # Mostrar despachos
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT d.id, d.guia_numero, d.mensajero_nombre, d.fecha, g.estado
        FROM despachos d
        LEFT JOIN guias g ON d.guia_numero = g.numero
        ORDER BY d.fecha DESC
    """)
    despachos = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('ver_despacho.html', despachos=despachos)

@app.route('/ver_guias')
def ver_guias():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM guias ORDER BY numero")
    guias = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('ver_guias.html', guias=guias)

@app.route('/ver_recogidas')
def ver_recogidas():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM recogidas ORDER BY fecha DESC")
    recogidas = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('ver_recogidas.html', recogidas=recogidas)

@app.route('/verificacion_entrada', methods=['GET', 'POST'])
def verificacion_entrada():
    if request.method == 'POST':
        # Procesar verificación
        flash('Verificación de entrada no implementada aún.', 'info')
        return redirect(url_for('verificacion_entrada'))
    return render_template('verificacion_entrada.html')


if __name__ == '__main__':
    app.run(debug=True, port=10000)
