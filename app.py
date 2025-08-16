import os
from flask import Flask, render_template, request, redirect, url_for, flash
import psycopg2
from urllib.parse import urlparse, parse_qsl
from datetime import datetime
import pandas as pd
import io

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "secreto")

# Config DB (Render: Settings > Environment)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_3owpfIUOAT0a@ep-soft-bush-acv2a8v4-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require"
)

def get_connection():
    """DSN para psycopg2 desde DATABASE_URL."""
    url = urlparse(DATABASE_URL)
    params = dict(parse_qsl(url.query))
    params.pop('channel_binding', None)

    dsn_parts = [
        f"dbname={url.path.lstrip('/')}",
        f"user={url.username}",
        f"password={url.password}",
        f"host={url.hostname}",
        f"port={url.port or 5432}",
    ]
    dsn_parts += [f"{k}={v}" for k, v in params.items() if v]
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

# Garantizar tablas
crear_tablas()

@app.route("/health")
def health():
    return "OK", 200

@app.route("/")
def index():
    return render_template("index.html")

# -----------------------
# REGISTRAR MENSAJERO
# -----------------------
@app.route('/registrar_mensajero', methods=['GET', 'POST'])
def registrar_mensajero():
    # Cargar zonas para el select
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT nombre FROM zonas ORDER BY nombre;")
        zonas = [z[0] for z in cur.fetchall()]
        cur.close()
        conn.close()
    except Exception as e:
        flash(f"Error cargando zonas: {e}", "error")
        zonas = []

    if request.method == 'POST':
        nombre = (request.form.get('nombre') or '').strip().lower()
        zona = (request.form.get('zona') or '').strip()

        if not nombre or not zona:
            flash("Debes ingresar nombre y zona", "error")
            return redirect(url_for('registrar_mensajero'))

        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT 1 FROM mensajeros WHERE LOWER(nombre) = %s", (nombre,))
            if cur.fetchone():
                flash('El mensajero ya existe', 'error')
            else:
                cur.execute("INSERT INTO mensajeros (nombre, zona) VALUES (%s, %s)", (nombre, zona))
                conn.commit()
                flash('Mensajero registrado exitosamente', 'success')
        except Exception as e:
            conn.rollback()
            flash(f"Error al registrar mensajero: {e}", "error")
        finally:
            cur.close()
            conn.close()

        return redirect(url_for('registrar_mensajero'))

    return render_template('registrar_mensajero.html', zonas=zonas)

# -----------------------
# DESPACHAR GUÍAS
# -----------------------
@app.route('/despachar_guias', methods=['GET', 'POST'])
def despachar_guias():
    if request.method == 'POST':
        numero_guia = (request.form.get('numero_guia') or '').strip()
        mensajero   = (request.form.get('mensajero') or '').strip()

        if not numero_guia or not mensajero:
            flash('Selecciona guía y mensajero', 'error')
            return redirect(url_for('despachar_guias'))

        conn = get_connection()
        cur = conn.cursor()
        try:
            # Validar guía pendiente
            cur.execute("SELECT estado FROM guias WHERE numero_guia = %s", (numero_guia,))
            row = cur.fetchone()
            if not row:
                flash('La guía no existe', 'error')
                return redirect(url_for('despachar_guias'))
            if row[0] != 'pendiente':
                flash('La guía no está en estado pendiente', 'error')
                return redirect(url_for('despachar_guias'))

            # Validar mensajero
            cur.execute("SELECT 1 FROM mensajeros WHERE nombre = %s", (mensajero,))
            if not cur.fetchone():
                flash('El mensajero seleccionado no existe', 'error')
                return redirect(url_for('despachar_guias'))

            # Insertar despacho y actualizar estado
            cur.execute(
                "INSERT INTO despachos (numero_guia, mensajero) VALUES (%s, %s)",
                (numero_guia, mensajero)
            )
            cur.execute(
                "UPDATE guias SET estado = 'despachado' WHERE numero_guia = %s",
                (numero_guia,)
            )
            conn.commit()
            flash(f'Guía {numero_guia} despachada correctamente', 'success')

        except Exception as e:
            conn.rollback()
            flash(f'Error al despachar guía: {e}', 'error')
        finally:
            cur.close()
            conn.close()

        return redirect(url_for('despachar_guias'))

    # GET: llenar selects
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT numero_guia FROM guias WHERE estado = 'pendiente' ORDER BY numero_guia;")
    guias = [g[0] for g in cur.fetchall()]

    cur.execute("SELECT nombre FROM mensajeros ORDER BY nombre;")
    mensajeros = [m[0] for m in cur.fetchall()]
    cur.close()
    conn.close()

    if not guias:
        flash('No hay guías pendientes para despachar.', 'info')
    if not mensajeros:
        flash('No hay mensajeros registrados. Registra uno primero.', 'info')

    return render_template('despachar_guias.html', guias=guias, mensajeros=mensajeros)

# -----------------------
# VER DESPACHOS
# -----------------------
@app.route('/ver_despachos', methods=['GET'])
def ver_despachos():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT d.numero_guia,
               d.mensajero,
               COALESCE(g.zona, '-') AS zona,
               d.fecha_despacho
        FROM despachos d
        JOIN guias g ON d.numero_guia = g.numero_guia
        ORDER BY d.fecha_despacho DESC;
    """)
    despachos = cur.fetchall()  # [(numero_guia, mensajero, zona, fecha_despacho), ...]
    cur.close()
    conn.close()
    return render_template('ver_despachos.html', despachos=despachos)

# -----------------------
# Resto de rutas (cargar_base, consultar_estado, recepcion, recogida, liquidacion)
# *Si las usas, mantenlas tal cual como ya las tienes.*
# -----------------------

if __name__ == '__main__':
    port = int(os.getenv("PORT", "10000"))
    app.run(host='0.0.0.0', port=port, debug=True)
