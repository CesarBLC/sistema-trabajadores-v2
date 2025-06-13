from flask import Flask, request, redirect, url_for, render_template, send_file, session, flash
import qrcode
import sqlite3
import uuid
import os
from io import BytesIO
from reportlab.pdfgen import canvas
from functools import wraps

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_aqui'  # Cambia esto por una clave segura

# Credenciales de administrador (cámbialas por las tuyas)
ADMIN_USER = "admin"
ADMIN_PASS = "admin123"

# Crear base de datos si no existe
conn = sqlite3.connect('personas.db')
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS personas
             (id TEXT PRIMARY KEY, nombres TEXT, apellidos TEXT, cedula TEXT, fecha_emision TEXT, cargo TEXT)''')
conn.commit()
conn.close()

# Decorator para rutas protegidas
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('Debes iniciar sesión para acceder al panel administrativo', 'error')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# RUTAS PÚBLICAS
@app.route('/')
def inicio():
    return render_template('inicio.html')

@app.route('/consultar', methods=['POST'])
def consultar_trabajador():
    cedula = request.form['cedula'].strip()
    
    conn = sqlite3.connect('personas.db')
    c = conn.cursor()
    c.execute("SELECT * FROM personas WHERE cedula=?", (cedula,))
    persona = c.fetchone()
    conn.close()
    
    if persona:
        return render_template('perfil_trabajador.html', persona=persona)
    else:
        flash('No se encontró ningún trabajador con esa cédula', 'error')
        return redirect(url_for('inicio'))

# RUTAS DE AUTENTICACIÓN
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username == ADMIN_USER and password == ADMIN_PASS:
            session['logged_in'] = True
            flash('Bienvenido al panel administrativo', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Usuario o contraseña incorrectos', 'error')
    
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('logged_in', None)
    flash('Has cerrado sesión correctamente', 'success')
    return redirect(url_for('inicio'))

# RUTAS ADMINISTRATIVAS (PROTEGIDAS)
@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    conn = sqlite3.connect('personas.db')
    c = conn.cursor()
    c.execute("SELECT * FROM personas")
    personas = c.fetchall()
    conn.close()
    return render_template('admin_dashboard.html', personas=personas)

@app.route('/admin/agregar', methods=['GET', 'POST'])
@login_required
def agregar_persona():
    qr_url = None
    if request.method == 'POST':
        nombres = request.form['nombres']
        apellidos = request.form['apellidos']
        cedula = request.form['cedula']
        fecha_emision = request.form['fecha_emision']
        cargo = request.form['cargo']

        # Verificar si ya existe la cédula
        conn = sqlite3.connect('personas.db')
        c = conn.cursor()
        c.execute("SELECT * FROM personas WHERE cedula=?", (cedula,))
        if c.fetchone():
            flash('Ya existe un trabajador con esa cédula', 'error')
            conn.close()
            return render_template('agregar_persona.html')

        persona_id = str(uuid.uuid4())

        c.execute("INSERT INTO personas VALUES (?, ?, ?, ?, ?, ?)",
                  (persona_id, nombres, apellidos, cedula, fecha_emision, cargo))
        conn.commit()
        conn.close()

        # Generar QR
        data_url = url_for('ver_persona', persona_id=persona_id, _external=True)
        qr = qrcode.make(data_url)
        qr_path = f'static/{persona_id}.png'
        os.makedirs('static', exist_ok=True)
        qr.save(qr_path)
        qr_url = '/' + qr_path
        
        flash('Trabajador agregado exitosamente', 'success')
        return render_template('agregar_persona.html', qr_url=qr_url, persona_id=persona_id)

    return render_template('agregar_persona.html')

@app.route('/admin/editar/<persona_id>', methods=['GET', 'POST'])
@login_required
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
        flash('Datos actualizados correctamente', 'success')
        return redirect(url_for('admin_dashboard'))
    else:
        c.execute("SELECT * FROM personas WHERE id=?", (persona_id,))
        p = c.fetchone()
        conn.close()
        if p:
            return render_template('editar_persona.html', p=p)
        else:
            flash('Trabajador no encontrado', 'error')
            return redirect(url_for('admin_dashboard'))

@app.route('/admin/eliminar/<persona_id>')
@login_required
def eliminar_persona(persona_id):
    conn = sqlite3.connect('personas.db')
    c = conn.cursor()
    c.execute("DELETE FROM personas WHERE id=?", (persona_id,))
    conn.commit()
    conn.close()
    
    # Eliminar archivo QR
    try:
        os.remove(f'static/{persona_id}.png')
    except FileNotFoundError:
        pass
    
    flash('Trabajador eliminado correctamente', 'success')
    return redirect(url_for('admin_dashboard'))

# RUTAS PARA QR Y PDF (mantienen la funcionalidad original)
@app.route('/persona/<persona_id>')
def ver_persona(persona_id):
    conn = sqlite3.connect('personas.db')
    c = conn.cursor()
    c.execute("SELECT * FROM personas WHERE id=?", (persona_id,))
    p = c.fetchone()
    conn.close()

    if p:
        return render_template('profile.html', p=p)
    else:
        return "Persona no encontrada", 404

@app.route('/pdf/<persona_id>')
@login_required
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