from flask import Flask, render_template, request, redirect, url_for, flash
import pandas as pd
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'secreto'
DATA_DIR = 'data'
os.makedirs(DATA_DIR, exist_ok=True)

# Cadena conexión PostgreSQL Neon
DATABASE_URL = "postgresql://neondb_owner:npg_3owpfIUOAT0a@ep-soft-bush-acv2a8v4-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

# Clases para Zona y Mensajero con tarifa
class Zona:
    def __init__(self, nombre, tarifa):
        self.nombre = nombre
        self.tarifa = tarifa

class Mensajero:
    def __init__(self, nombre, zona):
        self.nombre = nombre
        self.zona = zona

# Inicializamos listas (se cargarán desde DB)
zonas = []
mensajeros = []
guias = pd.DataFrame(columns=['remitente', 'numero_guia', 'destinatario', 'direccion', 'ciudad'])
despachos = []
recepciones = []
recogidas = []

# ---------- FUNCIONES PARA BASE DE DATOS ----------

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def crear_tablas():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS zonas (
            nombre VARCHAR(255) PRIMARY KEY,
            tarifa NUMERIC NOT NULL
        );
        CREATE TABLE IF NOT EXISTS mensajeros (
            nombre VARCHAR(255) PRIMARY KEY,
            zona VARCHAR(255) REFERENCES zonas(nombre)
        );
        CREATE TABLE IF NOT EXISTS guias (
            remitente VARCHAR(255),
            numero_guia VARCHAR(255) PRIMARY KEY,
            destinatario VARCHAR(255),
            direccion VARCHAR(255),
            ciudad VARCHAR(255)
        );
        CREATE TABLE IF NOT EXISTS despachos (
            numero_guia VARCHAR(255) PRIMARY KEY REFERENCES guias(numero_guia),
            mensajero VARCHAR(255) REFERENCES mensajeros(nombre),
            zona VARCHAR(255),
            fecha TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS recepciones (
            numero_guia VARCHAR(255) PRIMARY KEY REFERENCES guias(numero_guia),
            tipo VARCHAR(50),
            motivo TEXT,
            fecha TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS recogidas (
            id SERIAL PRIMARY KEY,
            numero_guia VARCHAR(255),
            fecha DATE,
            observaciones TEXT
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

def cargar_datos_desde_db():
    global zonas, mensajeros, guias, despachos, recepciones, recogidas

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Cargar zonas
    zonas = []
    cur.execute('SELECT nombre, tarifa FROM zonas;')
    for row in cur.fetchall():
        zonas.append(Zona(row['nombre'], float(row['tarifa'])))

    # Cargar mensajeros
    mensajeros = []
    cur.execute('SELECT nombre, zona FROM mensajeros;')
    for row in cur.fetchall():
        zona_obj = next((z for z in zonas if z.nombre == row['zona']), None)
        mensajeros.append(Mensajero(row['nombre'], zona_obj))

    # Cargar guias
    guias = pd.read_sql_query('SELECT remitente, numero_guia, destinatario, direccion, ciudad FROM guias;', conn)

    # Cargar despachos
    despachos = []
    cur.execute('SELECT numero_guia, mensajero, zona, fecha FROM despachos;')
    for row in cur.fetchall():
        despachos.append(row)

    # Cargar recepciones
    recepciones = []
    cur.execute('SELECT numero_guia, tipo, motivo, fecha FROM recepciones;')
    for row in cur.fetchall():
        recepciones.append(row)

    # Cargar recogidas
    recogidas = []
    cur.execute('SELECT id, numero_guia, fecha, observaciones FROM recogidas;')
    for row in cur.fetchall():
        recogidas.append(row)

    cur.close()
    conn.close()

def ejecutar_query(query, params=()):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    cur.close()
    conn.close()

# Crear tablas al iniciar app
crear_tablas()

# Cargar datos al iniciar app
cargar_datos_desde_db()

# ---------- RUTAS ----------

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/cargar_base', methods=['GET', 'POST'])
def cargar_base():
    global guias
    if request.method == 'POST':
        archivo = request.files.get('archivo_excel')
        if archivo:
            df = pd.read_excel(archivo)
            required_cols = ['remitente', 'numero_guia', 'destinatario', 'direccion', 'ciudad']
            if all(col in df.columns for col in required_cols):
                conn = get_db_connection()
                cur = conn.cursor()
                for _, row in df.iterrows():
                    cur.execute('SELECT 1 FROM guias WHERE numero_guia = %s', (str(row['numero_guia']),))
                    existe = cur.fetchone()
                    if not existe:
                        cur.execute(
                            'INSERT INTO guias (remitente, numero_guia, destinatario, direccion, ciudad) VALUES (%s, %s, %s, %s, %s)',
                            (row['remitente'], str(row['numero_guia']), row['destinatario'], row['direccion'], row['ciudad'])
                        )
                conn.commit()
                cur.close()
                conn.close()

                guias = pd.read_sql_query('SELECT remitente, numero_guia, destinatario, direccion, ciudad FROM guias;', get_db_connection())

                archivo.save(os.path.join(DATA_DIR, archivo.filename))
                flash('Base de datos cargada correctamente.', 'success')
            else:
                flash('El archivo debe contener las columnas: ' + ", ".join(required_cols), 'danger')
    return render_template('cargar_base.html')

@app.route('/registrar_zona', methods=['GET', 'POST'])
def registrar_zona():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        tarifa = request.form.get('tarifa')
        if nombre and tarifa:
            try:
                tarifa_float = float(tarifa)
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute('SELECT 1 FROM zonas WHERE nombre = %s', (nombre,))
                existe = cur.fetchone()
                if existe:
                    flash('La zona ya existe', 'warning')
                else:
                    cur.execute('INSERT INTO zonas (nombre, tarifa) VALUES (%s, %s)', (nombre, tarifa_float))
                    conn.commit()
                    flash(f'Zona {nombre} registrada con tarifa {tarifa_float}', 'success')
                cur.close()
                conn.close()
            except ValueError:
                flash('Tarifa inválida, debe ser un número', 'danger')
        else:
            flash('Debe completar todos los campos', 'danger')
        cargar_datos_desde_db()
    return render_template('registrar_zona.html', zonas=zonas)

@app.route('/registrar_mensajero', methods=['GET', 'POST'])
def registrar_mensajero():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        zona_nombre = request.form.get('zona')
        if nombre and zona_nombre:
            conn = get_db_connection()
            zona_obj = next((z for z in zonas if z.nombre == zona_nombre), None)
            if not zona_obj:
                flash('Zona no encontrada', 'danger')
                return redirect(url_for('registrar_mensajero'))

            cur = conn.cursor()
            cur.execute('SELECT 1 FROM mensajeros WHERE nombre = %s', (nombre,))
            existe = cur.fetchone()
            if existe:
                flash('El mensajero ya existe', 'warning')
            else:
                cur.execute('INSERT INTO mensajeros (nombre, zona) VALUES (%s, %s)', (nombre, zona_nombre))
                conn.commit()
                flash(f'Mensajero {nombre} registrado en zona {zona_nombre}', 'success')
            cur.close()
            conn.close()
            cargar_datos_desde_db()
        else:
            flash('Debe completar todos los campos', 'danger')
    return render_template('registrar_mensajero.html', zonas=zonas, mensajeros=mensajeros)

@app.route('/despachar_guias', methods=['GET', 'POST'])
def despachar_guias():
    if request.method == 'POST':
        mensajero_nombre = request.form.get('mensajero')
        guias_input = request.form.get('guias', '')
        guias_list = [g.strip() for g in guias_input.strip().splitlines() if g.strip()]
        fecha = datetime.now()

        mensajero_obj = next((m for m in mensajeros if m.nombre == mensajero_nombre), None)

        if not mensajero_obj:
            flash('Mensajero no encontrado', 'danger')
            return redirect(url_for('despachar_guias'))

        zona_obj = mensajero_obj.zona

        errores = []
        exito = []

        conn = get_db_connection()
        cur = conn.cursor()

        for numero in guias_list:
            cur.execute('SELECT 1 FROM guias WHERE numero_guia = %s', (numero,))
            existe_guia = cur.fetchone()
            if not existe_guia:
                errores.append(f'Guía {numero} no existe (FALTANTE)')
                continue

            cur.execute('SELECT * FROM despachos WHERE numero_guia = %s', (numero,))
            despacho_existente = cur.fetchone()
            cur.execute('SELECT * FROM recepciones WHERE numero_guia = %s', (numero,))
            recepcion_existente = cur.fetchone()

            if recepcion_existente:
                errores.append(f'Guía {numero} ya fue {recepcion_existente[1]}')  # tipo
                continue

            if despacho_existente:
                errores.append(f'Guía {numero} ya fue despachada a {despacho_existente[1]}')  # mensajero
                continue

            cur.execute(
                'INSERT INTO despachos (numero_guia, mensajero, zona, fecha) VALUES (%s, %s, %s, %s)',
                (numero, mensajero_nombre, zona_obj.nombre, fecha)
            )
            exito.append(f'Guía {numero} despachada a {mensajero_nombre}')

        conn.commit()
        cur.close()
        conn.close()

        if errores:
            flash("Errores:<br>" + "<br>".join(errores), 'danger')
        if exito:
            flash("Despachos exitosos:<br>" + "<br>".join(exito), 'success')

        cargar_datos_desde_db()
        return redirect(url_for('ver_despacho'))

    return render_template('despachar_guias.html', mensajeros=[m.nombre for m in mensajeros], zonas=[z.nombre for z in zonas])

@app.route('/ver_despacho')
def ver_despacho():
    return render_template('ver_despacho.html', despachos=despachos)

@app.route('/registrar_recepcion', methods=['GET', 'POST'])
def registrar_recepcion():
    if request.method == 'POST':
        numero_guia = request.form.get('numero_guia')
        tipo = request.form.get('estado')  # 'ENTREGADA' o 'DEVUELTA'
        motivo = request.form.get('motivo', '')

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT 1 FROM guias WHERE numero_guia = %s', (numero_guia,))
        existe_guia = cur.fetchone()
        if not existe_guia:
            flash('Número de guía no existe en la base (FALTANTE)', 'danger')
            cur.close()
            conn.close()
            return redirect(url_for('registrar_recepcion'))

        cur.execute('SELECT * FROM despachos WHERE numero_guia = %s', (numero_guia,))
        despacho_existente = cur.fetchone()
        if not despacho_existente:
            flash('La guía no ha sido despachada aún', 'warning')
            cur.close()
            conn.close()
            return redirect(url_for('registrar_recepcion'))

        cur.execute('SELECT * FROM recepciones WHERE numero_guia = %s', (numero_guia,))
        recepcion_existente = cur.fetchone()
        if recepcion_existente:
            flash('La recepción para esta guía ya está registrada', 'warning')
            cur.close()
            conn.close()
            return redirect(url_for('registrar_recepcion'))

        fecha = datetime.now()

        cur.execute(
            'INSERT INTO recepciones (numero_guia, tipo, motivo, fecha) VALUES (%s, %s, %s, %s)',
            (numero_guia, tipo, motivo if tipo == 'DEVUELTA' else '', fecha)
        )
        conn.commit()
        cur.close()
        conn.close()

        flash(f'Recepción de guía {numero_guia} registrada como {tipo}', 'success')
        cargar_datos_desde_db()
        return redirect(url_for('registrar_recepcion'))

    return render_template('registrar_recepcion.html')

@app.route('/consultar_estado', methods=['GET', 'POST'])
def consultar_estado():
    resultado = None
    if request.method == 'POST':
        numero_guia = request.form.get('numero_guia', '').strip()
        if not numero_guia:
            flash('Debe ingresar un número de guía', 'warning')
            return redirect(url_for('consultar_estado'))

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute('SELECT 1 FROM guias WHERE numero_guia = %s', (numero_guia,))
        existe_guia = cur.fetchone()
        if not existe_guia:
            resultado = {
                'numero_guia': numero_guia,
                'estado': 'FALTANTE',
                'motivo': '',
                'mensajero': '',
                'zona': '',
                'fecha': ''
            }
        else:
            cur.execute('SELECT * FROM despachos WHERE numero_guia = %s', (numero_guia,))
            despacho = cur.fetchone()
            cur.execute('SELECT * FROM recepciones WHERE numero_guia = %s', (numero_guia,))
            recepcion = cur.fetchone()

            if recepcion:
                estado = recepcion['tipo']
                motivo = recepcion['motivo']
                mensajero = despacho['mensajero'] if despacho else ''
                zona = despacho['zona'] if despacho else ''
                fecha = recepcion['fecha']
            elif despacho:
                estado = 'DESPACHADA'
                motivo = ''
                mensajero = despacho['mensajero']
                zona = despacho['zona']
                fecha = despacho['fecha']
            else:
                estado = 'EN VERIFICACION'
                motivo = ''
                mensajero = ''
                zona = ''
                fecha = ''

            resultado = {
                'numero_guia': numero_guia,
                'estado': estado,
                'motivo': motivo,
                'mensajero': mensajero,
                'zona': zona,
                'fecha': fecha
            }
        cur.close()
        conn.close()
    return render_template('consultar_estado.html', resultado=resultado)

@app.route('/liquidacion', methods=['GET', 'POST'])
def liquidacion():
    liquidacion = None
    if request.method == 'POST':
        mensajero_nombre = request.form.get('mensajero')
        fecha_inicio = request.form.get('fecha_inicio')
        fecha_fin = request.form.get('fecha_fin')

        try:
            dt_inicio = datetime.strptime(fecha_inicio, '%Y-%m-%d')
            dt_fin = datetime.strptime(fecha_fin, '%Y-%m-%d')
        except Exception:
            flash('Formato de fechas inválido', 'danger')
            return redirect(url_for('liquidacion'))

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            'SELECT * FROM despachos WHERE mensajero = %s AND fecha::date BETWEEN %s AND %s',
            (mensajero_nombre, fecha_inicio, fecha_fin)
        )
        gui_despachadas = cur.fetchall()
        cur.close()
        conn.close()

        cantidad_guias = len(gui_despachadas)
        mensajero_obj = next((m for m in mensajeros if m.nombre == mensajero_nombre), None)
        tarifa = mensajero_obj.zona.tarifa if mensajero_obj and mensajero_obj.zona else 0
        total_pagar = cantidad_guias * tarifa

        liquidacion = {
            'mensajero': mensajero_nombre,
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
            'cantidad_guias': cantidad_guias,
            'total_pagar': total_pagar
        }
    return render_template('liquidacion.html', mensajeros=mensajeros, liquidacion=liquidacion)

@app.route('/registrar_recogida', methods=['GET', 'POST'])
def registrar_recogida():
    if request.method == 'POST':
        numero_guia = request.form.get('numero_guia', '').strip()
        fecha = request.form.get('fecha')
        observaciones = request.form.get('observaciones', '').strip()

        if not numero_guia or not fecha:
            flash('Debe completar número de guía y fecha', 'danger')
            return redirect(url_for('registrar_recogida'))

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            'INSERT INTO recogidas (numero_guia, fecha, observaciones) VALUES (%s, %s, %s)',
            (numero_guia, fecha, observaciones)
        )
        conn.commit()
        cur.close()
        conn.close()

        flash(f'Recogida registrada para la guía {numero_guia}', 'success')
        cargar_datos_desde_db()
        return redirect(url_for('registrar_recogida'))

    return render_template('registrar_recogida.html')

@app.route('/ver_recogidas')
def ver_recogidas():
    filtro_numero = request.args.get('filtro_numero', '').strip().lower()

    if filtro_numero:
        recogidas_filtradas = [r for r in recogidas if filtro_numero in r['numero_guia'].lower()]
    else:
        recogidas_filtradas = recogidas

    return render_template('ver_recogidas.html', recogidas=recogidas_filtradas)

if __name__ == '__main__':
    app.run(debug=True)
