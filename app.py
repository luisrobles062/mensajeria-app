from flask import Flask, render_template, request, redirect, url_for, flash
import psycopg2
from urllib.parse import urlparse, parse_qsl
from datetime import datetime
import pandas as pd
import io
import os

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "secreto")

# Usa la variable de entorno DATABASE_URL en Render, si no está usa la que nos diste (pero recomiendo usar env var)
DATABASE_URL = os.getenv("DATABASE_URL",
    "postgresql://neondb_owner:npg_3owpfIUOAT0a@ep-soft-bush-acv2a8v4-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
)

def build_clean_dsn(database_url: str):
    """Parsea DATABASE_URL y devuelve un DSN seguro para psycopg2 (sin channel_binding ni & sobrantes)."""
    parsed = urlparse(database_url)
    params = dict(parse_qsl(parsed.query))
    # eliminar parámetros problemáticos
    params.pop("channel_binding", None)
    # si sslmode == 'require', cambiar a 'verify-full' para mayor compatibilidad (opcional)
    if params.get("sslmode") == "require":
        params["sslmode"] = "verify-full"
    # reconstrucir query string limpia
    query_string = "&".join(f"{k}={v}" for k, v in params.items() if v)
    dsn = (
        f"dbname={parsed.path.lstrip('/')} "
        f"user={parsed.username} "
        f"password={parsed.password} "
        f"host={parsed.hostname} "
        f"port={parsed.port or 5432}"
    )
    if query_string:
        dsn += " " + query_string
    return dsn

def get_connection():
    dsn = build_clean_dsn(DATABASE_URL)
    return psycopg2.connect(dsn)

