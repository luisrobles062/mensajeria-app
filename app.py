import os
from flask import Flask, render_template, request, redirect, url_for, flash
import psycopg2
from urllib.parse import urlparse, parse_qsl
from datetime import datetime
import pandas as pd
import io

app = Flask(__name__)
app.secret_key = 'secreto'

# Pon esta URL en un env en Render (Settings > Environment):
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_3owpfIUOAT0a@ep-soft-bush-acv2a8v4-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require"
)

def get_connection():
    """Construye un DSN válido para psycopg2 desde DATABASE_URL."""
    url = urlparse(DATABASE_URL)
    params = dict(parse_qsl(url.query))
    params.pop('channel_binding', None)  # psycopg2 no lo usa

    dsn_parts = [
        f"dbname={url.path.lstrip('/')}",
        f"user={url.username}",
        f"password={url.password}",
        f"host={url.hostname}",
        f"port={url.port or 5432}",
    ]
    dsn_parts += [f"{k}={v}" for k, v in params.items() if v]  # p. ej. sslmode=require
    dsn = ' '.join(dsn_parts)
    return psycopg2.connect(dsn)

def crear_tablas():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS zonas (
            nombre TEXT PRIMARY KEY,
            tarifa REAL NOT NULL
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mensajeros (
            nombre TEXT PRIMARY KEY,
            zona TEXT REFERENCES zonas(nombre)
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS guias (
            numero_guia TEXT PRIMARY KEY,
            remitente TEXT,
            destinatario TEXT,
            direccion TEXT,
            ciudad TEXT,
            zona TEXT DEFAULT NULL,
            estado TEXT DEFAULT 'pendiente'
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS despachos (
            id SERIAL PRIMARY KEY,
            numero_guia TEXT REFERENCES guias(numero_guia),
            mensajero TEXT REFERENCES mensajeros(nombre),
            fecha_despacho TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS recepciones (
            id SERIAL PRIMARY KEY,
            numero_guia TEXT REFERENCES guias(numero_guia),
            estado TEXT,
            causal TEXT,
            fecha_recepcion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS recogidas (
            id SERIAL PRIMARY KEY,
            numero_guia TEXT,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            observaciones TEXT
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

# Asegura tablas también con gunicorn
crear_tablas()

@app.route('/health')
def health():
    return "OK", 200

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
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO zonas (nombre, tarifa) VALUES (%s, %s)", (nombre, tarifa))
            conn.commit()
            flash('Zona registrada exitosamente', 'success')
        except psycopg2.IntegrityError:
            conn.rollback()
            flash('La zona ya existe', 'error')
        finally:
            cur.close()
            conn.close()
        return redirect(url_for('registrar_zona'))
    return render_template('registrar_zona.html')

@app.route('/registrar_mensajero', methods=['GET', 'POST'])
def registrar_mensajero():
    try:
        # Cargar las zonas para el formulario
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT nombre FROM zonas")
        zonas = [z[0] for z in cur.fetchall()]
        cur.close()
        conn.close()
    except Exception as e:
        flash(f"Error cargando zonas: {e}", "error")
        zonas = []

    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip().lower()
        zona = request.form.get('zona', '').strip()

        if not nombre or not zona:
            flash("Debes ingresar nombre y zona", "error")
            return redirect(url_for('registrar_mensajero'))

        conn = get_connection()
        cur = conn.cursor()

        try:
            # Verificar si ya existe el mensajero
            cur.execute("SELECT id FROM mensajeros WHERE LOWER(nombre) = %s", (nombre,))
            existe = cur.fetchone()

            if existe:
                flash('El mensajero ya existe', 'error')
            else:
                cur.execute(
                    "INSERT INTO mensajeros (nombre, zona) VALUES (%s, %s)",
                    (nombre, zona)
                )
                conn.commit()
                flash('Mensajero registrado exitosamente', 'success')

        except Exception as e:
            conn.rollback()
            flash(f"Error al registrar mensajero: {e}", "error")
            print(f"[ERROR registrar_mensajero] {e}")  # <-- Esto lo verás en logs

        finally:
            cur.close()
            conn.close()

        return redirect(url_for('registrar_mensajero'))

    return render_template('registrar_mensajero.html', zonas=zonas)

@app.route('/cargar_base', methods=['GET', 'POST'])
def cargar_base():
    if request.method == 'POST':
        if 'archivo' not in request.files or request.files['archivo'].filename == '':
            flash('No se seleccionó ningún archivo', 'error')
            return redirect(url_for('cargar_base'))
        file = request.files['archivo']
        try:
            data = file.read()
            df = pd.read_excel(io.BytesIO(data), engine='openpyxl')
        except Exception as e:
            flash(f'Error al leer el archivo Excel: {e}', 'error')
            return redirect(url_for('cargar_base'))

        columnas_esperadas = {'remitente', 'numero_guia', 'destinatario', 'direccion', 'ciudad'}
        cols_lower = set(df.columns.str.lower())
        if not columnas_esperadas.issubset(cols_lower):
            faltantes = columnas_esperadas - cols_lower
            flash(f'El archivo Excel debe contener las columnas: {", ".join(sorted(faltantes))}', 'error')
            return redirect(url_for('cargar_base'))

        df.columns = df.columns.str.lower()

        conn = get_connection()
        cur = conn.cursor()
        registros_insertados = 0
        try:
            for _, row in df.iterrows():
                cur.execute("""
                    INSERT INTO guias (numero_guia, remitente, destinatario, direccion, ciudad)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (numero_guia) DO UPDATE SET
                      remitente = EXCLUDED.remitente,
                      destinatario = EXCLUDED.destinatario,
                      direccion = EXCLUDED.direccion,
                      ciudad = EXCLUDED.ciudad
                """, (row['numero_guia'], row['remitente'], row['destinatario'], row['direccion'], row['ciudad']))
                registros_insertados += 1
            conn.commit()
            flash(f'{registros_insertados} guías insertadas/actualizadas correctamente', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'Error al guardar en DB: {e}', 'error')
        finally:
            cur.close()
            conn.close()
        return redirect(url_for('cargar_base'))

    return render_template('cargar_base.html')

@app.route('/consultar_estado', methods=['GET', 'POST'])
def consultar_estado():
    estado = None
    if request.method == 'POST':
        numero_guia = request.form['numero_guia']
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT estado FROM guias WHERE numero_guia = %s", (numero_guia,))
        row = cur.fetchone()
        if row:
            estado = row[0]
        else:
            flash('Guía no encontrada', 'error')
        cur.close()
        conn.close()
    return render_template('consultar_estado.html', estado=estado)

@app.route('/despachar_guias', methods=['GET', 'POST'])
def despachar_guias():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT numero_guia FROM guias WHERE estado='pendiente'")
    guias = cur.fetchall()
    cur.execute("SELECT nombre FROM mensajeros")
    mensajeros = cur.fetchall()
    cur.close()
    conn.close()

    if request.method == 'POST':
        numero_guia = request.form['numero_guia']
        mensajero = request.form['mensajero']
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO despachos (numero_guia, mensajero) VALUES (%s, %s)", (numero_guia, mensajero))
            cur.execute("UPDATE guias SET estado='despachado' WHERE numero_guia=%s", (numero_guia,))
            conn.commit()
            flash('Guía despachada correctamente', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'Error al despachar guía: {e}', 'error')
        finally:
            cur.close()
            conn.close()
        return redirect(url_for('despachar_guias'))

    return render_template('despachar_guias.html', guias=guias, mensajeros=mensajeros)

# ====== Aliases para plantillas antiguas ======
# /guias -> endpoint 'ver_guias'
app.add_url_rule('/guias', endpoint='ver_guias', view_func=despachar_guias, methods=['GET', 'POST'])
# /despachos -> endpoint 'ver_despacho'
app.add_url_rule('/despachos', endpoint='ver_despacho', view_func=despachar_guias, methods=['GET', 'POST'])
# ==============================================

@app.route('/registrar_recepcion', methods=['GET', 'POST'])
def registrar_recepcion():
    if request.method == 'POST':
        numero_guia = request.form['numero_guia']
        estado = request.form['estado']
        causal = request.form['causal']
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO recepciones (numero_guia, estado, causal) VALUES (%s, %s, %s)", (numero_guia, estado, causal))
            cur.execute("UPDATE guias SET estado=%s WHERE numero_guia=%s", (estado, numero_guia))
            conn.commit()
            flash('Recepción registrada', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'Error al registrar recepción: {e}', 'error')
        finally:
            cur.close()
            conn.close()
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
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO recogidas (numero_guia, fecha, observaciones) VALUES (%s, %s, %s)",
                (numero_guia, fecha_dt, observaciones)
            )
            conn.commit()
            flash('Recogida registrada', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'Error al registrar recogida: {e}', 'error')
        finally:
            cur.close()
            conn.close()
        return redirect(url_for('registrar_recogida'))
    return render_template('registrar_recogida.html')

@app.route('/liquidacion')
def liquidacion():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT d.mensajero,
               COUNT(*) AS total_guias,
               COALESCE(SUM(z.tarifa), 0) AS total_pago
        FROM despachos d
        JOIN guias g ON d.numero_guia = g.numero_guia
        JOIN zonas z ON g.zona = z.nombre
        GROUP BY d.mensajero
        ORDER BY d.mensajero
    """)
    resultados = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('liquidacion.html', resultados=resultados)

if __name__ == '__main__':
    port = int(os.getenv("PORT", "10000"))
    app.run(host='0.0.0.0', port=port, debug=True)


