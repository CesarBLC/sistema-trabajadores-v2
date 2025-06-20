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

app = Flask(__name__)
app.secret_key = '10000'  # Cambia esto por una clave segura

# Credenciales de administrador (cámbialas por las tuyas)
ADMIN_USER = "admin"
ADMIN_PASS = "admin123"

# CONFIGURACIÓN DE CLOUDINARY
cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key=os.environ.get('CLOUDINARY_API_KEY'),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET')
)

# CONFIGURACIÓN PARA SUBIDA DE ARCHIVOS
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

# SINDICATOS PREDETERMINADOS
SINDICATOS = ['UBT', 'CBST', 'FUNTTBCCAC']

def allowed_file(filename):
    """Verificar si el archivo tiene una extensión permitida"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def upload_to_cloudinary(file, cedula):
    """Subir archivo a Cloudinary y retornar la URL"""
    try:
        # Crear un public_id único basado en la cédula
        public_id = f"trabajadores/{cedula}_{uuid.uuid4().hex[:8]}"
        
        # Configurar opciones de transformación para optimizar la imagen
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
        
        print(f"✅ Imagen subida a Cloudinary: {upload_result['secure_url']}")
        return upload_result['secure_url']
        
    except Exception as e:
        print(f"❌ Error subiendo a Cloudinary: {e}")
        return None

def delete_from_cloudinary(foto_url):
    """Eliminar imagen de Cloudinary usando la URL"""
    try:
        if foto_url and 'cloudinary.com' in foto_url:
            # Extraer public_id de la URL
            parts = foto_url.split('/')
            if 'trabajadores' in parts:
                public_id_with_ext = parts[parts.index('trabajadores') + 1]
                public_id = public_id_with_ext.split('.')[0]  # Remover extensión
                full_public_id = f"trabajadores/{public_id}"
                
                result = cloudinary.uploader.destroy(full_public_id)
                print(f"🗑️ Imagen eliminada de Cloudinary: {result}")
                return result
    except Exception as e:
        print(f"❌ Error eliminando de Cloudinary: {e}")
    return None

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
        
        # Crear tabla - ACTUALIZADO: foto ahora guarda URL de Cloudinary
        create_sql = """
        CREATE TABLE IF NOT EXISTS personas (
            id VARCHAR(36) PRIMARY KEY,
            nombres VARCHAR(100) NOT NULL,
            apellidos VARCHAR(100) NOT NULL,
            cedula VARCHAR(20) NOT NULL UNIQUE,
            fecha_emision DATE NOT NULL,
            cargo VARCHAR(100) NOT NULL,
            foto TEXT,
            sindicato VARCHAR(100)
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

def actualizar_base_datos():
    """Script para agregar las nuevas columnas a la tabla existente"""
    if not DATABASE_URL:
        return
        
    print("🔧 ACTUALIZANDO BASE DE DATOS...")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Verificar si las columnas ya existen
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'personas' AND column_name IN ('foto', 'sindicato')
        """)
        
        existing_columns = [row[0] for row in cursor.fetchall()]
        
        # Agregar columna foto si no existe (TEXT para URLs de Cloudinary)
        if 'foto' not in existing_columns:
            cursor.execute("ALTER TABLE personas ADD COLUMN foto TEXT;")
            print("✅ Columna 'foto' agregada")
        else:
            print("ℹ️ Columna 'foto' ya existe")
            
        # Agregar columna sindicato si no existe
        if 'sindicato' not in existing_columns:
            cursor.execute("ALTER TABLE personas ADD COLUMN sindicato VARCHAR(100);")
            print("✅ Columna 'sindicato' agregada")
        else:
            print("ℹ️ Columna 'sindicato' ya existe")
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print("✅ Base de datos actualizada exitosamente")
        
    except Exception as e:
        print(f"❌ Error actualizando base de datos: {e}")
        # No hacer raise aquí para no detener la aplicación
        pass

# EJECUTAR INMEDIATAMENTE al importar
if DATABASE_URL:
    crear_tabla_si_no_existe()
    actualizar_base_datos()

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

# FUNCIÓN DE BÚSQUEDA - VERSIÓN COMPLETA
def buscar_trabajadores(termino_busqueda):
    """
    Buscar trabajadores por nombre, apellido, nombre completo o cédula
    """
    try:
        # Limpiar el término de búsqueda
        termino = termino_busqueda.strip()
        
        if not termino:
            print("⚠️ Búsqueda vacía - retornando lista vacía")
            return []
        
        print(f"🔍 Buscando: '{termino}'")
        
        # Extraer solo números del término (para búsqueda por cédula)
        numeros_termino = ''.join(filter(str.isdigit, termino))
        
        if DATABASE_URL:
            # PostgreSQL - Búsqueda completa
            query = """
            SELECT * FROM personas 
            WHERE 
                -- Buscar en nombres
                LOWER(nombres) LIKE LOWER(%s)
                -- Buscar en apellidos  
                OR LOWER(apellidos) LIKE LOWER(%s)
                -- Buscar nombre completo (nombre + apellido)
                OR LOWER(CONCAT(nombres, ' ', apellidos)) LIKE LOWER(%s)
                -- Buscar nombre completo (apellido + nombre)
                OR LOWER(CONCAT(apellidos, ' ', nombres)) LIKE LOWER(%s)
                -- Buscar por cédula exacta
                OR cedula = %s
                -- Buscar por cédula parcial
                OR cedula LIKE %s
                -- Buscar por números de cédula (sin formato)
                OR REGEXP_REPLACE(cedula, '[^0-9]', '', 'g') LIKE %s
            ORDER BY apellidos, nombres
            """
            params = (
                f'%{termino}%',           # nombres
                f'%{termino}%',           # apellidos
                f'%{termino}%',           # nombre + apellido
                f'%{termino}%',           # apellido + nombre
                termino,                   # cédula exacta
                f'%{termino}%',           # cédula parcial
                f'%{numeros_termino}%'    # números de cédula
            )
        else:
            # SQLite - Búsqueda completa
            query = """
            SELECT * FROM personas 
            WHERE 
                -- Buscar en nombres
                LOWER(nombres) LIKE LOWER(?)
                -- Buscar en apellidos
                OR LOWER(apellidos) LIKE LOWER(?)
                -- Buscar nombre completo (nombre + apellido)
                OR LOWER(nombres || ' ' || apellidos) LIKE LOWER(?)
                -- Buscar nombre completo (apellido + nombre)
                OR LOWER(apellidos || ' ' || nombres) LIKE LOWER(?)
                -- Buscar por cédula exacta
                OR cedula = ?
                -- Buscar por cédula parcial
                OR cedula LIKE ?
            ORDER BY apellidos, nombres
            """
            params = (
                f'%{termino}%',     # nombres
                f'%{termino}%',     # apellidos
                f'%{termino}%',     # nombre + apellido
                f'%{termino}%',     # apellido + nombre
                termino,             # cédula exacta
                f'%{termino}%'      # cédula parcial
            )
        
        resultados = execute_query(query, params, fetch=True)
        print(f"🔍 Búsqueda '{termino}': {len(resultados)} resultados encontrados")
        
        return resultados
        
    except Exception as e:
        print(f"❌ Error en búsqueda: {e}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")
        return []
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

      # 🔧 NUEVA LÍNEA: Extraer solo números de la cédula ingresada
    numeros_cedula = ''.join(filter(str.isdigit, cedula))
    

    print(f"🔍 Buscando cédula: '{cedula}'")
    
    # DEBUG: Verificar qué hay en la base de datos
    debug_database()
    
    try:
        # 🔧 NUEVA CONSULTA: Usar REGEXP_REPLACE para extraer solo números
        persona = execute_query_one(
            "SELECT * FROM personas WHERE REGEXP_REPLACE(cedula, '[^0-9]', '', 'g') = %s",
            (numeros_cedula,)
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
        # Obtener término de búsqueda si existe
        termino_busqueda = request.args.get('busqueda', '').strip()
        
        print(f"🔍 Dashboard - Término de búsqueda: '{termino_busqueda}'")
        
        # Si hay término de búsqueda, usar búsqueda
        if termino_busqueda:
            personas = buscar_trabajadores(termino_busqueda)
        else:
            # Si no hay búsqueda, mostrar todos los trabajadores
            personas = execute_query(
                "SELECT * FROM personas ORDER BY apellidos, nombres",
                fetch=True
            )
        
        print(f"📊 Personas encontradas: {len(personas)}")
        
        # Debug: mostrar los datos
        for i, persona in enumerate(personas):
            if DATABASE_URL:
                p_dict = dict(persona)
            else:
                p_dict = dict(persona)
            print(f"  👤 {i+1}. ID: {p_dict.get('id', 'SIN_ID')}, Nombre: {p_dict.get('nombres', 'SIN_NOMBRE')}, Cédula: {p_dict.get('cedula', 'SIN_CEDULA')}")
        
        return render_template('admin_dashboard.html', 
                             personas=personas, 
                             termino_busqueda=termino_busqueda)
        
    except Exception as e:
        print(f"❌ Error cargando dashboard: {e}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")
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
        sindicato = request.form['sindicato'].strip()

        # Validar campos vacíos
        if not all([nombres, apellidos, cedula, fecha_emision, cargo, sindicato]):
            flash('Todos los campos son obligatorios', 'error')
            return render_template('agregar_persona.html', sindicatos=SINDICATOS)

        print(f"💾 Guardando cédula: '{cedula}'")

        # Manejo de la foto con Cloudinary
        foto_url = None
        if 'foto' in request.files:
            file = request.files['foto']
            if file and file.filename != '' and allowed_file(file.filename):
                print(f"📸 Subiendo foto a Cloudinary...")
                foto_url = upload_to_cloudinary(file, cedula)
                if foto_url:
                    print(f"✅ Foto subida exitosamente: {foto_url}")
                else:
                    flash('Error al subir la foto. Se guardará el trabajador sin foto.', 'warning')

        try:
            # Verificar si ya existe la cédula
            existing = execute_query_one(
                "SELECT id FROM personas WHERE cedula = %s" if DATABASE_URL else "SELECT id FROM personas WHERE cedula = ?",
                (cedula,)
            )
            
            if existing:
                flash('Ya existe un trabajador con esa cédula', 'error')
                return render_template('agregar_persona.html', sindicatos=SINDICATOS)

            # Generar ID único
            persona_id = str(uuid.uuid4())

            # Insertar en la base de datos (ACTUALIZADO: foto ahora es URL de Cloudinary)
            affected = execute_query(
                """INSERT INTO personas (id, nombres, apellidos, cedula, fecha_emision, cargo, foto, sindicato) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""" if DATABASE_URL else 
                """INSERT INTO personas (id, nombres, apellidos, cedula, fecha_emision, cargo, foto, sindicato) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (persona_id, nombres, apellidos, cedula, fecha_emision, cargo, foto_url, sindicato)
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
                return render_template('agregar_persona.html', qr_url=qr_url, persona_id=persona_id, sindicatos=SINDICATOS)
            else:
                flash('Error al guardar el trabajador. Intente nuevamente.', 'error')
                return render_template('agregar_persona.html', sindicatos=SINDICATOS)
                
        except Exception as e:
            print(f"❌ Error al insertar: {e}")
            flash(f'Error en la base de datos: {str(e)}', 'error')
            return render_template('agregar_persona.html', sindicatos=SINDICATOS)

    return render_template('agregar_persona.html', sindicatos=SINDICATOS)

@app.route('/admin/editar/<persona_id>', methods=['GET', 'POST'])
@login_required
def editar_persona(persona_id):
    if request.method == 'POST':
        nombres = request.form['nombres'].strip()
        apellidos = request.form['apellidos'].strip()
        cedula = request.form['cedula'].strip()
        fecha_emision = request.form['fecha_emision'].strip()
        cargo = request.form['cargo'].strip()
        sindicato = request.form['sindicato'].strip()
        
        # Obtener datos actuales para preservar foto si no se cambia
        persona_actual = execute_query_one(
            "SELECT foto FROM personas WHERE id = %s" if DATABASE_URL else "SELECT foto FROM personas WHERE id = ?",
            (persona_id,)
        )
        
        foto_url = persona_actual['foto'] if persona_actual else None
        
        # Manejo de nueva foto con Cloudinary
        if 'foto' in request.files:
            file = request.files['foto']
            if file and file.filename != '' and allowed_file(file.filename):
                print(f"📸 Subiendo nueva foto a Cloudinary...")
                
                # Eliminar foto anterior de Cloudinary si existe
                if foto_url:
                    delete_from_cloudinary(foto_url)
                
                # Subir nueva foto
                nueva_foto_url = upload_to_cloudinary(file, cedula)
                if nueva_foto_url:
                    foto_url = nueva_foto_url
                    print(f"✅ Nueva foto subida exitosamente: {foto_url}")
                else:
                    flash('Error al subir la nueva foto. Se mantendrá la foto anterior.', 'warning')
        
        try:
            affected = execute_query(
                """UPDATE personas SET nombres=%s, apellidos=%s, cedula=%s, fecha_emision=%s, cargo=%s, foto=%s, sindicato=%s 
                   WHERE id=%s""" if DATABASE_URL else
                """UPDATE personas SET nombres=?, apellidos=?, cedula=?, fecha_emision=?, cargo=?, foto=?, sindicato=? 
                   WHERE id=?""",
                (nombres, apellidos, cedula, fecha_emision, cargo, foto_url, sindicato, persona_id)
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
                return render_template('editar_persona.html', p=persona, sindicatos=SINDICATOS)
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
        # Obtener datos antes de eliminar para borrar la foto de Cloudinary
        persona = execute_query_one(
            "SELECT foto FROM personas WHERE id = %s" if DATABASE_URL else "SELECT foto FROM personas WHERE id = ?",
            (persona_id,)
        )
        
        affected = execute_query(
            "DELETE FROM personas WHERE id = %s" if DATABASE_URL else "DELETE FROM personas WHERE id = ?",
            (persona_id,)
        )
        
        if affected > 0:
            # Eliminar archivo QR local
            try:
                os.remove(f'static/{persona_id}.png')
            except FileNotFoundError:
                pass
            
            # Eliminar foto de Cloudinary si existe
            if persona and persona['foto']:
                delete_from_cloudinary(persona['foto'])
                print(f"🗑️ Foto eliminada de Cloudinary")
            
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
                    'cargo': persona[5],
                    'foto': persona[6] if len(persona) > 6 else None,
                    'sindicato': persona[7] if len(persona) > 7 else None
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
                    'cargo': persona[5],
                    'foto': persona[6] if len(persona) > 6 else None,
                    'sindicato': persona[7] if len(persona) > 7 else None
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
                'cargo': persona[5],
                'foto': persona[6] if len(persona) > 6 else None,
                'sindicato': persona[7] if len(persona) > 7 else None
            }

        buffer = BytesIO()
        pdf = canvas.Canvas(buffer)
        pdf.drawString(100, 750, f"Nombre: {p['nombres']} {p['apellidos']}")
        pdf.drawString(100, 730, f"Cédula: {p['cedula']}")
        pdf.drawString(100, 710, f"Fecha de Emisión: {p['fecha_emision']}")
        pdf.drawString(100, 690, f"Cargo: {p['cargo']}")
        pdf.drawString(100, 670, f"Sindicato: {p.get('sindicato', 'No asignado')}")
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