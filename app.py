from flask import Flask, request, redirect, url_for, render_template_string, send_file
import qrcode
import sqlite3
import uuid
import os
from io import BytesIO
from reportlab.pdfgen import canvas

app = Flask(__name__)

# Crear base de datos si no existe
conn = sqlite3.connect('personas.db')
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS personas
             (id TEXT PRIMARY KEY, nombres TEXT, apellidos TEXT, cedula TEXT, fecha_emision TEXT, cargo TEXT)''')
conn.commit()
conn.close()

# HTML básico
form_html = '''
<!doctype html>
<title>Agregar Persona</title>
<h2>Agregar Persona</h2>
<form method=post>
  Nombres: <input type=text name=nombres required><br><br>
  Apellidos: <input type=text name=apellidos required><br><br>
  Cédula: <input type=text name=cedula required><br><br>
  Fecha de Emisión: <input type=date name=fecha_emision required><br><br>
  Cargo: <input type=text name=cargo required><br><br>
  <input type=submit value=Agregar>
</form>

{% if qr_url %}
  <p><strong>QR generado:</strong></p>
  <img src="{{ qr_url }}">
{% endif %}

<h2>Lista de Personas</h2>
<ul>
{% for persona in personas %}
  <li>{{ persona[1] }} {{ persona[2] }} - <a href="/persona/{{ persona[0] }}">Ver</a> | <a href="/editar/{{ persona[0] }}">Editar</a> | <a href="/eliminar/{{ persona[0] }}">Eliminar</a> | <a href="/pdf/{{ persona[0] }}">PDF</a></li>
{% endfor %}
</ul>
'''

profile_html = '''
<!doctype html>
<title>Perfil de Persona</title>
<h2>Datos de la Persona</h2>
<ul>
  <li><strong>Nombres:</strong> {{ p[1] }}</li>
  <li><strong>Apellidos:</strong> {{ p[2] }}</li>
  <li><strong>Cédula:</strong> {{ p[3] }}</li>
  <li><strong>Fecha de Emisión:</strong> {{ p[4] }}</li>
  <li><strong>Cargo:</strong> {{ p[5] }}</li>
</ul>
<a href="/">Volver</a>
'''

edit_html = '''
<!doctype html>
<title>Editar Persona</title>
<h2>Editar Persona</h2>
<form method=post>
  Nombres: <input type=text name=nombres value="{{ p[1] }}" required><br><br>
  Apellidos: <input type=text name=apellidos value="{{ p[2] }}" required><br><br>
  Cédula: <input type=text name=cedula value="{{ p[3] }}" required><br><br>
  Fecha de Emisión: <input type=date name=fecha_emision value="{{ p[4] }}" required><br><br>
  Cargo: <input type=text name=cargo value="{{ p[5] }}" required><br><br>
  <input type=submit value=Guardar>
</form>
<a href="/">Volver</a>
'''

@app.route('/', methods=['GET', 'POST'])
def agregar_persona():
    qr_url = None
    if request.method == 'POST':
        nombres = request.form['nombres']
        apellidos = request.form['apellidos']
        cedula = request.form['cedula']
        fecha_emision = request.form['fecha_emision']
        cargo = request.form['cargo']

        persona_id = str(uuid.uuid4())

        conn = sqlite3.connect('personas.db')
        c = conn.cursor()
        c.execute("INSERT INTO personas VALUES (?, ?, ?, ?, ?, ?)",
                  (persona_id, nombres, apellidos, cedula, fecha_emision, cargo))
        conn.commit()
        conn.close()

        data_url = url_for('ver_persona', persona_id=persona_id, _external=True)
        qr = qrcode.make(data_url)
        qr_path = f'static/{persona_id}.png'
        os.makedirs('static', exist_ok=True)
        qr.save(qr_path)
        qr_url = '/' + qr_path

    conn = sqlite3.connect('personas.db')
    c = conn.cursor()
    c.execute("SELECT * FROM personas")
    personas = c.fetchall()
    conn.close()

    return render_template_string(form_html, qr_url=qr_url, personas=personas)

@app.route('/persona/<persona_id>')
def ver_persona(persona_id):
    conn = sqlite3.connect('personas.db')
    c = conn.cursor()
    c.execute("SELECT * FROM personas WHERE id=?", (persona_id,))
    p = c.fetchone()
    conn.close()

    if p:
        return render_template_string(profile_html, p=p)
    else:
        return "Persona no encontrada", 404

@app.route('/editar/<persona_id>', methods=['GET', 'POST'])
def editar_persona(persona_id):
    conn = sqlite3.connect('personas.db')
    c = conn.cursor()
    if request.method == 'POST':
        nombres = request.form['nombres']
        apellidos = request.form['apellidos']
        cedula = request.form['cedula']
        fecha_emision = request.form['fecha_emision']
        cargo = request.form['cargo']
        c.execute("UPDATE personas SET nombres=?, apellidos=?, cedula=?, fecha_emision=?, cargo=? WHERE id=?",
                  (nombres, apellidos, cedula, fecha_emision, cargo, persona_id))
        conn.commit()
        conn.close()
        return redirect(url_for('agregar_persona'))
    else:
        c.execute("SELECT * FROM personas WHERE id=?", (persona_id,))
        p = c.fetchone()
        conn.close()
        return render_template_string(edit_html, p=p)

@app.route('/eliminar/<persona_id>')
def eliminar_persona(persona_id):
    conn = sqlite3.connect('personas.db')
    c = conn.cursor()
    c.execute("DELETE FROM personas WHERE id=?", (persona_id,))
    conn.commit()
    conn.close()
    try:
        os.remove(f'static/{persona_id}.png')
    except FileNotFoundError:
        pass
    return redirect(url_for('agregar_persona'))

@app.route('/pdf/<persona_id>')
def generar_pdf(persona_id):
    conn = sqlite3.connect('personas.db')
    c = conn.cursor()
    c.execute("SELECT * FROM personas WHERE id=?", (persona_id,))
    p = c.fetchone()
    conn.close()

    if not p:
        return "Persona no encontrada", 404

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(100, 750, f"Nombre: {p[1]} {p[2]}")
    pdf.drawString(100, 730, f"Cédula: {p[3]}")
    pdf.drawString(100, 710, f"Fecha de Emisión: {p[4]}")
    pdf.drawString(100, 690, f"Cargo: {p[5]}")
    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name=f"{p[1]}_{p[2]}.pdf", mimetype='application/pdf')

if __name__ == '__main__':
    app.run(debug=True)
