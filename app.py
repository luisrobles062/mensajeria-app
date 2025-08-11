# app.py  (COMPLETO)
import os
import io
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_sqlalchemy import SQLAlchemy
import pandas as pd
import matplotlib.pyplot as plt

# ----------------- CONFIG -----------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cambia_esto_en_produccion")

# DATABASE: prefer env var DATABASE_URL, sino fallback a SQLite local (data/app.db)
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    # Si la URL viene con channel_binding (Neon) y da problemas, quítalo en la variable de entorno.
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
else:
    os.makedirs("data", exist_ok=True)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///data/app.db"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# ----------------- MODELS -----------------
class Zona(db.Model):
    __tablename__ = "zonas"
    nombre = db.Column(db.String(100), primary_key=True)
    tarifa = db.Column(db.Float, nullable=False)

class Mensajero(db.Model):
    __tablename__ = "mensajeros"
    nombre = db.Column(db.String(100), primary_key=True)
    zona = db.Column(db.String(100), db.ForeignKey("zonas.nombre"), nullable=False)
    zona_rel = db.relationship("Zona", backref="mensajeros")

class Guia(db.Model):
    __tablename__ = "guias"
    id = db.Column(db.Integer, primary_key=True)
    remitente = db.Column(db.String(255), nullable=False)
    numero_guia = db.Column(db.String(255), nullable=False, unique=True)
    destinatario = db.Column(db.String(255), nullable=False)
    direccion = db.Column(db.String(255), nullable=False)
    ciudad = db.Column(db.String(255), nullable=False)

