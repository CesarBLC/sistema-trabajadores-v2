from flask import Flask, request, redirect, url_for, render_template, send_file, session, flash
import qrcode
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool
import uuid
import os
from io import BytesIO
from reportlab.pdfgen import canvas
from functools import wraps

app = Flask(__name__)
app.secret_key = '10000'  # Cambia esto por una clave segura

# Credenciales de administrador (cámbialas por las tuyas)
ADMIN_USER = "admin"
ADMIN_PASS = "admin123"

# Configuración de base de datos
DATABASE_URL = os.environ.get('DATABASE_URL')

# Pool de conexiones para PostgreSQL (mejor rendimiento)
connection_pool = None

def init_connection_pool():
    global connection_pool
    if DATABASE_URL and not connection_pool:
        try:
            connection_pool = psycopg2.pool.SimpleConnectionPool(
                1, 20,  # min y max conexiones
                DATABASE_URL
            )
            print("✅ Pool de conexiones PostgreSQL creado")
        except Exception as e:
            print(f"❌ Error creando pool de conexiones: {e}")
            # Si falla el pool, seguir sin él
            connection_pool = None


def get_db_connection():
    if DATABASE_URL:
        # Producción - PostgreSQL
        if connection_pool:
            conn = connection_pool.getconn()
            # IMPORTANTE: Configurar cursor factory en la conexión
            conn.cursor_factory = RealDictCursor
            return conn
        else:
            return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    else:
        # Desarrollo local - SQLite
        conn = sqlite3.connect('personas.db')
        conn.row_factory = sqlite3.Row
        return conn

def return_db_connection(conn):
    """Devuelve la conexión al pool (solo para PostgreSQL)"""
    if DATABASE_URL and connection_pool:
        connection_pool.putconn(conn)
    else:
        conn.close()

def crear_tabla_si_no_existe():
    """Crear tabla personas directamente - SIMPLIFICADO"""
    if not DATABASE_URL:
        return  # Solo para PostgreSQL
        
    print("🔧 CREANDO TABLA PERSONAS...")
    try:
        # Conexión directa a PostgreSQL
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Crear tabla
        create_sql = """
        CREATE TABLE IF NOT EXISTS personas (
            id VARCHAR(36) PRIMARY KEY,
            nombres VARCHAR(100) NOT NULL,
            apellidos VARCHAR(100) NOT NULL,
            cedula VARCHAR(20) NOT NULL UNIQUE,
            fecha_emision DATE NOT NULL,
            cargo VARCHAR(100) NOT NULL
        )
        """
        
        cursor.execute(create_sql)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_personas_cedula ON personas(cedula)")
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print("✅ Tabla 'personas' creada exitosamente")
        
    except Exception as e:
        print(f"❌ ERROR CREANDO TABLA: {e}")
        raise

# EJECUTAR INMEDIATAMENTE al importar
if DATABASE_URL:
    crear_tabla_si_no_existe()

# Función helper para conectar a la base de datos
def execute_query(query, params=None, fetch=False):
    """
    Ejecuta una query de forma segura
    fetch: True para SELECT, False para INSERT/UPDATE/DELETE
    """
    conn = get_db_connection()
    
    try:
        cursor = conn.cursor()
        
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        if fetch:
            result = cursor.fetchall()
            cursor.close()
            return result
        else:
            conn.commit()
            affected_rows = cursor.rowcount
            cursor.close()
            return affected_rows
            
    except Exception as e:
        print(f"❌ Error ejecutando query: {e}")
        if not fetch:
            conn.rollback()
        raise
    finally:
        if DATABASE_URL:
            return_db_connection(conn)
        else:
            conn.close()

def execute_query_one(query, params=None):
    """Ejecuta una query y devuelve solo un resultado"""
    conn = get_db_connection()
    cursor = None
    
    try:
        # Para PostgreSQL usar RealDictCursor
        if DATABASE_URL:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cursor = conn.cursor()
        
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        result = cursor.fetchone()
        return result
        
    except Exception as e:
        print(f"❌ Error ejecutando query: {e}")
        print(f"❌ Query: {query}")
        print(f"❌ Params: {params}")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            if DATABASE_URL and connection_pool:
                return_db_connection(conn)
            else:
                conn.close()

