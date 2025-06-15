import sqlite3
import uuid

def test_manual_insert():
    """Prueba insertar un registro manualmente para verificar que funciona"""
    
    try:
        conn = sqlite3.connect('personas.db')
        c = conn.cursor()
        
        # Datos de prueba
        persona_id = str(uuid.uuid4())
        nombres = "Juan Carlos"
        apellidos = "Pérez González"
        cedula = "12345678"
        fecha_emision = "2024-01-15"
        cargo = "Operario de Prueba"
        
        print(f"🧪 Insertando trabajador de prueba...")
        print(f"   ID: {persona_id}")
        print(f"   Nombres: {nombres}")
        print(f"   Apellidos: {apellidos}")
        print(f"   Cédula: {cedula}")
        print(f"   Fecha: {fecha_emision}")
        print(f"   Cargo: {cargo}")
        
        # Insertar el registro
        c.execute("""INSERT INTO personas 
                     (id, nombres, apellidos, cedula, fecha_emision, cargo) 
                     VALUES (?, ?, ?, ?, ?, ?)""",
                  (persona_id, nombres, apellidos, cedula, fecha_emision, cargo))
        
        conn.commit()
        print("✅ Inserción exitosa!")
        
        # Verificar que se insertó
        c.execute("SELECT * FROM personas WHERE cedula = ?", (cedula,))
        resultado = c.fetchone()
        
        if resultado:
            print("✅ Verificación exitosa - El registro se encuentra en la BD")
            print(f"   Registro encontrado: {resultado}")
        else:
            print("❌ Error: No se pudo encontrar el registro después de insertarlo")
        
        # Mostrar total de registros
        c.execute("SELECT COUNT(*) FROM personas")
        total = c.fetchone()[0]
        print(f"📊 Total de registros en la BD: {total}")
        
        conn.close()
        
        return True
        
    except sqlite3.Error as e:
        print(f"❌ Error de SQLite: {e}")
        return False
    except Exception as e:
        print(f"❌ Error general: {e}")
        return False

def test_search_function():
    """Probar la función de búsqueda con el registro insertado"""
    
    try:
        conn = sqlite3.connect('personas.db')
        conn.row_factory = sqlite3.Row  # Para simular el comportamiento de tu app
        
        cedula_buscar = "12345678"
        print(f"\n🔍 Probando búsqueda de cédula: '{cedula_buscar}'")
        
        persona = conn.execute("SELECT * FROM personas WHERE cedula = ?", (cedula_buscar,)).fetchone()
        
        if persona:
            print("✅ Búsqueda exitosa!")
            print(f"   Nombres: {persona[1]}")
            print(f"   Apellidos: {persona[2]}")
            print(f"   Cédula: {persona[3]}")
            print(f"   Cargo: {persona[5]}")
        else:
            print("❌ No se encontró el trabajador")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error en búsqueda: {e}")

if __name__ == "__main__":
    print("🧪 PRUEBA DE INSERCIÓN MANUAL")
    print("=" * 40)
    
    # Probar inserción
    if test_manual_insert():
        # Si la inserción fue exitosa, probar búsqueda
        test_search_function()
        
        print("\n" + "=" * 40)
        print("✅ Si ves este mensaje, tu base de datos funciona correctamente.")
        print("   El problema podría estar en el formulario web o en la función de agregar.")
        print("   Ahora prueba agregar un trabajador desde el panel web y ejecuta debug_db.py otra vez.")
    else:
        print("\n" + "=" * 40)
        print("❌ Hay un problema con la base de datos.")
        print("   Verifica los permisos del archivo personas.db")