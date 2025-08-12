from flask import Flask, render_template, request, redirect, url_for, flash
import pandas as pd
import os
import psycopg2
import psycopg2.extras
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'secreto'
DATA_DIR = 'data'
os.makedirs(DATA_DIR, exist_ok=True)

# Parámetros conexión PostgreSQL Neon (ajusta según tus datos)
DB_PARAMS = {
    'host': 'ep-soft-bush-acv2a8v4-pooler.sa-east-1.aws.neon.tech',
    'database': 'neondb',
    'user': 'neondb_owner',
    'password': 'npg_3owpfIUOAT0a',
    'port': 5432,
    'sslmode': 'require'
}

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
    conn = psycopg2.connect(**DB_PARAMS)
    return conn

def cargar_datos_desde_db():
    global zonas, mensajeros, guias, despachos, recepciones, recogidas

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # Cargar zonas
    zonas = []
    cur.execute('SELECT nombre, tarifa FROM zonas')
    for row in cur.fetchall():
        zonas.append(Zona(row['nombre'], row['tarifa']))

    # Cargar mensajeros
    mensajeros = []
    cur.execute('SELECT nombre, zona FROM mensajeros')
    for row in cur.fetchall():
        zona_obj = next((z for z in zonas if z.nombre == row['zona']), None)
        mensajeros.append(Mensajero(row['nombre'], zona_obj))

    # Cargar guías con pandas usando fetchall + DataFrame
    cur.execute('SELECT remitente, numero_guia, destinatario, direccion, ciudad FROM guias')
    rows = cur.fetchall()
    guias = pd.DataFrame(rows, columns=['remitente', 'numero_guia', 'destinatario', 'direccion', 'ciudad'])

    # Cargar despachos
    despachos = []
    cur.execute('SELECT numero_guia, mensajero, zona, fecha FROM despachos')
    for row in cur.fetchall():
        despachos.append(dict(row))

    # Cargar recepciones
    recepciones = []
    cur.execute('SELECT numero_guia, tipo, motivo, fecha FROM recepciones')
    for row in cur.fetchall():
        recepciones.append(dict(row))

    # Cargar recogidas
    recogidas = []
    cur.execute('SELECT numero_guia, fecha, observaciones FROM recogidas')
    for row in cur.fetchall():
        recogidas.append(dict(row))

    cur.close()
    conn.close()

def ejecutar_query(query, params=()):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    cur.close()
    conn.close()

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
                    # Insertar solo si no existe
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

                cargar_datos_desde_db()

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
            cur = conn.cursor()
            zona_obj = next((z for z in zonas if z.nombre == zona_nombre), None)
            if not zona_obj:
                flash('Zona no encontrada', 'danger')
                cur.close()
                conn.close()
                return redirect(url_for('registrar_mensajero'))

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
        fecha = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
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
            # Validar que la guía exista en la base cargada
            cur.execute('SELECT 1 FROM guias WHERE numero_guia = %s', (numero,))
            existe_guia = cur.fetchone()
            if not existe_guia:
                errores.append(f'Guía {numero} no existe (FALTANTE)')
                continue

            # Validar que no esté despachada a otro mensajero
            cur.execute('SELECT * FROM despachos WHERE numero_guia = %s', (numero,))
            despacho_existente = cur.fetchone()
            cur.execute('SELECT * FROM recepciones WHERE numero_guia = %s', (numero,))
            recepcion_existente = cur.fetchone()

            if recepcion_existente:
                errores.append(f'Guía {numero} ya fue {recepcion_existente[1]}')  # tipo está en index 1
                continue

            if despacho_existente:
                errores.append(f'Guía {numero} ya fue despachada a {despacho_existente[1]}')  # mensajero en index 1
                continue

            # Insertar despacho
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

        fecha = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

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
        cur = conn.cursor()
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
            cur.close()
            conn.close()

            if recepcion:
                estado = recepcion[1]  # tipo
                motivo = recepcion[2]
                mensajero = despacho[1] if despacho else ''
                zona = despacho[2] if despacho else ''
                fecha = recepcion[3]
            elif despacho:
                estado = 'DESPACHADA'
                motivo = ''
                mensajero = despacho[1]
                zona = despacho[2]
                fecha = despacho[3]
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
            flash('Fechas inválidas', 'danger')
            return redirect(url_for('liquidacion'))

        conn = get_db_connection()
        cur = conn.cursor()
        query = '''
            SELECT COUNT(*) AS cantidad, SUM(z.tarifa) AS total
            FROM despachos d
            JOIN zonas z ON d.zona = z.nombre
            WHERE d.mensajero = %s AND d.fecha::date BETWEEN %s AND %s
        '''
        cur.execute(query, (mensajero_nombre, fecha_inicio, fecha_fin))
        res = cur.fetchone()
        cantidad = res[0] or 0
        total = res[1] or 0.0
        cur.close()
        conn.close()

        liquidacion = {
            'mensajero': mensajero_nombre,
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
            'cantidad': cantidad,
            'total': total
        }

    return render_template('liquidacion.html', mensajeros=[m.nombre for m in mensajeros], liquidacion=liquidacion)

@app.route('/registrar_recogida', methods=['GET', 'POST'])
def registrar_recogida():
    if request.method == 'POST':
        numero_guia = request.form.get('numero_guia')
        fecha = request.form.get('fecha')
        observaciones = request.form.get('observaciones')

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT 1 FROM guias WHERE numero_guia = %s', (numero_guia,))
        existe_guia = cur.fetchone()
        if not existe_guia:
            flash('Número de guía no existe en la base (FALTANTE)', 'danger')
            cur.close()
            conn.close()
            return redirect(url_for('registrar_recogida'))

        cur.execute('INSERT INTO recogidas (numero_guia, fecha, observaciones) VALUES (%s, %s, %s)',
                    (numero_guia, fecha, observaciones))
        conn.commit()
        cur.close()
        conn.close()

        flash(f'Recogida de guía {numero_guia} registrada', 'success')
        cargar_datos_desde_db()
        return redirect(url_for('registrar_recogida'))

    return render_template('registrar_recogida.html')

if __name__ == '__main__':
    app.run(debug=True)
