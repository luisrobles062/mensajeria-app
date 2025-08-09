from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/cargar_base")
def cargar_base():
    return "<h2>📁 Cargar Base de Guías - Pendiente de implementar</h2>"

@app.route("/registrar_zona")
def registrar_zona():
    return "<h2>📍 Registrar Zona - Pendiente de implementar</h2>"

@app.route("/registrar_mensajero")
def registrar_mensajero():
    return "<h2>🚴 Registrar Mensajero - Pendiente de implementar</h2>"

@app.route("/despachar_guias")
def despachar_guias():
    return "<h2>📦 Despachar Guías - Pendiente de implementar</h2>"

@app.route("/registrar_recepcion")
def registrar_recepcion():
    return "<h2>✅ Registrar Recepción - Pendiente de implementar</h2>"

@app.route("/consultar_estado")
def consultar_estado():
    return "<h2>🔍 Consultar Estado de Guía - Pendiente de implementar</h2>"

@app.route("/liquidacion")
def liquidacion():
    return "<h2>💰 Liquidación Mensajero - Pendiente de implementar</h2>"

@app.route("/registrar_recogida")
def registrar_recogida():
    return "<h2>📅 Registrar Recogida - Pendiente de implementar</h2>"

@app.route("/ver_recogidas")
def ver_recogidas():
    return "<h2>📋 Ver Recogidas - Pendiente de implementar</h2>"

if __name__ == "__main__":
    app.run(debug=True)
