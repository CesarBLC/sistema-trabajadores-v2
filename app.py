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

# Función para inicializar la base de datos
def init_db():
    conn = sqlite3.connect('personas.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS personas
                 (id TEXT PRIMARY KEY, nombres TEXT, apellidos TEXT, cedula TEXT, fecha_emision TEXT, cargo TEXT)''')
    conn.commit()
    conn.close()

# Función helper para conectar a la base de datos
def get_db_connection():
    conn = sqlite3.connect('personas.db')
    conn.row_factory = sqlite3.Row  # Para acceder por nombre de columna
    return conn

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
    
    # Debug: imprimir lo que se está buscando
    print(f"🔍 Buscando cédula: '{cedula}' (longitud: {len(cedula)})")
    
    try:
        conn = get_db_connection()
        
        # Primero, verificar cuántos registros hay en total
        total_registros = conn.execute("SELECT COUNT(*) FROM personas").fetchone()[0]
        print(f"📊 Total de registros en BD: {total_registros}")
        
        # Búsqueda exacta
        persona = conn.execute("SELECT * FROM personas WHERE cedula = ?", (cedula,)).fetchone()
        
        if not persona:
            # Búsqueda alternativa quitando espacios de ambos lados
            print("❌ No encontrado con búsqueda exacta, probando búsqueda con TRIM...")
            persona = conn.execute("SELECT * FROM personas WHERE TRIM(cedula) = ?", (cedula,)).fetchone()
            
            if not persona:
                # Mostrar todas las cédulas para debug
                print("🔍 Mostrando todas las cédulas en la BD para debug:")
                todas_cedulas = conn.execute("SELECT cedula FROM personas").fetchall()
                for i, (c,) in enumerate(todas_cedulas, 1):
                    print(f"  {i}. '{c}' (longitud: {len(c)})")
        
        conn.close()
        
        if persona:
            print("✅ Trabajador encontrado!")
            # Convertir Row a dict para el template
            persona_dict = {
                'id': persona[0],
                'nombres': persona[1], 
                'apellidos': persona[2],
                'cedula': persona[3],
                'fecha_emision': persona[4],
                'cargo': persona[5]
            }
            return render_template('perfil_trabajador.html', persona=persona_dict)
        else:
            print("❌ Trabajador no encontrado después de todas las búsquedas")
            flash('No se encontró ningún trabajador con esa cédula', 'error')
            return redirect(url_for('inicio'))
            
    except sqlite3.Error as e:
        print(f"❌ Error de base de datos: {e}")
        flash('Error al consultar la base de datos', 'error')
        return redirect(url_for('inicio'))
    except Exception as e:
        print(f"❌ Error general: {e}")
        flash('Error interno del servidor', 'error')
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
    conn = get_db_connection()
    personas = conn.execute("SELECT * FROM personas ORDER BY apellidos, nombres").fetchall()
    conn.close()
    return render_template('admin_dashboard.html', personas=personas)

@app.route('/admin/agregar', methods=['GET', 'POST'])
@login_required
def agregar_persona():
    qr_url = None
    if request.method == 'POST':
        nombres = request.form['nombres'].strip()
        apellidos = request.form['apellidos'].strip()
        cedula = request.form['cedula'].strip()  # Esto ya está bien
        fecha_emision = request.form['fecha_emision'].strip()
        cargo = request.form['cargo'].strip()

        # Validar campos vacíos
        if not all([nombres, apellidos, cedula, fecha_emision, cargo]):
            flash('Todos los campos son obligatorios', 'error')
            return render_template('agregar_persona.html')

        # Validar que la cédula solo contenga números
        if not cedula.isdigit():
            flash('La cédula debe contener solo números', 'error')
            return render_template('agregar_persona.html')

        # Debug: mostrar lo que se va a guardar
        print(f"💾 Guardando cédula: '{cedula}' (longitud: {len(cedula)})")

        # Verificar si ya existe la cédula
        conn = get_db_connection()
        existing = conn.execute("SELECT id FROM personas WHERE cedula = ?", (cedula,)).fetchone()
        
        if existing:
            flash('Ya existe un trabajador con esa cédula', 'error')
            conn.close()
            return render_template('agregar_persona.html')

        # Generar ID único
        persona_id = str(uuid.uuid4())

        try:
            # Insertar en la base de datos
            conn.execute("INSERT INTO personas (id, nombres, apellidos, cedula, fecha_emision, cargo) VALUES (?, ?, ?, ?, ?, ?)",
                        (persona_id, nombres, apellidos, cedula, fecha_emision, cargo))
            conn.commit()
            
            # Verificar que se guardó correctamente
            verificacion = conn.execute("SELECT * FROM personas WHERE id = ?", (persona_id,)).fetchone()
            
            if verificacion:
                print(f"✅ Trabajador guardado exitosamente con cédula: '{verificacion[3]}'")
                
                # Generar QR que apunte al perfil público
                qr_data = url_for('ver_perfil_publico', cedula=cedula, _external=True)
                qr = qrcode.QRCode(version=1, box_size=10, border=5)
                qr.add_data(qr_data)
                qr.make(fit=True)
                
                # Crear directorio static si no existe
                os.makedirs('static', exist_ok=True)
                
                # Generar imagen QR
                qr_img = qr.make_image(fill_color="black", back_color="white")
                qr_path = f'static/{persona_id}.png'
                qr_img.save(qr_path)
                qr_url = '/' + qr_path
                
                flash('Trabajador agregado exitosamente', 'success')
                conn.close()
                return render_template('agregar_persona.html', qr_url=qr_url, persona_id=persona_id)
            else:
                flash('Error al guardar el trabajador. Intente nuevamente.', 'error')
                conn.close()
                return render_template('agregar_persona.html')
                
        except sqlite3.Error as e:
            print(f"❌ Error al insertar en BD: {e}")
            flash(f'Error en la base de datos: {str(e)}', 'error')
            conn.rollback()
            conn.close()
            return render_template('agregar_persona.html')

    return render_template('agregar_persona.html')

@app.route('/admin/editar/<persona_id>', methods=['GET', 'POST'])
@login_required
def editar_persona(persona_id):
    conn = get_db_connection()
    
    if request.method == 'POST':
        nombres = request.form['nombres'].strip()
        apellidos = request.form['apellidos'].strip()
        cedula = request.form['cedula'].strip()
        fecha_emision = request.form['fecha_emision'].strip()
        cargo = request.form['cargo'].strip()
        
        try:
            conn.execute("UPDATE personas SET nombres=?, apellidos=?, cedula=?, fecha_emision=?, cargo=? WHERE id=?",
                        (nombres, apellidos, cedula, fecha_emision, cargo, persona_id))
            conn.commit()
            conn.close()
            flash('Datos actualizados correctamente', 'success')
            return redirect(url_for('admin_dashboard'))
        except sqlite3.Error as e:
            flash(f'Error al actualizar: {str(e)}', 'error')
            conn.close()
            return redirect(url_for('admin_dashboard'))
    else:
        persona = conn.execute("SELECT * FROM personas WHERE id = ?", (persona_id,)).fetchone()
        conn.close()
        if persona:
            return render_template('editar_persona.html', p=persona)
        else:
            flash('Trabajador no encontrado', 'error')
            return redirect(url_for('admin_dashboard'))

@app.route('/admin/eliminar/<persona_id>')
@login_required
def eliminar_persona(persona_id):
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM personas WHERE id = ?", (persona_id,))
        conn.commit()
        conn.close()
        
        # Eliminar archivo QR
        try:
            os.remove(f'static/{persona_id}.png')
        except FileNotFoundError:
            pass
        
        flash('Trabajador eliminado correctamente', 'success')
    except sqlite3.Error as e:
        flash(f'Error al eliminar: {str(e)}', 'error')
        conn.close()
    
    return redirect(url_for('admin_dashboard'))

# NUEVA RUTA: Ver perfil desde el panel admin
@app.route('/admin/ver_perfil/<persona_id>')
@login_required
def admin_ver_perfil(persona_id):
    conn = get_db_connection()
    persona = conn.execute("SELECT * FROM personas WHERE id = ?", (persona_id,)).fetchone()
    conn.close()
    
    if persona:
        # CORREGIDO: Convertir Row a dict para el template
        persona_dict = {
            'id': persona[0],
            'nombres': persona[1], 
            'apellidos': persona[2],
            'cedula': persona[3],
            'fecha_emision': persona[4],
            'cargo': persona[5]
        }
        return render_template('perfil_trabajador.html', persona=persona_dict)
    else:
        flash('Trabajador no encontrado', 'error')
        return redirect(url_for('admin_dashboard'))

# RUTAS PARA QR (CORREGIDAS)
@app.route('/perfil/<cedula>')
def ver_perfil_publico(cedula):
    """Ruta pública para ver perfil mediante QR"""
    conn = get_db_connection()
    persona = conn.execute("SELECT * FROM personas WHERE cedula = ?", (cedula,)).fetchone()
    conn.close()
    
    if persona:
        # CORREGIDO: Convertir Row a dict para el template
        persona_dict = {
            'id': persona[0],
            'nombres': persona[1], 
            'apellidos': persona[2],
            'cedula': persona[3],
            'fecha_emision': persona[4],
            'cargo': persona[5]
        }
        return render_template('perfil_trabajador.html', persona=persona_dict)
    else:
        return render_template('error.html', mensaje="Trabajador no encontrado"), 404

@app.route('/persona/<persona_id>')
def ver_persona(persona_id):
    """Ruta legacy - redirige a perfil por cédula"""
    conn = get_db_connection()
    persona = conn.execute("SELECT cedula FROM personas WHERE id = ?", (persona_id,)).fetchone()
    conn.close()
    
    if persona:
        return redirect(url_for('ver_perfil_publico', cedula=persona['cedula']))
    else:
        return render_template('error.html', mensaje="Trabajador no encontrado"), 404

@app.route('/pdf/<persona_id>')
@login_required
def generar_pdf(persona_id):
    conn = get_db_connection()
    persona = conn.execute("SELECT * FROM personas WHERE id = ?", (persona_id,)).fetchone()
    conn.close()

    if not persona:
        return "Persona no encontrada", 404

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(100, 750, f"Nombre: {persona['nombres']} {persona['apellidos']}")
    pdf.drawString(100, 730, f"Cédula: {persona['cedula']}")
    pdf.drawString(100, 710, f"Fecha de Emisión: {persona['fecha_emision']}")
    pdf.drawString(100, 690, f"Cargo: {persona['cargo']}")
    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name=f"{persona['nombres']}_{persona['apellidos']}.pdf", mimetype='application/pdf')

if __name__ == '__main__':
    # Inicializar la base de datos al arrancar
    init_db()
    app.run(debug=True)