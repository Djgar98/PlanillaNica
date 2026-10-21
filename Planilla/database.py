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

