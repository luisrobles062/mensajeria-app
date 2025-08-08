from flask import Flask, render_template, request, redirect, url_for, flash
import pandas as pd
import os
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

app = Flask(__name__)
app.secret_key = 'secreto'
DATA_DIR = 'data'
os.makedirs(DATA_DIR, exist_ok=True)

# Obtén esta URL de tu variable de entorno o config, por ejemplo:
DATABASE_URL = os.getenv('DATABASE_URL')  # debe estar en formato correcto para SQLAlchemy

# Crear el motor SQLAlchemy
engine = create_engine(DATABASE_URL, echo=False, future=True)

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

def cargar_datos_desde_db():
    global zonas, mensajeros, guias, despachos, recepciones, recogidas
    try:
        with engine.connect() as conn:
            zonas = []
            result = conn.execute(text('SELECT nombre, tarifa FROM zonas'))
            for row in result:
                zonas.append(Zona(row['nombre'], row['tarifa']))

            mensajeros = []
            result = conn.execute(text('SELECT nombre, zona FROM mensajeros'))
            for row in result:
                zona_obj = next((z for z in zonas if z.nombre == row['zona']), None)
                mensajeros.append(Mensajero(row['nombre'], zona_obj))

            guias = pd.read_sql('SELECT remitente, numero_guia, destinatario, direccion, ciudad FROM guias', conn)

            despachos = []
            result = conn.execute(text('SELECT numero_guia, mensajero, zona, fecha FROM despachos'))
            for row in result:
                despachos.append(dict(row))

            recepciones = []
            result = conn.execute(text('SELECT numero_guia, tipo, motivo, fecha FROM recepciones'))
            for row in result:
                recepciones.append(dict(row))

            recogidas = []
            result = conn.execute(text('SELECT numero_guia, fecha, observaciones FROM recogidas'))
            for row in result:
                recogidas.append(dict(row))
    except SQLAlchemyError as e:
        print("Error al cargar datos desde DB:", e)

def ejecutar_query(query, params=()):
    try:
        with engine.begin() as conn:
            conn.execute(text(query), params)
    except SQLAlchemyError as e:
        print("Error en query:", e)
        raise

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
                try:
                    with engine.begin() as conn:
                        for _, row in df.iterrows():
                            existe = conn.execute(
                                text('SELECT 1 FROM guias WHERE numero_guia = :num'),
                                {'num': str(row['numero_guia'])}
                            ).first()
                            if not existe:
                                conn.execute(
                                    text('INSERT INTO guias (remitente, numero_guia, destinatario, direccion, ciudad) VALUES (:r, :n, :d, :dir, :c)'),
                                    {
                                        'r': row['remitente'],
                                        'n': str(row['numero_guia']),
                                        'd': row['destinatario'],
                                        'dir': row['direccion'],
                                        'c': row['ciudad']
                                    }
                                )
                    with engine.connect() as conn:
                        guias = pd.read_sql('SELECT remitente, numero_guia, destinatario, direccion, ciudad FROM guias', conn)

                    archivo.save(os.path.join(DATA_DIR, archivo.filename))
                    flash('Base de datos cargada correctamente.', 'success')
                except SQLAlchemyError as e:
                    flash(f'Error al cargar base: {e}', 'danger')
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
                with engine.begin() as conn:
                    existe = conn.execute(text('SELECT 1 FROM zonas WHERE nombre = :n'), {'n': nombre}).first()
                    if existe:
                        flash('La zona ya existe', 'warning')
                    else:
                        conn.execute(text('INSERT INTO zonas (nombre, tarifa) VALUES (:n, :t)'), {'n': nombre, 't': tarifa_float})
                        flash(f'Zona {nombre} registrada con tarifa {tarifa_float}', 'success')
            except ValueError:
                flash('Tarifa inválida, debe ser un número', 'danger')
            except SQLAlchemyError as e:
                flash(f'Error en base de datos: {e}', 'danger')
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
            zona_obj = next((z for z in zonas if z.nombre == zona_nombre), None)
            if not zona_obj:
                flash('Zona no encontrada', 'danger')
                return redirect(url_for('registrar_mensajero'))
            try:
                with engine.begin() as conn:
                    existe = conn.execute(text('SELECT 1 FROM mensajeros WHERE nombre = :n'), {'n': nombre}).first()
                    if existe:
                        flash('El mensajero ya existe', 'warning')
                    else:
                        conn.execute(text('INSERT INTO mensajeros (nombre, zona) VALUES (:n, :z)'), {'n': nombre, 'z': zona_nombre})
                        flash(f'Mensajero {nombre} registrado en zona {zona_nombre}', 'success')
            except SQLAlchemyError as e:
                flash(f'Error en base de datos: {e}', 'danger')
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

        try:
            with engine.begin() as conn:
                for numero in guias_list:
                    existe_guia = conn.execute(text('SELECT 1 FROM guias WHERE numero_guia = :num'), {'num': numero}).first()
                    if not existe_guia:
                        errores.append(f'Guía {numero} no existe (FALTANTE)')
                        continue

                    despacho_existente = conn.execute(text('SELECT * FROM despachos WHERE numero_guia = :num'), {'num': numero}).first()
                    recepcion_existente = conn.execute(text('SELECT * FROM recepciones WHERE numero_guia = :num'), {'num': numero}).first()

                    if recepcion_existente:
                        errores.append(f'Guía {numero} ya fue {recepcion_existente["tipo"]}')
                        continue

                    if despacho_existente:
                        errores.append(f'Guía {numero} ya fue despachada a {despacho_existente["mensajero"]}')
                        continue

                    conn.execute(
                        text('INSERT INTO despachos (numero_guia, mensajero, zona, fecha) VALUES (:n, :m, :z, :f)'),
                        {'n': numero, 'm': mensajero_nombre, 'z': zona_obj.nombre, 'f': fecha}
                    )
                    exito.append(f'Guía {numero} despachada a {mensajero_nombre}')
        except SQLAlchemyError as e:
            flash(f'Error en base de datos: {e}', 'danger')
            return redirect(url_for('despachar_guias'))

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

        try:
            with engine.connect() as conn:
                existe_guia = conn.execute(text('SELECT 1 FROM guias WHERE numero_guia = :n'), {'n': numero_guia}).first()
                if not existe_guia:
                    flash('Número de guía no existe en la base (FALTANTE)', 'danger')
                    return redirect(url_for('registrar_recepcion'))

                despacho_existente = conn.execute(text('SELECT * FROM despachos WHERE numero_guia = :n'), {'n': numero_guia}).first()
                if not despacho_existente:
                    flash('La guía no ha sido despachada aún', 'warning')
                    return redirect(url_for('registrar_recepcion'))

                recepcion_existente = conn.execute(text('SELECT * FROM recepciones WHERE numero_guia = :n'), {'n': numero_guia}).first()
                if recepcion_existente:
                    flash('La recepción para esta guía ya está registrada', 'warning')
                    return redirect(url_for('registrar_recepcion'))

                fecha = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                with engine.begin() as conn_write:
                    conn_write.execute(
                        text('INSERT INTO recepciones (numero_guia, tipo, motivo, fecha) VALUES (:n, :t, :m, :f)'),
                        {'n': numero_guia, 't': tipo, 'm': motivo if tipo == 'DEVUELTA' else '', 'f': fecha}
                    )
            flash(f'Recepción de guía {numero_guia} registrada como {tipo}', 'success')
            cargar_datos_desde_db()
            return redirect(url_for('registrar_recepcion'))
        except SQLAlchemyError as e:
            flash(f'Error en base de datos: {e}', 'danger')
    return render_template('registrar_recepcion.html')

