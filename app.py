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
from werkzeug.utils import secure_filename
import cloudinary
import cloudinary.uploader
import cloudinary.api
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from datetime import datetime
import logging
import socket

# Configuración de logging
logging.basicConfig(level=logging.INFO)

# Configurar timeout para evitar conexiones colgadas
socket.setdefaulttimeout(30)

app = Flask(__name__)
app.secret_key = '10000'

# Configuraciones
ADMIN_USER = "admin"
ADMIN_PASS = "admin123"
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
UNIDADES = ['Construcción', 'Cemento']
DATABASE_URL = os.environ.get('DATABASE_URL')

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Configuración Cloudinary
cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key=os.environ.get('CLOUDINARY_API_KEY'),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET')
)

# Pool de conexiones
connection_pool = None

def init_connection_pool():
    global connection_pool
    if DATABASE_URL and not connection_pool:
        try:
            # Configuración optimizada para Supabase
            connection_pool = psycopg2.pool.SimpleConnectionPool(
                1, 10,  # Reducir conexiones para Supabase
                DATABASE_URL,
                # Parámetros adicionales para Supabase
                connect_timeout=10,
                application_name='flask_trabajadores'
            )
            print("✅ Pool de conexiones Supabase inicializado correctamente")
        except Exception as e:
            print(f"❌ Error inicializando pool: {e}")
            connection_pool = None

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def upload_to_cloudinary(file, cedula):
    try:
        public_id = f"trabajadores/{cedula}_{uuid.uuid4().hex[:8]}"
        upload_result = cloudinary.uploader.upload(
            file,
            public_id=public_id,
            folder="trabajadores",
            transformation=[
                {'width': 400, 'height': 400, 'crop': 'fill', 'gravity': 'face'},
                {'quality': 'auto', 'fetch_format': 'auto'}
            ],
            overwrite=True,
            invalidate=True
        )
        return upload_result['secure_url']
    except Exception as e:
        return None

def delete_from_cloudinary(foto_url):
    try:
        if foto_url and 'cloudinary.com' in foto_url:
            parts = foto_url.split('/')
            if 'trabajadores' in parts:
                public_id_with_ext = parts[parts.index('trabajadores') + 1]
                public_id = public_id_with_ext.split('.')[0]
                full_public_id = f"trabajadores/{public_id}"
                result = cloudinary.uploader.destroy(full_public_id)
                return result
    except Exception as e:
        pass
    return None

def get_db_connection():
    if DATABASE_URL:
        try:
            if connection_pool:
                conn = connection_pool.getconn()
                conn.cursor_factory = RealDictCursor
                return conn
            else:
                return psycopg2.connect(
                    DATABASE_URL, 
                    cursor_factory=RealDictCursor,
                    connect_timeout=10
                )
        except psycopg2.OperationalError as e:
            print(f"Error de conexión a Supabase: {e}")
            # Intentar reconectar
            if connection_pool:
                init_connection_pool()
                if connection_pool:
                    conn = connection_pool.getconn()
                    conn.cursor_factory = RealDictCursor
                    return conn
            raise
    else:
        conn = sqlite3.connect('personas.db')
        conn.row_factory = sqlite3.Row
        return conn

def return_db_connection(conn):
    if DATABASE_URL and connection_pool:
        connection_pool.putconn(conn)
    else:
        conn.close()

def crear_tabla_si_no_existe():
    if not DATABASE_URL:
        return
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        create_sql = """
        CREATE TABLE IF NOT EXISTS personas (
            id VARCHAR(36) PRIMARY KEY,
            nombres VARCHAR(100) NOT NULL,
            apellidos VARCHAR(100) NOT NULL,
            cedula VARCHAR(20) NOT NULL UNIQUE,
            fecha_emision DATE NOT NULL,
            cargo VARCHAR(100) NOT NULL,
            foto TEXT,
            sindicato VARCHAR(100),
            telefono VARCHAR(15),
            region VARCHAR(100),
            oficio VARCHAR(100)
        )
        """
        
        cursor.execute(create_sql)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_personas_cedula ON personas(cedula)")
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        raise

