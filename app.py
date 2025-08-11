from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy
import pandas as pd
import io
import matplotlib.pyplot as plt
import base64
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_aqui'

# Configura tu URI de conexión a Postgres
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://neondb_owner:npg_3owpfIUOAT0a@ep-soft-bush-acv2a8v4-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ------------------ MODELOS ------------------------

class Zona(db.Model):
    __tablename__ = 'zonas'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)
    tarifa = db.Column(db.Float, nullable=False)

    mensajeros = db.relationship('Mensajero', backref='zona', lazy=True)

class Mensajero(db.Model):
    __tablename__ = 'mensajeros'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)
    zona_id = db.Column(db.Integer, db.ForeignKey('zonas.id'), nullable=False)

    despachos = db.relationship('Despacho', backref='mensajero', lazy=True)

class Guia(db.Model):
    __tablename__ = 'guias'
    numero_guia = db.Column(db.String(50), primary_key=True)
    remitente = db.Column(db.String(200))
    destinatario = db.Column(db.String(200))
    direccion = db.Column(db.String(300))
    ciudad = db.Column(db.String(100))

class Despacho(db.Model):
    __tablename__ = 'despachos'
    id = db.Column(db.Integer, primary_key=True)
    numero_guia = db.Column(db.String(50), db.ForeignKey('guias.numero_guia'), nullable=False)
    mensajero_id = db.Column(db.Integer, db.ForeignKey('mensajeros.id'), nullable=False)
    fecha_despacho = db.Column(db.DateTime, default=datetime.utcnow)

    recepciones = db.relationship('Recepcion', backref='despacho', lazy=True)

class Recepcion(db.Model):
    __tablename__ = 'recepciones'
    id = db.Column(db.Integer, primary_key=True)
    despacho_id = db.Column(db.Integer, db.ForeignKey('despachos.id'), nullable=False)
    tipo_evento = db.Column(db.String(20))  # ENTREGA o DEVOLUCION
    motivo = db.Column(db.String(50), nullable=True)  # Si es devolución, motivo
    fecha_recepcion = db.Column(db.DateTime, default=datetime.utcnow)

class Recogida(db.Model):
    __tablename__ = 'recogidas'
    id = db.Column(db.Integer, primary_key=True)
    numero_interno = db.Column(db.String(50), unique=True, nullable=False)
    fecha = db.Column(db.Date)
    observaciones = db.Column(db.Text)

# ------------------ RUTAS ------------------------

@app.route('/')
def index():
    return render_template('index.html')

# --- Cargar base desde Excel ---
@app.route('/cargar_base', methods=['GET', 'POST'])
def cargar_base():
    if request.method == 'POST':
        archivo = request.files.get('archivo')
        if not archivo:
            flash('No se seleccionó ningún archivo', 'danger')
            return redirect(request.url)
        try:
            df = pd.read_excel(archivo)
            columnas_necesarias = {'numero_guia', 'remitente', 'destinatario', 'direccion', 'ciudad'}
            if not columnas_necesarias.issubset(set(col.lower() for col in df.columns)):
                flash(f'El archivo debe contener estas columnas: {columnas_necesarias}', 'danger')
                return redirect(request.url)
            df.columns = [col.lower() for col in df.columns]
            for _, row in df.iterrows():
                guia = Guia.query.get(row['numero_guia'])
                if not guia:
                    guia = Guia(
                        numero_guia=row['numero_guia'],
                        remitente=row['remitente'],
                        destinatario=row['destinatario'],
                        direccion=row['direccion'],
                        ciudad=row['ciudad']
                    )
                    db.session.add(guia)
                else:
                    guia.remitente = row['remitente']
                    guia.destinatario = row['destinatario']
                    guia.direccion = row['direccion']
                    guia.ciudad = row['ciudad']
            db.session.commit()
            flash('Base de guías cargada correctamente', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'Error al procesar archivo: {e}', 'danger')
            return redirect(request.url)
    return render_template('cargar_base.html')

# --- Registrar Zona ---
@app.route('/registrar_zona', methods=['GET', 'POST'])
def registrar_zona():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        tarifa = request.form.get('tarifa')
        if not nombre or not tarifa:
            flash('Debe ingresar nombre y tarifa', 'danger')
            return redirect(request.url)
        try:
            tarifa_val = float(tarifa)
            if tarifa_val < 0:
                raise ValueError('Tarifa negativa')
        except:
            flash('Tarifa debe ser un número positivo', 'danger')
            return redirect(request.url)
        if Zona.query.filter_by(nombre=nombre).first():
            flash('Ya existe una zona con ese nombre', 'danger')
            return redirect(request.url)
        nueva_zona = Zona(nombre=nombre, tarifa=tarifa_val)
        db.session.add(nueva_zona)
        db.session.commit()
        flash('Zona registrada con éxito', 'success')
        return redirect(url_for('index'))
    return render_template('registrar_zona.html')