class Despacho(db.Model):
    __tablename__ = "despachos"
    id = db.Column(db.Integer, primary_key=True)
    numero_guia = db.Column(db.String(255), db.ForeignKey("guias.numero_guia"), nullable=False)
    mensajero = db.Column(db.String(100), db.ForeignKey("mensajeros.nombre"), nullable=False)
    zona = db.Column(db.String(100), db.ForeignKey("zonas.nombre"), nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

class Recepcion(db.Model):
    __tablename__ = "recepciones"
    id = db.Column(db.Integer, primary_key=True)
    numero_guia = db.Column(db.String(255), db.ForeignKey("guias.numero_guia"), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # ENTREGA / DEVUELTA
    motivo = db.Column(db.String(255))
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

class Recogida(db.Model):
    __tablename__ = "recogidas"
    id = db.Column(db.Integer, primary_key=True)
    numero_interno = db.Column(db.String(100))
    fecha = db.Column(db.Date)
    observaciones = db.Column(db.String(500))


# ----------------- UTIL -----------------
def safe_commit():
    try:
        db.session.commit()
        return None
    except Exception as e:
        db.session.rollback()
        return str(e)

def lista_guias_str_to_list(texto):
    """Convierte entrada multi-línea (scanner) en lista limpia."""
    if not texto:
        return []
    return [line.strip() for line in texto.splitlines() if line.strip()]

# ----------------- ROUTES -----------------
@app.route("/")
def index():
    return render_template("index.html")

# -------- CARGAR BASE DE GUIAS (Excel) --------
@app.route("/cargar_base", methods=["GET", "POST"])
def cargar_base():
    if request.method == "POST":
        archivo = request.files.get("archivo_excel")
        if not archivo:
            flash("Selecciona un archivo Excel (.xlsx).", "danger")
            return redirect(url_for("cargar_base"))
        try:
            df = pd.read_excel(archivo)
            required = {"remitente", "numero_guia", "destinatario", "direccion", "ciudad"}
            if not required.issubset(set(df.columns)):
                flash(f"El archivo debe contener columnas: {', '.join(required)}", "danger")
                return redirect(url_for("cargar_base"))

            added = 0
            for _, row in df.iterrows():
                num = str(row["numero_guia"]).strip()
                if not Guia.query.filter_by(numero_guia=num).first():
                    guia = Guia(
                        remitente=str(row["remitente"]),
                        numero_guia=num,
                        destinatario=str(row["destinatario"]),
                        direccion=str(row["direccion"]),
                        ciudad=str(row["ciudad"])
                    )
                    db.session.add(guia)
                    added += 1
            err = safe_commit()
            if err:
                flash(f"Error al guardar guías: {err}", "danger")
            else:
                flash(f"{added} guías añadidas correctamente.", "success")
        except Exception as e:
            flash(f"Error procesando archivo: {e}", "danger")
        return redirect(url_for("cargar_base"))
    return render_template("cargar_base.html")

# -------- REGISTRAR ZONA --------
@app.route("/registrar_zona", methods=["GET", "POST"])
def registrar_zona():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        tarifa = request.form.get("tarifa", "").strip()
        if not nombre or not tarifa:
            flash("Completa todos los campos.", "danger")
            return redirect(url_for("registrar_zona"))
        try:
            tarifa_f = float(tarifa)
        except ValueError:
            flash("Tarifa inválida.", "danger")
            return redirect(url_for("registrar_zona"))

        if Zona.query.get(nombre):
            flash("La zona ya existe.", "warning")
        else:
            db.session.add(Zona(nombre=nombre, tarifa=tarifa_f))
            err = safe_commit()
            if err:
                flash(f"Error guardando zona: {err}", "danger")
            else:
                flash("Zona registrada.", "success")
        return redirect(url_for("registrar_zona"))

    zonas = Zona.query.order_by(Zona.nombre).all()
    return render_template("registrar_zona.html", zonas=zonas)

# -------- REGISTRAR MENSAJERO --------
@app.route("/registrar_mensajero", methods=["GET", "POST"])
def registrar_mensajero():
    zonas = Zona.query.order_by(Zona.nombre).all()
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        zona_nombre = request.form.get("zona", "").strip()
        if not nombre or not zona_nombre:
            flash("Completa todos los campos.", "danger")
            return redirect(url_for("registrar_mensajero"))

        if not Zona.query.get(zona_nombre):
            flash("Zona no encontrada.", "danger")
            return redirect(url_for("registrar_mensajero"))

        if Mensajero.query.get(nombre):
            flash("El mensajero ya existe.", "warning")
        else:
            db.session.add(Mensajero(nombre=nombre, zona=zona_nombre))
            err = safe_commit()
            if err:
                flash(f"Error guardando mensajero: {err}", "danger")
            else:
                flash("Mensajero registrado.", "success")
        return redirect(url_for("registrar_mensajero"))
    mensajeros = Mensajero.query.order_by(Mensajero.nombre).all()
    return render_template("registrar_mensajero.html", zonas=zonas, mensajeros=mensajeros)

# -------- DESPACHO MASIVO (scanner lines) --------
@app.route("/despachar_guias", methods=["GET", "POST"])
def despachar_guias():
    mensajeros = Mensajero.query.order_by(Mensajero.nombre).all()
    if request.method == "POST":
        mensajero_nombre = request.form.get("mensajero")
        guias_texto = request.form.get("guias", "")
        guias_list = lista_guias_str_to_list(guias_texto)
        mensajero = Mensajero.query.get(mensajero_nombre)
        if not mensajero:
            flash("Mensajero no encontrado.", "danger")
            return redirect(url_for("despachar_guias"))
        errores = []
        exito = []
        for numero in guias_list:
            numero = str(numero).strip()
            guia = Guia.query.filter_by(numero_guia=numero).first()
            if not guia:
                errores.append(f"Guía {numero} no existe (FALTANTE)")
                continue
            despacho_existente = Despacho.query.filter_by(numero_guia=numero).first()
            recepcion_existente = Recepcion.query.filter_by(numero_guia=numero).first()
            if recepcion_existente:
                errores.append(f"Guía {numero} ya fue {recepcion_existente.tipo}")
                continue
            if despacho_existente:
                errores.append(f"Guía {numero} ya fue despachada a {despacho_existente.mensajero}")
                continue
            nuevo = Despacho(numero_guia=numero, mensajero=mensajero_nombre, zona=mensajero.zona, fecha=datetime.utcnow())
            db.session.add(nuevo)
            exito.append(f"Guía {numero} despachada a {mensajero_nombre}")
        err = safe_commit()
        if err:
            flash(f"Error en base de datos: {err}", "danger")
        if errores:
            flash("Errores:<br>" + "<br>".join(errores), "danger")
        if exito:
            flash("Despachos exitosos:<br>" + "<br>".join(exito), "success")
        return redirect(url_for("ver_despacho"))
    return render_template("despachar_guias.html", mensajeros=mensajeros)

# -------- VER DESPACHO --------
@app.route("/ver_despacho")
def ver_despacho():
    despachos = Despacho.query.order_by(Despacho.fecha.desc()).all()
    return render_template("ver_despacho.html", despachos=despachos)

# -------- REGISTRAR RECEPCION --------
@app.route("/registrar_recepcion", methods=["GET", "POST"])
def registrar_recepcion():
    if request.method == "POST":
        numero = request.form.get("numero_guia", "").strip()
        tipo = request.form.get("estado")
        motivo = request.form.get("motivo", "").strip()
        if not numero:
            flash("Ingrese número de guía.", "danger")
            return redirect(url_for("registrar_recepcion"))
        guia = Guia.query.filter_by(numero_guia=numero).first()
        if not guia:
            flash("Número de guía no existe en la base (FALTANTE).", "danger")
            return redirect(url_for("registrar_recepcion"))
        despacho = Despacho.query.filter_by(numero_guia=numero).first()
        if not despacho:
            flash("La guía no ha sido despachada aún.", "warning")
            return redirect(url_for("registrar_recepcion"))
        if Recepcion.query.filter_by(numero_guia=numero).first():
            flash("La recepción para esta guía ya está registrada.", "warning")
            return redirect(url_for("registrar_recepcion"))
        recep = Recepcion(numero_guia=numero, tipo=tipo, motivo=(motivo if tipo == "DEVUELTA" else ""), fecha=datetime.utcnow())
        db.session.add(recep)
        err = safe_commit()
        if err:
            flash(f"Error guardando recepción: {err}", "danger")
        else:
            flash(f"Recepción de guía {numero} registrada como {tipo}.", "success")
        return redirect(url_for("registrar_recepcion"))
    return render_template("registrar_recepcion.html")

# -------- CONSULTAR ESTADO (multi) + EXPORT to EXCEL --------
@app.route("/consultar_estado", methods=["GET", "POST"])
def consultar_estado():
    resultados = []
    if request.method == "POST":
        guias_texto = request.form.get("guias", "")
        guias_list = lista_guias_str_to_list(guias_texto)
        for numero in guias_list:
            numero = str(numero).strip()
            estado = "EN VERIFICACIÓN"
            motivo = ""
            mensajero = ""
            zona = ""
            fecha_despacho = ""
            gestion = ""
            guia = Guia.query.filter_by(numero_guia=numero).first()
            recepcion = Recepcion.query.filter_by(numero_guia=numero).first()
            despacho = Despacho.query.filter_by(numero_guia=numero).first()
            if not guia:
                estado = "FALTANTE"
            elif recepcion:
                estado = recepcion.tipo
                motivo = recepcion.motivo or ""
                gestion = f"{recepcion.tipo}" + (f" - {motivo}" if motivo else "")
                despacho_ref = Despacho.query.filter_by(numero_guia=numero).first()
                if despacho_ref:
                    mensajero = despacho_ref.mensajero
                    zona = despacho_ref.zona
                    fecha_despacho = despacho_ref.fecha
            elif despacho:
                estado = "DESPACHADA"
                mensajero = despacho.mensajero
                zona = despacho.zona
                fecha_despacho = despacho.fecha
            resultados.append({
                "numero_guia": numero,
                "estado": estado,
                "motivo": motivo,
                "mensajero": mensajero,
                "zona": zona,
                "fecha_despacho": fecha_despacho,
                "gestion": gestion
            })
        # Si el usuario pidió exportar:
        if request.form.get("exportar") == "1":
            df = pd.DataFrame(resultados)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="estado")
            output.seek(0)
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            return send_file(output, download_name=f"consulta_estado_{ts}.xlsx", as_attachment=True, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        return render_template("consultar_estado.html", resultados=resultados)
    return render_template("consultar_estado.html", resultados=None)

# -------- VERIFICACION DE CORREO ENTRANTE (scan uno por uno) --------
@app.route("/verificacion_entrada", methods=["GET", "POST"])
def verificacion_entrada():
    if request.method == "POST":
        numero = request.form.get("numero_guia", "").strip()
        if not numero:
            flash("Ingrese número de guía.", "danger")
            return redirect(url_for("verificacion_entrada"))
        guia = Guia.query.filter_by(numero_guia=numero).first()
        if not guia:
            flash("FALTANTE: la guía no existe en la base.", "danger")
            return redirect(url_for("verificacion_entrada"))
        flash(f"Guía {numero} validada correctamente.", "success")
        return redirect(url_for("verificacion_entrada"))
    return render_template("verificacion_entrada.html")

# -------- LIQUIDACION (por rango) + EXPORT + GRAFICO --------
@app.route("/liquidacion", methods=["GET", "POST"])
def liquidacion():
    liquidaciones = None
    fecha_inicio = fecha_fin = None
    chart_png = None
    if request.method == "POST":
        fecha_inicio = request.form.get("fecha_inicio")
        fecha_fin = request.form.get("fecha_fin")
        try:
            fi = datetime.strptime(fecha_inicio, "%Y-%m-%d")
            ff = datetime.strptime(fecha_fin, "%Y-%m-%d")
            # Query: contar despachos por mensajero y sumar tarifa de la zona
            from sqlalchemy import func
            q = db.session.query(
                Despacho.mensajero,
                func.count(Despacho.id).label("cantidad"),
                func.sum(Zona.tarifa).label("total")
            ).join(Zona, Despacho.zona == Zona.nombre).filter(
                Despacho.fecha.between(fi, ff)
            ).group_by(Despacho.mensajero).all()
            liquidaciones = [{"mensajero": r.mensajero, "cantidad": r.cantidad, "total": float(r.total or 0)} for r in q]

            # Generar gráfico de barras
            if liquidaciones:
                names = [l["mensajero"] for l in liquidaciones]
                totals = [l["total"] for l in liquidaciones]
                plt.figure(figsize=(8,4))
                plt.bar(names, totals)
                plt.title("Liquidación por mensajero")
                plt.ylabel("Total")
                plt.tight_layout()
                buf = io.BytesIO()
                plt.savefig(buf, format="png")
                plt.close()
                buf.seek(0)
                chart_png = base64.b64encode(buf.read()).decode("ascii")
        except Exception as e:
            flash(f"Error al calcular liquidación: {e}", "danger")

        # Exportar si pidió
        if request.form.get("exportar") == "1" and liquidaciones:
            df = pd.DataFrame(liquidaciones)
            out = io.BytesIO()
            with pd.ExcelWriter(out, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="liquidacion")
            out.seek(0)
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            return send_file(out, download_name=f"liquidacion_{ts}.xlsx", as_attachment=True, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    return render_template("liquidacion.html", liquidaciones=liquidaciones, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin, chart_png=chart_png)

# -------- RECOGIDAS: registrar, listar, editar --------
@app.route("/registrar_recogida", methods=["GET", "POST"])
def registrar_recogida():
    if request.method == "POST":
        numero_interno = request.form.get("numero_interno", "").strip()
        fecha_str = request.form.get("fecha", "").strip()
        observaciones = request.form.get("observaciones", "").strip()
        if not fecha_str:
            flash("Fecha obligatoria.", "danger")
            return redirect(url_for("registrar_recogida"))
        try:
            f = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Formato de fecha inválido. Use YYYY-MM-DD.", "danger")
            return redirect(url_for("registrar_recogida"))
        rec = Recogida(numero_interno=numero_interno, fecha=f, observaciones=observaciones)
        db.session.add(rec)
        err = safe_commit()
        if err:
            flash(f"Error guardando recogida: {err}", "danger")
        else:
            flash("Recogida registrada.", "success")
        return redirect(url_for("ver_recogidas"))
    return render_template("registrar_recogida.html")

@app.route("/ver_recogidas")
def ver_recogidas():
    lista = Recogida.query.order_by(Recogida.fecha.desc()).all()
    return render_template("ver_recogidas.html", recogidas=lista)

@app.route("/editar_recogida/<int:id>", methods=["GET", "POST"])
def editar_recogida(id):
    rec = Recogida.query.get_or_404(id)
    if request.method == "POST":
        rec.numero_interno = request.form.get("numero_interno", rec.numero_interno)
        fecha_str = request.form.get("fecha", rec.fecha.strftime("%Y-%m-%d"))
        try:
            rec.fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Fecha inválida.", "danger")
            return redirect(url_for("editar_recogida", id=id))
        rec.observaciones = request.form.get("observaciones", rec.observaciones)
        err = safe_commit()
        if err:
            flash(f"Error actualizando: {err}", "danger")
        else:
            flash("Recogida actualizada.", "success")
        return redirect(url_for("ver_recogidas"))
    return render_template("editar_recogida.html", recogida=rec)

# -------- API auxiliar para comprobar si número existe (útil en JS) --------
@app.route("/api/existe_guia/<numero>")
def api_existe_guia(numero):
    existe = Guia.query.filter_by(numero_guia=numero).first() is not None
    return jsonify({"existe": existe})

# ----------------- START -----------------
if __name__ == "__main__":
    # Crear tablas si no existen (protegido)
    with app.app_context():
        try:
            db.create_all()
            print("Tablas creadas/verificadas.")
        except Exception as e:
            print("No se pudieron crear todas las tablas automáticamente:", e)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
