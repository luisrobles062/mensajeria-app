from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
import pandas as pd
import os

app = Flask(__name__)
app.secret_key = "clave_secreta"  # Cambia esto por algo seguro

# Configuración de conexión a Neon (PostgreSQL)
app.config['SQLALCHEMY_DATABASE_URI'] = "postgresql://neondb_owner:npg_3owpfIUOAT0a@ep-soft-bush-acv2a8v4-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Modelo de la tabla guias
class Guia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    remitente = db.Column(db.String(255), nullable=False)
    numero_guia = db.Column(db.String(255), nullable=False)
    destinatario = db.Column(db.String(255), nullable=False)
    direccion = db.Column(db.String(255), nullable=False)
    ciudad = db.Column(db.String(255), nullable=False)

# Ruta principal
@app.route("/")
def index():
    return render_template("index.html")

# Ruta para cargar base de guías
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

if __name__ == "__main__":
    # Crear tablas si no existen
    with app.app_context():
        db.create_all()
    app.run(debug=True)
