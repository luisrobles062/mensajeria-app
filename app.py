from flask import Flask, render_template, request, redirect, send_file, flash, url_for, jsonify
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

# Variables en memoria
zonas = []  # [{'nombre': 'Zona 1', 'tarifa': 250}]
mensajeros = []  # [{'nombre': 'Pedro', 'zona': 'Zona 1'}]
guias_cargadas = pd.DataFrame()
despachos = []
recepciones = []

# Inyectar la función ahora() en las plantillas para mostrar año actual sin error
@app.context_processor
def inject_now():
    return {'ahora': datetime.utcnow}

def safe_commit():
    try:
        # En versión con base de datos, aquí iría commit
        return None
    except Exception as e:
        return str(e)

def lista_guias_str_to_list(texto):
    if not texto:
        return []
    return [line.strip() for line in texto.splitlines() if line.strip()]

# Rutas
@app.route("/")
def index():
    return render_template("index.html")

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

@app.route("/ver_despacho")
def ver_despacho():
    return render_template("ver_despacho.html", despachos=despachos)

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
            guia_en_base = (not guias_cargadas.empty) and (numero in guias_cargadas["numero_guia"].astype(str).values)
            if not guia_en_base:
                estado = "FALTANTE"
            else:
                recepcion_ref = next((r for r in recepciones if r["numero_guia"] == numero), None)
                despacho_ref = next((d for d in despachos if d["numero_guia"] == numero), None)
                if recepcion_ref:
                    estado = recepcion_ref["tipo"]
                    motivo = recepcion_ref.get("motivo", "")
                    gestion = f"{estado}" + (f" - {motivo}" if motivo else "")
                    if despacho_ref:
                        mensajero = despacho_ref["mensajero"]
                        zona = despacho_ref["zona"]
                        fecha_despacho = despacho_ref["fecha"].strftime("%Y-%m-%d %H:%M:%S")
                elif despacho_ref:
                    estado = "DESPACHADA"
                    mensajero = despacho_ref["mensajero"]
                    zona = despacho_ref["zona"]
                    fecha_despacho = despacho_ref["fecha"].strftime("%Y-%m-%d %H:%M:%S")
            resultados.append({
                "numero_guia": numero,
                "estado": estado,
                "motivo": motivo,
                "mensajero": mensajero,
                "zona": zona,
                "fecha_despacho": fecha_despacho,
                "gestion": gestion
            })
        # Exportar Excel si pidió
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

@app.route("/verificacion_entrada", methods=["GET", "POST"])
def verificacion_entrada():
    if request.method == "POST":
        numero = request.form.get("numero_guia", "").strip()
        if not numero:
            flash("Ingrese número de guía.", "danger")
            return redirect(url_for("verificacion_entrada"))
        guia_en_base = (not guias_cargadas.empty) and (numero in guias_cargadas["numero_guia"].astype(str).values)
        if not guia_en_base:
            flash("FALTANTE: la guía no existe en la base.", "danger")
            return redirect(url_for("verificacion_entrada"))
        flash(f"Guía {numero} validada correctamente.", "success")
        return redirect(url_for("verificacion_entrada"))
    return render_template("verificacion_entrada.html")

@app.route("/registrar_recogida", methods=["GET", "POST"])
def registrar_recogida():
    # Esta parte depende de base de datos, pero dejamos dummy para evitar errores
    flash("Funcionalidad de recogidas aún no implementada en versión sin base de datos.", "info")
    return redirect(url_for("index"))

@app.route("/ver_recogidas")
def ver_recogidas():
    flash("Funcionalidad de recogidas aún no implementada en versión sin base de datos.", "info")
    return redirect(url_for("index"))

@app.route("/editar_recogida/<int:id>", methods=["GET", "POST"])
def editar_recogida(id):
    flash("Funcionalidad de recogidas aún no implementada en versión sin base de datos.", "info")
    return redirect(url_for("index"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