def crear_tablas():
    conn = get_connection()
    cur = conn.cursor()
    # tablas básicas necesarias
    cur.execute("""
    CREATE TABLE IF NOT EXISTS zonas (
        nombre TEXT PRIMARY KEY,
        tarifa NUMERIC DEFAULT 0
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
        zona TEXT REFERENCES zonas(nombre),
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

# Crear tablas al iniciar (safe)
try:
    crear_tablas()
except Exception as e:
    # Mensaje en logs pero la app sigue (Render mostrará error si la DB está inaccesible)
    print("Advertencia: crear_tablas falló:", e)

# -------------------- RUTAS --------------------

@app.route('/')
def index():
    return render_template('index.html')

# ---------- Zonas ----------
@app.route('/registrar_zona', methods=['GET', 'POST'])
def registrar_zona():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        tarifa = request.form.get('tarifa', '').strip()
        if not nombre or tarifa == '':
            flash('Debe completar nombre y tarifa', 'error')
            return redirect(url_for('registrar_zona'))
        try:
            tarifa_val = float(tarifa)
        except ValueError:
            flash('Tarifa inválida', 'error')
            return redirect(url_for('registrar_zona'))
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO zonas (nombre, tarifa) VALUES (%s, %s) ON CONFLICT (nombre) DO UPDATE SET tarifa = EXCLUDED.tarifa",
                        (nombre, tarifa_val))
            conn.commit()
            cur.close()
            conn.close()
            flash('Zona registrada/actualizada correctamente', 'success')
            return redirect(url_for('registrar_zona'))
        except Exception as e:
            flash(f'Error al registrar zona: {e}', 'error')
            return redirect(url_for('registrar_zona'))
    # GET: listar zonas para mostrar
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT nombre, tarifa FROM zonas ORDER BY nombre")
        zonas = cur.fetchall()
        cur.close()
        conn.close()
    except Exception:
        zonas = []
    return render_template('registrar_zona.html', zonas=zonas)

# ---------- Mensajeros ----------
@app.route('/registrar_mensajero', methods=['GET', 'POST'])
def registrar_mensajero():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        zona = request.form.get('zona', '').strip()
        if not nombre or not zona:
            flash('Debe completar nombre y zona', 'error')
            return redirect(url_for('registrar_mensajero'))
        try:
            conn = get_connection()
            cur = conn.cursor()
            # validar zona existente
            cur.execute("SELECT 1 FROM zonas WHERE nombre = %s", (zona,))
            if cur.fetchone() is None:
                cur.close()
                conn.close()
                flash('Zona no registrada', 'error')
                return redirect(url_for('registrar_mensajero'))
            cur.execute("INSERT INTO mensajeros (nombre, zona) VALUES (%s, %s) ON CONFLICT (nombre) DO UPDATE SET zona = EXCLUDED.zona",
                        (nombre, zona))
            conn.commit()
            cur.close()
            conn.close()
            flash('Mensajero registrado/actualizado', 'success')
            return redirect(url_for('registrar_mensajero'))
        except Exception as e:
            flash(f'Error al registrar mensajero: {e}', 'error')
            return redirect(url_for('registrar_mensajero'))
    # GET
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT nombre FROM zonas ORDER BY nombre")
        zonas = [r[0] for r in cur.fetchall()]
        cur.close()
        conn.close()
    except Exception:
        zonas = []
    return render_template('registrar_mensajero.html', zonas=zonas)

# ---------- Cargar base (Excel) ----------
@app.route('/cargar_base', methods=['GET', 'POST'])
def cargar_base():
    if request.method == 'POST':
        if 'archivo' not in request.files:
            flash('No se subió ningún archivo', 'error')
            return redirect(url_for('cargar_base'))
        file = request.files['archivo']
        if file.filename == '':
            flash('File sin nombre', 'error')
            return redirect(url_for('cargar_base'))
        # leer excel con pandas (en memoria)
        try:
            content = file.read()
            df = pd.read_excel(io.BytesIO(content))
        except Exception as e:
            flash(f'Error leyendo el archivo Excel: {e}', 'error')
            return redirect(url_for('cargar_base'))

        # normalizar nombres de columnas a minúsculas y sin espacios
        df.columns = [str(c).strip().lower() for c in df.columns]

        required = {"numero_guia", "remitente", "destinatario", "direccion", "ciudad"}
        if not required.issubset(set(df.columns)):
            flash(f'Columnas detectadas: {", ".join(df.columns)}', 'error')
            flash(f'El archivo debe contener: {", ".join(sorted(required))}', 'error')
            return redirect(url_for('cargar_base'))

        # si no hay zona, la dejamos vacía
        if 'zona' not in df.columns:
            df['zona'] = None

        # Insertar/actualizar guías
        try:
            conn = get_connection()
            cur = conn.cursor()
            inserted = 0
            updated = 0
            for _, row in df.iterrows():
                numero = str(row.get('numero_guia')).strip()
                remitente = str(row.get('remitente') or '').strip()
                destinatario = str(row.get('destinatario') or '').strip()
                direccion = str(row.get('direccion') or '').strip()
                ciudad = str(row.get('ciudad') or '').strip()
                zona = str(row.get('zona')) if row.get('zona') is not None else None
                # UPSERT: si existe actualizamos, si no insertamos
                cur.execute("""
                    INSERT INTO guias (numero_guia, remitente, destinatario, direccion, ciudad, zona)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (numero_guia) DO UPDATE SET
                        remitente = EXCLUDED.remitente,
                        destinatario = EXCLUDED.destinatario,
                        direccion = EXCLUDED.direccion,
                        ciudad = EXCLUDED.ciudad,
                        zona = EXCLUDED.zona
                """, (numero, remitente, destinatario, direccion, ciudad, zona))
                # psycopg2 .rowcount after insert... uses 1 for insert or 0 for do nothing; we won't rely on it exactly
            conn.commit()
            cur.close()
            conn.close()
            flash('Archivo procesado correctamente', 'success')
        except Exception as e:
            flash(f'Error al guardar en DB: {e}', 'error')
            return redirect(url_for('cargar_base'))

        return redirect(url_for('cargar_base'))

    return render_template('cargar_base.html')

# ---------- Consultar estado ----------
@app.route('/consultar_estado', methods=['GET', 'POST'])
def consultar_estado():
    resultado = None
    if request.method == 'POST':
        numero = request.form.get('numero_guia', '').strip()
        if not numero:
            flash('Ingrese número de guía', 'error')
            return redirect(url_for('consultar_estado'))
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT numero_guia, estado FROM guias WHERE numero_guia = %s", (numero,))
            row = cur.fetchone()
            cur.close()
            conn.close()
            if row:
                resultado = {'numero_guia': row[0], 'estado': row[1]}
            else:
                resultado = {'numero_guia': numero, 'estado': 'FALTANTE'}
        except Exception as e:
            flash(f'Error consultando DB: {e}', 'error')
            return redirect(url_for('consultar_estado'))
    return render_template('consultar_estado.html', resultado=resultado)

# ---------- Despachar guías ----------
@app.route('/despachar_guias', methods=['GET', 'POST'])
def despachar_guias():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT numero_guia FROM guias WHERE estado = 'pendiente' ORDER BY numero_guia")
        guias = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT nombre FROM mensajeros ORDER BY nombre")
        mensajeros = [r[0] for r in cur.fetchall()]
        cur.close()
        conn.close()
    except Exception as e:
        flash(f'Error obteniendo datos: {e}', 'error')
        guias = []
        mensajeros = []

    if request.method == 'POST':
        numero = request.form.get('numero_guia')
        mensajero = request.form.get('mensajero')
        if not numero or not mensajero:
            flash('Seleccione guía y mensajero', 'error')
            return redirect(url_for('despachar_guias'))
        try:
            conn = get_connection()
            cur = conn.cursor()
            # Validaciones
            cur.execute("SELECT estado, zona FROM guias WHERE numero_guia = %s", (numero,))
            info = cur.fetchone()
            if not info:
                flash('Guía no encontrada', 'error')
                cur.close()
                conn.close()
                return redirect(url_for('despachar_guias'))
            estado_actual, zona_guia = info
            if estado_actual != 'pendiente':
                flash('La guía no está en estado pendiente', 'error')
                cur.close()
                conn.close()
                return redirect(url_for('despachar_guias'))
            cur.execute("SELECT zona FROM mensajeros WHERE nombre = %s", (mensajero,))
            mz = cur.fetchone()
            if not mz:
                flash('Mensajero no existe', 'error')
                cur.close()
                conn.close()
                return redirect(url_for('despachar_guias'))
            zona_mensajero = mz[0]
            # opcional: exigir coincidencia de zona (si guia.zona está vacío, permitir)
            if zona_guia and zona_mensajero != zona_guia:
                flash(f'El mensajero no pertenece a la zona de la guía ({zona_guia})', 'error')
                cur.close()
                conn.close()
                return redirect(url_for('despachar_guias'))
            cur.execute("INSERT INTO despachos (numero_guia, mensajero) VALUES (%s, %s)", (numero, mensajero))
            cur.execute("UPDATE guias SET estado = 'despachado' WHERE numero_guia = %s", (numero,))
            conn.commit()
            cur.close()
            conn.close()
            flash('Guía despachada', 'success')
            return redirect(url_for('despachar_guias'))
        except Exception as e:
            flash(f'Error al despachar: {e}', 'error')
            return redirect(url_for('despachar_guias'))

    return render_template('despachar_guias.html', guias=guias, mensajeros=mensajeros)

# ---------- Recepciones ----------
@app.route('/registrar_recepcion', methods=['GET', 'POST'])
def registrar_recepcion():
    if request.method == 'POST':
        numero = request.form.get('numero_guia', '').strip()
        estado = request.form.get('estado', '').strip()
        causal = request.form.get('causal', '').strip()
        if not numero or not estado:
            flash('Número de guía y estado son obligatorios', 'error')
            return redirect(url_for('registrar_recepcion'))
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO recepciones (numero_guia, estado, causal) VALUES (%s, %s, %s)", (numero, estado, causal))
            cur.execute("UPDATE guias SET estado = %s WHERE numero_guia = %s", (estado, numero))
            conn.commit()
            cur.close()
            conn.close()
            flash('Recepción registrada', 'success')
            return redirect(url_for('registrar_recepcion'))
        except Exception as e:
            flash(f'Error al registrar recepción: {e}', 'error')
            return redirect(url_for('registrar_recepcion'))
    return render_template('registrar_recepcion.html')

# ---------- Recogidas ----------
@app.route('/registrar_recogida', methods=['GET', 'POST'])
def registrar_recogida():
    if request.method == 'POST':
        numero = request.form.get('numero_guia', '').strip()
        fecha = request.form.get('fecha', '').strip()
        observ = request.form.get('observaciones', '').strip()
        if not numero or not fecha:
            flash('Número de guía y fecha obligatorios', 'error')
            return redirect(url_for('registrar_recogida'))
        try:
            fecha_dt = datetime.strptime(fecha, "%Y-%m-%d")
        except ValueError:
            flash('Formato de fecha inválido', 'error')
            return redirect(url_for('registrar_recogida'))
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO recogidas (numero_guia, fecha, observaciones) VALUES (%s, %s, %s)",
                        (numero, fecha_dt, observ))
            conn.commit()
            cur.close()
            conn.close()
            flash('Recogida registrada', 'success')
            return redirect(url_for('registrar_recogida'))
        except Exception as e:
            flash(f'Error al registrar recogida: {e}', 'error')
            return redirect(url_for('registrar_recogida'))
    return render_template('registrar_recogida.html')

# ---------- Ver listados ----------
@app.route('/ver_guias')
def ver_guias():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT numero_guia, remitente, destinatario, direccion, ciudad, zona, estado FROM guias ORDER BY numero_guia")
        guias = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        flash(f'Error al obtener guías: {e}', 'error')
        guias = []
    return render_template('ver_guias.html', guias=guias)

@app.route('/ver_despacho')
def ver_despacho():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT d.id, d.numero_guia, d.mensajero, d.fecha_despacho, g.estado
            FROM despachos d LEFT JOIN guias g ON d.numero_guia = g.numero_guia
            ORDER BY d.fecha_despacho DESC
        """)
        despachos = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        flash(f'Error al obtener despachos: {e}', 'error')
        despachos = []
    return render_template('ver_despacho.html', despachos=despachos)