# FUNCIÓN PARA DEPURAR - Agregar temporalmente
def debug_database():
    """Función para verificar qué hay en la base de datos"""
    try:
        # Contar registros
        count = execute_query_one("SELECT COUNT(*) as total FROM personas")
        print(f"🔢 Total registros en DB: {count}")
        
        # Mostrar todos los registros
        personas = execute_query("SELECT * FROM personas", fetch=True)
        print(f"📋 Registros encontrados: {len(personas)}")
        
        for i, persona in enumerate(personas):
            print(f"  {i+1}. {dict(persona) if DATABASE_URL else dict(persona)}")
            
    except Exception as e:
        print(f"❌ Error en debug: {e}")

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
    
    print(f"🔍 Buscando cédula: '{cedula}'")
    
    # DEBUG: Verificar qué hay en la base de datos
    debug_database()
    
    try:
        persona = execute_query_one(
            "SELECT * FROM personas WHERE cedula = %s" if DATABASE_URL else "SELECT * FROM personas WHERE cedula = ?",
            (cedula,)
        )
        
        print(f"🔍 Resultado de búsqueda: {persona}")
        
        if persona:
            print("✅ Trabajador encontrado!")
            # Con RealDictCursor, persona ya es un dict-like object
            persona_dict = dict(persona)
            print(f"📋 Datos del trabajador: {persona_dict}")
            return render_template('perfil_trabajador.html', persona=persona_dict)
        else:
            print("❌ Trabajador no encontrado")
            flash('No se encontró ningún trabajador con esa cédula', 'error')
            return redirect(url_for('inicio'))
            
    except Exception as e:
        print(f"❌ Error: {e}")
        flash('Error al consultar la base de datos', 'error')
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
    try:
        personas = execute_query(
            "SELECT * FROM personas ORDER BY apellidos, nombres",
            fetch=True
        )
        return render_template('admin_dashboard.html', personas=personas)
    except Exception as e:
        print(f"❌ Error cargando dashboard: {e}")
        flash('Error cargando los datos', 'error')
        return render_template('admin_dashboard.html', personas=[])

