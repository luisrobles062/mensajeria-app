import os
from flask import Flask, render_template, request, redirect, url_for, flash
import psycopg2
import psycopg2.extras
import pandas as pd

app = Flask(__name__)
app.secret_key = 'tu_secreto_aqui'

# String de conexión a tu base PostgreSQL Neon/Render
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://usuario:password@host:puerto/dbname')

# Función para conectar a la DB
def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

# Crear tablas si no existen (adaptar a tu estructura)
def crear_tablas():
    conn = get_db_connection()
    cur = conn.cursor()
    # Ajusta columnas según tus datos y necesidades
    cur.execute('''
        CREATE TABLE IF NOT EXISTS zonas (
            nombre TEXT PRIMARY KEY,
            tarifa NUMERIC
        );
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS mensajeros (
            nombre TEXT PRIMARY KEY,
            zona TEXT,
            FOREIGN KEY (zona) REFERENCES zonas(nombre)
        );
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS guias (
            numero_guia TEXT PRIMARY KEY,
            remitente TEXT,
            destinatario TEXT,
            direccion TEXT,
            ciudad TEXT,
            zona TEXT
        );
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS despachos (
            numero_guia TEXT PRIMARY KEY,
            mensajero TEXT,
            fecha TIMESTAMP,
            FOREIGN KEY (numero_guia) REFERENCES guias(numero_guia),
            FOREIGN KEY (mensajero) REFERENCES mensajeros(nombre)
        );
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS recepciones (
            numero_guia TEXT PRIMARY KEY,
            fecha TIMESTAMP,
            estado TEXT,
            causal TEXT,
            FOREIGN KEY (numero_guia) REFERENCES guias(numero_guia)
        );
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS recogidas (
            numero_guia TEXT PRIMARY KEY,
            fecha TIMESTAMP,
            observaciones TEXT
        );
    ''')
    conn.commit()
    cur.close()
    conn.close()

# Carga inicial para crear tablas
crear_tablas()

# Ruta principal (index)
@app.route('/')
def index():
    return render_template('index.html')

# Ruta para cargar base de guías desde Excel
@app.route('/cargar_base', methods=['GET', 'POST'])
def cargar_base():
    if request.method == 'POST':
        file = request.files.get('archivo_excel')
        if not file:
            flash('No se ha seleccionado ningún archivo')
            return redirect(request.url)
        try:
            df = pd.read_excel(file)
            # Esperamos columnas: remitente, numero_guia, destinatario, direccion, ciudad, zona
            conn = get_db_connection()
            cur = conn.cursor()
            for _, row in df.iterrows():
                cur.execute('''
                    INSERT INTO guias (numero_guia, remitente, destinatario, direccion, ciudad, zona)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (numero_guia) DO NOTHING;
                ''', (str(row['numero_guia']), row['remitente'], row['destinatario'], row['direccion'], row['ciudad'], row.get('zona', None)))
            conn.commit()
            cur.close()
            conn.close()
            flash('Base de guías cargada correctamente')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'Error al cargar el archivo: {e}')
            return redirect(request.url)
    return render_template('cargar_base.html')

# Ruta para registrar zona
@app.route('/registrar_zona', methods=['GET', 'POST'])
def registrar_zona():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        tarifa = request.form.get('tarifa')
        if not nombre or not tarifa:
            flash('Debe ingresar nombre y tarifa')
            return redirect(request.url)
        try:
            tarifa_float = float(tarifa)
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('INSERT INTO zonas (nombre, tarifa) VALUES (%s, %s) ON CONFLICT (nombre) DO UPDATE SET tarifa = EXCLUDED.tarifa;', (nombre, tarifa_float))
            conn.commit()
            cur.close()
            conn.close()
            flash('Zona registrada/actualizada correctamente')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'Error al registrar zona: {e}')
            return redirect(request.url)
    return render_template('registrar_zona.html')

# Ruta para registrar mensajero
@app.route('/registrar_mensajero', methods=['GET', 'POST'])
def registrar_mensajero():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        zona = request.form.get('zona')
        if not nombre or not zona:
            flash('Debe ingresar nombre y zona')
            return redirect(request.url)
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            # Verificar si zona existe
            cur.execute('SELECT nombre FROM zonas WHERE nombre = %s', (zona,))
            if not cur.fetchone():
                flash('La zona indicada no existe')
                return redirect(request.url)
            cur.execute('INSERT INTO mensajeros (nombre, zona) VALUES (%s, %s) ON CONFLICT (nombre) DO UPDATE SET zona = EXCLUDED.zona;', (nombre, zona))
            conn.commit()
            cur.close()
            conn.close()
            flash('Mensajero registrado/actualizado correctamente')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'Error al registrar mensajero: {e}')
            return redirect(request.url)
    # Para mostrar zonas en el formulario
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT nombre FROM zonas')
    zonas = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return render_template('registrar_mensajero.html', zonas=zonas)