def actualizar_base_datos():
    if not DATABASE_URL:
        return
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'personas' AND column_name IN ('foto', 'sindicato', 'telefono', 'region', 'oficio')
        """)
        
        existing_columns = [row[0] for row in cursor.fetchall()]
        
        if 'foto' not in existing_columns:
            cursor.execute("ALTER TABLE personas ADD COLUMN foto TEXT;")
            
        if 'sindicato' not in existing_columns:
            cursor.execute("ALTER TABLE personas ADD COLUMN sindicato VARCHAR(100);")
            
        if 'telefono' not in existing_columns:
            cursor.execute("ALTER TABLE personas ADD COLUMN telefono VARCHAR(15);")
            
        if 'region' not in existing_columns:
            cursor.execute("ALTER TABLE personas ADD COLUMN region VARCHAR(100);")
            
        if 'oficio' not in existing_columns:
            cursor.execute("ALTER TABLE personas ADD COLUMN oficio VARCHAR(100);")
        
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        pass

# Inicialización
if DATABASE_URL:
    crear_tabla_si_no_existe()
    actualizar_base_datos()

def execute_query(query, params=None, fetch=False):
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
        if not fetch:
            conn.rollback()
        raise
    finally:
        if DATABASE_URL:
            return_db_connection(conn)
        else:
            conn.close()

def execute_query_one(query, params=None):
    conn = get_db_connection()
    cursor = None
    try:
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
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            if DATABASE_URL and connection_pool:
                return_db_connection(conn)
            else:
                conn.close()

def buscar_trabajadores(termino_busqueda):
    try:
        termino = termino_busqueda.strip()
        if not termino:
            return []
        
        if DATABASE_URL:
            query = "SELECT * FROM personas WHERE LOWER(nombres) LIKE LOWER(%s) OR cedula LIKE %s ORDER BY nombres"
            params = (f'%{termino}%', f'%{termino}%')
        else:
            query = "SELECT * FROM personas WHERE LOWER(nombres) LIKE LOWER(?) OR cedula LIKE ? ORDER BY nombres"
            params = (f'%{termino}%', f'%{termino}%')
        
        resultados = execute_query(query, params, fetch=True)
        return resultados
    except Exception as e:
        return []

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('Debes iniciar sesión para acceder al panel administrativo', 'error')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# HEALTH CHECK
@app.route('/health')
def health_check():
    try:
        # Verificar conexión a Supabase
        test_query = execute_query_one("SELECT 1 as test")
        if test_query:
            return {"status": "healthy", "database": "connected"}, 200
        else:
            return {"status": "unhealthy", "database": "error"}, 500
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}, 500

# RUTAS
@app.route('/')
def inicio():
    return render_template('inicio.html')

@app.route('/consultar', methods=['POST'])
def consultar_trabajador():
    cedula = request.form['cedula'].strip()
    numeros_cedula = ''.join(filter(str.isdigit, cedula))
    
    try:
        # Buscar por cédula exacta o solo números
        persona = execute_query_one(
            "SELECT * FROM personas WHERE cedula = %s OR cedula = %s",
            (cedula, numeros_cedula)
        )

        if persona:
            persona_dict = dict(persona)
            return render_template('perfil_trabajador.html', persona=persona_dict)
        else:
            flash('No se encontró ningún trabajador con esa cédula', 'error')
            return redirect(url_for('inicio'))
    except Exception as e:
        flash('Error al consultar la base de datos', 'error')
        return redirect(url_for('inicio'))

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

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    try:
        termino_busqueda = request.args.get('busqueda', '').strip()
        
        if termino_busqueda:
            personas = buscar_trabajadores(termino_busqueda)
        else:
            personas = execute_query(
                "SELECT * FROM personas ORDER BY apellidos, nombres",
                fetch=True
            )
        
        return render_template('admin_dashboard.html', 
                             personas=personas, 
                             termino_busqueda=termino_busqueda)
    except Exception as e:
        flash('Error cargando los datos', 'error')
        return render_template('admin_dashboard.html', 
                             personas=[], 
                             termino_busqueda='')

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
        unidad = request.form['unidad'].strip()
        telefono = request.form['telefono'].strip()
        region = request.form['region'].strip()
        oficio = request.form['oficio'].strip()

        # Validación de teléfono (solo números)
        if telefono and not telefono.isdigit():
            flash('El teléfono solo puede contener números', 'error')
            return render_template('agregar_persona.html', unidades=UNIDADES)

        if not all([nombres, apellidos, cedula, fecha_emision, cargo, unidad]):
            flash('Los campos nombres, apellidos, cédula, fecha de emisión, cargo y unidad son obligatorios', 'error')
            return render_template('agregar_persona.html', unidades=UNIDADES)

        foto_url = None
        if 'foto' in request.files:
            file = request.files['foto']
            if file and file.filename != '' and allowed_file(file.filename):
                foto_url = upload_to_cloudinary(file, cedula)
                if not foto_url:
                    flash('Error al subir la foto. Se guardará el trabajador sin foto.', 'warning')

        try:
            existing = execute_query_one(
                "SELECT id FROM personas WHERE cedula = %s" if DATABASE_URL else "SELECT id FROM personas WHERE cedula = ?",
                (cedula,)
            )
            
            if existing:
                flash('Ya existe un trabajador con esa cédula', 'error')
                return render_template('agregar_persona.html', unidades=UNIDADES)

            persona_id = str(uuid.uuid4())

            affected = execute_query(
    """INSERT INTO personas (id, nombres, apellidos, cedula, fecha_emision, cargo, foto, sindicato, telefono, region, oficio) 
       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""" if DATABASE_URL else 
    """INSERT INTO personas (id, nombres, apellidos, cedula, fecha_emision, cargo, foto, sindicato, telefono, region, oficio) 
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
    (persona_id, nombres, apellidos, cedula, fecha_emision, cargo, foto_url, unidad, telefono, region, oficio)
)            
            if affected > 0:
                qr_data = url_for('ver_perfil_publico', cedula=cedula, _external=True)
                qr = qrcode.QRCode(version=1, box_size=10, border=5)
                qr.add_data(qr_data)
                qr.make(fit=True)
                
                os.makedirs('static', exist_ok=True)
                
                qr_img = qr.make_image(fill_color="black", back_color="white")
                qr_path = f'static/{persona_id}.png'
                qr_img.save(qr_path)
                qr_url = '/' + qr_path
                
                flash('Trabajador agregado exitosamente', 'success')
                return render_template('agregar_persona.html', qr_url=qr_url, persona_id=persona_id, unidades=UNIDADES)
            else:
                flash('Error al guardar el trabajador. Intente nuevamente.', 'error')
                return render_template('agregar_persona.html', unidades=UNIDADES)
        except Exception as e:
            flash(f'Error en la base de datos: {str(e)}', 'error')
            return render_template('agregar_persona.html', unidades=UNIDADES)

    return render_template('agregar_persona.html', unidades=UNIDADES)