@app.route('/admin/agregar', methods=['GET', 'POST'])
@login_required
def agregar_persona():
    qr_url = None
    if request.method == 'POST':
        nombres = request.form['nombres'].strip()
        apellidos = request.form['apellidos'].strip()
        cedula = request.form['cedula'].strip()
        fecha_emision = request.form['fecha_emision'].strip()
        cargo = request.form['cargo'].strip()

        # Validar campos vacíos
        if not all([nombres, apellidos, cedula, fecha_emision, cargo]):
            flash('Todos los campos son obligatorios', 'error')
            return render_template('agregar_persona.html')

        print(f"💾 Guardando cédula: '{cedula}'")

        try:
            # Verificar si ya existe la cédula
            existing = execute_query_one(
                "SELECT id FROM personas WHERE cedula = %s" if DATABASE_URL else "SELECT id FROM personas WHERE cedula = ?",
                (cedula,)
            )
            
            if existing:
                flash('Ya existe un trabajador con esa cédula', 'error')
                return render_template('agregar_persona.html')

            # Generar ID único
            persona_id = str(uuid.uuid4())

            # Insertar en la base de datos
            affected = execute_query(
                """INSERT INTO personas (id, nombres, apellidos, cedula, fecha_emision, cargo) 
                   VALUES (%s, %s, %s, %s, %s, %s)""" if DATABASE_URL else 
                """INSERT INTO personas (id, nombres, apellidos, cedula, fecha_emision, cargo) 
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (persona_id, nombres, apellidos, cedula, fecha_emision, cargo)
            )
            
            if affected > 0:
                print(f"✅ Trabajador guardado exitosamente")
                
                # Generar QR
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
                return render_template('agregar_persona.html', qr_url=qr_url, persona_id=persona_id)
            else:
                flash('Error al guardar el trabajador. Intente nuevamente.', 'error')
                return render_template('agregar_persona.html')
                
        except Exception as e:
            print(f"❌ Error al insertar: {e}")
            flash(f'Error en la base de datos: {str(e)}', 'error')
            return render_template('agregar_persona.html')

    return render_template('agregar_persona.html')


@app.route('/admin/editar/<persona_id>', methods=['GET', 'POST'])
@login_required
def editar_persona(persona_id):
    if request.method == 'POST':
        nombres = request.form['nombres'].strip()
        apellidos = request.form['apellidos'].strip()
        cedula = request.form['cedula'].strip()
        fecha_emision = request.form['fecha_emision'].strip()
        cargo = request.form['cargo'].strip()
        
        try:
            affected = execute_query(
                """UPDATE personas SET nombres=%s, apellidos=%s, cedula=%s, fecha_emision=%s, cargo=%s 
                   WHERE id=%s""" if DATABASE_URL else
                """UPDATE personas SET nombres=?, apellidos=?, cedula=?, fecha_emision=?, cargo=? 
                   WHERE id=?""",
                (nombres, apellidos, cedula, fecha_emision, cargo, persona_id)
            )
            
            if affected > 0:
                flash('Datos actualizados correctamente', 'success')
            else:
                flash('No se encontró el trabajador para actualizar', 'error')
            
            return redirect(url_for('admin_dashboard'))
            
        except Exception as e:
            flash(f'Error al actualizar: {str(e)}', 'error')
            return redirect(url_for('admin_dashboard'))
    else:
        try:
            persona = execute_query_one(
                "SELECT * FROM personas WHERE id = %s" if DATABASE_URL else "SELECT * FROM personas WHERE id = ?",
                (persona_id,)
            )
            
            if persona:
                return render_template('editar_persona.html', p=persona)
            else:
                flash('Trabajador no encontrado', 'error')
                return redirect(url_for('admin_dashboard'))
                
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
            return redirect(url_for('admin_dashboard'))


@app.route('/admin/eliminar/<persona_id>')
@login_required
def eliminar_persona(persona_id):
    try:
        affected = execute_query(
            "DELETE FROM personas WHERE id = %s" if DATABASE_URL else "DELETE FROM personas WHERE id = ?",
            (persona_id,)
        )
        
        if affected > 0:
            # Eliminar archivo QR
            try:
                os.remove(f'static/{persona_id}.png')
            except FileNotFoundError:
                pass
            
            flash('Trabajador eliminado correctamente', 'success')
        else:
            flash('No se encontró el trabajador para eliminar', 'error')
            
    except Exception as e:
        flash(f'Error al eliminar: {str(e)}', 'error')
    
    return redirect(url_for('admin_dashboard'))

# RUTAS CORREGIDAS para PostgreSQL
@app.route('/admin/ver_perfil/<persona_id>')
@login_required
def admin_ver_perfil(persona_id):
    try:
        persona = execute_query_one(
            "SELECT * FROM personas WHERE id = %s" if DATABASE_URL else "SELECT * FROM personas WHERE id = ?",
            (persona_id,)
        )
        
        if persona:
            # Convertir a dict - CORREGIDO para PostgreSQL
            if DATABASE_URL:
                persona_dict = dict(persona)
            else:
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
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('admin_dashboard'))

# RUTAS PARA QR (CORREGIDAS)
@app.route('/perfil/<cedula>')
def ver_perfil_publico(cedula):
    """Ruta pública para ver perfil mediante QR"""
    try:
        persona = execute_query_one(
            "SELECT * FROM personas WHERE cedula = %s" if DATABASE_URL else "SELECT * FROM personas WHERE cedula = ?",
            (cedula,)
        )
        
        if persona:
            # Convertir a dict - CORREGIDO para PostgreSQL
            if DATABASE_URL:
                persona_dict = dict(persona)
            else:
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
    except Exception as e:
        return render_template('error.html', mensaje=f"Error: {str(e)}"), 500

@app.route('/persona/<persona_id>')
def ver_persona(persona_id):
    """Ruta legacy - redirige a perfil por cédula"""
    try:
        persona = execute_query_one(
            "SELECT cedula FROM personas WHERE id = %s" if DATABASE_URL else "SELECT cedula FROM personas WHERE id = ?",
            (persona_id,)
        )
        
        if persona:
            if DATABASE_URL:
                cedula = persona['cedula']
            else:
                cedula = persona[0]
            return redirect(url_for('ver_perfil_publico', cedula=cedula))
        else:
            return render_template('error.html', mensaje="Trabajador no encontrado"), 404
    except Exception as e:
        return render_template('error.html', mensaje=f"Error: {str(e)}"), 500

@app.route('/pdf/<persona_id>')
@login_required
def generar_pdf(persona_id):
    try:
        persona = execute_query_one(
            "SELECT * FROM personas WHERE id = %s" if DATABASE_URL else "SELECT * FROM personas WHERE id = ?",
            (persona_id,)
        )

        if not persona:
            return "Persona no encontrada", 404

        # Convertir a dict si es necesario
        if DATABASE_URL:
            p = dict(persona)
        else:
            p = {
                'nombres': persona[1],
                'apellidos': persona[2],
                'cedula': persona[3],
                'fecha_emision': persona[4],
                'cargo': persona[5]
            }

        buffer = BytesIO()
        pdf = canvas.Canvas(buffer)
        pdf.drawString(100, 750, f"Nombre: {p['nombres']} {p['apellidos']}")
        pdf.drawString(100, 730, f"Cédula: {p['cedula']}")
        pdf.drawString(100, 710, f"Fecha de Emisión: {p['fecha_emision']}")
        pdf.drawString(100, 690, f"Cargo: {p['cargo']}")
        pdf.showPage()
        pdf.save()
        buffer.seek(0)

        return send_file(buffer, as_attachment=True, download_name=f"{p['nombres']}_{p['apellidos']}.pdf", mimetype='application/pdf')
    except Exception as e:
        return f"Error generando PDF: {str(e)}", 500

if __name__ == '__main__':
    # Inicializar pool de conexiones
    if DATABASE_URL:
        init_connection_pool()
        
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)