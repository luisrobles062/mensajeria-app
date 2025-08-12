from flask import Flask, render_template, request, redirect, url_for, flash
import psycopg2
import psycopg2.extras
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'secreto'

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://usuario:password@host:puerto/dbname')

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

# -- RUTAS PRINCIPALES --

@app.route('/')
def index():
    return render_template('index.html')

# -- ZONAS --

@app.route('/zonas')
def ver_zonas():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT nombre, tarifa FROM zonas ORDER BY nombre;')
    zonas = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('zonas.html', zonas=zonas)

@app.route('/zonas/nuevo', methods=['GET', 'POST'])
def nueva_zona():
    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        tarifa = request.form['tarifa'].strip()
        try:
            tarifa = float(tarifa)
        except ValueError:
            flash('La tarifa debe ser un número válido.', 'error')
            return redirect(url_for('nueva_zona'))

        conn = get_db_connection()
        cur = conn.cursor()
        # Aquí asumimos que 'nombre' es UNIQUE en la tabla zonas
        cur.execute('INSERT INTO zonas (nombre, tarifa) VALUES (%s, %s)', (nombre, tarifa))
        conn.commit()
        cur.close()
        conn.close()
        flash('Zona agregada correctamente.')
        return redirect(url_for('ver_zonas'))
    return render_template('nueva_zona.html')

# -- MENSAJEROS --

@app.route('/mensajeros')
def ver_mensajeros():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    # Relacion por nombre de zona, sin usar id
    cur.execute('''
        SELECT m.nombre as mensajero, z.nombre as zona_nombre 
        FROM mensajeros m 
        LEFT JOIN zonas z ON m.zona = z.nombre 
        ORDER BY m.nombre;
    ''')
    mensajeros = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('mensajeros.html', mensajeros=mensajeros)

@app.route('/mensajeros/nuevo', methods=['GET', 'POST'])
def nuevo_mensajero():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT nombre FROM zonas ORDER BY nombre;')
    zonas = cur.fetchall()
    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        zona = request.form['zona'].strip()
        cur.execute('INSERT INTO mensajeros (nombre, zona) VALUES (%s, %s)', (nombre, zona))
        conn.commit()
        cur.close()
        conn.close()
        flash('Mensajero agregado correctamente.')
        return redirect(url_for('ver_mensajeros'))
    cur.close()
    conn.close()
    return render_template('nuevo_mensajero.html', zonas=zonas)

# -- GUIAS --

@app.route('/guias')
def ver_guias():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT remitente, numero_guia, destinatario, direccion, ciudad FROM guias ORDER BY numero_guia;')
    guias = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('guias.html', guias=guias)

@app.route('/guias/nuevo', methods=['GET', 'POST'])
def nueva_guia():
    if request.method == 'POST':
        remitente = request.form['remitente'].strip()
        numero_guia = request.form['numero_guia'].strip()
        destinatario = request.form['destinatario'].strip()
        direccion = request.form['direccion'].strip()
        ciudad = request.form['ciudad'].strip()
        fecha = datetime.now().date()

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO guias (remitente, numero_guia, destinatario, direccion, ciudad, fecha) 
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (remitente, numero_guia, destinatario, direccion, ciudad, fecha))
        conn.commit()
        cur.close()
        conn.close()
        flash('Guía agregada correctamente.')
        return redirect(url_for('ver_guias'))
    return render_template('nueva_guia.html')

# -- DESPACHOS --

@app.route('/despachos')
def ver_despachos():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('''
        SELECT d.numero_guia, d.fecha_despacho, m.nombre as mensajero, m.zona
        FROM despachos d
        LEFT JOIN mensajeros m ON d.mensajero = m.nombre
        ORDER BY d.fecha_despacho DESC;
    ''')
    despachos = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('despachos.html', despachos=despachos)

@app.route('/despachos/nuevo', methods=['GET', 'POST'])
def nuevo_despacho():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT nombre FROM mensajeros ORDER BY nombre;')
    mensajeros = cur.fetchall()
    if request.method == 'POST':
        numero_guia = request.form['numero_guia'].strip()
        mensajero = request.form['mensajero'].strip()
        fecha_despacho = datetime.now()

        cur.execute('INSERT INTO despachos (numero_guia, mensajero, fecha_despacho) VALUES (%s, %s, %s)',
                    (numero_guia, mensajero, fecha_despacho))
        conn.commit()
        cur.close()
        conn.close()
        flash('Despacho registrado correctamente.')
        return redirect(url_for('ver_despachos'))
    cur.close()
    conn.close()
    return render_template('nuevo_despacho.html', mensajeros=mensajeros)

# -- RECOGIDAS --

@app.route('/recogidas')
def ver_recogidas():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT numero_guia, fecha, observaciones FROM recogidas ORDER BY fecha DESC;')
    recogidas = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('ver_recogidas.html', recogidas=recogidas)

@app.route('/recogidas/registrar', methods=['GET', 'POST'])
def registrar_recogida():
    if request.method == 'POST':
        numero_guia = request.form['numero_guia'].strip()
        fecha = request.form['fecha'].strip()
        observaciones = request.form['observaciones'].strip()

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('INSERT INTO recogidas (numero_guia, fecha, observaciones) VALUES (%s, %s, %s)',
                    (numero_guia, fecha, observaciones))
        conn.commit()
        cur.close()
        conn.close()
        flash('Recogida registrada correctamente.')
        return redirect(url_for('ver_recogidas'))
    return render_template('registrar_recogida.html')

# -- LIQUIDACIÓN --

@app.route('/liquidacion')
def liquidacion():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    # Sumando tarifas agrupadas por mensajero según zona
    cur.execute('''
        SELECT m.nombre as mensajero, COUNT(d.numero_guia) as total_guias, SUM(z.tarifa) as total_pago
        FROM despachos d
        JOIN mensajeros m ON d.mensajero = m.nombre
        JOIN zonas z ON m.zona = z.nombre
        GROUP BY m.nombre
        ORDER BY m.nombre;
    ''')
    liquidacion = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('liquidacion.html', liquidacion=liquidacion)

# -- Error 404 --

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404


if __name__ == '__main__':
    app.run(debug=True)