@app.route('/registrar_recogida', methods=['GET', 'POST'])
def registrar_recogida():
    if request.method == 'POST':
        numero_guia = request.form.get('numero_guia')
        fecha = request.form.get('fecha')
        observaciones = request.form.get('observaciones')

        if not fecha:
            flash('La fecha es obligatoria', 'danger')
            return redirect(url_for('registrar_recogida'))

        # EN ESTA SECCIÓN NO VALIDAMOS QUE NUMERO DE GUIA EXISTA (como pediste)
        try:
            with engine.begin() as conn:
                conn.execute(
                    text('INSERT INTO recogidas (numero_guia, fecha, observaciones) VALUES (:n, :f, :o)'),
                    {'n': numero_guia, 'f': fecha, 'o': observaciones}
                )
            flash(f'Recogida registrada para guía {numero_guia}', 'success')
            cargar_datos_desde_db()
            return redirect(url_for('registrar_recogida'))
        except SQLAlchemyError as e:
            flash(f'Error en base de datos: {e}', 'danger')

    return render_template('registrar_recogida.html')

@app.route('/ver_recogidas')
def ver_recogidas():
    return render_template('ver_recogidas.html', recogidas=recogidas)

@app.route('/liquidacion', methods=['GET', 'POST'])
def liquidacion():
    if request.method == 'POST':
        fecha_inicio = request.form.get('fecha_inicio')
        fecha_fin = request.form.get('fecha_fin')

        try:
            with engine.connect() as conn:
                query = text('''
                    SELECT mensajero, COUNT(*) AS cantidad, SUM(z.tarifa) AS total
                    FROM despachos d
                    JOIN zonas z ON d.zona = z.nombre
                    WHERE fecha BETWEEN :f1 AND :f2
                    GROUP BY mensajero
                ''')
                result = conn.execute(query, {'f1': fecha_inicio, 'f2': fecha_fin})
                liquidaciones = [dict(row) for row in result]
            return render_template('liquidacion.html', liquidaciones=liquidaciones, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)
        except SQLAlchemyError as e:
            flash(f'Error en base de datos: {e}', 'danger')

    return render_template('liquidacion.html', liquidaciones=None)

if __name__ == '__main__':
    app.run(debug=True)
