from flask import Flask, render_template, request, redirect, send_file, flash
import pandas as pd
import io
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import base64
from datetime import datetime
import os

# ----------------- CONFIGURACIÓN APP -----------------
app = Flask(__name__)
app.secret_key = "clave_secreta_segura"

# ----------------- VARIABLES EN MEMORIA -----------------
zonas = []  # [{'nombre': 'Zona 1', 'tarifa': 250}]
mensajeros = []  # [{'nombre': 'Pedro', 'zona': 'Zona 1'}]
guias_cargadas = pd.DataFrame()
despachos = []
recepciones = []

# ----------------- UTIL -----------------
def safe_commit():
    try:
        # Aquí debería ir commit a BD si usas SQLAlchemy, pero en esta versión usa variables en memoria
        return None
    except Exception as e:
        return str(e)

def lista_guias_str_to_list(texto):
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
            return redirect("/cargar_base")
        try:
            df = pd.read_excel(archivo)
            required = {"remitente", "numero_guia", "destinatario", "direccion", "ciudad"}
            if not required.issubset(set(df.columns)):
                flash(f"El archivo debe contener columnas: {', '.join(required)}", "danger")
                return redirect("/cargar_base")
            global guias_cargadas
            guias_cargadas = df
            flash(f"Archivo cargado con {len(df)} registros.", "success")
        except Exception as e:
            flash(f"Error procesando archivo: {e}", "danger")
        return redirect("/cargar_base")
    return render_template("cargar_base.html")

# -------- REGISTRAR ZONA --------
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
        if any(z["nombre"] == nombre for z in zonas):
            flash("La zona ya existe.", "warning")
        else:
            zonas.append({"nombre": nombre, "tarifa": tarifa_f})
            flash("Zona registrada.", "success")
        return redirect("/registrar_zona")
    return render_template("registrar_zona.html", zonas=zonas)

# -------- REGISTRAR MENSAJERO --------
@app.route("/registrar_mensajero", methods=["GET", "POST"])
def registrar_mensajero():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        zona_nombre = request.form.get("zona", "").strip()
        if not nombre or not zona_nombre:
            flash("Completa todos los campos.", "danger")
            return redirect("/registrar_mensajero")
        if not any(z["nombre"] == zona_nombre for z in zonas):
            flash("Zona no encontrada.", "danger")
            return redirect("/registrar_mensajero")
        if any(m["nombre"] == nombre for m in mensajeros):
            flash("El mensajero ya existe.", "warning")
        else:
            mensajeros.append({"nombre": nombre, "zona": zona_nombre})
            flash("Mensajero registrado.", "success")
        return redirect("/registrar_mensajero")
    return render_template("registrar_mensajero.html", zonas=zonas, mensajeros=mensajeros)

# -------- DESPACHO MASIVO (scanner lines) --------
@app.route("/despachar_guias", methods=["GET", "POST"])
def despachar_guias():
    if request.method == "POST":
        mensajero_nombre = request.form.get("mensajero")
        guias_texto = request.form.get("guias", "")
        guias_list = lista_guias_str_to_list(guias_texto)
        mensajero = next((m for m in mensajeros if m["nombre"] == mensajero_nombre), None)
        if not mensajero:
            flash("Mensajero no encontrado.", "danger")
            return redirect("/despachar_guias")
        errores = []
        exito = []
        for numero in guias_list:
            numero = str(numero).strip()
            if guias_cargadas.empty or numero not in guias_cargadas["numero_guia"].astype(str).values:
                errores.append(f"Guía {numero} no existe (FALTANTE)")
                continue
            if any(d["numero_guia"] == numero for d in despachos):
                errores.append(f"Guía {numero} ya fue despachada")
                continue
            if any(r["numero_guia"] == numero for r in recepciones):
                errores.append(f"Guía {numero} ya fue recepcionada")
                continue
            despacho = {"numero_guia": numero, "mensajero": mensajero_nombre, "zona": mensajero["zona"], "fecha": datetime.utcnow()}
            despachos.append(despacho)
            exito.append(f"Guía {numero} despachada a {mensajero_nombre}")
        if errores:
            flash("Errores:<br>" + "<br>".join(errores), "danger")
        if exito:
            flash("Despachos exitosos:<br>" + "<br>".join(exito), "success")
        return redirect("/ver_despacho")
    return render_template("despachar_guias.html", mensajeros=mensajeros)

# -------- VER DESPACHO --------
@app.route("/ver_despacho")
def ver_despacho():
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
            return redirect("/registrar_recepcion")
        if guias_cargadas.empty or numero not in guias_cargadas["numero_guia"].astype(str).values:
            flash("Número de guía no existe en la base (FALTANTE).", "danger")
            return redirect("/registrar_recepcion")
        if not any(d["numero_guia"] == numero for d in despachos):
            flash("La guía no ha sido despachada aún.", "warning")
            return redirect("/registrar_recepcion")
        if any(r["numero_guia"] == numero for r in recepciones):
            flash("La recepción para esta guía ya está registrada.", "warning")
            return redirect("/registrar_recepcion")
        recepcion = {"numero_guia": numero, "tipo": tipo, "motivo": motivo if tipo == "DEVUELTA" else "", "fecha": datetime.utcnow()}
        recepciones.append(recepcion)
        flash(f"Recepción de guía {numero} registrada como {tipo}.", "success")
        return redirect("/registrar_recepcion")
    return render_template("registrar_recepcion.html")

# -------- CONSULTAR ESTADO (multi) --------
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
            fecha_despacho =_
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
