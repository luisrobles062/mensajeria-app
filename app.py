from flask import Flask, render_template, request, redirect, flash, send_file, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
import pandas as pd
import io
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import base64
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = "clave_secreta_segura"

# Configura aquí tu conexión a Neon/PostgreSQL
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    "DATABASE_URL",
    "postgresql://usuario:contraseña@host:puerto/dbname"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# -------- MODELOS --------

class Zona(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)
    tarifa = db.Column(db.Float, nullable=False)

class Mensajero(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)
    zona_nombre = db.Column(db.String(100), db.ForeignKey('zona.nombre'), nullable=False)
    zona = db.relationship('Zona', backref='mensajeros', lazy=True)

class Guia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    remitente = db.Column(db.String(200))
    numero_guia = db.Column(db.String(100), unique=True, nullable=False)
    destinatario = db.Column(db.String(200))
    direccion = db.Column(db.String(200))
    ciudad = db.Column(db.String(100))

class Despacho(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero_guia = db.Column(db.String(100), db.ForeignKey('guia.numero_guia'), nullable=False)
    mensajero = db.Column(db.String(100), nullable=False)
    zona = db.Column(db.String(100), nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

class Recepcion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero_guia = db.Column(db.String(100), db.ForeignKey('guia.numero_guia'), nullable=False)
    tipo = db.Column(db.String(20))  # ENTREGA o DEVUELTA
    motivo = db.Column(db.String(100), default="")
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

class Recogida(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero_interno = db.Column(db.String(100))
    fecha = db.Column(db.Date, nullable=False)
    observaciones = db.Column(db.Text)

# -------- UTILIDADES --------

def lista_guias_str_to_list(texto):
    if not texto:
        return []
    return [line.strip() for line in texto.splitlines() if line.strip()]

def safe_commit():
    try:
        db.session.commit()
        return None
    except Exception as e:
        db.session.rollback()
        return str(e)

# -------- RUTAS --------

@app.route("/")
def index():
    return render_template("index.html")

# Cargar base de guías desde Excel
@app.route("/cargar_base", methods=["GET", "POST"])
def cargar_base():
    if request.method == "POST":
        archivo = request.files.get("archivo_excel")
        if not archivo:
            flash("Selecciona un archivo Excel (.xlsx).", "danger")
            return redirect("/cargar_base")
        try:
            df = pd.read_excel(archivo)
            required = {"remitente", "numero_guia", "destinatario", "direccion", "ciudad"}
            if not required.issubset(set(df.columns)):
                flash(f"El archivo debe contener columnas: {', '.join(required)}", "danger")
                return redirect("/cargar_base")
            count = 0
            for _, row in df.iterrows():
                if not Guia.query.filter_by(numero_guia=str(row['numero_guia'])).first():
                    g = Guia(
                        remitente=row['remitente'],
                        numero_guia=str(row['numero_guia']),
                        destinatario=row['destinatario'],
                        direccion=row['direccion'],
                        ciudad=row['ciudad']
                    )
                    db.session.add(g)
                    count += 1
            err = safe_commit()
            if err:
                flash(f"Error guardando guías: {err}", "danger")
            else:
                flash(f"{count} guías cargadas exitosamente.", "success")
        except Exception as e:
            flash(f"Error procesando archivo: {e}", "danger")
        return redirect("/cargar_base")
    return render_template("cargar_base.html")

# Registrar zona
@app.route("/registrar_zona", methods=["GET", "POST"])
def registrar_zona():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        tarifa = request.form.get("tarifa", "").strip()
        if not nombre or not tarifa:
            flash("Completa todos los campos.", "danger")
            return redirect("/registrar_zona")
        try:
            tarifa_f = float(tarifa)
        except ValueError:
            flash("Tarifa inválida.", "danger")
            return redirect("/registrar_zona")
        if Zona.query.filter_by(nombre=nombre).first():
            flash("La zona ya existe.", "warning")
        else:
            nueva = Zona(nombre=nombre, tarifa=tarifa_f)
            db.session.add(nueva)
            err = safe_commit()
            if err:
                flash(f"Error guardando zona: {err}", "danger")
            else:
                flash("Zona registrada.", "success")
        return redirect("/registrar_zona")
    zonas = Zona.query.all()
    return render_template("registrar_zona.html", zonas=zonas)

# Registrar mensajero
@app.route("/registrar_mensajero", methods=["GET", "POST"])
def registrar_mensajero():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        zona_nombre = request.form.get("zona", "").strip()
        if not nombre or not zona_nombre:
            flash("Completa todos los campos.", "danger")
            return redirect("/registrar_mensajero")
        if not Zona.query.filter_by(nombre=zona_nombre).first():
            flash("Zona no encontrada.", "danger")
            return redirect("/registrar_mensajero")
        if Mensajero.query.filter_by(nombre=nombre).first():
            flash("El mensajero ya existe.", "warning")
        else:
            nuevo = Mensajero(nombre=nombre, zona_nombre=zona_nombre)
            db.session.add(nuevo)
            err = safe_commit()
            if err:
                flash(f"Error guardando mensajero: {err}", "danger")
            else:
                flash("Mensajero registrado.", "success")
        return redirect("/registrar_mensajero")
    zonas = Zona.query.all()
    mensajeros = Mensajero.query.all()
    return render_template("registrar_mensajero.html", zonas=zonas, mensajeros=mensajeros)

# Despachar guías masivamente (con validaciones)
@app.route("/despachar_guias", methods=["GET", "POST"])
def despachar_guias():
    if request.method == "POST":
        mensajero_nombre = request.form.get("mensajero")
        guias_texto = request.form.get("guias", "")
        guias_list = lista_guias_str_to_list(guias_texto)
        mensajero = Mensajero.query.filter_by(nombre=mensajero_nombre).first()
        if not mensajero:
            flash("Mensajero no encontrado.", "danger")
            return redirect("/despachar_guias")
        errores = []
        exito = []
        for numero in guias_list:
            numero = str(numero).strip()
            guia = Guia.query.filter_by(numero_guia=numero).first()
            if not guia:
                errores.append(f"Guía {numero} no existe (FALTANTE)")
                continue
            if Despacho.query.filter_by(numero_guia=numero).first():
                errores.append(f"Guía {numero} ya fue despachada")
                continue
            if Recepcion.query.filter_by(numero_guia=numero).first():
                errores.append(f"Guía {numero} ya fue recepcionada")
                continue
            despacho = Despacho(numero_guia=numero, mensajero=mensajero_nombre, zona=mensajero.zona_nombre, fecha=datetime.utcnow())
            db.session.add(despacho)
            exito.append(f"Guía {numero} despachada a {mensajero_nombre}")
        err = safe_commit()
        if err:
            flash(f"Error al despachar: {err}", "danger")
        if errores:
            flash("Errores:<br>" + "<br>".join(errores), "danger")
        if exito:
            flash("Despachos exitosos:<br>" + "<br>".join(exito), "success")
        return redirect("/ver_despacho")
    mensajeros = Mensajero.query.all()
    return render_template("despachar_guias.html", mensajeros=mensajeros)

# Ver despacho (lista)
@app.route("/ver_despacho")
def ver_despacho():
    despachos = Despacho.query.order_by(Despacho.fecha.desc()).all()
    return render_template("ver_despacho.html", despachos=despachos)

# Registrar recepción
@app.route("/registrar_recepcion", methods=["GET", "POST"])
def registrar_recepcion():
    if request.method == "POST":
        numero = request.form.get("numero_guia", "").strip()
        tipo = request.form.get("estado")
        motivo = request.form.get("motivo", "").strip()
        if not numero:
            flash("Ingrese número de guía.", "danger")
            return redirect("/registrar_recepcion")
        guia = Guia.query.filter_by(numero_guia=numero).first()
        if not guia:
            flash("Número de guía no existe en la base (FALTANTE).", "danger")
            return redirect("/registrar_recepcion")
        if not Despacho.query.filter_by(numero_guia=numero).first():
            flash("La guía no ha sido despachada aún.", "warning")
            return redirect("/registrar_recepcion")
        if Recepcion.query.filter_by(numero_guia=numero).first():
            flash("La recepción para esta guía ya está registrada.", "warning")
            return redirect("/registrar_recepcion")
        recepcion = Recepcion(numero_guia=numero, tipo=tipo, motivo=motivo if tipo == "DEVUELTA" else "", fecha=datetime.utcnow())
        db.session.add(recepcion)
        err = safe_commit()
        if err:
            flash(f"Error guardando recepción: {err}", "danger")
        else:
            flash(f"Recepción de guía {numero} registrada como {tipo}.", "success")
        return redirect("/registrar_recepcion")
    return render_template("registrar_recepcion.html")

# Consultar estado (varias guías)
@app.route("/consultar_estado", methods=["GET", "POST"])
def consultar_estado():
    resultados = []
    if request.method == "POST":
        guias_texto = request.form.get("guias", "")
        guias_list = lista_guias_str_to_list(guias_texto)
        for numero in guias_list:
            numero = str(numero).strip()
            guia = Guia.query.filter_by(numero_guia=numero).first()
            recepcion = Recepcion.query.filter_by(numero_guia=numero).first()
            despacho = Despacho.query.filter_by(numero_guia=numero).first()
            estado = "EN VERIFICACIÓN"
            motivo = ""
            mensajero = ""
            zona = ""
            fecha_despacho = None
            gestion = ""
            if not guia:
                estado = "FALTANTE"
            elif recepcion:
                estado = recepcion.tipo
                motivo = recepcion.motivo or ""
                gestion = f"{recepcion.tipo}" + (f" - {motivo}" if motivo else "")
                if despacho:
                    mensajero = despacho.mensajero
                    zona = despacho.zona
                    fecha_despacho = despacho.fecha
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
        if request.form.get("exportar") == "1":
            df = pd.DataFrame(resultados)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="estado")
            output.seek(0)
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            return send_file(output, download_name=f"consulta_estado_{ts}.xlsx", as_attachment=True,
                             mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        return render_template("consultar_estado.html", resultados=resultados)
    return render_template("consultar_estado.html", resultados=None)

# Liquidación con gráfico y export
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
            from sqlalchemy import func
            q = db.session.query(
                Despacho.mensajero,
                func.count(Despacho.id).label("cantidad"),
                func.sum(Zona.tarifa).label("total")
            ).join(Zona, Despacho.zona == Zona.nombre).filter(
                Despacho.fecha.between(fi, ff)
            ).group_by(Despacho.mensajero).all()
            liquidaciones = [{"mensajero": r.mensajero, "cantidad": r.cantidad, "total": float(r.total or 0)} for r in q]

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

        if request.form.get("exportar") == "1" and liquidaciones:
            df = pd.DataFrame(liquidaciones)
            out = io.BytesIO()
            with pd.ExcelWriter(out, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="liquidacion")
            out.seek(0)
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            return send_file(out, download_name=f"liquidacion_{ts}.xlsx", as_attachment=True,
                             mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    return render_template("liquidacion.html", liquidaciones=liquidaciones, fecha_inicio=fecha_inicio,
                           fecha_fin=fecha_fin, chart_png=chart_png)

# Registrar recogida
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

# Ver recogidas
@app.route("/ver_recogidas")
def ver_recogidas():
    lista = Recogida.query.order_by(Recogida.fecha.desc()).all()
    return render_template("ver_recogidas.html", recogidas=lista)

# Editar recogida
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

# API para validar existencia guía
@app.route("/api/existe_guia/<numero>")
def api_existe_guia(numero):
    existe = Guia.query.filter_by(numero_guia=numero).first() is not None
    return jsonify({"existe": existe})

# Iniciar app y crear tablas si no existen
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        print("Tablas creadas/verificadas.")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