# --- Registrar Mensajero ---
@app.route('/registrar_mensajero', methods=['GET', 'POST'])
def registrar_mensajero():
    zonas = Zona.query.order_by(Zona.nombre).all()
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        zona_id = request.form.get('zona_id')
        if not nombre or not zona_id:
            flash('Debe ingresar nombre y zona', 'danger')
            return redirect(request.url)
        if Mensajero.query.filter_by(nombre=nombre).first():
            flash('Ya existe un mensajero con ese nombre', 'danger')
            return redirect(request.url)
        nueva = Mensajero(nombre=nombre, zona_id=zona_id)
        db.session.add(nueva)
        db.session.commit()
        flash('Mensajero registrado con éxito', 'success')
        return redirect(url_for('index'))
    return render_template('registrar_mensajero.html', zonas=zonas)

# --- Despachar guías ---
@app.route('/despachar_guias', methods=['GET', 'POST'])
def despachar_guias():
    zonas = Zona.query.order_by(Zona.nombre).all()
    if request.method == 'POST':
        mensajero_id = request.form.get('mensajero_id')
        guias_input = request.form.get('guias_input')
        if not mensajero_id or not guias_input:
            flash('Debe seleccionar mensajero y guías', 'danger')
            return redirect(request.url)
        guias = [g.strip() for g in guias_input.split('\n') if g.strip()]
        errores = []
        despachadas = []
        for num_guia in guias:
            guia = Guia.query.get(num_guia)
            if not guia:
                errores.append(f'Guía {num_guia} no existe en base')
                continue
            # Verificar si ya despachada
            ya_despachada = Despacho.query.filter_by(numero_guia=num_guia).first()
            if ya_despachada:
                errores.append(f'Guía {num_guia} ya fue despachada')
                continue
            despacho = Despacho(numero_guia=num_guia, mensajero_id=mensajero_id)
            db.session.add(despacho)
            despachadas.append(num_guia)
        db.session.commit()
        if errores:
            flash('Errores: ' + '; '.join(errores), 'danger')
        if despachadas:
            flash(f'Guías despachadas: {", ".join(despachadas)}', 'success')
        return redirect(url_for('index'))
    return render_template('despachar_guias.html', zonas=zonas)

# --- Consultar estado de guías ---
@app.route('/consultar_estado', methods=['GET', 'POST'])
def consultar_estado():
    resultados = []
    if request.method == 'POST':
        guias_input = request.form.get('guias_input')
        if not guias_input:
            flash('Debe ingresar números de guía', 'danger')
            return redirect(request.url)
        guias = [g.strip() for g in guias_input.split('\n') if g.strip()]
        for num_guia in guias:
            guia = Guia.query.get(num_guia)
            if not guia:
                resultados.append({'numero_guia': num_guia, 'estado': 'FALTANTE'})
                continue
            despacho = Despacho.query.filter_by(numero_guia=num_guia).first()
            if not despacho:
                resultados.append({'numero_guia': num_guia, 'estado': 'EN VERIFICACIÓN'})
                continue
            recepcion = Recepcion.query.filter_by(despacho_id=despacho.id).order_by(Recepcion.fecha_recepcion.desc()).first()
            if recepcion:
                estado = recepcion.tipo_evento
                motivo = recepcion.motivo
            else:
                estado = 'DESPACHADA'
                motivo = ''
            resultados.append({
                'numero_guia': num_guia,
                'estado': estado,
                'motivo': motivo,
                'mensajero': despacho.mensajero.nombre,
                'zona': despacho.mensajero.zona.nombre,
                'fecha_despacho': despacho.fecha_despacho.strftime('%Y-%m-%d %H:%M'),
            })
    return render_template('consultar_estado.html', resultados=resultados)

# --- Registrar recepción (entrega o devolución) ---
@app.route('/registrar_recepcion', methods=['GET', 'POST'])
def registrar_recepcion():
    if request.method == 'POST':
        numero_guia = request.form.get('numero_guia')
        tipo_evento = request.form.get('tipo_evento')
        motivo = request.form.get('motivo') if tipo_evento == 'DEVOLUCION' else None

        despacho = Despacho.query.filter_by(numero_guia=numero_guia).first()
        if not despacho:
            flash('Esta guía no ha sido despachada', 'danger')
            return redirect(request.url)

        recepcion = Recepcion(
            despacho_id=despacho.id,
            tipo_evento=tipo_evento,
            motivo=motivo,
            fecha_recepcion=datetime.utcnow()
        )
        db.session.add(recepcion)
        db.session.commit()
        flash(f'Recepción registrada: {tipo_evento}', 'success')
        return redirect(url_for('index'))

    return render_template('registrar_recepcion.html')

