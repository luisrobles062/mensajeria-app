from flask import Flask, render_template, request, redirect, url_for, flash
import psycopg2
from urllib.parse import urlparse, parse_qsl
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'secreto'

# Pon aquí la URL completa de la base de datos PostgreSQL Neon (sin espacios)
DATABASE_URL = "postgresql://neondb_owner:npg_3owpfIUOAT0a@ep-soft-bush-acv2a8v4-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

def get_connection():
    url = urlparse(DATABASE_URL)
    query_params = dict(parse_qsl(url.query))
    # Eliminar channel_binding porque psycopg2 no lo soporta
    query_params.pop('channel_binding', None)
    # Reconstruir query string válido
    query_string = '&'.join(f"{k}={v}" for k, v in query_params.items() if v)
    dsn = (
        f"dbname={url.path[1:]} "
        f"user={url.username} "
        f"password={url.password} "
        f"host={url.hostname} "
        f"port={url.port}"
    )
    if query_string:
        dsn += f" {query_string}"
    return psycopg2.connect(dsn)

def crear_tablas():
    conn = get_connection()
    cursor = conn.cursor()
    # Aquí crea todas tus tablas necesarias, ejemplo:
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS zonas (
        nombre TEXT PRIMARY KEY,
        tarifa REAL NOT NULL
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS mensajeros (
        nombre TEXT PRIMARY KEY,
        zona TEXT REFERENCES zonas(nombre)
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS guias (
        numero_guia TEXT PRIMARY KEY,
        remitente TEXT,
        destinatario TEXT,
        direccion TEXT,
        ciudad TEXT,
        zona TEXT REFERENCES zonas(nombre),
        estado TEXT DEFAULT 'pendiente'
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS despachos (
        id SERIAL PRIMARY KEY,
        numero_guia TEXT REFERENCES guias(numero_guia),
        mensajero TEXT REFERENCES mensajeros(nombre),
        fecha_despacho TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS recepciones (
        id SERIAL PRIMARY KEY,
        numero_guia TEXT REFERENCES guias(numero_guia),
        estado TEXT,
        causal TEXT,
        fecha_recepcion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS recogidas (
        id SERIAL PRIMARY KEY,
        numero_guia TEXT,
        fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        observaciones TEXT
    );
    """)
    conn.commit()
    cursor.close()
    conn.close()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/registrar_zona', methods=['GET', 'POST'])
def registrar_zona():
    if request.method == 'POST':
        nombre = request.form['nombre']
        tarifa = request.form['tarifa']
        try:
            tarifa = float(tarifa)
        except ValueError:
            flash('Tarifa inválida', 'error')
            return redirect(url_for('registrar_zona'))

        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO zonas (nombre, tarifa) VALUES (%s, %s)", (nombre, tarifa))
            conn.commit()
            flash('Zona registrada exitosamente', 'success')
        except psycopg2.IntegrityError:
            conn.rollback()
            flash('La zona ya existe', 'error')
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('registrar_zona'))
    return render_template('registrar_zona.html')

@app.route('/registrar_mensajero', methods=['GET', 'POST'])
def registrar_mensajero():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT nombre FROM zonas")
    zonas = cursor.fetchall()
    cursor.close()
    conn.close()

    if request.method == 'POST':
        nombre = request.form['nombre']
        zona = request.form['zona']
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO mensajeros (nombre, zona) VALUES (%s, %s)", (nombre, zona))
            conn.commit()
            flash('Mensajero registrado exitosamente', 'success')
        except psycopg2.IntegrityError:
            conn.rollback()
            flash('El mensajero ya existe', 'error')
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('registrar_mensajero'))
    return render_template('registrar_mensajero.html', zonas=zonas)

@app.route('/cargar_base', methods=['GET', 'POST'])
def cargar_base():
    # Aquí implementarás la carga de archivos Excel y procesamiento
    # Para empezar solo una plantilla simple:
    if request.method == 'POST':
        # Implementa la carga y procesamiento aquí
        flash('Carga de base aún no implementada', 'info')
        return redirect(url_for('cargar_base'))
    return render_template('cargar_base.html')

@app.route('/consultar_estado', methods=['GET', 'POST'])
def consultar_estado():
    estado = None
    if request.method == 'POST':
        numero_guia = request.form['numero_guia']
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT estado FROM guias WHERE numero_guia = %s", (numero_guia,))
        row = cursor.fetchone()
        if row:
            estado = row[0]
        else:
            flash('Guía no encontrada', 'error')
        cursor.close()
        conn.close()
    return render_template('consultar_estado.html', estado=estado)

@app.route('/despachar_guias', methods=['GET', 'POST'])
def despachar_guias():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT numero_guia FROM guias WHERE estado='pendiente'")
    guias = cursor.fetchall()

    cursor.execute("SELECT nombre FROM mensajeros")
    mensajeros = cursor.fetchall()
    cursor.close()
    conn.close()

    if request.method == 'POST':
        numero_guia = request.form['numero_guia']
        mensajero = request.form['mensajero']
        conn = get_connection()
        cursor = conn.cursor()
        # Aquí deberías validar que la guía está en la zona del mensajero, etc.
        cursor.execute("INSERT INTO despachos (numero_guia, mensajero) VALUES (%s, %s)", (numero_guia, mensajero))
        cursor.execute("UPDATE guias SET estado='despachado' WHERE numero_guia=%s", (numero_guia,))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Guía despachada correctamente', 'success')
        return redirect(url_for('despachar_guias'))
    return render_template('despachar_guias.html', guias=guias, mensajeros=mensajeros)

@app.route('/registrar_recepcion', methods=['GET', 'POST'])
def registrar_recepcion():
    if request.method == 'POST':
        numero_guia = request.form['numero_guia']
        estado = request.form['estado']
        causal = request.form['causal']
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO recepciones (numero_guia, estado, causal) VALUES (%s, %s, %s)", (numero_guia, estado, causal))
        cursor.execute("UPDATE guias SET estado=%s WHERE numero_guia=%s", (estado, numero_guia))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Recepción registrada', 'success')
        return redirect(url_for('registrar_recepcion'))
    return render_template('registrar_recepcion.html')

@app.route('/registrar_recogida', methods=['GET', 'POST'])
def registrar_recogida():
    if request.method == 'POST':
        numero_guia = request.form['numero_guia']
        fecha = request.form['fecha']
        observaciones = request.form['observaciones']
        try:
            fecha_dt = datetime.strptime(fecha, '%Y-%m-%d')
        except ValueError:
            flash('Fecha inválida', 'error')
            return redirect(url_for('registrar_recogida'))
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO recogidas (numero_guia, fecha, observaciones) VALUES (%s, %s, %s)", (numero_guia, fecha_dt, observaciones))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Recogida registrada', 'success')
        return redirect(url_for('registrar_recogida'))
    return render_template('registrar_recogida.html')

@app.route('/liquidacion')
def liquidacion():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT mensajero, COUNT(*) as total_guias, SUM(z.tarifa) as total_pago
        FROM despachos d
        JOIN guias g ON d.numero_guia = g.numero_guia
        JOIN zonas z ON g.zona = z.nombre
        GROUP BY mensajero
    """)
    resultados = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('liquidacion.html', resultados=resultados)

# Aquí agrega más rutas según lo necesites, siguiendo el patrón arriba.

if __name__ == '__main__':
    crear_tablas()
    app.run(host='0.0.0.0', port=10000, debug=True)
