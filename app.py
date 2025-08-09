from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
import pandas as pd
from datetime import datetime

app = Flask(__name__)
app.secret_key = "clave_secreta"  # Cambia esto por algo seguro

# Config Neon PostgreSQL
app.config['SQLALCHEMY_DATABASE_URI'] = "postgresql://neondb_owner:npg_3owpfIUOAT0a@ep-soft-bush-acv2a8v4-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Modelos DB

class Zona(db.Model):
    __tablename__ = 'zonas'
    nombre = db.Column(db.String(100), primary_key=True)
    tarifa = db.Column(db.Float, nullable=False)

class Mensajero(db.Model):
    __tablename__ = 'mensajeros'
    nombre = db.Column(db.String(100), primary_key=True)
    zona = db.Column(db.String(100), db.ForeignKey('zonas.nombre'), nullable=False)
    zona_rel = db.relationship('Zona')

class Guia(db.Model):
    __tablename__ = 'guias'
    id = db.Column(db.Integer, primary_key=True)
    remitente = db.Column(db.String(255), nullable=False)
    numero_guia = db.Column(db.String(255), nullable=False, unique=True)
    destinatario = db.Column(db.String(255), nullable=False)
    direccion = db.Column(db.String(255), nullable=False)
    ciudad = db.Column(db.String(255), nullable=False)

