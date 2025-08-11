from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import pandas as pd
import matplotlib.pyplot as plt
import io
import base64

app = Flask(__name__)
app.secret_key = "supersecretkey"

app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://neondb_owner:npg_3owpfIUOAT0a@ep-soft-bush-acv2a8v4-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# MODELOS

class Zona(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)
    tarifa = db.Column(db.Float, nullable=False)

class Mensajero(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    zona_id = db.Column(db.Integer, db.ForeignKey('zona.id'), nullable=False)
    zona = db.relationship('Zona', backref=db.backref('mensajeros', lazy=True))

class Guia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero_guia = db.Column(db.String(100), unique=True, nullable=False)
    cliente = db.Column(db.String(200))

class Despacho(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    guia_id = db.Column(db.Integer, db.ForeignKey('guia.id'), nullable=False)
    mensajero_id = db.Column(db.Integer, db.ForeignKey('mensajero.id'), nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

    guia = db.relationship('Guia', backref=db.backref('despachos', lazy=True))
    mensajero = db.relationship('Mensajero', backref=db.backref('despachos', lazy=True))

class Recepcion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    guia_id = db.Column(db.Integer, db.ForeignKey('guia.id'), nullable=False)
    tipo_evento = db.Column(db.String(20), nullable=False)  # ENTREGA, DEVOLUCION
    motivo = db.Column(db.String(50))
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

    guia = db.relationship('Guia', backref=db.backref('recepciones', lazy=True))

class Recogida(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero_interno = db.Column(db.String(100), nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    observaciones = db.Column(db.Text)

# RUTAS

@app.route('/')
def index():
    return render_template('index.html')

# Cargar Base (ejemplo para cargar datos masivos - placeholder)
@app.route('/cargar_base', methods=['GET', 'POST'])
def cargar_base():
    if request.method == 'POST':
        # Lógica para cargar base de datos masiva (ej. desde Excel)
        flash("Funcionalidad de carga de base aún no implementada.", "info")
        return redirect(url_for('cargar_base'))
    return render_template('cargar_base.html')

# Cargar guías (subir excel o ingresar manualmente)
@app.route('/cargar_guias', methods=['GET', 'POST'])
def cargar_guias():
    if request.method == 'POST':
        flash("Funcionalidad de carga guías aún no implementada.", "info")
        return redirect(url_for('cargar_guias'))
    return render_template('cargar_guias.html')

# Consultar estado de guías
@app.route('/consultar_estado', methods=['GET', 'POST'])
def consultar_estado():
    resultados = []
    if request.method == 'POST':
        numeros = request.form.get('numeros_guias', '').split()
        for numero in numeros:
            guia = Guia.query.filter_by(numero_guia=numero).first()
            if guia:
                despacho = Despacho.query.filter_by(guia_id=guia.id).first()
                recepcion = Recepcion.query.filter_by(guia_id=guia.id).order_by(Recepcion.fecha.desc()).first()
                estado = "EN VERIFICACIÓN"
                motivo = ""
                mensajero = ""
                zona = ""
                fecha_despacho = ""
                gestion = ""
                if despacho:
                    mensajero = despacho.mensajero.nombre
                    zona = despacho.mensajero.zona.nombre
                    fecha_despacho = despacho.fecha.strftime("%Y-%m-%d")
                    estado = "DESPACHADA"
                if recepcion:
                    estado = recepcion.tipo_evento
                    motivo = recepcion.motivo or ""
                    gestion = f"{recepcion.tipo_evento} {motivo}".strip()
                resultados.append({
                    'numero_guia': numero,
                    'estado': estado,
                    'motivo': motivo,
                    'mensajero': mensajero,
                    'zona': zona,
                    'fecha_despacho': fecha_despacho,
                    'gestion': gestion
                })
            else:
                resultados.append({'numero_guia': numero, 'estado': 'FALTANTE'})
    return render_template('consultar_estado.html', resultados=resultados)

# Despachar guías a mensajeros
@app.route('/despachar_guias', methods=['GET', 'POST'])
def despachar_guias():
    mensajeros = Mensajero.query.all()
    if request.method == 'POST':
        mensajero_id = request.form.get('mensajero_id')
        guias_texto = request.form.get('guias').strip()
        if not mensajero_id or not guias_texto:
            flash("Debe seleccionar mensajero e ingresar guías.", "warning")
            return redirect(url_for('despachar_guias'))
        guias_lista = guias_texto.split()
        despachadas = 0
        for num_guia in guias_lista:
            guia = Guia.query.filter_by(numero_guia=num_guia).first()
            if not guia:
                flash(f"Guía {num_guia} FALTANTE. No se puede despachar.", "danger")
                continue
            ya_despachada = Despacho.query.filter_by(guia_id=guia.id).first()
            if ya_despachada:
                flash(f"Guía {num_guia} ya fue despachada.", "warning")
                continue
            despacho = Despacho(guia_id=guia.id, mensajero_id=int(mensajero_id))
            db.session.add(despacho)
            despachadas += 1
        db.session.commit()
        flash(f"{despachadas} guías despachadas correctamente.", "success")
        return redirect(url_for('despachar_guias'))
    return render_template('despachar_guias.html', mensajeros=mensajeros)

# Registrar mensajero
@app.route('/registrar_mensajero', methods=['GET', 'POST'])
def registrar_mensajero():
    zonas = Zona.query.all()
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        zona_id = request.form.get('zona_id')
        if not nombre or not zona_id:
            flash("Debe ingresar nombre y seleccionar zona.", "warning")
            return redirect(url_for('registrar_mensajero'))
        mensajero = Mensajero(nombre=nombre, zona_id=int(zona_id))
        db.session.add(mensajero)
        db.session.commit()
        flash("Mensajero registrado.", "success")
        return redirect(url_for('registrar_mensajero'))
    return render_template('registrar_mensajero.html', zonas=zonas)

# Registrar recepción
@app.route('/registrar_recepcion', methods=['GET', 'POST'])
def registrar_recepcion():
    if request.method == 'POST':
        numero_guia = request.form.get('numero_guia')
        tipo_evento = request.form.get('tipo_evento')
        motivo = request.form.get('motivo', '')
        guia = Guia.query.filter_by(numero_guia=numero_guia).first()
        if not guia:
            flash("Guía no existe.", "danger")
            return redirect(url_for('registrar_recepcion'))
        recepcion = Recepcion(guia_id=guia.id, tipo_evento=tipo_evento, motivo=motivo)
        db.session.add(recepcion)
        db.session.commit()
        flash("Recepción registrada.", "success")
        return redirect(url_for('registrar_recepcion'))
    return render_template('registrar_recepcion.html')

# Registrar recogida
@app.route('/registrar_recogida', methods=['GET', 'POST'])
def registrar_recogida():
    if request.method == 'POST':
        numero_interno = request.form.get('numero_interno')
        fecha = request.form.get('fecha')
        observaciones = request.form.get('observaciones')
        try:
            fecha_dt = datetime.strptime(fecha, "%Y-%m-%d")
        except:
            flash("Fecha inválida.", "warning")
            return redirect(url_for('registrar_recogida'))
        recogida = Recogida(numero_interno=numero_interno, fecha=fecha_dt, observaciones=observaciones)
        db.session.add(recogida)
        db.session.commit()
        flash("Recogida registrada.", "success")
        return redirect(url_for('registrar_recogida'))
    return render_template('registrar_recogida.html')

# Ver despacho
@app.route('/ver_despacho')
def ver_despacho():
    despachos = Despacho.query.order_by(Despacho.fecha.desc()).all()
    return render_template('ver_despacho.html', despachos=despachos)

# Ver guías
@app.route('/ver_guias')
def ver_guias():
    guias = Guia.query.all()
    return render_template('ver_guias.html', guias=guias)

# Ver recogidas
@app.route('/ver_recogidas')
def ver_recogidas():
    recogidas = Recogida.query.order_by(Recogida.fecha.desc()).all()
    return render_template('ver_recogidas.html', recogidas=recogidas)

# Verificación de entrada (escaneo y validación)
@app.route('/verificacion_entrada', methods=['GET', 'POST'])
def verificacion_entrada():
    mensaje = None
    if request.method == 'POST':
        numero_guia = request.form.get('numero_guia')
        guia = Guia.query.filter_by(numero_guia=numero_guia).first()
        if not guia:
            mensaje = f"Guía {numero_guia} FALTANTE. No existe en base."
        else:
            mensaje = f"Guía {numero_guia} existe en base."
    return render_template('verificacion_entrada.html', mensaje=mensaje)

# Liquidación por mensajero con gráfica y exportación
@app.route('/liquidacion', methods=['GET', 'POST'])
def liquidacion():
    liquidaciones = None
    chart_png = None
    fecha_inicio = ''
    fecha_fin = ''

    if request.method == 'POST':
        fecha_inicio = request.form.get('fecha_inicio')
        fecha_fin = request.form.get('fecha_fin')

        if not fecha_inicio or not fecha_fin:
            flash("Por favor, ingrese ambas fechas para la liquidación.", "warning")
            return redirect(url_for('liquidacion'))

        fecha_inicio_dt = datetime.strptime(fecha_inicio, "%Y-%m-%d")
        fecha_fin_dt = datetime.strptime(fecha_fin, "%Y-%m-%d")

        resultados = (
            db.session.query(Mensajero.nombre.label('mensajero'),
                             db.func.count(Despacho.id).label('cantidad'),
                             db.func.sum(Zona.tarifa).label('total'))
            .join(Despacho, Mensajero.id == Despacho.mensajero_id)
            .join(Zona, Mensajero.zona_id == Zona.id)
            .filter(Despacho.fecha >= fecha_inicio_dt, Despacho.fecha <= fecha_fin_dt)
            .group_by(Mensajero.nombre)
            .all()
        )

        liquidaciones = []
        for r in resultados:
            liquidaciones.append({
                'mensajero': r.mensajero,
                'cantidad': r.cantidad,
                'total': r.total if r.total else 0.0
            })

        if liquidaciones:
            nombres = [l['mensajero'] for l in liquidaciones]
            totales = [l['total'] for l in liquidaciones]

            fig, ax = plt.subplots(figsize=(6, 4))
            ax.bar(nombres, totales, color='royalblue')
            ax.set_title('Liquidación por Mensajero')
            ax.set_ylabel('Total (COP)')
            ax.set_xlabel('Mensajero')
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()

            img = io.BytesIO()
            plt.savefig(img, format='png')
            img.seek(0)
            chart_png = base64.b64encode(img.getvalue()).decode('utf8')
            plt.close(fig)

        if request.form.get('exportar'):
            df = pd.DataFrame(liquidaciones)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Liquidacion')
            output.seek(0)
            return send_file(output,
                             as_attachment=True,
                             download_name='liquidacion.xlsx',
                             mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    return render_template('liquidacion.html',
                           liquidaciones=liquidaciones,
                           chart_png=chart_png,
                           fecha_inicio=fecha_inicio,
                           fecha_fin=fecha_fin)

# Registrar zona
@app.route('/registrar_zona', methods=['GET', 'POST'])
def registrar_zona():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        tarifa = request.form.get('tarifa')
        try:
            tarifa = float(tarifa)
        except:
            flash("Tarifa inválida.", "warning")
            return redirect(url_for('registrar_zona'))

        if Zona.query.filter_by(nombre=nombre).first():
            flash("Zona ya existe.", "warning")
            return redirect(url_for('registrar_zona'))

        zona = Zona(nombre=nombre, tarifa=tarifa)
        db.session.add(zona)
        db.session.commit()
        flash("Zona registrada.", "success")
        return redirect(url_for('registrar_zona'))
    return render_template('registrar_zona.html')

if __name__ == '__main__':
    app.run(debug=True)