# --- Liquidación ---
@app.route('/liquidacion', methods=['GET', 'POST'])
def liquidacion():
    liquidaciones = []
    chart_png = None
    fecha_inicio = None
    fecha_fin = None

    if request.method == 'POST':
        fecha_inicio = request.form.get('fecha_inicio')
        fecha_fin = request.form.get('fecha_fin')
        exportar = request.form.get('exportar')

        try:
            fi = datetime.strptime(fecha_inicio, '%Y-%m-%d')
            ff = datetime.strptime(fecha_fin, '%Y-%m-%d')
        except Exception:
            flash('Fechas inválidas', 'danger')
            return redirect(request.url)

        # Consulta liquidación por mensajero
        query = db.session.query(
            Mensajero.nombre.label('mensajero'),
            db.func.count(Despacho.id).label('cantidad'),
            db.func.sum(Zona.tarifa).label('total')
        ).join(Zona, Mensajero.zona_id == Zona.id)\
         .join(Despacho, Despacho.mensajero_id == Mensajero.id)\
         .filter(Despacho.fecha_despacho >= fi, Despacho.fecha_despacho <= ff)\
         .group_by(Mensajero.nombre)

        liquidaciones = query.all()

        if exportar:
            # Exportar a Excel
            df = pd.DataFrame([(l.mensajero, l.cantidad, l.total) for l in liquidaciones], columns=['Mensajero', 'Cantidad Guías', 'Total (COP)'])
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Liquidacion')
            output.seek(0)
            return send_file(output, download_name='liquidacion.xlsx', as_attachment=True)

        # Generar gráfico
        if liquidaciones:
            nombres = [l.mensajero for l in liquidaciones]
            totales = [l.total for l in liquidaciones]
            plt.figure(figsize=(8,4))
            plt.bar(nombres, totales, color='skyblue')
            plt.xlabel('Mensajero')
            plt.ylabel('Total (COP)')
            plt.title('Liquidación por Mensajero')
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()
            img = io.BytesIO()
            plt.savefig(img, format='png')
            plt.close()
            img.seek(0)
            chart_png = base64.b64encode(img.getvalue()).decode('utf8')

    return render_template('liquidacion.html', liquidaciones=liquidaciones, chart_png=chart_png,
                           fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)

# --- Registrar recogida ---
@app.route('/registrar_recogida', methods=['GET', 'POST'])
def registrar_recogida():
    if request.method == 'POST':
        numero_interno = request.form.get('numero_interno')
        fecha = request.form.get('fecha')
        observaciones = request.form.get('observaciones')
        if not numero_interno or not fecha:
            flash('Número interno y fecha son obligatorios', 'danger')
            return redirect(request.url)
        try:
            fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
        except:
            flash('Fecha inválida', 'danger')
            return redirect(request.url)
        if Recogida.query.filter_by(numero_interno=numero_interno).first():
            flash('Número interno ya registrado', 'danger')
            return redirect(request.url)
        recogida = Recogida(numero_interno=numero_interno, fecha=fecha_obj, observaciones=observaciones)
        db.session.add(recogida)
        db.session.commit()
        flash('Recogida registrada', 'success')
        return redirect(url_for('ver_recogidas'))
    return render_template('registrar_recogida.html')

# --- Ver recogidas ---
@app.route('/ver_recogidas')
def ver_recogidas():
    recogidas = Recogida.query.order_by(Recogida.fecha.desc()).all()
    return render_template('ver_recogidas.html', recogidas=recogidas)

# --- Ver despacho ---
@app.route('/ver_despacho')
def ver_despacho():
    despachos = Despacho.query.order_by(Despacho.fecha_despacho.desc()).all()
    return render_template('ver_despacho.html', despachos=despachos)

# --- Ver guías ---
@app.route('/ver_guias')
def ver_guias():
    guias = Guia.query.order_by(Guia.numero_guia).all()
    return render_template('ver_guias.html', guias=guias)

# --- Verificación entrada (escaneo rápido) ---
@app.route('/verificacion_entrada', methods=['GET', 'POST'])
def verificacion_entrada():
    if request.method == 'POST':
        numero_guia = request.form.get('numero_guia')
        guia = Guia.query.get(numero_guia)
        if not guia:
            flash('Guía FALTANTE', 'danger')
            return redirect(request.url)
        flash(f'Guía {numero_guia} existe en la base', 'success')
        return redirect(request.url)
    return render_template('verificacion_entrada.html')

# ------------------ UTILIDADES ------------------------

@app.context_processor
def inject_now():
    return {'now': datetime.utcnow()}

# ------------------ INICIALIZAR ------------------------

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
