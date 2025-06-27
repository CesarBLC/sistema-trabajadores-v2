# exportar_datos.py
import psycopg2
import csv
from psycopg2.extras import RealDictCursor

# Pega aquí tu DATABASE_URL de Render
DATABASE_URL = "postgresql://personas_user:SUmufAksy0CRifRKJdMk4HwUYuHFc08b@dpg-d17ojtmmcj7s73c3j2d0-a.oregon-postgres.render.com/personas_9alm"  # Reemplaza con tu URL real

try:
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM personas ORDER BY id")
    datos = cursor.fetchall()
    
    with open('personas_backup.csv', 'w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['id', 'nombres', 'apellidos', 'cedula', 'fecha_emision', 
                        'cargo', 'foto', 'sindicato', 'telefono', 'region', 'oficio'])
        
        for fila in datos:
            writer.writerow([
                fila['id'], fila['nombres'], fila['apellidos'], fila['cedula'],
                fila['fecha_emision'], fila['cargo'], fila['foto'], 
                fila['sindicato'], fila['telefono'], fila['region'], fila['oficio']
            ])
    
    print(f"✅ Exportados {len(datos)} registros a personas_backup.csv")
    conn.close()
    
except Exception as e:
    print(f"❌ Error: {e}")