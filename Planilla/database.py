import sqlite3
from datetime import datetime
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


def init_db():
    """Crea y actualiza el esquema local sin eliminar datos existentes."""
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
        
        conn.execute("""CREATE TABLE IF NOT EXISTS categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            activo INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0,1))
        )""")
        conn.execute("INSERT OR IGNORE INTO categorias (id, nombre) VALUES (1, 'General')")

        conn.execute("""CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT NOT NULL UNIQUE,
            nombre TEXT NOT NULL, password_hash TEXT NOT NULL,
            rol TEXT NOT NULL DEFAULT 'vendedor' CHECK (rol IN ('admin','vendedor','rrhh','bodega')),
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
        
        # add foreign key defaults rows if needed (optional)
        conn.executemany("INSERT OR IGNORE INTO marcas (nombre) VALUES (?)", [("Sin Marca",)])
        conn.executemany("INSERT OR IGNORE INTO tipos (nombre) VALUES (?)", [("Sin Tipo",)])
            
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
    """Obtiene los pagos registrados en un mes YYYY-MM, junto con el empleado."""
    with get_db() as conn:
        return conn.execute("""SELECT p.*, e.nombre, e.cedula, e.cargo
            FROM planilla p JOIN empleados e ON e.id = p.empleado_id
            WHERE strftime('%Y-%m', p.fecha) = ?
            ORDER BY p.fecha ASC, e.nombre ASC""", (mes,)).fetchall()
