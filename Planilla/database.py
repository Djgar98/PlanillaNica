import calendar
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

DATABASE = Path(__file__).resolve().parent / "planilla_ni.db"
INSS_LABORAL_TASA = 0.07
INSS_PATRONAL_MENOR_50_TASA = 0.215
INSS_PATRONAL_50_O_MAS_TASA = 0.225
HORAS_MENSUALES = 240
RECARGO_HORA_EXTRA = 2


def get_db():
    """Abre una conexión SQLite con claves foráneas activas."""
    conn = sqlite3.connect(DATABASE, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _agregar_columna_si_falta(conn, tabla, columna, definicion):
    columnas = {fila["name"] for fila in conn.execute(f"PRAGMA table_info({tabla})")}
    if columna not in columnas:
        conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")


def _migrar_roles_usuarios_si_requerido():
    """Migra la tabla usuarios para soportar los 8 roles de la monografía de forma atómica y segura."""
    raw_conn = sqlite3.connect(DATABASE, timeout=20)
    try:
        raw_conn.execute("PRAGMA foreign_keys = OFF")
        row = raw_conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='usuarios'").fetchone()
        if row and row[0] and "'contabilidad'" not in row[0]:
            raw_conn.execute("""CREATE TABLE IF NOT EXISTS usuarios_temp (
                id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT NOT NULL UNIQUE,
                nombre TEXT NOT NULL, password_hash TEXT NOT NULL,
                rol TEXT NOT NULL DEFAULT 'vendedor' CHECK (rol IN ('admin','rrhh','vendedor','bodega','contabilidad','compras','supervisor','auditor')),
                empleado_id INTEGER,
                activo INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0,1)),
                creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (empleado_id) REFERENCES empleados(id))""")
            raw_conn.execute("""INSERT INTO usuarios_temp (id, usuario, nombre, password_hash, rol, empleado_id, activo, creado_en)
                                SELECT id, usuario, nombre, password_hash, rol, empleado_id, activo, creado_en FROM usuarios""")
            raw_conn.execute("DROP TABLE usuarios")
            raw_conn.execute("ALTER TABLE usuarios_temp RENAME TO usuarios")
            raw_conn.commit()
    finally:
        raw_conn.close()


def _adecuar_inventario_tecnologico(conn):
    """
    Adecua la base de datos exclusivamente para productos tecnológicos:
    1. Elimina productos no tecnológicos (calzado, mochilas, vestimenta) y sus registros dependientes.
    2. Elimina categorías, marcas y tipos que no correspondan al giro de tecnología.
    3. Carga categorías, marcas y tipos del sector de computación y electrónica.
    4. Actualiza productos tecnológicos existentes y precarga un catálogo representativo con SKU, modelos y garantías.
    """
    # 1. Identificar y eliminar productos no tecnológicos (respetando restricciones de clave foránea)
    rows_eliminar = conn.execute("""
        SELECT id FROM productos 
        WHERE LOWER(nombre) LIKE '%mochila%' 
           OR LOWER(nombre) LIKE '%zapato%' 
           OR LOWER(nombre) LIKE '%tenis%'
           OR LOWER(nombre) LIKE '%pantalon%'
           OR LOWER(nombre) LIKE '%camisa%'
           OR LOWER(nombre) LIKE '%sandalia%'
           OR id IN (1, 2)
    """).fetchall()
    ids_no_tech = [r["id"] for r in rows_eliminar]
    
    if ids_no_tech:
        placeholders = ",".join("?" for _ in ids_no_tech)
        conn.execute(f"DELETE FROM garantias WHERE producto_id IN ({placeholders})", ids_no_tech)
        conn.execute(f"DELETE FROM movimientos_inventario WHERE producto_id IN ({placeholders})", ids_no_tech)
        conn.execute(f"DELETE FROM detalle_ventas WHERE producto_id IN ({placeholders})", ids_no_tech)
        conn.execute("DELETE FROM solicitudes_anulacion WHERE venta_id NOT IN (SELECT DISTINCT venta_id FROM detalle_ventas)")
        conn.execute("DELETE FROM ventas WHERE id NOT IN (SELECT DISTINCT venta_id FROM detalle_ventas)")
        conn.execute(f"DELETE FROM productos WHERE id IN ({placeholders})", ids_no_tech)
    
    # 2. Limpieza general de dependencias huérfanas
    conn.execute("DELETE FROM movimientos_inventario WHERE producto_id NOT IN (SELECT id FROM productos)")
    conn.execute("DELETE FROM garantias WHERE producto_id NOT IN (SELECT id FROM productos)")
    conn.execute("DELETE FROM detalle_ventas WHERE producto_id NOT IN (SELECT id FROM productos)")
    conn.execute("DELETE FROM solicitudes_anulacion WHERE venta_id NOT IN (SELECT DISTINCT venta_id FROM detalle_ventas)")
    conn.execute("DELETE FROM ventas WHERE id NOT IN (SELECT DISTINCT venta_id FROM detalle_ventas)")

    # 3. Eliminar marcas, tipos y categorías no tecnológicas
    conn.execute("""
        DELETE FROM marcas 
        WHERE LOWER(nombre) IN ('nike', 'adidas', 'puma', 'reebok', 'vans', 'converse', 'zara')
    """)
    conn.execute("""
        DELETE FROM tipos 
        WHERE LOWER(nombre) IN ('mochila', 'zapatos', 'calzado', 'ropa', 'camisa', 'pantalon', 'bolso')
    """)
    conn.execute("""
        DELETE FROM categorias 
        WHERE LOWER(nombre) IN ('zapateria', 'calzado', 'ropa', 'vestimenta', 'moda')
    """)

    # 4. Sembrar categorías tecnológicas
    categorias_tech = [
        "Laptops & Portátiles",
        "Computadoras & Servidores",
        "Smartphones & Tablets",
        "Componentes & Hardware",
        "Periféricos & Accesorios",
        "Monitores & Pantallas",
        "Almacenamiento & Memorias",
        "Redes & Conectividad",
        "Audio, Video & Streaming"
    ]
    for cat in categorias_tech:
        conn.execute("INSERT OR IGNORE INTO categorias (nombre, activo) VALUES (?, 1)", (cat,))

    # 5. Sembrar marcas tecnológicas líderes
    marcas_tech = [
        "Dell", "HP", "Lenovo", "Apple", "Asus", "Acer", "Samsung",
        "Xiaomi", "Logitech", "Kingston", "Corsair", "TP-Link", "Sony",
        "Intel", "AMD", "NVIDIA"
    ]
    for marca in marcas_tech:
        conn.execute("INSERT OR IGNORE INTO marcas (nombre, activo) VALUES (?, 1)", (marca,))

    # 6. Sembrar tipos de artículos tecnológicos
    tipos_tech = [
        "Laptop Ultrabook",
        "Laptop Gamer",
        "PC de Escritorio",
        "Smartphone",
        "Tablet",
        "Monitor LED / IPS",
        "Teclado Mecánico",
        "Mouse Óptico / Gamer",
        "Disco SSD NVMe",
        "Memoria RAM DDR4 / DDR5",
        "Tarjeta Gráfica (GPU)",
        "Procesador (CPU)",
        "Router Wi-Fi / Mesh",
        "Switch de Red",
        "Auriculares / Headset",
        "Webcam Full HD",
        "Impresora Multifuncional"
    ]
    for tipo in tipos_tech:
        conn.execute("INSERT OR IGNORE INTO tipos (nombre, activo) VALUES (?, 1)", (tipo,))

    # 7. Mapeos de IDs de categorías, marcas y tipos
    cat_map = {r["nombre"]: r["id"] for r in conn.execute("SELECT id, nombre FROM categorias").fetchall()}
    marca_map = {r["nombre"]: r["id"] for r in conn.execute("SELECT id, nombre FROM marcas").fetchall()}
    tipo_map = {r["nombre"]: r["id"] for r in conn.execute("SELECT id, nombre FROM tipos").fetchall()}

    # 8. Adecuar producto tecnológico existente (ID 801 - Laptop Gamer Pro)
    cat_lap = cat_map.get("Laptops & Portátiles", 1)
    mar_asus = marca_map.get("Asus", 1)
    tip_gamer = tipo_map.get("Laptop Gamer", 1)
    conn.execute("""
        UPDATE productos 
        SET categoria_id = ?, marca_id = ?, tipo_id = ?,
            modelo = CASE WHEN modelo IS NULL OR modelo = '' THEN 'ROG Strix G16 - G614' ELSE modelo END,
            descripcion = CASE WHEN descripcion IS NULL OR descripcion = '' THEN 'Laptop Gamer ASUS ROG Strix G16. Pantalla 16" FHD+ 165Hz, Intel Core i7-13650HX, 16GB RAM DDR5, 512GB SSD PCIe 4.0, NVIDIA GeForce RTX 4060 8GB GDDR6.' ELSE descripcion END,
            meses_garantia = CASE WHEN meses_garantia IS NULL OR meses_garantia <= 0 THEN 12 ELSE meses_garantia END
        WHERE id = 801 OR codigo = 'TEST-GAR-01'
    """, (cat_lap, mar_asus, tip_gamer))

    # 9. Cargar catálogo de productos tecnológicos si el catálogo actual tiene pocos artículos
    total_prods = conn.execute("SELECT COUNT(*) FROM productos WHERE activo = 1").fetchone()[0]
    if total_prods <= 1:
        catalogo_inicial = [
            {
                "codigo": "TEC-LAP-001",
                "nombre": "Laptop Lenovo ThinkPad E14 Gen 5",
                "modelo": "ThinkPad E14 Gen 5 (21EY000CLM)",
                "descripcion": "AMD Ryzen 5 7530U (6C/12T hasta 4.5GHz), 16GB RAM DDR4 3200MHz, 512GB SSD NVMe M.2, Pantalla 14\" FHD IPS Antirreflejo, Teclado retroiluminado resistente a salpicaduras, Windows 11 Pro.",
                "categoria": "Laptops & Portátiles",
                "marca": "Lenovo",
                "tipo": "Laptop Ultrabook",
                "precio_compra": 18500.0,
                "precio_venta": 23900.0,
                "existencia": 12,
                "stock_minimo": 3,
                "meses_garantia": 12
            },
            {
                "codigo": "TEC-LAP-002",
                "nombre": "Laptop Dell Inspiron 3520 15.6\"",
                "modelo": "Inspiron 3520 (I3520-5832BLK)",
                "descripcion": "Intel Core i5-1235U (10 núcleos, 12 hilos), 16GB RAM DDR4, Disco 512GB SSD PCIe NVMe, Pantalla 15.6\" FHD 120Hz, Gráficos Intel Iris Xe, Windows 11 Home.",
                "categoria": "Laptops & Portátiles",
                "marca": "Dell",
                "tipo": "Laptop Ultrabook",
                "precio_compra": 16000.0,
                "precio_venta": 20500.0,
                "existencia": 15,
                "stock_minimo": 4,
                "meses_garantia": 12
            },
            {
                "codigo": "TEC-LAP-003",
                "nombre": "MacBook Air 13\" Apple M2",
                "modelo": "MacBook Air M2 (MLXY3LL/A)",
                "descripcion": "Chip Apple M2 CPU 8 núcleos y GPU 8 núcleos, 8GB RAM Unificada, 256GB SSD ultrarrápido, Pantalla Liquid Retina de 13.6\" True Tone, Cámara FaceTime HD 1080p, Batería hasta 18 horas.",
                "categoria": "Laptops & Portátiles",
                "marca": "Apple",
                "tipo": "Laptop Ultrabook",
                "precio_compra": 34000.0,
                "precio_venta": 41500.0,
                "existencia": 8,
                "stock_minimo": 2,
                "meses_garantia": 12
            },
            {
                "codigo": "TEC-TEL-001",
                "nombre": "Smartphone Samsung Galaxy A54 5G 128GB",
                "modelo": "Galaxy A54 5G (SM-A546E/DS)",
                "descripcion": "Pantalla 6.4\" Super AMOLED 120Hz FHD+, 8GB RAM + 128GB Almacenamiento, Cámara triple 50MP OIS + 12MP + 5MP, Batería 5000mAh con Carga Rápida 25W, Protección IP67 contra agua y polvo.",
                "categoria": "Smartphones & Tablets",
                "marca": "Samsung",
                "tipo": "Smartphone",
                "precio_compra": 10500.0,
                "precio_venta": 13900.0,
                "existencia": 18,
                "stock_minimo": 5,
                "meses_garantia": 12
            },
            {
                "codigo": "TEC-TEL-002",
                "nombre": "Smartphone Xiaomi Redmi Note 13 Pro 256GB",
                "modelo": "Redmi Note 13 Pro 4G",
                "descripcion": "Cámara principal de 200MP con OIS, Pantalla AMOLED 6.67\" 120Hz FHD+, MediaTek Helio G99 Ultra, 8GB RAM + 256GB Almacenamiento, Batería 5000mAh con Turbo Carga de 67W.",
                "categoria": "Smartphones & Tablets",
                "marca": "Xiaomi",
                "tipo": "Smartphone",
                "precio_compra": 7800.0,
                "precio_venta": 10200.0,
                "existencia": 20,
                "stock_minimo": 5,
                "meses_garantia": 12
            },
            {
                "codigo": "TEC-MON-001",
                "nombre": "Monitor Gamer ASUS TUF Gaming VG249Q1A 24\"",
                "modelo": "TUF Gaming VG249Q1A",
                "descripcion": "Pantalla 23.8\" Full HD (1920x1080) IPS, 165Hz (Overclocked), 1ms MPRT, FreeSync Premium, Extreme Low Motion Blur (ELMB), Shadow Boost, Altavoces estéreo 2W x 2 integrados.",
                "categoria": "Monitores & Pantallas",
                "marca": "Asus",
                "tipo": "Monitor LED / IPS",
                "precio_compra": 5200.0,
                "precio_venta": 6900.0,
                "existencia": 10,
                "stock_minimo": 3,
                "meses_garantia": 24
            },
            {
                "codigo": "TEC-PER-001",
                "nombre": "Mouse Inalámbrico Logitech MX Master 3S",
                "modelo": "MX Master 3S (910-006557)",
                "descripcion": "Sensor óptico Darkfield 8000 DPI sobre cualquier superficie (incluso cristal), Clics 90% silenciosos, Rueda electromagnética MagSpeed, Conectividad Logi Bolt y Bluetooth multipunto.",
                "categoria": "Periféricos & Accesorios",
                "marca": "Logitech",
                "tipo": "Mouse Óptico / Gamer",
                "precio_compra": 3100.0,
                "precio_venta": 4200.0,
                "existencia": 14,
                "stock_minimo": 4,
                "meses_garantia": 12
            },
            {
                "codigo": "TEC-PER-002",
                "nombre": "Teclado Mecánico Corsair K55 RGB PRO",
                "modelo": "K55 RGB PRO (CH-9226765-SP)",
                "descripcion": "Retroiluminación RGB dinámica por zonas, 6 teclas macro dedicadas con integración Elgato Stream Deck, Resistencia IP42 al polvo y derrames, Reposamuñecas extraíble.",
                "categoria": "Periféricos & Accesorios",
                "marca": "Corsair",
                "tipo": "Teclado Mecánico",
                "precio_compra": 1800.0,
                "precio_venta": 2550.0,
                "existencia": 16,
                "stock_minimo": 3,
                "meses_garantia": 12
            },
            {
                "codigo": "TEC-ALM-001",
                "nombre": "SSD Kingston KC3000 PCIe 4.0 NVMe M.2 1TB",
                "modelo": "KC3000 M.2 2280 (SKC3000S/1024G)",
                "descripcion": "Controlador Phison E18 NVMe. Velocidades de lectura hasta 7,000 MB/s y escritura 6,000 MB/s. Disipador térmico de aluminio y grafeno de bajo perfil.",
                "categoria": "Almacenamiento & Memorias",
                "marca": "Kingston",
                "tipo": "Disco SSD NVMe",
                "precio_compra": 2900.0,
                "precio_venta": 3950.0,
                "existencia": 25,
                "stock_minimo": 6,
                "meses_garantia": 36
            },
            {
                "codigo": "TEC-MEM-001",
                "nombre": "Memoria RAM Kingston Fury Beast 16GB DDR4 3200MHz",
                "modelo": "Fury Beast DDR4 (KF432C16BB/16)",
                "descripcion": "Módulo 16GB DDR4 3200 MT/s, Latencia CL16, Disipador negro de perfil bajo, Soporte Intel XMP 2.0 y AMD Ryzen.",
                "categoria": "Componentes & Hardware",
                "marca": "Kingston",
                "tipo": "Memoria RAM DDR4 / DDR5",
                "precio_compra": 1300.0,
                "precio_venta": 1850.0,
                "existencia": 30,
                "stock_minimo": 8,
                "meses_garantia": 24
            },
            {
                "codigo": "TEC-RED-001",
                "nombre": "Router Wi-Fi 6 TP-Link Archer AX53 AX3000",
                "modelo": "Archer AX53 Gigabit",
                "descripcion": "Doble Banda Wi-Fi 6 (2402 Mbps en 5GHz + 574 Mbps en 2.4GHz), 4 antenas de alta ganancia Beamforming, Procesador Dual-Core, Seguridad TP-Link HomeShield, Soporte EasyMesh.",
                "categoria": "Redes & Conectividad",
                "marca": "TP-Link",
                "tipo": "Router Wi-Fi / Mesh",
                "precio_compra": 2200.0,
                "precio_venta": 3100.0,
                "existencia": 15,
                "stock_minimo": 4,
                "meses_garantia": 12
            },
            {
                "codigo": "TEC-AUD-001",
                "nombre": "Audífonos Inalámbricos Sony WH-1000XM5 Noise Cancelling",
                "modelo": "WH-1000XM5 Black",
                "descripcion": "Cancelación activa de ruido con dos procesadores y 8 micrófonos. Audio Hi-Res LDAC, 30 horas de batería, Carga ultrarrápida, Conexión multipunto Bluetooth 5.2.",
                "categoria": "Audio, Video & Streaming",
                "marca": "Sony",
                "tipo": "Auriculares / Headset",
                "precio_compra": 11500.0,
                "precio_venta": 14900.0,
                "existencia": 9,
                "stock_minimo": 2,
                "meses_garantia": 12
            },
            {
                "codigo": "TEC-GPU-001",
                "nombre": "Tarjeta Gráfica ASUS Dual GeForce RTX 4060 OC 8GB",
                "modelo": "DUAL-RTX4060-O8G",
                "descripcion": "Arquitectura NVIDIA Ada Lovelace, 8GB GDDR6 128-bit, DLSS 3, Ray Tracing 3ra gen, Doble ventilador Axial-tech con rodamientos dobles, Placa trasera protectora de aluminio.",
                "categoria": "Componentes & Hardware",
                "marca": "Asus",
                "tipo": "Tarjeta Gráfica (GPU)",
                "precio_compra": 12800.0,
                "precio_venta": 16500.0,
                "existencia": 7,
                "stock_minimo": 2,
                "meses_garantia": 24
            }
        ]

        for item in catalogo_inicial:
            c_id = cat_map.get(item["categoria"], 1)
            m_id = marca_map.get(item["marca"], 1)
            t_id = tipo_map.get(item["tipo"], 1)
            
            cur = conn.execute("""
                INSERT OR IGNORE INTO productos (
                    codigo, nombre, descripcion, modelo, categoria_id, marca_id, tipo_id,
                    precio_compra, precio_venta, existencia, stock_minimo, meses_garantia, activo
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (
                item["codigo"], item["nombre"], item["descripcion"], item["modelo"],
                c_id, m_id, t_id, item["precio_compra"], item["precio_venta"],
                item["existencia"], item["stock_minimo"], item["meses_garantia"]
            ))
            
            if cur.rowcount > 0:
                p_id = cur.lastrowid
                conn.execute("""
                    INSERT INTO movimientos_inventario (
                        producto_id, tipo, cantidad, existencia_anterior, existencia_posterior,
                        referencia, nota, fecha
                    ) VALUES (?, 'entrada', ?, 0, ?, 'Inventario Inicial', 'Alta de catálogo tecnológico', CURRENT_TIMESTAMP)
                """, (p_id, item["existencia"], item["existencia"]))


def init_db():
    """Crea y actualiza el esquema local sin eliminar datos existentes."""
    _migrar_roles_usuarios_si_requerido()
    with get_db() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""CREATE TABLE IF NOT EXISTS cargos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL
        )""")
        _agregar_columna_si_falta(conn, "cargos", "activo", "INTEGER NOT NULL DEFAULT 1")
        
        conn.executemany("INSERT OR IGNORE INTO cargos (nombre) VALUES (?)",
                         [("Administrador",), ("Vendedor",), ("Bodega",), ("RRHH",)])
                         
        conn.execute("""CREATE TABLE IF NOT EXISTS departamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            activo INTEGER NOT NULL DEFAULT 1
        )""")
        conn.executemany("INSERT OR IGNORE INTO departamentos (nombre) VALUES (?)",
                         [("Ventas",), ("TI",), ("Administración",), ("Operaciones",)])
                         
        conn.execute("""CREATE TABLE IF NOT EXISTS empleados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cedula TEXT UNIQUE NOT NULL,
            nombre TEXT,                     -- backup full name
            primer_nombre TEXT,
            segundo_nombre TEXT,
            primer_apellido TEXT,
            segundo_apellido TEXT,
            cargo_id INTEGER NOT NULL,
            numero_inss TEXT,
            departamento TEXT,
            departamento_id INTEGER,
            fecha_ingreso TEXT,
            salario_base REAL DEFAULT 0.0,
            activo INTEGER DEFAULT 1 CHECK (activo IN (0, 1)),
            FOREIGN KEY (cargo_id) REFERENCES cargos(id),
            FOREIGN KEY (departamento_id) REFERENCES departamentos(id)
        )""")
        
        # Migraciones obligatorias para SQLite antiguo:
        for col in ["primer_nombre", "segundo_nombre", "primer_apellido", "segundo_apellido"]:
            _agregar_columna_si_falta(conn, "empleados", col, "TEXT")
        _agregar_columna_si_falta(conn, "empleados", "cargo_id", "INTEGER DEFAULT 1")
        _agregar_columna_si_falta(conn, "empleados", "departamento_id", "INTEGER")
        
        conn.execute("""CREATE TABLE IF NOT EXISTS planilla (
            id INTEGER PRIMARY KEY AUTOINCREMENT, empleado_id INTEGER NOT NULL,
            fecha TEXT DEFAULT CURRENT_TIMESTAMP, salario_base REAL NOT NULL, horas_extras REAL DEFAULT 0,
            pago_horas_extras REAL DEFAULT 0, salario_bruto REAL NOT NULL, inss_laboral REAL NOT NULL,
            inss_laboral_tasa REAL, ir_laboral REAL NOT NULL, inss_patronal REAL NOT NULL,
            inss_patronal_tasa REAL, salario_neto REAL NOT NULL,
            FOREIGN KEY (empleado_id) REFERENCES empleados (id))""")
        _agregar_columna_si_falta(conn, "planilla", "firma_text", "TEXT")
        _agregar_columna_si_falta(conn, "planilla", "inss_patronal_tasa", "REAL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_planilla_empleado_fecha ON planilla (empleado_id, fecha)")
        
        # Integración de esquema de Pagos Diferidos, Contratos y Aguinaldo
        import payroll_module
        payroll_module.GestorPlanillaDiferida().asegurar_esquema(conn)
        
        conn.execute("""CREATE TABLE IF NOT EXISTS categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            activo INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0,1))
        )""")
        conn.execute("INSERT OR IGNORE INTO categorias (id, nombre) VALUES (1, 'General')")

        conn.execute("""CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT NOT NULL UNIQUE,
            nombre TEXT NOT NULL, password_hash TEXT NOT NULL,
            rol TEXT NOT NULL DEFAULT 'vendedor' CHECK (rol IN ('admin','rrhh','vendedor','bodega','contabilidad','compras','supervisor','auditor')),
            empleado_id INTEGER,
            activo INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0,1)),
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (empleado_id) REFERENCES empleados(id))""")
            
        conn.execute("""CREATE TABLE IF NOT EXISTS marcas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL
        )""")
        _agregar_columna_si_falta(conn, "marcas", "activo", "INTEGER NOT NULL DEFAULT 1")
        
        conn.execute("""CREATE TABLE IF NOT EXISTS tipos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL
        )""")
        _agregar_columna_si_falta(conn, "tipos", "activo", "INTEGER NOT NULL DEFAULT 1")
        conn.execute("""CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, codigo TEXT NOT NULL UNIQUE,
            nombre TEXT NOT NULL, descripcion TEXT DEFAULT '', 
            categoria_id INTEGER DEFAULT 1,
            marca_id INTEGER DEFAULT 1,
            tipo_id INTEGER DEFAULT 1,
            precio_compra REAL NOT NULL DEFAULT 0 CHECK (precio_compra >= 0),
            precio_venta REAL NOT NULL CHECK (precio_venta >= 0),
            existencia INTEGER NOT NULL DEFAULT 0 CHECK (existencia >= 0),
            stock_minimo INTEGER NOT NULL DEFAULT 0 CHECK (stock_minimo >= 0),
            activo INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0,1)),
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (categoria_id) REFERENCES categorias(id),
            FOREIGN KEY (marca_id) REFERENCES marcas(id),
            FOREIGN KEY (tipo_id) REFERENCES tipos(id)
        )""")
        _agregar_columna_si_falta(conn, "productos", "marca_id", "INTEGER DEFAULT 1")
        _agregar_columna_si_falta(conn, "productos", "tipo_id", "INTEGER DEFAULT 1")
        _agregar_columna_si_falta(conn, "productos", "meses_garantia", "INTEGER NOT NULL DEFAULT 12")
        _agregar_columna_si_falta(conn, "productos", "modelo", "TEXT DEFAULT ''")
        
        # add foreign key defaults rows if needed (optional)
        conn.executemany("INSERT OR IGNORE INTO marcas (nombre) VALUES (?)", [("Sin Marca",)])
        conn.executemany("INSERT OR IGNORE INTO tipos (nombre) VALUES (?)", [("Sin Tipo",)])
        
        # Adecuar la base de datos exclusivamente para productos tecnológicos
        _adecuar_inventario_tecnologico(conn)
            
        conn.execute("""CREATE TABLE IF NOT EXISTS movimientos_inventario (
            id INTEGER PRIMARY KEY AUTOINCREMENT, producto_id INTEGER NOT NULL,
            tipo TEXT NOT NULL CHECK (tipo IN ('entrada','ajuste','venta','devolucion','anulacion')),
            cantidad INTEGER NOT NULL, existencia_anterior INTEGER NOT NULL,
            existencia_posterior INTEGER NOT NULL, referencia TEXT, nota TEXT,
            usuario_id INTEGER, fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (producto_id) REFERENCES productos(id),
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id))""")
            
        conn.execute("""CREATE TABLE IF NOT EXISTS ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            cliente TEXT DEFAULT '', usuario_id INTEGER NOT NULL,
            subtotal REAL NOT NULL DEFAULT 0, total REAL NOT NULL DEFAULT 0,
            estado TEXT NOT NULL DEFAULT 'completada' CHECK (estado IN ('completada','anulada','devuelta','pendiente_anulacion','pendiente_devolucion')),
            motivo_anulacion TEXT DEFAULT '', FOREIGN KEY (usuario_id) REFERENCES usuarios(id))""")
            
        conn.execute("""CREATE TABLE IF NOT EXISTS detalle_ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, venta_id INTEGER NOT NULL, producto_id INTEGER NOT NULL,
            cantidad INTEGER NOT NULL CHECK (cantidad > 0), precio_unitario REAL NOT NULL,
            subtotal REAL NOT NULL, FOREIGN KEY (venta_id) REFERENCES ventas(id),
            FOREIGN KEY (producto_id) REFERENCES productos(id))""")
            
        conn.execute("""CREATE TABLE IF NOT EXISTS solicitudes_anulacion (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            venta_id INTEGER NOT NULL,
            tipo TEXT NOT NULL CHECK (tipo IN ('anulacion','devolucion')),
            usuario_solicita_id INTEGER NOT NULL, 
            motivo TEXT NOT NULL, 
            estado TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente','aprobada','rechazada')), 
            usuario_autoriza_id INTEGER,
            fecha_solicitud TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            fecha_resolucion TEXT,
            FOREIGN KEY (venta_id) REFERENCES ventas(id),
            FOREIGN KEY (usuario_solicita_id) REFERENCES usuarios(id),
            FOREIGN KEY (usuario_autoriza_id) REFERENCES usuarios(id)
        )""")
            
        conn.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_producto_fecha ON movimientos_inventario(producto_id, fecha)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ventas_fecha ON ventas(fecha)")

        conn.execute("""CREATE TABLE IF NOT EXISTS garantias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL UNIQUE,
            venta_id INTEGER NOT NULL,
            detalle_venta_id INTEGER,
            producto_id INTEGER NOT NULL,
            cliente TEXT DEFAULT '',
            fecha_inicio TEXT NOT NULL,
            fecha_vencimiento TEXT NOT NULL,
            meses_cobertura INTEGER NOT NULL DEFAULT 6,
            numero_serie TEXT DEFAULT '',
            estado TEXT NOT NULL DEFAULT 'activa' CHECK (estado IN ('activa', 'vencida', 'ejecutada', 'anulada')),
            fecha_ejecucion TEXT,
            usuario_ejecuta_id INTEGER,
            tipo_resolucion TEXT CHECK (tipo_resolucion IN ('reemplazo', 'reparacion', 'reembolso', 'otro') OR tipo_resolucion IS NULL),
            motivo_reclamo TEXT DEFAULT '',
            diagnostico TEXT DEFAULT '',
            resolucion_notas TEXT DEFAULT '',
            motivo_anulacion TEXT DEFAULT '',
            fecha_anulacion TEXT,
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (venta_id) REFERENCES ventas(id),
            FOREIGN KEY (detalle_venta_id) REFERENCES detalle_ventas(id),
            FOREIGN KEY (producto_id) REFERENCES productos(id),
            FOREIGN KEY (usuario_ejecuta_id) REFERENCES usuarios(id)
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_garantias_venta ON garantias(venta_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_garantias_producto ON garantias(producto_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_garantias_estado ON garantias(estado)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_garantias_fecha_vencimiento ON garantias(fecha_vencimiento)")

        # Backfill inicial si la tabla garantias está vacía y existen ventas previas
        total_gar = conn.execute("SELECT COUNT(*) FROM garantias").fetchone()[0]
        if total_gar == 0:
            ventas_previas = conn.execute("SELECT id, cliente, fecha, estado, motivo_anulacion FROM ventas ORDER BY id ASC").fetchall()
            for v in ventas_previas:
                detalles = conn.execute("SELECT id, producto_id, cantidad FROM detalle_ventas WHERE venta_id=?", (v["id"],)).fetchall()
                for d in detalles:
                    prod = conn.execute("SELECT meses_garantia FROM productos WHERE id=?", (d["producto_id"],)).fetchone()
                    meses = prod["meses_garantia"] if (prod and prod["meses_garantia"] is not None) else 6
                    if meses > 0:
                        f_ini = v["fecha"][:10] if v["fecha"] else datetime.now().strftime("%Y-%m-%d")
                        f_fin = sumar_meses(f_ini, meses).isoformat()
                        cant = int(d["cantidad"])
                        for unit in range(1, cant + 1):
                            cod = f"GAR-{v['id']:04d}-{d['producto_id']:03d}-{unit:02d}"
                            if v["estado"] in ("anulada", "devuelta"):
                                est_g = "anulada"
                                mot_anul = f"Venta {v['estado']}: {v['motivo_anulacion'] or 'Devolución/anulación de venta'}"
                            elif f_fin < datetime.now().strftime("%Y-%m-%d"):
                                est_g = "vencida"
                                mot_anul = ""
                            else:
                                est_g = "activa"
                                mot_anul = ""

                            conn.execute("""
                                INSERT OR IGNORE INTO garantias (
                                    codigo, venta_id, detalle_venta_id, producto_id, cliente,
                                    fecha_inicio, fecha_vencimiento, meses_cobertura, estado, motivo_anulacion
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                cod, v["id"], d["id"], d["producto_id"], v["cliente"] or "Consumidor Final",
                                f_ini, f_fin, meses, est_g, mot_anul
                            ))

        # Tabla de registro y control de Vacaciones Gozadas (Art. 76 Ley 185)
        conn.execute("""CREATE TABLE IF NOT EXISTS vacaciones_gozadas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empleado_id INTEGER NOT NULL,
            fecha_inicio TEXT NOT NULL,
            fecha_fin TEXT NOT NULL,
            dias_gozados REAL NOT NULL CHECK (dias_gozados > 0),
            observaciones TEXT DEFAULT '',
            estado TEXT NOT NULL DEFAULT 'aprobada' CHECK (estado IN ('pendiente', 'aprobada', 'rechazada')),
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            usuario_id INTEGER,
            FOREIGN KEY (empleado_id) REFERENCES empleados(id),
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_vacaciones_empleado ON vacaciones_gozadas(empleado_id)")

        # Tabla de Liquidaciones Laborales (Despido / Renuncia - Ley 185 y Ley 476)
        conn.execute("""CREATE TABLE IF NOT EXISTS liquidaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL UNIQUE,
            empleado_id INTEGER NOT NULL,
            fecha_ingreso TEXT NOT NULL,
            fecha_salida TEXT NOT NULL,
            salario_base_mensual REAL NOT NULL,
            salario_diario REAL NOT NULL,
            motivo TEXT NOT NULL CHECK (motivo IN ('despido', 'renuncia')),
            regimen TEXT NOT NULL DEFAULT 'privada' CHECK (regimen IN ('privada', 'publica')),
            anios_servicio INTEGER NOT NULL DEFAULT 0,
            meses_servicio INTEGER NOT NULL DEFAULT 0,
            dias_servicio INTEGER NOT NULL DEFAULT 0,
            total_dias_trabajados INTEGER NOT NULL DEFAULT 0,
            dias_salario_pendiente REAL NOT NULL DEFAULT 0,
            monto_salario_pendiente REAL NOT NULL DEFAULT 0,
            inss_salario_pendiente REAL NOT NULL DEFAULT 0,
            dias_vacaciones_pendientes REAL NOT NULL DEFAULT 0,
            monto_vacaciones REAL NOT NULL DEFAULT 0,
            dias_aguinaldo_proporcional REAL NOT NULL DEFAULT 0,
            monto_aguinaldo REAL NOT NULL DEFAULT 0,
            aplica_indemnizacion INTEGER NOT NULL DEFAULT 1 CHECK (aplica_indemnizacion IN (0, 1)),
            meses_indemnizacion REAL NOT NULL DEFAULT 0,
            monto_indemnizacion REAL NOT NULL DEFAULT 0,
            otras_deducciones REAL NOT NULL DEFAULT 0,
            motivo_deducciones TEXT DEFAULT '',
            total_bruto REAL NOT NULL DEFAULT 0,
            total_deducciones REAL NOT NULL DEFAULT 0,
            total_neto REAL NOT NULL DEFAULT 0,
            estado TEXT NOT NULL DEFAULT 'registrada' CHECK (estado IN ('borrador', 'registrada', 'pagada', 'anulada')),
            observaciones TEXT DEFAULT '',
            usuario_id INTEGER,
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (empleado_id) REFERENCES empleados(id),
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_liquidaciones_emp ON liquidaciones(empleado_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_liquidaciones_fecha ON liquidaciones(fecha_salida)")



def registrar_movimiento(conn, producto_id, tipo, cantidad, usuario_id=None, referencia=None, nota=""):
    """Actualiza existencias y deja una traza auditable del cambio."""
    producto = conn.execute("SELECT existencia FROM productos WHERE id = ?", (producto_id,)).fetchone()
    if producto is None:
        raise ValueError("El producto seleccionado no existe.")
    anterior, posterior = producto["existencia"], producto["existencia"] + cantidad
    if posterior < 0:
        raise ValueError("Existencias insuficientes para completar la operación.")
    conn.execute("UPDATE productos SET existencia = ? WHERE id = ?", (posterior, producto_id))
    conn.execute("""INSERT INTO movimientos_inventario
        (producto_id, tipo, cantidad, existencia_anterior, existencia_posterior, referencia, nota, usuario_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (producto_id, tipo, cantidad, anterior, posterior, referencia, nota, usuario_id))
    return posterior


def calcular_ir_nicaragua(salario_bruto_mensual, inss_laboral_mensual):
    """Calcula el IR mensual a partir de la proyección anual gravable."""
    base_anual = max(0, salario_bruto_mensual - inss_laboral_mensual) * 12
    if base_anual <= 100000:
        ir_anual = 0.0
    elif base_anual <= 200000:
        ir_anual = (base_anual - 100000) * 0.15
    elif base_anual <= 350000:
        ir_anual = 15000 + (base_anual - 200000) * 0.20
    elif base_anual <= 500000:
        ir_anual = 45000 + (base_anual - 350000) * 0.25
    else:
        ir_anual = 82500 + (base_anual - 500000) * 0.30
    return round(ir_anual / 12, 2)


def calcular_planilla_completa(salario_base, horas_extras=0):
    """Calcula salario, deducciones y aportes con las tasas configuradas arriba."""
    with get_db() as conn:
        total_activos = conn.execute("SELECT COUNT(*) FROM empleados WHERE activo = 1").fetchone()[0]
    tasa_patronal = INSS_PATRONAL_MENOR_50_TASA if total_activos < 50 else INSS_PATRONAL_50_O_MAS_TASA
    pago_horas_extras = horas_extras * (salario_base / HORAS_MENSUALES) * RECARGO_HORA_EXTRA
    salario_bruto = salario_base + pago_horas_extras
    inss_laboral = round(salario_bruto * INSS_LABORAL_TASA, 2)
    inss_patronal = round(salario_bruto * tasa_patronal, 2)
    ir_laboral = calcular_ir_nicaragua(salario_bruto, inss_laboral)
    return {"salario_base": salario_base, "horas_extras": horas_extras,
            "pago_horas_extras": round(pago_horas_extras, 2), "salario_bruto": round(salario_bruto, 2),
            "inss_laboral": inss_laboral, "inss_laboral_tasa": INSS_LABORAL_TASA,
            "ir_laboral": ir_laboral, "inss_patronal": inss_patronal,
            "inss_patronal_tasa": tasa_patronal,
            "salario_neto": round(salario_bruto - inss_laboral - ir_laboral, 2)}


def obtener_empleados_con_ultimo_pago(fecha_desde=None, fecha_hasta=None):
    with get_db() as conn:
        if fecha_desde and fecha_hasta:
            return conn.execute("""SELECT e.*, p.salario_neto, p.salario_bruto, p.inss_laboral, p.ir_laboral, p.fecha AS fecha_pago
                FROM empleados e JOIN planilla p ON p.id = (SELECT MAX(id) FROM planilla WHERE empleado_id = e.id
                AND date(fecha) BETWEEN date(?) AND date(?)) ORDER BY e.activo DESC, e.nombre ASC""", (fecha_desde, fecha_hasta)).fetchall()
        return conn.execute("""SELECT e.*, p.salario_neto, p.salario_bruto, p.inss_laboral, p.ir_laboral, p.fecha AS fecha_pago
            FROM empleados e LEFT JOIN planilla p ON p.id = (SELECT MAX(id) FROM planilla WHERE empleado_id = e.id)
            ORDER BY e.activo DESC, e.nombre ASC""").fetchall()


def obtener_historial_empleado(empleado_id):
    with get_db() as conn:
        return conn.execute("SELECT * FROM planilla WHERE empleado_id = ? ORDER BY id DESC", (empleado_id,)).fetchall()


def obtener_planillas_por_mes(mes):
    """
    Obtiene los registros de nómina para el mes YYYY-MM especificado.
    Incluye:
    1. Períodos de periodos_planilla cuyo año-mes coincide o que tuvieron abonos en ese mes.
    2. Registros históricos de la tabla planilla.
    Garantiza que los pagos parciales y saldos pendientes aparezcan correctamente.
    """
    try:
        anio = int(mes[:4])
        mes_num = int(mes[5:7])
    except (ValueError, TypeError, IndexError):
        return []

    with get_db() as conn:
        # 1. Obtener períodos correspondientes a este mes calendario o con abonos registrados en él
        query_periodos = """
        SELECT 
            p.id,
            p.empleado_id,
            e.nombre,
            e.cedula,
            e.cargo,
            COALESCE(
                (SELECT MAX(t.fecha_pago) FROM transacciones_pago_planilla t WHERE t.periodo_planilla_id = p.id),
                p.fecha_inicio
            ) AS fecha,
            p.salario_base_pactado AS salario_base,
            p.horas_extras,
            p.pago_horas_extras,
            p.salario_bruto,
            p.inss_laboral,
            p.ir_laboral,
            p.inss_patronal,
            p.salario_neto_total AS salario_neto,
            p.total_pagado,
            p.saldo_pendiente,
            p.estado,
            p.descripcion AS periodo_descripcion,
            (SELECT COUNT(*) FROM transacciones_pago_planilla t WHERE t.periodo_planilla_id = p.id) AS num_abonos,
            'periodo' AS origen
        FROM periodos_planilla p
        JOIN empleados e ON e.id = p.empleado_id
        WHERE (p.anio = ? AND p.mes = ?)
           OR p.id IN (
               SELECT DISTINCT periodo_planilla_id 
               FROM transacciones_pago_planilla 
               WHERE strftime('%Y-%m', fecha_pago) = ?
           )
        ORDER BY e.nombre ASC
        """
        periodos_rows = conn.execute(query_periodos, (anio, mes_num, mes)).fetchall()
        empleados_en_periodos = {r["empleado_id"] for r in periodos_rows}

        # 2. Registros históricos de tabla planilla que no colisionen con los períodos
        query_historico = """
        SELECT 
            p.id,
            p.empleado_id,
            e.nombre,
            e.cedula,
            e.cargo,
            p.fecha,
            p.salario_base,
            p.horas_extras,
            p.pago_horas_extras,
            p.salario_bruto,
            p.inss_laboral,
            p.ir_laboral,
            p.inss_patronal,
            p.salario_neto,
            p.salario_neto AS total_pagado,
            0.0 AS saldo_pendiente,
            'pagado_completo' AS estado,
            strftime('Planilla %Y-%m', p.fecha) AS periodo_descripcion,
            1 AS num_abonos,
            'historico' AS origen
        FROM planilla p
        JOIN empleados e ON e.id = p.empleado_id
        WHERE strftime('%Y-%m', p.fecha) = ?
        ORDER BY p.fecha ASC, e.nombre ASC
        """
        historicos_rows = conn.execute(query_historico, (mes,)).fetchall()

        resultado = list(periodos_rows)
        for h in historicos_rows:
            if h["empleado_id"] not in empleados_en_periodos:
                resultado.append(h)

        return resultado


def obtener_transacciones_abonos_por_mes(mes):
    """
    Obtiene todas las transacciones de abonos parciales desembolsados en el mes YYYY-MM.
    """
    with get_db() as conn:
        query = """
        SELECT 
            t.id,
            t.periodo_planilla_id,
            t.empleado_id,
            e.nombre,
            e.cedula,
            e.cargo,
            p.descripcion AS periodo_nombre,
            t.monto,
            t.fecha_pago,
            t.concepto,
            t.metodo_pago,
            t.referencia,
            t.notas,
            t.registrado_por,
            t.fecha_registro
        FROM transacciones_pago_planilla t
        JOIN empleados e ON e.id = t.empleado_id
        JOIN periodos_planilla p ON p.id = t.periodo_planilla_id
        WHERE strftime('%Y-%m', t.fecha_pago) = ?
        ORDER BY t.fecha_pago ASC, t.id ASC
        """
        return conn.execute(query, (mes,)).fetchall()



# =====================================================================
# FUNCIONES AUXILIARES: PAGOS DIFERIDOS Y AGUINALDO
# =====================================================================

def obtener_todos_periodos_planilla(empleado_id=None, estado=None):
    """Obtiene períodos de planilla registrados con datos del colaborador y porcentaje pagado."""
    with get_db() as conn:
        query = """
        SELECT p.*, e.nombre, e.cedula, e.cargo,
               ROUND((p.total_pagado * 100.0) / CASE WHEN p.salario_neto_total > 0 THEN p.salario_neto_total ELSE 1 END, 1) AS porcentaje_pagado
        FROM periodos_planilla p
        JOIN empleados e ON e.id = p.empleado_id
        WHERE 1=1
        """
        params = []
        if empleado_id:
            query += " AND p.empleado_id = ?"
            params.append(empleado_id)
        if estado:
            query += " AND p.estado = ?"
            params.append(estado)
        query += " ORDER BY p.anio DESC, p.mes DESC, e.nombre ASC"
        return conn.execute(query, params).fetchall()


def obtener_periodo_con_transacciones(periodo_id):
    """Obtiene un período específico junto con su lista de pagos diferidos/abonos."""
    with get_db() as conn:
        periodo = conn.execute("""
        SELECT p.*, e.nombre, e.cedula, e.cargo, e.salario_base AS salario_base_emp,
               ROUND((p.total_pagado * 100.0) / CASE WHEN p.salario_neto_total > 0 THEN p.salario_neto_total ELSE 1 END, 1) AS porcentaje_pagado
        FROM periodos_planilla p
        JOIN empleados e ON e.id = p.empleado_id
        WHERE p.id = ?
        """, (periodo_id,)).fetchone()
        
        if not periodo:
            return None, []
            
        transacciones = conn.execute("""
        SELECT t.*, u.usuario AS usuario_login
        FROM transacciones_pago_planilla t
        LEFT JOIN usuarios u ON u.id = t.usuario_id
        WHERE t.periodo_planilla_id = ?
        ORDER BY t.fecha_pago ASC, t.id ASC
        """, (periodo_id,)).fetchall()
        
        return periodo, transacciones


def obtener_todos_empleados():
    """Obtiene el listado completo de empleados activos e inactivos."""
    with get_db() as conn:
        return conn.execute("SELECT * FROM empleados ORDER BY activo DESC, nombre ASC").fetchall()


def sumar_meses(fecha_base, meses):
    """Suma un número de meses a una fecha asegurando días válidos de fin de mes."""
    if isinstance(fecha_base, str):
        fecha_base = datetime.strptime(fecha_base[:10], "%Y-%m-%d").date()
    elif isinstance(fecha_base, datetime):
        fecha_base = fecha_base.date()
        
    anio = fecha_base.year + (fecha_base.month + meses - 1) // 12
    mes = (fecha_base.month + meses - 1) % 12 + 1
    max_dias = calendar.monthrange(anio, mes)[1]
    dia = min(fecha_base.day, max_dias)
    return date(anio, mes, dia)


def crear_garantias_para_venta(conn, venta_id, cliente="", fecha_venta=None):
    """Crea registros de garantía automáticamente para cada unidad de los productos vendidos que tengan garantía."""
    detalles = conn.execute("""
        SELECT d.id AS detalle_id, d.producto_id, d.cantidad, p.meses_garantia, p.nombre
        FROM detalle_ventas d
        JOIN productos p ON p.id = d.producto_id
        WHERE d.venta_id = ?
    """, (venta_id,)).fetchall()

    if not fecha_venta:
        venta_row = conn.execute("SELECT fecha, cliente FROM ventas WHERE id = ?", (venta_id,)).fetchone()
        if venta_row:
            fecha_venta = venta_row["fecha"][:10] if venta_row["fecha"] else datetime.now().strftime("%Y-%m-%d")
            if not cliente:
                cliente = venta_row["cliente"] or "Consumidor Final"
        else:
            fecha_venta = datetime.now().strftime("%Y-%m-%d")

    cliente = cliente or "Consumidor Final"
    creadas = 0

    for d in detalles:
        meses = d["meses_garantia"] if (d["meses_garantia"] is not None) else 6
        if meses > 0:
            f_ini = fecha_venta[:10]
            f_fin = sumar_meses(f_ini, meses).isoformat()
            cant = int(d["cantidad"])
            for unit in range(1, cant + 1):
                codigo = f"GAR-{venta_id:04d}-{d['producto_id']:03d}-{unit:02d}"
                conn.execute("""
                    INSERT OR IGNORE INTO garantias (
                        codigo, venta_id, detalle_venta_id, producto_id, cliente,
                        fecha_inicio, fecha_vencimiento, meses_cobertura, estado
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'activa')
                """, (codigo, venta_id, d["detalle_id"], d["producto_id"], cliente, f_ini, f_fin, meses))
                creadas += 1

    return creadas


def anular_garantias_de_venta(conn, venta_id, motivo=""):
    """Anula todas las garantías asociadas a una venta cuando esta se anula o devuelve por completo."""
    conn.execute("""
        UPDATE garantias
        SET estado = 'anulada',
            motivo_anulacion = ?,
            fecha_anulacion = CURRENT_TIMESTAMP
        WHERE venta_id = ? AND estado != 'ejecutada'
    """, (motivo or "Venta anulada o devuelta", venta_id))


def anular_garantias_parcial(conn, venta_id, producto_id, cantidad, motivo=""):
    """Anula la cantidad especificada de garantías para un producto en una devolución parcial."""
    filas = conn.execute("""
        SELECT id FROM garantias
        WHERE venta_id = ? AND producto_id = ? AND estado IN ('activa', 'vencida')
        LIMIT ?
    """, (venta_id, producto_id, cantidad)).fetchall()

    for f in filas:
        conn.execute("""
            UPDATE garantias
            SET estado = 'anulada',
                motivo_anulacion = ?,
                fecha_anulacion = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (motivo or "Devolución parcial de producto", f["id"]))


def actualizar_estados_garantias(conn):
    """Actualiza automáticamente a 'vencida' aquellas garantías activas cuya fecha ya expiró."""
    conn.execute("""
        UPDATE garantias
        SET estado = 'vencida'
        WHERE estado = 'activa' AND date(fecha_vencimiento) < date('now')
    """)


def obtener_garantias(conn, estado=None, busqueda=None, fecha_desde=None, fecha_hasta=None, usuario_id=None):
    """Consulta el listado de garantías con cálculo dinámico de días restantes y filtros."""
    actualizar_estados_garantias(conn)

    sql = """
        SELECT g.*, 
               p.nombre AS producto_nombre, 
               p.codigo AS producto_codigo,
               p.modelo AS producto_modelo,
               p.existencia AS producto_existencia,
               v.fecha AS venta_fecha,
               v.usuario_id AS venta_usuario_id,
               v.estado AS venta_estado,
               u_v.usuario AS vendedor_usuario,
               u_e.usuario AS usuario_ejecuta_nombre
        FROM garantias g
        JOIN productos p ON p.id = g.producto_id
        JOIN ventas v ON v.id = g.venta_id
        LEFT JOIN usuarios u_v ON u_v.id = v.usuario_id
        LEFT JOIN usuarios u_e ON u_e.id = g.usuario_ejecuta_id
        WHERE 1=1
    """
    params = []

    if usuario_id is not None:
        sql += " AND v.usuario_id = ?"
        params.append(usuario_id)

    if busqueda:
        b = f"%{busqueda.strip()}%"
        sql += " AND (g.codigo LIKE ? OR g.cliente LIKE ? OR p.nombre LIKE ? OR p.codigo LIKE ? OR CAST(g.venta_id AS TEXT) LIKE ?)"
        params.extend([b, b, b, b, b])

    if fecha_desde:
        sql += " AND date(g.fecha_inicio) >= date(?)"
        params.append(fecha_desde)

    if fecha_hasta:
        sql += " AND date(g.fecha_inicio) <= date(?)"
        params.append(fecha_hasta)

    sql += " ORDER BY g.id DESC"
    filas = conn.execute(sql, params).fetchall()

    hoy = datetime.now().date()
    resultado = []

    for f in filas:
        item = dict(f)
        try:
            f_venc = datetime.strptime(item["fecha_vencimiento"][:10], "%Y-%m-%d").date()
            dias = (f_venc - hoy).days
            item["dias_restantes"] = dias
        except Exception:
            item["dias_restantes"] = None

        # Clasificación para filtro "por_vencer" (activas con <= 30 días restantes)
        item["es_por_vencer"] = bool(item["estado"] == "activa" and item["dias_restantes"] is not None and 0 <= item["dias_restantes"] <= 30)

        # Aplicar filtro de estado si se especificó
        if estado:
            estado_lower = estado.lower().strip()
            if estado_lower in ("todas", "todos", ""):
                pass
            elif estado_lower == "por_vencer":
                if not item["es_por_vencer"]:
                    continue
            elif estado_lower in ("activa", "activas", "vigentes"):
                if item["estado"] != "activa":
                    continue
            elif estado_lower in ("vencida", "vencidas"):
                if item["estado"] != "vencida":
                    continue
            elif estado_lower in ("ejecutada", "ejecutadas"):
                if item["estado"] != "ejecutada":
                    continue
            elif estado_lower in ("anulada", "anuladas"):
                if item["estado"] != "anulada":
                    continue
            else:
                if item["estado"] != estado_lower:
                    continue

        resultado.append(item)

    return resultado


def obtener_resumen_garantias(conn, usuario_id=None):
    """Calcula totales globales de garantías para tarjetas KPI."""
    actualizar_estados_garantias(conn)

    sql_base = """
        SELECT g.*, v.usuario_id AS venta_usuario_id
        FROM garantias g
        JOIN ventas v ON v.id = g.venta_id
    """
    params = []
    if usuario_id is not None:
        sql_base += " WHERE v.usuario_id = ?"
        params.append(usuario_id)

    filas = conn.execute(sql_base, params).fetchall()
    hoy = datetime.now().date()

    resumen = {
        "total": len(filas),
        "activas": 0,
        "por_vencer": 0,
        "vencidas": 0,
        "ejecutadas": 0,
        "anuladas": 0
    }

    for f in filas:
        est = f["estado"]
        if est == "ejecutada":
            resumen["ejecutadas"] += 1
        elif est == "anulada":
            resumen["anuladas"] += 1
        elif est == "vencida":
            resumen["vencidas"] += 1
        elif est == "activa":
            resumen["activas"] += 1
            try:
                f_venc = datetime.strptime(f["fecha_vencimiento"][:10], "%Y-%m-%d").date()
                dias = (f_venc - hoy).days
                if 0 <= dias <= 30:
                    resumen["por_vencer"] += 1
            except Exception:
                pass

    return resumen


def obtener_garantia_por_id(conn, garantia_id):
    """Obtiene los detalles completos de una garantía por su ID."""
    actualizar_estados_garantias(conn)
    sql = """
        SELECT g.*, 
               p.nombre AS producto_nombre, 
               p.codigo AS producto_codigo,
               p.modelo AS producto_modelo,
               p.descripcion AS producto_descripcion,
               p.precio_venta AS producto_precio,
               p.existencia AS producto_existencia,
               c.nombre AS categoria_nombre,
               m.nombre AS marca_nombre,
               t.nombre AS tipo_nombre,
               v.fecha AS venta_fecha,
               v.cliente AS venta_cliente,
               v.total AS venta_total,
               v.estado AS venta_estado,
               u_v.usuario AS vendedor_usuario,
               u_e.usuario AS usuario_ejecuta_nombre
        FROM garantias g
        JOIN productos p ON p.id = g.producto_id
        LEFT JOIN categorias c ON c.id = p.categoria_id
        LEFT JOIN marcas m ON m.id = p.marca_id
        LEFT JOIN tipos t ON t.id = p.tipo_id
        JOIN ventas v ON v.id = g.venta_id
        LEFT JOIN usuarios u_v ON u_v.id = v.usuario_id
        LEFT JOIN usuarios u_e ON u_e.id = g.usuario_ejecuta_id
        WHERE g.id = ?
    """
    row = conn.execute(sql, (garantia_id,)).fetchone()
    if not row:
        return None
    item = dict(row)
    hoy = datetime.now().date()
    try:
        f_venc = datetime.strptime(item["fecha_vencimiento"][:10], "%Y-%m-%d").date()
        dias = (f_venc - hoy).days
        item["dias_restantes"] = dias
    except Exception:
        item["dias_restantes"] = None
    item["es_por_vencer"] = bool(item["estado"] == "activa" and item["dias_restantes"] is not None and 0 <= item["dias_restantes"] <= 30)
    return item


def ejecutar_garantia(conn, garantia_id, usuario_id, tipo_resolucion, motivo_reclamo, diagnostico, resolucion_notas, descontar_inventario=False):
    """Registra la ejecución técnica o comercial de una garantía."""
    garantia = conn.execute("SELECT * FROM garantias WHERE id = ?", (garantia_id,)).fetchone()
    if not garantia:
        raise ValueError("La garantía seleccionada no existe.")

    if garantia["estado"] == "anulada":
        raise ValueError("No se puede ejecutar una garantía que ha sido anulada por devolución de venta.")

    if garantia["estado"] == "ejecutada":
        raise ValueError("Esta garantía ya fue ejecutada anteriormente.")

    conn.execute("""
        UPDATE garantias
        SET estado = 'ejecutada',
            fecha_ejecucion = CURRENT_TIMESTAMP,
            usuario_ejecuta_id = ?,
            tipo_resolucion = ?,
            motivo_reclamo = ?,
            diagnostico = ?,
            resolucion_notas = ?
        WHERE id = ?
    """, (usuario_id, tipo_resolucion, motivo_reclamo, diagnostico, resolucion_notas, garantia_id))

    if descontar_inventario and tipo_resolucion == "reemplazo":
        prod = conn.execute("SELECT existencia FROM productos WHERE id = ?", (garantia["producto_id"],)).fetchone()
        if prod and prod["existencia"] > 0:
            registrar_movimiento(
                conn,
                garantia["producto_id"],
                "ajuste",
                -1,
                usuario_id,
                f"Garantía #{garantia['codigo']}",
                f"Entrega de producto por reemplazo de garantía (#{garantia['codigo']})"
            )
        else:
            raise ValueError("No hay existencias en bodega para realizar el reemplazo físico del producto.")

    return garantia["codigo"]


# =====================================================================
# MÓDULO DE VACACIONES (Art. 76 Código del Trabajo de Nicaragua)
# =====================================================================

def calcular_saldo_vacaciones(conn, empleado_id, fecha_corte=None):
    """
    Calcula el saldo exacto de vacaciones para un empleado a una fecha de corte determinada.
    En Nicaragua: 15 días por cada 6 meses continuos = 30 días al año (2.5 días por mes).
    """
    emp = conn.execute("""
        SELECT e.*, c.nombre AS cargo_nombre
        FROM empleados e
        LEFT JOIN cargos c ON c.id = e.cargo_id
        WHERE e.id = ?
    """, (empleado_id,)).fetchone()

    if not emp:
        raise ValueError(f"Empleado #{empleado_id} no encontrado.")

    salario_base = float(emp["salario_base"] or 0.0)
    salario_diario = round(salario_base / 30.0, 2)

    hoy = datetime.now().date()
    if fecha_corte:
        if isinstance(fecha_corte, str):
            f_corte = date.fromisoformat(fecha_corte[:10])
        elif isinstance(fecha_corte, datetime):
            f_corte = fecha_corte.date()
        else:
            f_corte = fecha_corte
    else:
        f_corte = hoy

    f_ingreso = None
    if emp["fecha_ingreso"]:
        try:
            f_ingreso = date.fromisoformat(emp["fecha_ingreso"][:10])
        except Exception:
            pass

    if not f_ingreso:
        f_ingreso = f_corte

    # Días trabajados desde el ingreso hasta la fecha de corte
    dias_antiguedad = max(0, (f_corte - f_ingreso).days + 1)
    
    # Días de vacaciones acumulados por ley: (días_antiguedad / 365) * 30
    dias_acumulados = round((dias_antiguedad / 365.0) * 30.0, 2)

    # Días gozados registrados y aprobados
    row_gozadas = conn.execute("""
        SELECT COALESCE(SUM(dias_gozados), 0.0) AS total_gozadas
        FROM vacaciones_gozadas
        WHERE empleado_id = ? AND estado = 'aprobada'
    """, (empleado_id,)).fetchone()
    dias_gozados = round(float(row_gozadas["total_gozadas"]), 2)

    # Saldo de días pendientes
    dias_pendientes = max(0.0, round(dias_acumulados - dias_gozados, 2))
    valor_saldo = round(dias_pendientes * salario_diario, 2)

    return {
        "empleado_id": emp["id"],
        "nombre": emp["nombre"] or f"{emp['primer_nombre']} {emp['primer_apellido']}".strip(),
        "cedula": emp["cedula"],
        "cargo": emp["cargo_nombre"] or "Sin Cargo",
        "salario_base": salario_base,
        "salario_diario": salario_diario,
        "fecha_ingreso": f_ingreso.isoformat(),
        "fecha_corte": f_corte.isoformat(),
        "dias_antiguedad": dias_antiguedad,
        "dias_acumulados": dias_acumulados,
        "dias_gozados": dias_gozados,
        "dias_pendientes": dias_pendientes,
        "valor_saldo_vacaciones": valor_saldo,
        "activo": emp["activo"]
    }


def registrar_vacaciones_gozadas(conn, empleado_id, fecha_inicio, fecha_fin, dias_gozados, observaciones="", usuario_id=None):
    """Registra una toma de vacaciones por un empleado."""
    dias = float(dias_gozados)
    if dias <= 0:
        raise ValueError("Los días de vacaciones gozados deben ser mayores a cero.")

    f_ini = date.fromisoformat(fecha_inicio[:10])
    f_fin = date.fromisoformat(fecha_fin[:10])
    if f_ini > f_fin:
        raise ValueError("La fecha de inicio de vacaciones no puede ser posterior a la fecha de fin.")

    cursor = conn.execute("""
        INSERT INTO vacaciones_gozadas (empleado_id, fecha_inicio, fecha_fin, dias_gozados, observaciones, estado, usuario_id)
        VALUES (?, ?, ?, ?, ?, 'aprobada', ?)
    """, (empleado_id, f_ini.isoformat(), f_fin.isoformat(), dias, observaciones.strip(), usuario_id))

    return cursor.lastrowid


def obtener_historial_vacaciones(conn, empleado_id=None):
    """Retorna el listado de vacaciones gozadas registradas."""
    sql = """
        SELECT v.*, e.nombre AS empleado_nombre, e.cedula AS empleado_cedula, u.usuario AS usuario_registro
        FROM vacaciones_gozadas v
        JOIN empleados e ON e.id = v.empleado_id
        LEFT JOIN usuarios u ON u.id = v.usuario_id
        WHERE 1=1
    """
    params = []
    if empleado_id:
        sql += " AND v.empleado_id = ?"
        params.append(empleado_id)
    sql += " ORDER BY v.fecha_inicio DESC, v.id DESC"

    return conn.execute(sql, params).fetchall()


def obtener_resumen_vacaciones_todos(conn, fecha_corte=None):
    """Calcula el estado de vacaciones para todos los empleados de la empresa."""
    empleados = conn.execute("SELECT id FROM empleados WHERE activo = 1 ORDER BY nombre ASC").fetchall()
    resumen = []
    totales = {
        "empleados": len(empleados),
        "total_dias_acumulados": 0.0,
        "total_dias_gozados": 0.0,
        "total_dias_pendientes": 0.0,
        "total_pasivo_cordobas": 0.0
    }

    for emp in empleados:
        saldo = calcular_saldo_vacaciones(conn, emp["id"], fecha_corte)
        resumen.append(saldo)
        totales["total_dias_acumulados"] += saldo["dias_acumulados"]
        totales["total_dias_gozados"] += saldo["dias_gozados"]
        totales["total_dias_pendientes"] += saldo["dias_pendientes"]
        totales["total_pasivo_cordobas"] += saldo["valor_saldo_vacaciones"]

    totales["total_dias_acumulados"] = round(totales["total_dias_acumulados"], 2)
    totales["total_dias_gozados"] = round(totales["total_dias_gozados"], 2)
    totales["total_dias_pendientes"] = round(totales["total_dias_pendientes"], 2)
    totales["total_pasivo_cordobas"] = round(totales["total_pasivo_cordobas"], 2)

    return resumen, totales


# =====================================================================
# MÓDULO DE LIQUIDACIONES (Despido / Renuncia - Ley 185 y Ley 476)
# =====================================================================

def calcular_antiguedad_detallada(fecha_inicio, fecha_fin):
    """Calcula años, meses y días exactos entre dos fechas."""
    if isinstance(fecha_inicio, str):
        fecha_inicio = date.fromisoformat(fecha_inicio[:10])
    if isinstance(fecha_fin, str):
        fecha_fin = date.fromisoformat(fecha_fin[:10])

    if fecha_inicio > fecha_fin:
        return 0, 0, 0, 0

    total_dias = (fecha_fin - fecha_inicio).days + 1

    anios = fecha_fin.year - fecha_inicio.year
    meses = fecha_fin.month - fecha_inicio.month
    dias = fecha_fin.day - fecha_inicio.day

    if dias < 0:
        mes_ant = fecha_fin.month - 1 if fecha_fin.month > 1 else 12
        anio_ant = fecha_fin.year if fecha_fin.month > 1 else fecha_fin.year - 1
        dias_mes_ant = calendar.monthrange(anio_ant, mes_ant)[1]
        dias += dias_mes_ant
        meses -= 1

    if meses < 0:
        meses += 12
        anios -= 1

    return max(0, anios), max(0, meses), max(0, dias), total_dias


def calcular_liquidacion(
    conn,
    empleado_id,
    fecha_salida=None,
    motivo="despido",
    regimen="privada",
    dias_salario_pendiente=0,
    otras_deducciones=0,
    motivo_deducciones="",
    forzar_indemnizacion=None
):
    """
    Calcula la liquidación laboral completa conforme al Código del Trabajo de Nicaragua (Ley 185)
    y Ley de Servicio Civil (Ley 476).
    
    Conceptos calculados:
    1. Salario Pendiente (- INSS Laboral 7%)
    2. Vacaciones Proporcionales / Pendientes (Art. 76)
    3. Décimo Tercer Mes / Aguinaldo Proporcional (Art. 93, 94)
    4. Indemnización por Antigüedad (Art. 45):
       - Despido (Privada/Pública): 1 mes por cada uno de los primeros 3 años + 20 días por año subsiguiente (tope 5 meses).
       - Renuncia (Privada): C$ 0.00 (salvo convenio o forzar_indemnizacion=True).
    """
    emp = conn.execute("""
        SELECT e.*, c.nombre AS cargo_nombre
        FROM empleados e
        LEFT JOIN cargos c ON c.id = e.cargo_id
        WHERE e.id = ?
    """, (empleado_id,)).fetchone()

    if not emp:
        raise ValueError(f"Empleado #{empleado_id} no encontrado.")

    salario_base = float(emp["salario_base"] or 0.0)
    salario_diario = round(salario_base / 30.0, 2)

    # 1. Fechas y Antigüedad
    f_salida = date.fromisoformat(fecha_salida[:10]) if fecha_salida else datetime.now().date()
    f_ingreso = date.fromisoformat(emp["fecha_ingreso"][:10]) if emp["fecha_ingreso"] else f_salida

    if f_ingreso > f_salida:
        raise ValueError("La fecha de salida no puede ser anterior a la fecha de ingreso.")

    anios, meses, dias, total_dias_trabajados = calcular_antiguedad_detallada(f_ingreso, f_salida)
    antiguedad_anios_decimal = total_dias_trabajados / 365.0

    # 2. Salario Pendiente del último período
    dias_sal_pend = max(0.0, float(dias_salario_pendiente))
    monto_salario_pendiente = round(dias_sal_pend * salario_diario, 2)
    inss_salario_pendiente = round(monto_salario_pendiente * 0.07, 2)

    # 3. Vacaciones Pendientes / Proporcionales (Art. 76)
    saldo_vac = calcular_saldo_vacaciones(conn, empleado_id, f_salida)
    dias_vacaciones_pendientes = saldo_vac["dias_pendientes"]
    monto_vacaciones = round(dias_vacaciones_pendientes * salario_diario, 2)

    # 4. Décimo Tercer Mes (Aguinaldo Proporcional - Art. 93, 94)
    # Ciclo de aguinaldo: 1 de diciembre anterior al 30 de noviembre actual
    if f_salida.month == 12:
        inicio_ciclo_aguinaldo = date(f_salida.year, 12, 1)
    else:
        inicio_ciclo_aguinaldo = date(f_salida.year - 1, 12, 1)

    inicio_efectivo_aguinaldo = max(inicio_ciclo_aguinaldo, f_ingreso)
    dias_acum_aguinaldo = max(0, (f_salida - inicio_efectivo_aguinaldo).days + 1)
    dias_aguinaldo_proporcional = round((dias_acum_aguinaldo / 365.0) * 30.0, 2)
    monto_aguinaldo = round(dias_aguinaldo_proporcional * salario_diario, 2)

    # 5. Indemnización por Antigüedad (Art. 45 Ley 185 / Ley 476)
    motivo_normalizado = motivo.lower().strip()
    regimen_normalizado = regimen.lower().strip()

    if forzar_indemnizacion is not None:
        aplica_indemnizacion = bool(forzar_indemnizacion)
    elif motivo_normalizado == "despido":
        aplica_indemnizacion = True
    else:  # renuncia
        aplica_indemnizacion = bool(regimen_normalizado == "publica")  # en pública o por convenio

    meses_indemnizacion = 0.0
    monto_indemnizacion = 0.0

    if aplica_indemnizacion and total_dias_trabajados >= 30:
        # Primeros 3 años: 1 mes por año
        anios_primeros = min(antiguedad_anios_decimal, 3.0)
        meses_indemnizacion = anios_primeros * 1.0

        # A partir del 4to año: 20 días por año (20/30 mes)
        if antiguedad_anios_decimal > 3.0:
            anios_restantes = antiguedad_anios_decimal - 3.0
            meses_indemnizacion += anios_restantes * (20.0 / 30.0)

        # Límite legal máximo: 5 meses
        meses_indemnizacion = min(meses_indemnizacion, 5.0)

        # Límite mínimo legal si laboró al menos 1 año
        if antiguedad_anios_decimal >= 1.0 and meses_indemnizacion < 1.0:
            meses_indemnizacion = 1.0

        meses_indemnizacion = round(meses_indemnizacion, 4)
        monto_indemnizacion = round(meses_indemnizacion * salario_base, 2)

    # 6. Deducciones y Totales
    otras_ded = max(0.0, float(otras_deducciones))
    total_bruto = round(monto_salario_pendiente + monto_vacaciones + monto_aguinaldo + monto_indemnizacion, 2)
    total_deducciones = round(inss_salario_pendiente + otras_ded, 2)
    total_neto = max(0.0, round(total_bruto - total_deducciones, 2))

    return {
        "empleado_id": emp["id"],
        "nombre": emp["nombre"] or f"{emp['primer_nombre']} {emp['primer_apellido']}".strip(),
        "cedula": emp["cedula"],
        "cargo": emp["cargo_nombre"] or "Sin Cargo",
        "salario_base_mensual": salario_base,
        "salario_diario": salario_diario,
        "fecha_ingreso": f_ingreso.isoformat(),
        "fecha_salida": f_salida.isoformat(),
        "motivo": motivo_normalizado,
        "regimen": regimen_normalizado,
        "anios_servicio": anios,
        "meses_servicio": meses,
        "dias_servicio": dias,
        "total_dias_trabajados": total_dias_trabajados,
        
        # Conceptos:
        "dias_salario_pendiente": dias_sal_pend,
        "monto_salario_pendiente": monto_salario_pendiente,
        "inss_salario_pendiente": inss_salario_pendiente,
        
        "dias_vacaciones_pendientes": dias_vacaciones_pendientes,
        "monto_vacaciones": monto_vacaciones,
        
        "dias_aguinaldo_proporcional": dias_aguinaldo_proporcional,
        "monto_aguinaldo": monto_aguinaldo,
        
        "aplica_indemnizacion": 1 if aplica_indemnizacion else 0,
        "meses_indemnizacion": meses_indemnizacion,
        "monto_indemnizacion": monto_indemnizacion,
        
        "otras_deducciones": otras_ded,
        "motivo_deducciones": motivo_deducciones.strip(),
        
        "total_bruto": total_bruto,
        "total_deducciones": total_deducciones,
        "total_neto": total_neto
    }


def guardar_liquidacion(conn, datos, usuario_id=None, dar_de_baja=True):
    """Guarda formalmente una liquidación en la base de datos y opcionalmente desactiva al empleado."""
    anio_actual = datetime.now().year
    
    # Generar código correlativo: LIQ-YYYY-XXXX
    count_row = conn.execute("SELECT COUNT(*) FROM liquidaciones").fetchone()
    seq = (count_row[0] if count_row else 0) + 1
    codigo = f"LIQ-{anio_actual}-{seq:04d}"

    cursor = conn.execute("""
        INSERT INTO liquidaciones (
            codigo, empleado_id, fecha_ingreso, fecha_salida,
            salario_base_mensual, salario_diario, motivo, regimen,
            anios_servicio, meses_servicio, dias_servicio, total_dias_trabajados,
            dias_salario_pendiente, monto_salario_pendiente, inss_salario_pendiente,
            dias_vacaciones_pendientes, monto_vacaciones,
            dias_aguinaldo_proporcional, monto_aguinaldo,
            aplica_indemnizacion, meses_indemnizacion, monto_indemnizacion,
            otras_deducciones, motivo_deducciones,
            total_bruto, total_deducciones, total_neto,
            estado, observaciones, usuario_id
        ) VALUES (
            ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?, ?,
            'registrada', ?, ?
        )
    """, (
        codigo, datos["empleado_id"], datos["fecha_ingreso"], datos["fecha_salida"],
        datos["salario_base_mensual"], datos["salario_diario"], datos["motivo"], datos["regimen"],
        datos["anios_servicio"], datos["meses_servicio"], datos["dias_servicio"], datos["total_dias_trabajados"],
        datos["dias_salario_pendiente"], datos["monto_salario_pendiente"], datos["inss_salario_pendiente"],
        datos["dias_vacaciones_pendientes"], datos["monto_vacaciones"],
        datos["dias_aguinaldo_proporcional"], datos["monto_aguinaldo"],
        datos["aplica_indemnizacion"], datos["meses_indemnizacion"], datos["monto_indemnizacion"],
        datos["otras_deducciones"], datos["motivo_deducciones"],
        datos["total_bruto"], datos["total_deducciones"], datos["total_neto"],
        datos.get("observaciones", ""), usuario_id
    ))

    liq_id = cursor.lastrowid

    if dar_de_baja:
        conn.execute("UPDATE empleados SET activo = 0 WHERE id = ?", (datos["empleado_id"],))

    return liq_id, codigo


def obtener_liquidaciones(conn, motivo=None, estado=None, busqueda=None):
    """Consulta el listado de liquidaciones registradas."""
    sql = """
        SELECT l.*, e.nombre AS empleado_nombre, e.cedula AS empleado_cedula,
               c.nombre AS cargo_nombre, u.usuario AS usuario_registro
        FROM liquidaciones l
        JOIN empleados e ON e.id = l.empleado_id
        LEFT JOIN cargos c ON c.id = e.cargo_id
        LEFT JOIN usuarios u ON u.id = l.usuario_id
        WHERE 1=1
    """
    params = []

    if motivo:
        sql += " AND l.motivo = ?"
        params.append(motivo.lower().strip())

    if estado:
        sql += " AND l.estado = ?"
        params.append(estado.lower().strip())

    if busqueda:
        b = f"%{busqueda.strip()}%"
        sql += " AND (l.codigo LIKE ? OR e.nombre LIKE ? OR e.cedula LIKE ?)"
        params.extend([b, b, b])

    sql += " ORDER BY l.id DESC"
    return conn.execute(sql, params).fetchall()


def obtener_resumen_liquidaciones(conn):
    """Retorna totales generales de liquidaciones."""
    filas = conn.execute("SELECT motivo, total_neto FROM liquidaciones WHERE estado != 'anulada'").fetchall()
    resumen = {
        "total": len(filas),
        "despidos": 0,
        "renuncias": 0,
        "total_liquidado": 0.0
    }
    for f in filas:
        resumen["total_liquidado"] += float(f["total_neto"] or 0.0)
        if f["motivo"] == "despido":
            resumen["despidos"] += 1
        else:
            resumen["renuncias"] += 1

    resumen["total_liquidado"] = round(resumen["total_liquidado"], 2)
    return resumen


def obtener_liquidacion_por_id(conn, liquidacion_id):
    """Obtiene el detalle completo de una liquidación por su ID."""
    sql = """
        SELECT l.*, e.nombre AS empleado_nombre, e.cedula AS empleado_cedula,
               e.numero_inss, c.nombre AS cargo_nombre, d.nombre AS departamento_nombre,
               u.usuario AS usuario_registro
        FROM liquidaciones l
        JOIN empleados e ON e.id = l.empleado_id
        LEFT JOIN cargos c ON c.id = e.cargo_id
        LEFT JOIN departamentos d ON d.id = e.departamento_id
        LEFT JOIN usuarios u ON u.id = l.usuario_id
        WHERE l.id = ?
    """
    return conn.execute(sql, (liquidacion_id,)).fetchone()