@app.route('/admin/editar/<persona_id>', methods=['GET', 'POST'])
@login_required
def editar_persona(persona_id):
    if request.method == 'POST':
        nombres = request.form['nombres'].strip()
        apellidos = request.form['apellidos'].strip()
        cedula = request.form['cedula'].strip()
        fecha_emision = request.form['fecha_emision'].strip()
        cargo = request.form['cargo'].strip()
        unidad = request.form['unidad'].strip()
        telefono = request.form['telefono'].strip()
        region = request.form['region'].strip()
        oficio = request.form['oficio'].strip()
        
        # Validación de teléfono (solo números)
        if telefono and not telefono.isdigit():
            flash('El teléfono solo puede contener números', 'error')
            persona = execute_query_one(
                "SELECT * FROM personas WHERE id = %s" if DATABASE_URL else "SELECT * FROM personas WHERE id = ?",
                (persona_id,)
            )
            return render_template('editar_persona.html', p=persona, unidades=UNIDADES)
        
        persona_actual = execute_query_one(
            "SELECT foto FROM personas WHERE id = %s" if DATABASE_URL else "SELECT foto FROM personas WHERE id = ?",
            (persona_id,)
        )
        
        foto_url = persona_actual['foto'] if persona_actual else None
        
        if 'foto' in request.files:
            file = request.files['foto']
            if file and file.filename != '' and allowed_file(file.filename):
                if foto_url:
                    delete_from_cloudinary(foto_url)
                
                nueva_foto_url = upload_to_cloudinary(file, cedula)
                if nueva_foto_url:
                    foto_url = nueva_foto_url
                else:
                    flash('Error al subir la nueva foto. Se mantendrá la foto anterior.', 'warning')
        
        try:
            affected = execute_query(
    """UPDATE personas SET nombres=%s, apellidos=%s, cedula=%s, fecha_emision=%s, cargo=%s, foto=%s, sindicato=%s, telefono=%s, region=%s, oficio=%s 
       WHERE id=%s""" if DATABASE_URL else
    """UPDATE personas SET nombres=?, apellidos=?, cedula=?, fecha_emision=?, cargo=?, foto=?, sindicato=?, telefono=?, region=?, oficio=? 
       WHERE id=?""",
    (nombres, apellidos, cedula, fecha_emision, cargo, foto_url, unidad, telefono, region, oficio, persona_id)
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
               return render_template('editar_persona.html', p=persona, unidades=UNIDADES)
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
        persona = execute_query_one(
            "SELECT foto FROM personas WHERE id = %s" if DATABASE_URL else "SELECT foto FROM personas WHERE id = ?",
            (persona_id,)
        )
        
        affected = execute_query(
            "DELETE FROM personas WHERE id = %s" if DATABASE_URL else "DELETE FROM personas WHERE id = ?",
            (persona_id,)
        )
        
        if affected > 0:
            try:
                os.remove(f'static/{persona_id}.png')
            except FileNotFoundError:
                pass
            
            if persona and persona['foto']:
                delete_from_cloudinary(persona['foto'])
            
            flash('Trabajador eliminado correctamente', 'success')
        else:
            flash('No se encontró el trabajador para eliminar', 'error')
    except Exception as e:
        flash(f'Error al eliminar: {str(e)}', 'error')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/ver_perfil/<persona_id>')
@login_required
def admin_ver_perfil(persona_id):
    try:
        persona = execute_query_one(
            "SELECT * FROM personas WHERE id = %s" if DATABASE_URL else "SELECT * FROM personas WHERE id = ?",
            (persona_id,)
        )
        
        if persona:
            if DATABASE_URL:
                persona_dict = dict(persona)
            else:
                persona_dict = {
                    'id': persona[0],
                    'nombres': persona[1], 
                    'apellidos': persona[2],
                    'cedula': persona[3],
                    'fecha_emision': persona[4],
                    'cargo': persona[5],
                    'foto': persona[6] if len(persona) > 6 else None,
                    'sindicato': persona[7] if len(persona) > 7 else None,
                    'telefono': persona[8] if len(persona) > 8 else None,
                    'region': persona[9] if len(persona) > 9 else None,
                    'oficio': persona[10] if len(persona) > 10 else None
                }
            return render_template('perfil_trabajador.html', persona=persona_dict)
        else:
            flash('Trabajador no encontrado', 'error')
            return redirect(url_for('admin_dashboard'))
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/perfil/<cedula>')
def ver_perfil_publico(cedula):
    try:
        persona = execute_query_one(
            "SELECT * FROM personas WHERE cedula = %s" if DATABASE_URL else "SELECT * FROM personas WHERE cedula = ?",
            (cedula,)
        )
        
        if persona:
            if DATABASE_URL:
                persona_dict = dict(persona)
            else:
                persona_dict = {
                    'id': persona[0],
                    'nombres': persona[1], 
                    'apellidos': persona[2],
                    'cedula': persona[3],
                    'fecha_emision': persona[4],
                    'cargo': persona[5],
                    'foto': persona[6] if len(persona) > 6 else None,
                    'sindicato': persona[7] if len(persona) > 7 else None,
                    'telefono': persona[8] if len(persona) > 8 else None,
                    'region': persona[9] if len(persona) > 9 else None,
                    'oficio': persona[10] if len(persona) > 10 else None
                }
            return render_template('perfil_trabajador.html', persona=persona_dict)
        else:
            return render_template('error.html', mensaje="Trabajador no encontrado"), 404
    except Exception as e:
        return render_template('error.html', mensaje=f"Error: {str(e)}"), 500

@app.route('/persona/<persona_id>')
def ver_persona(persona_id):
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

        if DATABASE_URL:
            p = dict(persona)
        else:
            p = {
                'nombres': persona[1],
                'apellidos': persona[2],
                'cedula': persona[3],
                'fecha_emision': persona[4],
                'cargo': persona[5],
                'foto': persona[6] if len(persona) > 6 else None,
                'sindicato': persona[7] if len(persona) > 7 else None,
                'telefono': persona[8] if len(persona) > 8 else None,
                'region': persona[9] if len(persona) > 9 else None,
                'oficio': persona[10] if len(persona) > 10 else None
            }

        buffer = BytesIO()
        pdf = canvas.Canvas(buffer)
        pdf.drawString(100, 750, f"Nombre: {p['nombres']} {p['apellidos']}")
        pdf.drawString(100, 730, f"Cédula: {p['cedula']}")
        pdf.drawString(100, 710, f"Fecha de Emisión: {p['fecha_emision']}")
        pdf.drawString(100, 690, f"Cargo: {p['cargo']}")
        pdf.drawString(100, 670, f"Sindicato: {p.get('sindicato', 'No asignado')}")
        pdf.drawString(100, 650, f"Teléfono: {p.get('telefono', 'No registrado')}")
        pdf.drawString(100, 630, f"Región: {p.get('region', 'No registrada')}")
        pdf.drawString(100, 610, f"Oficio: {p.get('oficio', 'No registrado')}")
        pdf.showPage()
        pdf.save()
        buffer.seek(0)

        return send_file(buffer, as_attachment=True, download_name=f"{p['nombres']}_{p['apellidos']}.pdf", mimetype='application/pdf')
    except Exception as e:
        return f"Error generando PDF: {str(e)}", 500

@app.route('/admin/pdf_todos')
@login_required
def generar_pdf_todos():
    try:
        # Consulta usando el campo 'sindicato' que contiene las unidades
        personas = execute_query(
            "SELECT nombres, apellidos, cedula, cargo, fecha_emision, sindicato, telefono, region, oficio FROM personas ORDER BY sindicato, apellidos, nombres",
            fetch=True
        )
        
        if not personas:
            flash('No hay trabajadores registrados para generar el PDF', 'warning')
            return redirect(url_for('admin_dashboard'))
        
        # Agrupar trabajadores por unidad
        trabajadores_cemento = []
        trabajadores_construccion = []
        
        for persona in personas:
            if DATABASE_URL:
                p = dict(persona)
            else:
                p = dict(persona)
            
            unidad = p.get('sindicato', '').strip() if p.get('sindicato') else ''
            
            if unidad.lower() == 'cemento':
                trabajadores_cemento.append(p)
            elif unidad.lower() == 'construcción':
                trabajadores_construccion.append(p)
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, 
                              pagesize=A4,
                              topMargin=0.5*inch,
                              bottomMargin=0.5*inch,
                              leftMargin=0.5*inch,
                              rightMargin=0.5*inch)
        
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            spaceAfter=30,
            alignment=TA_CENTER,
            textColor=colors.darkblue
        )
        
        # Estilo para títulos de sección
        section_style = ParagraphStyle(
            'SectionTitle',
            parent=styles['Heading2'],
            fontSize=14,
            spaceAfter=15,
            spaceBefore=20,
            alignment=TA_CENTER,
            textColor=colors.darkgreen
        )
        
        story = []
        
        # Título principal
        titulo = Paragraph("LISTADO DE TRABAJADORES POR UNIDAD", title_style)
        story.append(titulo)
        
        fecha_actual = datetime.now().strftime("%d/%m/%Y %H:%M")
        fecha_para = Paragraph(f"Generado el: {fecha_actual}", styles['Normal'])
        story.append(fecha_para)
        story.append(Spacer(1, 20))
        
        # Resumen
        total_trabajadores = len(personas)
        total_cemento = len(trabajadores_cemento)
        total_construccion = len(trabajadores_construccion)
        
        resumen = Paragraph(f"Total de trabajadores: {total_trabajadores} | Cemento: {total_cemento} | Construcción: {total_construccion}", styles['Heading3'])
        story.append(resumen)
        story.append(Spacer(1, 30))
        
        # Función para crear tabla de trabajadores
        def crear_tabla_trabajadores(trabajadores_lista, contador_inicial=1):
            data = [['N°', 'Nombre Completo', 'Cédula', 'Cargo', 'Teléfono', 'Región', 'Oficio', 'Fecha Emisión']]
            
            for i, p in enumerate(trabajadores_lista, contador_inicial):
                nombre_completo = f"{p['nombres']} {p['apellidos']}"
                fecha_emision = p['fecha_emision'].strftime("%d/%m/%Y") if p['fecha_emision'] else "N/A"
                telefono = p.get('telefono', 'No registrado') or 'No registrado'
                region = p.get('region', 'No registrada') or 'No registrada'
                oficio = p.get('oficio', 'No registrado') or 'No registrado'
                
                data.append([
                    str(i),
                    nombre_completo,
                    p['cedula'],
                    p['cargo'],
                    telefono,
                    region,
                    oficio,
                    fecha_emision
                ])
            
            table = Table(data, colWidths=[0.4*inch, 2.0*inch, 1.0*inch, 1.5*inch, 0.9*inch, 0.9*inch, 0.9*inch, 0.9*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
            ]))
            
            return table
        
        contador = 1
        
        # SECCIÓN CEMENTO
        if trabajadores_cemento:
            titulo_cemento = Paragraph("UNIDAD DE CEMENTO", section_style)
            story.append(titulo_cemento)
            
            subtotal_cemento = Paragraph(f"Total trabajadores: {len(trabajadores_cemento)}", styles['Normal'])
            story.append(subtotal_cemento)
            story.append(Spacer(1, 10))
            
            tabla_cemento = crear_tabla_trabajadores(trabajadores_cemento, contador)
            story.append(tabla_cemento)
            story.append(Spacer(1, 30))
            
            contador += len(trabajadores_cemento)
        
        # SECCIÓN CONSTRUCCIÓN
        if trabajadores_construccion:
            titulo_construccion = Paragraph("UNIDAD DE CONSTRUCCIÓN", section_style)
            story.append(titulo_construccion)
            
            subtotal_construccion = Paragraph(f"Total trabajadores: {len(trabajadores_construccion)}", styles['Normal'])
            story.append(subtotal_construccion)
            story.append(Spacer(1, 10))
            
            tabla_construccion = crear_tabla_trabajadores(trabajadores_construccion, contador)
            story.append(tabla_construccion)
        
        doc.build(story)
        
        buffer.seek(0)
        fecha_archivo = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"trabajadores_por_unidad_{fecha_archivo}.pdf"
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )
    except Exception as e:
        flash(f'Error al generar el PDF: {str(e)}', 'error')
        return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    if DATABASE_URL:
        init_connection_pool()
        
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)