# Ruta para despachar guías
@app.route('/despachar', methods=['GET', 'POST'])
def despachar():
    if request.method == 'POST':
        mensajero = request.form.get('mensajero')
        numeros_guias = request.form.get('numeros_guias')
        if not mensajero or not numeros_guias:
            flash('Debe ingresar mensajero y números de guía')
            return redirect(request.url)
        numeros = [n.strip() for n in numeros_guias.split(',')]
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            # Validar mensajero y zona
            cur.execute('SELECT zona FROM mensajeros WHERE nombre = %s', (mensajero,))
            zona_mensajero = cur.fetchone()
            if not zona_mensajero:
                flash('Mensajero no existe')
                return redirect(request.url)
            zona_mensajero = zona_mensajero[0]
            for num in numeros:
                # Validar guía existe y pertenece a la zona
                cur.execute('SELECT zona FROM guias WHERE numero_guia = %s', (num,))
                guia = cur.fetchone()
                if not guia:
                    flash(f'Guía {num} no existe')
                    continue
                if guia[0] != zona_mensajero:
                    flash(f'Guía {num} no pertenece a la zona del mensajero')
                    continue
                # Verificar si ya fue despachada
                cur.execute('SELECT numero_guia FROM despachos WHERE numero_guia = %s', (num,))
                if cur.fetchone():
                    flash(f'Guía {num} ya fue despachada')
                    continue
                # Insertar despacho
                cur.execute('INSERT INTO despachos (numero_guia, mensajero, fecha) VALUES (%s, %s, NOW())', (num, mensajero))
            conn.commit()
            cur.close()
            conn.close()
            flash('Despacho realizado (verifique mensajes)')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'Error al despachar: {e}')
            return redirect(request.url)
    # Listar mensajeros para formulario
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT nombre FROM mensajeros')
    mensajeros = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return render_template('despachar.html', mensajeros=mensajeros)

# Ruta para consultar estado de guías
@app.route('/consultar_estado', methods=['GET', 'POST'])
def consultar_estado():
    estado_info = None
    if request.method == 'POST':
        numero_guia = request.form.get('numero_guia')
        if not numero_guia:
            flash('Debe ingresar número de guía')
            return redirect(request.url)
        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute('''
                SELECT g.*, d.fecha as fecha_despacho, r.fecha as fecha_recepcion, r.estado, r.causal, m.zona as zona_mensajero
                FROM guias g
                LEFT JOIN despachos d ON g.numero_guia = d.numero_guia
                LEFT JOIN recepciones r ON g.numero_guia = r.numero_guia
                LEFT JOIN mensajeros m ON d.mensajero = m.nombre
                WHERE g.numero_guia = %s
            ''', (numero_guia,))
            estado_info = cur.fetchone()
            cur.close()
            conn.close()
            if not estado_info:
                flash('Número de guía no encontrado')
                return redirect(request.url)
        except Exception as e:
            flash(f'Error al consultar estado: {e}')
            return redirect(request.url)
    return render_template('consultar_estado.html', estado=estado_info)

# Ruta para registrar recepción (entrega o devolución)
@app.route('/registrar_recepcion', methods=['GET', 'POST'])
def registrar_recepcion():
    if request.method == 'POST':
        numero_guia = request.form.get('numero_guia')
        estado = request.form.get('estado')
        causal = request.form.get('causal')
        if not numero_guia or not estado:
            flash('Debe ingresar número de guía y estado')
            return redirect(request.url)
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('INSERT INTO recepciones (numero_guia, fecha, estado, causal) VALUES (%s, NOW(), %s, %s) ON CONFLICT (numero_guia) DO UPDATE SET fecha = NOW(), estado = EXCLUDED.estado, causal = EXCLUDED.causal;', (numero_guia, estado, causal))
            conn.commit()
            cur.close()
            conn.close()
            flash('Recepción registrada correctamente')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'Error al registrar recepción: {e}')
            return redirect(request.url)
    return render_template('registrar_recepcion.html')

# Ruta para registrar recogida
@app.route('/registrar_recogida', methods=['GET', 'POST'])
def registrar_recogida():
    if request.method == 'POST':
        numero_guia = request.form.get('numero_guia')
        observaciones = request.form.get('observaciones')
        if not numero_guia:
            flash('Debe ingresar número de guía')
            return redirect(request.url)
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('INSERT INTO recogidas (numero_guia, fecha, observaciones) VALUES (%s, NOW(), %s) ON CONFLICT (numero_guia) DO UPDATE SET fecha = NOW(), observaciones = EXCLUDED.observaciones;', (numero_guia, observaciones))
            conn.commit()
            cur.close()
            conn.close()
            flash('Recogida registrada correctamente')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'Error al registrar recogida: {e}')
            return redirect(request.url)
    return render_template('registrar_recogida.html')

if __name__ == '__main__':
    app.run(debug=True, port=5000)
