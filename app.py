from flask import Flask, render_template, request, redirect, send_file, flash
import pandas as pd
import io
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import base64
from datetime import datetime

app = Flask(__name__)
app.secret_key = "clave_secreta_segura"

# ----------------- VARIABLES EN MEMORIA -----------------
zonas = []  # [{'nombre': 'Zona 1', 'tarifa': 250}]
mensajeros = []  # [{'nombre': 'Pedro', 'zona': 'Zona 1'}]
guias_cargadas = pd.DataFrame()
despachos = []  # [{'guias': [...], 'zona':..., 'mensajero':..., 'fecha':...}]
recepciones = []  # [{'guia':..., 'tipo':..., 'motivo':..., 'fecha':...}]
recogidas = []  # [{'numero':..., 'fecha':..., 'observacion':...}]

# ----------------- RUTA PRINCIPAL -----------------
@app.route('/')
def index():
    return render_template('index.html')

# ----------------- CARGAR BASE DE GUÍAS -----------------
@app.route('/cargar', methods=['GET', 'POST'])
def cargar():
    global guias_cargadas
    if request.method == 'POST':
        archivo = request.files['archivo']
        if archivo.filename.endswith('.xlsx'):
            df = pd.read_excel(archivo)
            columnas_requeridas = {'remitente', 'numero_guia', 'destinatario', 'direccion', 'ciudad'}
            if columnas_requeridas.issubset(df.columns):
                guias_cargadas = df
                flash("Base de datos cargada correctamente", "success")
            else:
                flash("El archivo no tiene las columnas requeridas", "danger")
        else:
            flash("Formato no válido. Debe ser .xlsx", "danger")
    return render_template('cargar.html')

# ----------------- REGISTRAR ZONA -----------------
@app.route('/zonas', methods=['GET', 'POST'])
def zonas_view():
    if request.method == 'POST':
        nombre = request.form['nombre']
        tarifa = request.form['tarifa']
        zonas.append({'nombre': nombre, 'tarifa': float(tarifa)})
        flash("Zona registrada", "success")
    return render_template('zonas.html', zonas=zonas)

# ----------------- REGISTRAR MENSAJERO -----------------
@app.route('/mensajeros', methods=['GET', 'POST'])
def mensajeros_view():
    if request.method == 'POST':
        nombre = request.form['nombre']
        zona = request.form['zona']
        mensajeros.append({'nombre': nombre, 'zona': zona})
        flash("Mensajero registrado", "success")
    return render_template('mensajeros.html', mensajeros=mensajeros, zonas=zonas)

