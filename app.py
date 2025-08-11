from flask import Flask, render_template, request, redirect, send_file
import pandas as pd
import io
import matplotlib.pyplot as plt
import base64
from datetime import datetime
import os

# ----------------- CONFIGURACIÓN APP -----------------
app = Flask(__name__)

# ----------------- VARIABLES EN MEMORIA -----------------
zonas = []
mensajeros = []
guias_cargadas = pd.DataFrame()
despachos = []
recepciones = []
recogidas = []

# ----------------- RUTA PRINCIPAL -----------------
@app.route('/')
def index():
    return render_template('index.html')

# ----------------- REGISTRAR ZONA -----------------
@app.route('/registrar_zona', methods=['GET', 'POST'])
def registrar_zona():
    if request.method == 'POST':
        nombre = request.form['nombre']
        tarifa = float(request.form['tarifa'])
        zonas.append({'nombre': nombre, 'tarifa': tarifa})
        return redirect('/')
    return render_template('registrar_zona.html')

# ----------------- REGISTRAR MENSAJERO -----------------
@app.route('/registrar_mensajero', methods=['GET', 'POST'])
def registrar_mensajero():
    if request.method == 'POST':
        nombre = request.form['nombre']
        zona = request.form['zona']
        mensajeros.append({'nombre': nombre, 'zona': zona})
        return redirect('/')
    return render_template('registrar_mensajero.html', zonas=zonas)

# ----------------- CARGAR BASE DE GUÍAS -----------------
@app.route('/cargar_guias', methods=['GET', 'POST'])
def cargar_guias():
    global guias_cargadas
    if request.method == 'POST':
        file = request.files['archivo']
        df = pd.read_excel(file)
        required_cols = ['remitente', 'numero_guia', 'destinatario', 'direccion', 'ciudad']
        if not all(col in df.columns for col in required_cols):
            return "El archivo no tiene las columnas necesarias."
        guias_cargadas = df
        return redirect('/')
    return render_template('cargar_guias.html')

# ----------------- DESPACHAR MENSAJERO -----------------
@app.route('/despachar', methods=['GET', 'POST'])
def despachar():
    if request.method == 'POST':
        zona = request.form['zona']
        mensajero = request.form['mensajero']
        codigos = request.form['guias'].strip().split("\n")
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for codigo in codigos:
            codigo = codigo.strip()
            if codigo not in guias_cargadas['numero_guia'].astype(str).values:
                continue
            if any(d['numero_guia'] == codigo for d in despachos):
                continue
            despachos.append({
                'numero_guia': codigo,
                'zona': zona,
                'mensajero': mensajero,
                'fecha': fecha
            })

        return redirect('/ver_despacho')
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
        codigos = request.form['guias'].strip().split("\n")
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for codigo in codigos:
            codigo = codigo.strip()
            recepciones.append({
                'numero_guia': codigo,
                'tipo': tipo,
                'motivo': motivo,
                'fecha': fecha
            })
        return redirect('/')
    return render_template('recepcion.html')

# ----------------- CONSULTAR ESTADO -----------------
@app.route('/consultar_estado', methods=['GET', 'POST'])
def consultar_estado():
    resultados = []
    if request.method == 'POST':
        codigos = request.form['guias'].strip().split("\n")
        for codigo in codigos:
            codigo = codigo.strip()
            estado = "EN VERIFICACIÓN"
            motivo = ""
            mensajero = ""
            zona = ""
            fecha_despacho = ""
            gestion = ""

            despacho = next((d for d in despachos if d['numero_guia'] == codigo), None)
            recepcion = next((r for r in recepciones if r['numero_guia'] == codigo), None)

            if codigo not in guias_cargadas['numero_guia'].astype(str).values:
                estado = "FALTANTE"
            elif recepcion:
                estado = recepcion['tipo']
                motivo = recepcion['motivo']
                gestion = recepcion['tipo'] + (f" - {motivo}" if motivo else "")
            elif despacho:
                estado = "DESPACHADA"
                mensajero = despacho['mensajero']
                zona = despacho['zona']
                fecha_despacho = despacho['fecha']

            resultados.append({
                'numero_guia': codigo,
                'estado': estado,
                'motivo': motivo,
                'mensajero': mensajero,
                'zona': zona,
                'fecha_despacho': fecha_despacho,
                'gestion': gestion
            })
        return render_template('consultar_estado.html', resultados=resultados)
    return render_template('consultar_estado.html')

# ----------------- RECOGIDAS -----------------
@app.route('/recogidas', methods=['GET', 'POST'])
def recogidas_view():
    if request.method == 'POST':
        numero_interno = request.form['numero_interno']
        fecha = request.form['fecha']
        observaciones = request.form['observaciones']
        recogidas.append({
            'numero_interno': numero_interno,
            'fecha': fecha,
            'observaciones': observaciones
        })
        return redirect('/recogidas')
    return render_template('recogidas.html', recogidas=recogidas)

# ----------------- INICIO APP -----------------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