class Despacho(db.Model):
    __tablename__ = 'despachos'
    id = db.Column(db.Integer, primary_key=True)
    numero_guia = db.Column(db.String(255), db.ForeignKey('guias.numero_guia'), nullable=False)
    mensajero = db.Column(db.String(100), db.ForeignKey('mensajeros.nombre'), nullable=False)
    zona = db.Column(db.String(100), db.ForeignKey('zonas.nombre'), nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

class Recepcion(db.Model):
    __tablename__ = 'recepciones'
    id = db.Column(db.Integer, primary_key=True)
    numero_guia = db.Column(db.String(255), db.ForeignKey('guias.numero_guia'), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # ENTREGADA o DEVUELTA
    motivo = db.Column(db.String(255))
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

class Recogida(db.Model):
    __tablename__ = 'recogidas'
    id = db.Column(db.Integer, primary_key=True)
    numero_guia = db.Column(db.String(255))
    fecha = db.Column(db.Date)
    observaciones = db.Column(db.String(255))

# Rutas

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/cargar_base", methods=["GET", "POST"])
def cargar_base():
    if request.method == "POST":
        archivo = request.files.get("archivo")
        if not archivo:
            flash("Por favor, selecciona un archivo Excel.", "danger")
            return redirect(url_for("cargar_base"))

        try:
            df = pd.read_excel(archivo)
            columnas_esperadas = {"remitente", "numero_guia", "destinatario", "direccion", "ciudad"}
            if not columnas_esperadas.issubset(df.columns):
                flash(f"El archivo debe contener las columnas: {', '.join(columnas_esperadas)}", "danger")
                return redirect(url_for("cargar_base"))

            for _, row in df.iterrows():
                # Solo agrega si no existe el número de guía
                if not Guia.query.filter_by(numero_guia=row["numero_guia"]).first():
                    guia = Guia(
                        remitente=row["remitente"],
                        numero_guia=row["numero_guia"],
                        destinatario=row["destinatario"],
                        direccion=row["direccion"],
                        ciudad=row["ciudad"]
                    )
                    db.session.add(guia)
            db.session.commit()
            flash("Base de guías cargada exitosamente.", "success")
        except Exception as e:
            flash(f"Error al cargar el archivo: {e}", "danger")

        return redirect(url_for("cargar_base"))

    return render_template("cargar_base.html")

@app.route("/registrar_zona", methods=["GET", "POST"])
def registrar_zona():
    if request.method == "POST":
        nombre = request.form.get("nombre")
        tarifa = request.form.get("tarifa")
        if not nombre or not tarifa:
            flash("Completa todos los campos.", "danger")
        else:
            try:
                tarifa_float = float(tarifa)
                if Zona.query.get(nombre):
                    flash("La zona ya existe.", "warning")
                else:
                    nueva_zona = Zona(nombre=nombre, tarifa=tarifa_float)
                    db.session.add(nueva_zona)
                    db.session.commit()
                    flash(f"Zona {nombre} registrada con tarifa {tarifa_float}.", "success")
            except ValueError:
                flash("Tarifa inválida, debe ser un número.", "danger")

    zonas = Zona.query.all()
    return render_template("registrar_zona.html", zonas=zonas)

@app.route("/registrar_mensajero", methods=["GET", "POST"])
def registrar_mensajero():
    zonas = Zona.query.all()
    if request.method == "POST":
        nombre = request.form.get("nombre")
        zona_nombre = request.form.get("zona")
        if not nombre or not zona_nombre:
            flash("Completa todos los campos.", "danger")
        else:
            if not Zona.query.get(zona_nombre):
                flash("Zona no encontrada.", "danger")
            elif Mensajero.query.get(nombre):
                flash("El mensajero ya existe.", "warning")
            else:
                mensajero = Mensajero(nombre=nombre, zona=zona_nombre)
                db.session.add(mensajero)
                db.session.commit()
                flash(f"Mensajero {nombre} registrado en zona {zona_nombre}.", "success")

    mensajeros = Mensajero.query.all()
    return render_template("registrar_mensajero.html", zonas=zonas, mensajeros=mensajeros)

@app.route("/despachar_guias", methods=["GET", "POST"])
def despachar_guias():
    mensajeros = Mensajero.query.all()
    if request.method == "POST":
        mensajero_nombre = request.form.get("mensajero")
        guias_texto = request.form.get("guias", "")
        guias_list = [g.strip() for g in guias_texto.strip().splitlines() if g.strip()]

        mensajero = Mensajero.query.get(mensajero_nombre)
        if not mensajero:
            flash("Mensajero no encontrado.", "danger")
            return redirect(url_for("despachar_guias"))

        errores = []
        exito = []
        for numero in guias_list:
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

            nuevo_despacho = Despacho(
                numero_guia=numero,
                mensajero=mensajero_nombre,
                zona=mensajero.zona,
                fecha=datetime.utcnow()
            )
            db.session.add(nuevo_despacho)
            exito.append(f"Guía {numero} despachada a {mensajero_nombre}")

        if errores:
            flash("Errores:<br>" + "<br>".join(errores), "danger")
        if exito:
            flash("Despachos exitosos:<br>" + "<br>".join(exito), "success")

        db.session.commit()
        return redirect(url_for("ver_despacho"))

    return render_template("despachar_guias.html", mensajeros=mensajeros)

@app.route("/ver_despacho")
def ver_despacho():
    despachos = Despacho.query.order_by(Despacho.fecha.desc()).all()
    return render_template("ver_despacho.html", despachos=despachos)

@app.route("/registrar_recepcion", methods=["GET", "POST"])
def registrar_recepcion():
    if request.method == "POST":
        numero_guia = request.form.get("numero_guia")
        tipo = request.form.get("estado")
        motivo = request.form.get("motivo", "")

        guia = Guia.query.filter_by(numero_guia=numero_guia).first()
        if not guia:
            flash("Número de guía no existe en la base (FALTANTE).", "danger")
            return redirect(url_for("registrar_recepcion"))

        despacho = Despacho.query.filter_by(numero_guia=numero_guia).first()
        if not despacho:
            flash("La guía no ha sido despachada aún.", "warning")
            return redirect(url_for("registrar_recepcion"))

        recepcion_existente = Recepcion.query.filter_by(numero_guia=numero_guia).first()
        if recepcion_existente:
            flash("La recepción para esta guía ya está registrada.", "warning")
            return redirect(url_for("registrar_recepcion"))

        nueva_recepcion = Recepcion(
            numero_guia=numero_guia,
            tipo=tipo,
            motivo=motivo if tipo == "DEVUELTA" else "",
            fecha=datetime.utcnow()
        )
        db.session.add(nueva_recepcion)
        db.session.commit()

        flash(f"Recepción de guía {numero_guia} registrada como {tipo}.", "success")
        return redirect(url_for("registrar_recepcion"))

    return render_template("registrar_recepcion.html")

@app.route("/registrar_recogida", methods=["GET", "POST"])
def registrar_recogida():
    if request.method == "POST":
        numero_guia = request.form.get("numero_guia")
        fecha_str = request.form.get("fecha")
        observaciones = request.form.get("observaciones")

        if not fecha_str:
            flash("La fecha es obligatoria.", "danger")
            return redirect(url_for("registrar_recogida"))

        try:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Formato de fecha inválido. Use YYYY-MM-DD.", "danger")
            return redirect(url_for("registrar_recogida"))

        recogida = Recogida(
            numero_guia=numero_guia,
            fecha=fecha,
            observaciones=observaciones
        )
        db.session.add(recogida)
        db.session.commit()
        flash(f"Recogida registrada para guía {numero_guia}.", "success")
        return redirect(url_for("registrar_recogida"))

    return render_template("registrar_recogida.html")

@app.route("/ver_recogidas")
def ver_recogidas():
    recogidas = Recogida.query.order_by(Recogida.fecha.desc()).all()
    return render_template("ver_recogidas.html", recogidas=recogidas)

@app.route("/liquidacion", methods=["GET", "POST"])
def liquidacion():
    liquidaciones = None
    fecha_inicio = fecha_fin = None

    if request.method == "POST":
        fecha_inicio = request.form.get("fecha_inicio")
        fecha_fin = request.form.get("fecha_fin")

        try:
            fi = datetime.strptime(fecha_inicio, "%Y-%m-%d")
            ff = datetime.strptime(fecha_fin, "%Y-%m-%d")

            # Query que junta despachos y zonas para sumar tarifas
            from sqlalchemy import func
            result = db.session.query(
                Despacho.mensajero,
                func.count(Despacho.id).label("cantidad"),
                func.sum(Zona.tarifa).label("total")
            ).join(Zona, Despacho.zona == Zona.nombre).filter(
                Despacho.fecha.between(fi, ff)
            ).group_by(Despacho.mensajero).all()

            liquidaciones = [{
                "mensajero": r.mensajero,
                "cantidad": r.cantidad,
                "total": float(r.total) if r.total else 0
            } for r in result]
        except Exception as e:
            flash(f"Error al calcular liquidación: {e}", "danger")

    return render_template("liquidacion.html", liquidaciones=liquidaciones, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
