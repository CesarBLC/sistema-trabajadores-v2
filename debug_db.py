import sqlite3

def verificar_base_datos():
    """Script para verificar el contenido de la base de datos"""
    
    try:
        conn = sqlite3.connect('personas.db')
        c = conn.cursor()
        
        # Verificar si la tabla existe
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='personas';")
        tabla_existe = c.fetchone()
        
        if not tabla_existe:
            print("❌ La tabla 'personas' no existe")
            return
        
        print("✅ La tabla 'personas' existe")
        
        # Obtener todos los registros
        c.execute("SELECT * FROM personas")
        registros = c.fetchall()
        
        print(f"\n📊 Total de registros: {len(registros)}")
        
        if len(registros) == 0:
            print("⚠️  No hay registros en la base de datos")
        else:
            print("\n📋 Registros encontrados:")
            print("-" * 80)
            for i, registro in enumerate(registros, 1):
                print(f"Registro {i}:")
                print(f"  ID: {registro[0]}")
                print(f"  Nombres: '{registro[1]}'")
                print(f"  Apellidos: '{registro[2]}'")
                print(f"  Cédula: '{registro[3]}' (tipo: {type(registro[3])}, longitud: {len(str(registro[3]))})")
                print(f"  Fecha emisión: '{registro[4]}'")
                print(f"  Cargo: '{registro[5]}'")
                print("-" * 80)
        
        # Probar una búsqueda específica
        print("\n🔍 Prueba de búsqueda:")
        if len(registros) > 0:
            cedula_prueba = registros[0][3]  # Tomar la primera cédula
            print(f"Buscando cédula: '{cedula_prueba}'")
            
            c.execute("SELECT * FROM personas WHERE cedula = ?", (cedula_prueba,))
            resultado = c.fetchone()
            
            if resultado:
                print("✅ Búsqueda exitosa")
            else:
                print("❌ No se encontró el registro (esto indica un problema)")
        
        conn.close()
        
    except sqlite3.Error as e:
        print(f"❌ Error de base de datos: {e}")
    except Exception as e:
        print(f"❌ Error general: {e}")

def limpiar_cedulas():
    """Función para limpiar cédulas con espacios en blanco"""
    try:
        conn = sqlite3.connect('personas.db')
        c = conn.cursor()
        
        # Obtener todas las cédulas
        c.execute("SELECT id, cedula FROM personas")
        registros = c.fetchall()
        
        actualizaciones = 0
        for registro in registros:
            id_persona = registro[0]
            cedula_original = registro[1]
            cedula_limpia = cedula_original.strip()
            
            if cedula_original != cedula_limpia:
                c.execute("UPDATE personas SET cedula = ? WHERE id = ?", (cedula_limpia, id_persona))
                print(f"Actualizada cédula: '{cedula_original}' -> '{cedula_limpia}'")
                actualizaciones += 1
        
        if actualizaciones > 0:
            conn.commit()
            print(f"✅ Se actualizaron {actualizaciones} cédulas")
        else:
            print("✅ No se encontraron cédulas que necesiten limpieza")
        
        conn.close()
        
    except sqlite3.Error as e:
        print(f"❌ Error al limpiar cédulas: {e}")

if __name__ == "__main__":
    print("🔧 DIAGNÓSTICO DE BASE DE DATOS")
    print("=" * 50)
    
    # Verificar estado actual
    verificar_base_datos()
    
    # Ofrecer limpiar cédulas
    respuesta = input("\n¿Quieres limpiar espacios en blanco de las cédulas? (s/n): ")
    if respuesta.lower() == 's':
        limpiar_cedulas()
        print("\n🔄 Verificando después de la limpieza:")
        verificar_base_datos()