# ----------------- DESPACHAR -----------------
@app.route('/despachar', methods=['GET', 'POST'])
def despachar():
    if request.method == 'POST':
        zona = request.form['zona']
        mensajero = request.form['mensajero']
        guias_texto = request.form['guias'].strip().splitlines()
        guias_validas = []
        for g in guias_texto:
            if guias_cargadas.empty or g not in guias_cargadas['numero_guia'].astype(str).values:
                flash(f"Guía {g} FALTANTE - No se despachó", "danger")
                continue
            if any(g in d['guias'] for d in despachos):
                flash(f"Guía {g} ya fue despachada", "danger")
                continue
            guias_validas.append(g)
        if guias_validas:
            despachos.append({
                'guias': guias_validas,
                'zona': zona,
                'mensajero': mensajero,
                'fecha': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            flash("Despacho registrado", "success")
    return render_template('despachar.html', zonas=zonas, mensajeros=mensajeros)

# ----------------- VER DESPACHO -----------------
@app.route('/ver_despacho')
def ver_despacho():
    return render_template('ver_despacho.html', despachos=despachos)

# ----------------- RECEPCIÓN -----------------
@app.route('/recepcion', methods=['GET', 'POST'])
def recepcion():
    if request.method == 'POST':
        tipo = request.form['tipo']
        motivo = request.form.get('motivo', '')
        guias_texto = request.form['guias'].strip().splitlines()
        for g in guias_texto:
            if guias_cargadas.empty or g not in guias_cargadas['numero_guia'].astype(str).values:
                flash(f"Guía {g} FALTANTE - No se registró recepción", "danger")
                continue
            recepciones.append({
                'guia': g,
                'tipo': tipo,
                'motivo': motivo if tipo == "DEVOLUCION" else '',
                'fecha': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
        flash("Recepción registrada", "success")
    return render_template('recepcion.html')

# ----------------- CONSULTAR ESTADO -----------------
@app.route('/consultar', methods=['GET', 'POST'])
def consultar():
    resultados = []
    if request.method == 'POST':
        guias_texto = request.form['guias'].strip().splitlines()
        for g in guias_texto:
            estado = "EN VERIFICACION"
            motivo = ''
            mensajero_asignado = ''
            zona_asignada = ''
            fecha_despacho = ''
            if not guias_cargadas.empty and g not in guias_cargadas['numero_guia'].astype(str).values:
                estado = "FALTANTE"
            else:
                for d in despachos:
                    if g in d['guias']:
                        mensajero_asignado = d['mensajero']
                        zona_asignada = d['zona']
                        fecha_despacho = d['fecha']
                for r in recepciones:
                    if r['guia'] == g:
                        estado = "ENTREGADA" if r['tipo'] == "ENTREGA" else "DEVOLUCION"
                        motivo = r['motivo']
                        break
            resultados.append({
                'guia': g,
                'estado': estado,
                'motivo': motivo,
                'mensajero': mensajero_asignado,
                'zona': zona_asignada,
                'fecha_despacho': fecha_despacho
            })
    return render_template('consultar.html', resultados=resultados)

# ----------------- EXPORTAR CONSULTA -----------------
@app.route('/exportar_consulta', methods=['POST'])
def exportar_consulta():
    datos = request.form['datos']
    df = pd.read_json(datos)
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name="consulta_estado.xlsx")

# ----------------- LIQUIDAR -----------------
@app.route('/liquidar', methods=['GET', 'POST'])
def liquidar():
    resumen = []
    grafico = None
    if request.method == 'POST':
        fecha_inicio = request.form['fecha_inicio']
        fecha_fin = request.form['fecha_fin']
        for d in despachos:
            fecha_d = datetime.strptime(d['fecha'], "%Y-%m-%d %H:%M:%S").date()
            if fecha_inicio <= str(fecha_d) <= fecha_fin:
                tarifa = next((z['tarifa'] for z in zonas if z['nombre'] == d['zona']), 0)
                total = tarifa * len(d['guias'])
                resumen.append({
                    'mensajero': d['mensajero'],
                    'zona': d['zona'],
                    'cantidad': len(d['guias']),
                    'fecha': d['fecha'],
                    'total': total
                })
        if resumen:
            df = pd.DataFrame(resumen)
            plt.figure(figsize=(6, 4))
            df.groupby('mensajero')['total'].sum().plot(kind='bar')
            plt.title("Total por Mensajero")
            plt.ylabel("Valor")
            img = io.BytesIO()
            plt.savefig(img, format='png')
            img.seek(0)
            grafico = base64.b64encode(img.read()).decode('utf-8')
    return render_template('liquidar.html', resumen=resumen, grafico=grafico)

# ----------------- RECOGIDAS -----------------
@app.route('/recogidas', methods=['GET', 'POST'])
def recogidas_view():
    if request.method == 'POST':
        numero = request.form['numero']
        fecha = request.form['fecha']
        observacion = request.form['observacion']
        recogidas.append({'numero': numero, 'fecha': fecha, 'observacion': observacion})
        flash("Recogida registrada", "success")
    return render_template('recogidas.html', recogidas=recogidas)

# ----------------- EDITAR RECOGIDA -----------------
@app.route('/editar_recogida/<int:indice>', methods=['GET', 'POST'])
def editar_recogida(indice):
    if request.method == 'POST':
        recogidas[indice]['numero'] = request.form['numero']
        recogidas[indice]['fecha'] = request.form['fecha']
        recogidas[indice]['observacion'] = request.form['observacion']
        flash("Recogida editada", "success")
        return redirect('/recogidas')
    return render_template('editar_recogida.html', recogida=recogidas[indice])

# ----------------- EJECUTAR -----------------
if __name__ == '__main__':
    app.run(debug=True)