@app.route('/ver_recogidas')
def ver_recogidas():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, numero_guia, fecha, observaciones FROM recogidas ORDER BY fecha DESC")
        recogidas = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        flash(f'Error al obtener recogidas: {e}', 'error')
        recogidas = []
    return render_template('ver_recogidas.html', recogidas=recogidas)

# ---------- Liquidación ----------
@app.route('/liquidacion')
def liquidacion():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT d.mensajero, COUNT(*) AS total_guias, COALESCE(SUM(z.tarifa),0) AS total_pago
            FROM despachos d
            JOIN guias g ON d.numero_guia = g.numero_guia
            LEFT JOIN zonas z ON g.zona = z.nombre
            GROUP BY d.mensajero
        """)
        resultados = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        flash(f'Error calculando liquidación: {e}', 'error')
        resultados = []
    return render_template('liquidacion.html', resultados=resultados)

# ---------- Verificación entrada ----------
@app.route('/verificacion_entrada', methods=['GET', 'POST'])
def verificacion_entrada():
    mensaje = None
    if request.method == 'POST':
        numero = request.form.get('numero_guia', '').strip()
        if not numero:
            flash('Ingrese número de guía', 'error')
            return redirect(url_for('verificacion_entrada'))
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT numero_guia, estado FROM guias WHERE numero_guia = %s", (numero,))
            row = cur.fetchone()
            cur.close()
            conn.close()
            if row:
                mensaje = f'Guía {row[0]}: estado {row[1]}'
            else:
                mensaje = f'Guía {numero} no encontrada'
        except Exception as e:
            flash(f'Error en verificación: {e}', 'error')
            return redirect(url_for('verificacion_entrada'))
    return render_template('verificacion_entrada.html', mensaje=mensaje)

# ------------------------------------------------
if __name__ == '__main__':
    # crear_tablas() ya fue llamado arriba, pero llamamos de nuevo por seguridad
    try:
        crear_tablas()
    except Exception as e:
        print("crear_tablas error al ejecutar __main__:", e)
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 10000)), debug=True)
