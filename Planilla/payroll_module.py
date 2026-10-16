"""
payroll_module.py
=================
Módulo de Gestión de Planilla con Pagos Diferidos y Cálculo de Aguinaldo.
Cumple con la legislación laboral de la República de Nicaragua (Ley 185 - Código del Trabajo).

Entidades modeladas:
- Empleado
- Contrato
- PeriodoPlanilla
- TransaccionPagoPlanilla
- ResultadoAguinaldo

Reglas de negocio:
- Registro de N pagos parciales/diferidos para un mismo período mensual.
- Validación estricta para evitar pagos que excedan el salario neto pactado.
- Opción de validar correlatividad de pagos (mes anterior completado).
- Auditoría completa de transacciones (usuario, fecha_pago, fecha_registro, referencia).
- Precisión decimal fija (Decimal) sin errores de punto flotante.
- Cálculo de Décimo Tercer Mes (Aguinaldo) para año completo y proporcional.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Tuple, Dict, Any
import sqlite3
from pathlib import Path

CENTAVO = Decimal("0.01")
DATABASE_PATH = Path(__file__).resolve().parent / "planilla_ni.db"


def a_decimal(valor: Any) -> Decimal:
    """Convierte un valor numérico o cadena a Decimal con 2 decimales exactos."""
    if valor is None:
        return Decimal("0.00")
    if isinstance(valor, Decimal):
        return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)
    try:
        return Decimal(str(valor)).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")


# =====================================================================
# ENTIDADES / CLASES DEL DOMINIO
# =====================================================================

@dataclass
class Empleado:
    """Entidad que representa el expediente de un colaborador."""
    id: Optional[int]
    cedula: str
    nombre: str
    primer_nombre: str = ""
    segundo_nombre: str = ""
    primer_apellido: str = ""
    segundo_apellido: str = ""
    cargo_id: int = 1
    numero_inss: Optional[str] = None
    departamento_id: Optional[int] = None
    fecha_ingreso: Optional[str] = None
    salario_base: Decimal = Decimal("0.00")
    activo: int = 1

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Empleado":
        return cls(
            id=row["id"],
            cedula=row["cedula"],
            nombre=row["nombre"] or f"{row['primer_nombre']} {row['primer_apellido']}".strip(),
            primer_nombre=row["primer_nombre"] or "",
            segundo_nombre=row["segundo_nombre"] or "",
            primer_apellido=row["primer_apellido"] or "",
            segundo_apellido=row["segundo_apellido"] or "",
            cargo_id=row["cargo_id"] if "cargo_id" in row.keys() else 1,
            numero_inss=row["numero_inss"] if "numero_inss" in row.keys() else None,
            departamento_id=row["departamento_id"] if "departamento_id" in row.keys() else None,
            fecha_ingreso=row["fecha_ingreso"] if "fecha_ingreso" in row.keys() else None,
            salario_base=a_decimal(row["salario_base"]),
            activo=row["activo"] if "activo" in row.keys() else 1,
        )


@dataclass
class Contrato:
    """Entidad que formaliza la relación laboral y el salario base pactado."""
    id: Optional[int]
    empleado_id: int
    salario_base: Decimal
    tipo_contrato: str = "Indeterminado"  # Indeterminado, Determinado, Servicios Profesionales
    moneda: str = "NIO"
    fecha_inicio: str = field(default_factory=lambda: date.today().isoformat())
    fecha_fin: Optional[str] = None
    activo: int = 1
    observaciones: str = ""
    creado_en: Optional[str] = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Contrato":
        return cls(
            id=row["id"],
            empleado_id=row["empleado_id"],
            salario_base=a_decimal(row["salario_base"]),
            tipo_contrato=row["tipo_contrato"],
            moneda=row["moneda"],
            fecha_inicio=row["fecha_inicio"],
            fecha_fin=row["fecha_fin"],
            activo=row["activo"],
            observaciones=row["observaciones"] or "",
            creado_en=row["creado_en"],
        )


@dataclass
class TransaccionPagoPlanilla:
    """Entidad que registra cada transacción o abono diferido a un período de nómina."""
    id: Optional[int]
    periodo_planilla_id: int
    empleado_id: int
    monto: Decimal
    fecha_pago: str
    concepto: str = "Abono de salario"
    metodo_pago: str = "Transferencia"  # Transferencia, Efectivo, Cheque, Depósito
    referencia: str = ""
    notas: str = ""
    usuario_id: Optional[int] = None
    registrado_por: str = "Sistema"
    fecha_registro: Optional[str] = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "TransaccionPagoPlanilla":
        return cls(
            id=row["id"],
            periodo_planilla_id=row["periodo_planilla_id"],
            empleado_id=row["empleado_id"],
            monto=a_decimal(row["monto"]),
            fecha_pago=row["fecha_pago"],
            concepto=row["concepto"] or "Abono de salario",
            metodo_pago=row["metodo_pago"] or "Transferencia",
            referencia=row["referencia"] or "",
            notas=row["notas"] or "",
            usuario_id=row["usuario_id"] if "usuario_id" in row.keys() else None,
            registrado_por=row["registrado_por"] or "Sistema",
            fecha_registro=row["fecha_registro"],
        )


@dataclass
class PeriodoPlanilla:
    """
    Entidad que representa el período mensual de nómina de un empleado.
    Permite registrar N transacciones de pago diferidas/parciales.
    """
    id: Optional[int]
    empleado_id: int
    contrato_id: Optional[int]
    anio: int
    mes: int
    descripcion: str
    fecha_inicio: str
    fecha_fin: str
    salario_base_pactado: Decimal
    horas_extras: Decimal = Decimal("0.00")
    pago_horas_extras: Decimal = Decimal("0.00")
    salario_bruto: Decimal = Decimal("0.00")
    inss_laboral: Decimal = Decimal("0.00")
    ir_laboral: Decimal = Decimal("0.00")
    inss_patronal: Decimal = Decimal("0.00")
    salario_neto_total: Decimal = Decimal("0.00")
    total_pagado: Decimal = Decimal("0.00")
    saldo_pendiente: Decimal = Decimal("0.00")
    estado: str = "pendiente"  # 'pendiente', 'pago_parcial', 'pagado_completo'
    creado_en: Optional[str] = None
    actualizado_en: Optional[str] = None
    transacciones: List[TransaccionPagoPlanilla] = field(default_factory=list)

    @classmethod
    def from_row(cls, row: sqlite3.Row, transacciones: Optional[List[TransaccionPagoPlanilla]] = None) -> "PeriodoPlanilla":
        return cls(
            id=row["id"],
            empleado_id=row["empleado_id"],
            contrato_id=row["contrato_id"],
            anio=row["anio"],
            mes=row["mes"],
            descripcion=row["descripcion"],
            fecha_inicio=row["fecha_inicio"],
            fecha_fin=row["fecha_fin"],
            salario_base_pactado=a_decimal(row["salario_base_pactado"]),
            horas_extras=a_decimal(row["horas_extras"]),
            pago_horas_extras=a_decimal(row["pago_horas_extras"]),
            salario_bruto=a_decimal(row["salario_bruto"]),
            inss_laboral=a_decimal(row["inss_laboral"]),
            ir_laboral=a_decimal(row["ir_laboral"]),
            inss_patronal=a_decimal(row["inss_patronal"]),
            salario_neto_total=a_decimal(row["salario_neto_total"]),
            total_pagado=a_decimal(row["total_pagado"]),
            saldo_pendiente=a_decimal(row["saldo_pendiente"]),
            estado=row["estado"],
            creado_en=row["creado_en"],
            actualizado_en=row["actualizado_en"],
            transacciones=transacciones or [],
        )


@dataclass
class ResultadoAguinaldo:
    """Estructura del resultado de cálculo de aguinaldo (Ley 185 Nicaragua)."""
    empleado_id: int
    nombre_empleado: str
    salario_base_mensual: Decimal
    anio_fiscal: int
    fecha_inicio_periodo: str  # 1 de diciembre de (anio - 1)
    fecha_fin_periodo: str     # 30 de noviembre de anio
    fecha_exigible_pago: str   # 1 al 10 de diciembre de anio
    dias_totales_anio: int
    dias_trabajados: int
    es_anio_completo: bool
    total_salario_acumulado: Decimal
    
    # Cálculos según fórmulas:
    # 1. Fórmula solicitada en el requerimiento: (TotalSalarioDevengado / 365) * DiasTrabajados
    aguinaldo_formula_solicitada: Decimal
    
    # 2. Fórmula Ley 185 Nicaragua estándar:
    # - Año completo: 1 mes de salario ordinario.
    # - Proporcional por salarios devengados: TotalSalariosDevengados / 12
    # - Proporcional por días: (SalarioBaseMensual / 365) * DiasTrabajados
    aguinaldo_ley_185_acumulado: Decimal
    aguinaldo_ley_185_dias: Decimal
    
    # Monto final seleccionado a pagar:
    aguinaldo_calculado: Decimal
    
    # Estado de pagos e historial
    estado_pagos: str
    transacciones_incluidas: List[Dict[str, Any]] = field(default_factory=list)


# =====================================================================
# GESTOR DE REGLAS DE NEGOCIO Y PERSISTENCIA
# =====================================================================

class GestorPlanillaDiferida:
    """Controlador de lógica de negocio para pagos diferidos y aguinaldo."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DATABASE_PATH

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=20)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # -----------------------------------------------------------------
    # MIGRACIÓN / INICIALIZACIÓN DE TABLAS
    # -----------------------------------------------------------------
    def asegurar_esquema(self, conn: Optional[sqlite3.Connection] = None) -> None:
        """Crea las tablas de contratos, períodos y transacciones de pago si no existen."""
        gestor_propio = conn is None
        c = conn or self.get_connection()
        try:
            # 1. Contratos laborales
            c.execute("""
            CREATE TABLE IF NOT EXISTS contratos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empleado_id INTEGER NOT NULL,
                tipo_contrato TEXT NOT NULL DEFAULT 'Indeterminado',
                salario_base REAL NOT NULL CHECK (salario_base > 0),
                moneda TEXT NOT NULL DEFAULT 'NIO',
                fecha_inicio TEXT NOT NULL,
                fecha_fin TEXT,
                activo INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
                observaciones TEXT DEFAULT '',
                creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (empleado_id) REFERENCES empleados(id) ON DELETE CASCADE
            );
            """)

            # 2. Periodos de planilla mensuales
            c.execute("""
            CREATE TABLE IF NOT EXISTS periodos_planilla (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empleado_id INTEGER NOT NULL,
                contrato_id INTEGER,
                anio INTEGER NOT NULL,
                mes INTEGER NOT NULL CHECK (mes BETWEEN 1 AND 12),
                descripcion TEXT NOT NULL,
                fecha_inicio TEXT NOT NULL,
                fecha_fin TEXT NOT NULL,
                salario_base_pactado REAL NOT NULL CHECK (salario_base_pactado >= 0),
                horas_extras REAL NOT NULL DEFAULT 0,
                pago_horas_extras REAL NOT NULL DEFAULT 0,
                salario_bruto REAL NOT NULL,
                inss_laboral REAL NOT NULL,
                ir_laboral REAL NOT NULL,
                inss_patronal REAL NOT NULL,
                salario_neto_total REAL NOT NULL,
                total_pagado REAL NOT NULL DEFAULT 0.0,
                saldo_pendiente REAL NOT NULL,
                estado TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'pago_parcial', 'pagado_completo')),
                creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (empleado_id) REFERENCES empleados(id) ON DELETE CASCADE,
                FOREIGN KEY (contrato_id) REFERENCES contratos(id) ON DELETE SET NULL,
                UNIQUE (empleado_id, anio, mes)
            );
            """)

            # 3. Transacciones de pago diferido / abonos
            c.execute("""
            CREATE TABLE IF NOT EXISTS transacciones_pago_planilla (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                periodo_planilla_id INTEGER NOT NULL,
                empleado_id INTEGER NOT NULL,
                monto REAL NOT NULL CHECK (monto > 0),
                fecha_pago TEXT NOT NULL,
                concepto TEXT NOT NULL DEFAULT 'Abono de salario',
                metodo_pago TEXT NOT NULL DEFAULT 'Transferencia' CHECK (metodo_pago IN ('Transferencia', 'Efectivo', 'Cheque', 'Depósito')),
                referencia TEXT DEFAULT '',
                notas TEXT DEFAULT '',
                usuario_id INTEGER,
                registrado_por TEXT NOT NULL DEFAULT 'Sistema',
                fecha_registro TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (periodo_planilla_id) REFERENCES periodos_planilla(id) ON DELETE CASCADE,
                FOREIGN KEY (empleado_id) REFERENCES empleados(id) ON DELETE CASCADE,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
            );
            """)

            # Índices de alto rendimiento
            c.execute("CREATE INDEX IF NOT EXISTS idx_periodos_emp_fecha ON periodos_planilla (empleado_id, anio, mes)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_transacciones_periodo ON transacciones_pago_planilla (periodo_planilla_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_transacciones_emp_fecha ON transacciones_pago_planilla (empleado_id, fecha_pago)")
            
            c.commit()
        finally:
            if gestor_propio:
                c.close()

    # -----------------------------------------------------------------
    # GESTIÓN DE CONTRATOS
    # -----------------------------------------------------------------
    def registrar_o_actualizar_contrato(
        self,
        empleado_id: int,
        salario_base: Decimal,
        tipo_contrato: str = "Indeterminado",
        fecha_inicio: Optional[str] = None,
        fecha_fin: Optional[str] = None,
        observaciones: str = "",
        conn: Optional[sqlite3.Connection] = None
    ) -> Contrato:
        """Crea o actualiza el contrato activo del colaborador."""
        salario_dec = a_decimal(salario_base)
        if salario_dec <= Decimal("0.00"):
            raise ValueError("El salario base del contrato debe ser mayor a 0 NIO.")

        inicio = fecha_inicio or date.today().isoformat()
        gestor_propio = conn is None
        c = conn or self.get_connection()
        try:
            # Desactivar contratos previos activos para este empleado
            c.execute("UPDATE contratos SET activo = 0 WHERE empleado_id = ? AND activo = 1", (empleado_id,))
            
            cursor = c.execute("""
            INSERT INTO contratos (empleado_id, tipo_contrato, salario_base, moneda, fecha_inicio, fecha_fin, activo, observaciones)
            VALUES (?, ?, ?, 'NIO', ?, ?, 1, ?)
            """, (empleado_id, tipo_contrato, float(salario_dec), inicio, fecha_fin, observaciones))
            
            # Sincronizar salario base en tabla empleados
            c.execute("UPDATE empleados SET salario_base = ? WHERE id = ?", (float(salario_dec), empleado_id))
            
            contrato_id = cursor.lastrowid
            c.commit()

            row = c.execute("SELECT * FROM contratos WHERE id = ?", (contrato_id,)).fetchone()
            return Contrato.from_row(row)
        finally:
            if gestor_propio:
                c.close()

    def obtener_contrato_activo(self, empleado_id: int, conn: Optional[sqlite3.Connection] = None) -> Optional[Contrato]:
        """Recupera el contrato activo actual del empleado."""
        gestor_propio = conn is None
        c = conn or self.get_connection()
        try:
            row = c.execute("SELECT * FROM contratos WHERE empleado_id = ? AND activo = 1 ORDER BY id DESC LIMIT 1", (empleado_id,)).fetchone()
            return Contrato.from_row(row) if row else None
        finally:
            if gestor_propio:
                c.close()

    # -----------------------------------------------------------------
    # CÁLCULO DE DEDUCCIONES FISCALES (INSS / IR NICARAGUA)
    # -----------------------------------------------------------------
    @staticmethod
    def calcular_deducciones(salario_base: Decimal, horas_extras: Decimal = Decimal("0.00"), total_empleados_activos: int = 1) -> Dict[str, Decimal]:
        """Calcula retenciones de ley nicaragüense con tipos Decimal exactos."""
        sal_base = a_decimal(salario_base)
        h_extras = a_decimal(horas_extras)

        # Horas extras al 100% de recargo (doble) sobre jornada de 240 horas
        pago_he = (h_extras * (sal_base / Decimal("240.00")) * Decimal("2.00")).quantize(CENTAVO, rounding=ROUND_HALF_UP)
        salario_bruto = (sal_base + pago_he).quantize(CENTAVO, rounding=ROUND_HALF_UP)

        # INSS Laboral (7%)
        inss_laboral = (salario_bruto * Decimal("0.07")).quantize(CENTAVO, rounding=ROUND_HALF_UP)

        # INSS Patronal (21.5% para < 50 trabajadores, 22.5% para >= 50)
        tasa_patronal = Decimal("0.215") if total_empleados_activos < 50 else Decimal("0.225")
        inss_patronal = (salario_bruto * tasa_patronal).quantize(CENTAVO, rounding=ROUND_HALF_UP)

        # IR Laboral progresivo anual (Art. 52 Ley de Concertación Tributaria de Nicaragua)
        base_mensual = max(Decimal("0.00"), salario_bruto - inss_laboral)
        base_anual = base_mensual * Decimal("12.00")

        if base_anual <= Decimal("100000.00"):
            ir_anual = Decimal("0.00")
        elif base_anual <= Decimal("200000.00"):
            ir_anual = (base_anual - Decimal("100000.00")) * Decimal("0.15")
        elif base_anual <= Decimal("350000.00"):
            ir_anual = Decimal("15000.00") + (base_anual - Decimal("200000.00")) * Decimal("0.20")
        elif base_anual <= Decimal("500000.00"):
            ir_anual = Decimal("45000.00") + (base_anual - Decimal("350000.00")) * Decimal("0.25")
        else:
            ir_anual = Decimal("82500.00") + (base_anual - Decimal("500000.00")) * Decimal("0.30")

        ir_laboral = (ir_anual / Decimal("12.00")).quantize(CENTAVO, rounding=ROUND_HALF_UP)
        salario_neto = salario_bruto - inss_laboral - ir_laboral

        return {
            "salario_base": sal_base,
            "horas_extras": h_extras,
            "pago_horas_extras": pago_he,
            "salario_bruto": salario_bruto,
            "inss_laboral": inss_laboral,
            "ir_laboral": ir_laboral,
            "inss_patronal": inss_patronal,
            "salario_neto": salario_neto,
        }

    # -----------------------------------------------------------------
    # GESTIÓN DE PERÍODOS DE PLANILLA
    # -----------------------------------------------------------------
    def obtener_o_crear_periodo(
        self,
        empleado_id: int,
        anio: int,
        mes: int,
        salario_base_manual: Optional[Decimal] = None,
        conn: Optional[sqlite3.Connection] = None
    ) -> PeriodoPlanilla:
        """
        Obtiene un período mensual existente o lo crea inicializando
        el salario total a pagar y el saldo pendiente.
        """
        gestor_propio = conn is None
        c = conn or self.get_connection()
        try:
            row = c.execute(
                "SELECT * FROM periodos_planilla WHERE empleado_id = ? AND anio = ? AND mes = ?",
                (empleado_id, anio, mes)
            ).fetchone()

            if row:
                trans = self.obtener_transacciones_periodo(row["id"], c)
                return PeriodoPlanilla.from_row(row, trans)

            # Si no existe, crearlo
            emp_row = c.execute("SELECT * FROM empleados WHERE id = ?", (empleado_id,)).fetchone()
            if not emp_row:
                raise ValueError(f"No existe el empleado con ID {empleado_id}.")

            contrato = self.obtener_contrato_activo(empleado_id, c)
            contrato_id = contrato.id if contrato else None
            
            salario_base = a_decimal(salario_base_manual) if salario_base_manual is not None else (
                contrato.salario_base if contrato else a_decimal(emp_row["salario_base"])
            )

            if salario_base <= Decimal("0.00"):
                raise ValueError("El salario base debe ser superior a cero para abrir un período.")

            total_activos = c.execute("SELECT COUNT(*) FROM empleados WHERE activo = 1").fetchone()[0]
            calculo = self.calcular_deducciones(salario_base, Decimal("0.00"), total_activos)

            # Nombre descriptivo del mes
            meses_nombres = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                             "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
            desc = f"Planilla {meses_nombres[mes - 1]} {anio}"
            
            # Fechas del mes
            import calendar
            _, ultimo_dia = calendar.monthrange(anio, mes)
            f_inicio = f"{anio:04d}-{mes:02d}-01"
            f_fin = f"{anio:04d}-{mes:02d}-{ultimo_dia:02d}"

            salario_neto = calculo["salario_neto"]

            cursor = c.execute("""
            INSERT INTO periodos_planilla (
                empleado_id, contrato_id, anio, mes, descripcion, fecha_inicio, fecha_fin,
                salario_base_pactado, horas_extras, pago_horas_extras, salario_bruto,
                inss_laboral, ir_laboral, inss_patronal, salario_neto_total,
                total_pagado, saldo_pendiente, estado
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, ?, 'pendiente')
            """, (
                empleado_id, contrato_id, anio, mes, desc, f_inicio, f_fin,
                float(calculo["salario_base"]), float(calculo["horas_extras"]), float(calculo["pago_horas_extras"]),
                float(calculo["salario_bruto"]), float(calculo["inss_laboral"]), float(calculo["ir_laboral"]),
                float(calculo["inss_patronal"]), float(salario_neto), float(salario_neto)
            ))
            periodo_id = cursor.lastrowid
            c.commit()

            row_creada = c.execute("SELECT * FROM periodos_planilla WHERE id = ?", (periodo_id,)).fetchone()
            return PeriodoPlanilla.from_row(row_creada, [])
        finally:
            if gestor_propio:
                c.close()

    def obtener_transacciones_periodo(self, periodo_id: int, conn: Optional[sqlite3.Connection] = None) -> List[TransaccionPagoPlanilla]:
        """Obtiene todas las transacciones de pago registradas para un período dado."""
        gestor_propio = conn is None
        c = conn or self.get_connection()
        try:
            rows = c.execute(
                "SELECT * FROM transacciones_pago_planilla WHERE periodo_planilla_id = ? ORDER BY fecha_pago ASC, id ASC",
                (periodo_id,)
            ).fetchall()
            return [TransaccionPagoPlanilla.from_row(r) for r in rows]
        finally:
            if gestor_propio:
                c.close()

    # -----------------------------------------------------------------
    # VALIDACIONES Y REGISTRO DE PAGOS PARCIALES / DIFERIDOS
    # -----------------------------------------------------------------
    def validar_mes_anterior_completado(self, empleado_id: int, anio: int, mes: int, conn: sqlite3.Connection) -> Tuple[bool, str]:
        """
        Valida si el mes inmediatamente anterior tiene saldo pendiente por pagar.
        Regla contable preventiva (opcional/configurable).
        """
        if mes == 1:
            prev_anio = anio - 1
            prev_mes = 12
        else:
            prev_anio = anio
            prev_mes = mes - 1

        prev_periodo = conn.execute(
            "SELECT * FROM periodos_planilla WHERE empleado_id = ? AND anio = ? AND mes = ?",
            (empleado_id, prev_anio, prev_mes)
        ).fetchone()

        if prev_periodo and prev_periodo["estado"] != "pagado_completo":
            saldo = a_decimal(prev_periodo["saldo_pendiente"])
            if saldo > Decimal("0.00"):
                return False, f"El período anterior ({prev_mes:02d}/{prev_anio}) aún tiene un saldo pendiente de C$ {saldo:,.2f}."
        return True, ""

    def registrar_pago_diferido(
        self,
        empleado_id: int,
        periodo_planilla_id: int,
        monto: Decimal,
        fecha_pago: str,
        concepto: str = "Abono de salario",
        metodo_pago: str = "Transferencia",
        referencia: str = "",
        notas: str = "",
        usuario_id: Optional[int] = None,
        registrado_por: str = "Sistema",
        validar_mes_anterior: bool = False,
        conn: Optional[sqlite3.Connection] = None
    ) -> TransaccionPagoPlanilla:
        """
        Registra una transacción de pago parcial para un período de planilla.
        
        Validaciones aplicadas:
        1. Monto mayor que cero.
        2. El monto no debe exceder el saldo pendiente del período (impide sobrepago).
        3. Si validar_mes_anterior=True, valida que el mes anterior esté completamente saldado.
        4. Auditoría de usuario, fecha y referencia.
        5. Actualización atómica de saldo_pendiente, total_pagado y estado del período.
        """
        monto_dec = a_decimal(monto)
        if monto_dec <= Decimal("0.00"):
            raise ValueError("El monto del pago debe ser mayor que cero.")

        try:
            date.fromisoformat(fecha_pago)
        except ValueError:
            raise ValueError(f"La fecha de pago '{fecha_pago}' no es válida (debe ser formato YYYY-MM-DD).")

        gestor_propio = conn is None
        c = conn or self.get_connection()
        try:
            # Bloqueo y lectura del período
            periodo = c.execute(
                "SELECT * FROM periodos_planilla WHERE id = ? AND empleado_id = ?",
                (periodo_planilla_id, empleado_id)
            ).fetchone()

            if not periodo:
                raise ValueError("El período de planilla especificado no existe o no corresponde al empleado.")

            saldo_pendiente = a_decimal(periodo["saldo_pendiente"])
            total_pagado_actual = a_decimal(periodo["total_pagado"])
            salario_neto_total = a_decimal(periodo["salario_neto_total"])

            # Regla de Negocio 1: Validación contra el salario mensual total del período
            if monto_dec > saldo_pendiente:
                raise ValueError(
                    f"Pago rechazado: El monto a registrar (C$ {monto_dec:,.2f}) excede el saldo pendiente "
                    f"del período (C$ {saldo_pendiente:,.2f}). Salario neto total: C$ {salario_neto_total:,.2f}, "
                    f"ya pagado: C$ {total_pagado_actual:,.2f}."
                )

            # Regla opcional: Validación de período anterior
            if validar_mes_anterior:
                ok_prev, msg_prev = self.validar_mes_anterior_completado(empleado_id, periodo["anio"], periodo["mes"], c)
                if not ok_prev:
                    raise ValueError(f"Restricción contable: {msg_prev}")

            # Registrar la transacción (auditoría completa)
            cursor = c.execute("""
            INSERT INTO transacciones_pago_planilla (
                periodo_planilla_id, empleado_id, monto, fecha_pago,
                concepto, metodo_pago, referencia, notas, usuario_id,
                registrado_por, fecha_registro
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                periodo_planilla_id, empleado_id, float(monto_dec), fecha_pago,
                concepto, metodo_pago, referencia, notas, usuario_id, registrado_por
            ))
            transaccion_id = cursor.lastrowid

            # Actualizar período: recalcular saldo y estado
            nuevo_total_pagado = (total_pagado_actual + monto_dec).quantize(CENTAVO, rounding=ROUND_HALF_UP)
            nuevo_saldo = (salario_neto_total - nuevo_total_pagado).quantize(CENTAVO, rounding=ROUND_HALF_UP)

            if nuevo_saldo <= Decimal("0.00"):
                nuevo_estado = "pagado_completo"
                nuevo_saldo = Decimal("0.00")
            elif nuevo_total_pagado > Decimal("0.00"):
                nuevo_estado = "pago_parcial"
            else:
                nuevo_estado = "pendiente"

            c.execute("""
            UPDATE periodos_planilla
            SET total_pagado = ?, saldo_pendiente = ?, estado = ?, actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """, (float(nuevo_total_pagado), float(nuevo_saldo), nuevo_estado, periodo_planilla_id))

            c.commit()

            row_tx = c.execute("SELECT * FROM transacciones_pago_planilla WHERE id = ?", (transaccion_id,)).fetchone()
            return TransaccionPagoPlanilla.from_row(row_tx)
        finally:
            if gestor_propio:
                c.close()

    # -----------------------------------------------------------------
    # CÁLCULO DE AGUINALDO (DÉCIMO TERCER MES - LEY 185 NICARAGUA)
    # -----------------------------------------------------------------
    def CalcularAguinaldo(
        self,
        idEmpleado: int,
        añoActual: int,
        conn: Optional[sqlite3.Connection] = None
    ) -> ResultadoAguinaldo:
        """
        Calcula el Aguinaldo o Décimo Tercer Mes de acuerdo con el Código del Trabajo
        de la República de Nicaragua (Ley 185, Artículos 93 al 99).
        
        Parámetros:
        - idEmpleado: ID numérico del empleado.
        - añoActual: Año fiscal de corte a evaluar (ej. 2026).
        
        Período de cómputo en Nicaragua:
        - Corre del 1 de diciembre del año anterior al 30 de noviembre del año actual.
          Ejemplo: para 2026 -> 01/12/2025 al 30/11/2026.
        - Total de días del año fiscal: 365 días (o 366 si es bisiesto).
        
        Reglas de cálculo:
        1. Cuenta los días efectivamente trabajados por el colaborador en dicho ciclo.
        2. Suma el total de salarios ordinarios pagados y registrados en las TransaccionesPagoPlanilla.
        3. Si el empleado cumplió el año completo (365 días), tiene derecho a un mes completo de salario ordinario.
        4. Si no hay un año completo, calcula el proporcional con la fórmula solicitada:
           Aguinaldo = (TotalSalarioDevengado / 365) * DiasTrabajados
        5. También desglosa las fórmulas legales estándares de Nicaragua:
           - Por devengado: TotalSalarioDevengado / 12
           - Por días trabajados: (SalarioBaseMensual / 365) * DiasTrabajados
        """
        gestor_propio = conn is None
        c = conn or self.get_connection()
        try:
            # 1. Obtener datos del empleado
            emp_row = c.execute("SELECT * FROM empleados WHERE id = ?", (idEmpleado,)).fetchone()
            if not emp_row:
                raise ValueError(f"Empleado con ID {idEmpleado} no encontrado.")

            nombre_completo = emp_row["nombre"] or f"{emp_row['primer_nombre']} {emp_row['primer_apellido']}".strip()
            salario_base_mensual = a_decimal(emp_row["salario_base"])

            # Si tiene contrato activo con salario específico, priorizarlo
            contrato = self.obtener_contrato_activo(idEmpleado, c)
            if contrato and contrato.salario_base > Decimal("0.00"):
                salario_base_mensual = contrato.salario_base

            # 2. Determinar fechas del período fiscal
            # Inicio: 1 de diciembre de (añoActual - 1)
            # Fin: 30 de noviembre de añoActual
            inicio_periodo = date(añoActual - 1, 12, 1)
            fin_periodo = date(añoActual, 11, 30)
            dias_totales_periodo = (fin_periodo - inicio_periodo).days + 1  # 365 (o 366)

            # Fecha de exigibilidad legal de pago (Art. 96 Ley 185)
            fecha_exigible = f"1 al 10 de Diciembre de {añoActual}"

            # 3. Determinar fecha de inicio y fin laboral del empleado dentro del período
            fecha_ingreso_emp = None
            if emp_row["fecha_ingreso"]:
                try:
                    fecha_ingreso_emp = date.fromisoformat(emp_row["fecha_ingreso"])
                except ValueError:
                    pass

            if contrato and contrato.fecha_inicio:
                try:
                    f_contrato = date.fromisoformat(contrato.fecha_inicio)
                    # Si no había fecha de ingreso o la del contrato es anterior/específica
                    if not fecha_ingreso_emp or f_contrato < fecha_ingreso_emp:
                        fecha_ingreso_emp = f_contrato
                except ValueError:
                    pass

            # Inicio efectivo: el mayor entre inicio del período e ingreso del trabajador
            if fecha_ingreso_emp and fecha_ingreso_emp > inicio_periodo:
                inicio_efectivo = fecha_ingreso_emp
            else:
                inicio_efectivo = inicio_periodo

            # Fin efectivo: el menor entre fin de período y fecha de terminación/baja
            fin_efectivo = fin_periodo
            if contrato and contrato.fecha_fin:
                try:
                    f_fin_c = date.fromisoformat(contrato.fecha_fin)
                    if f_fin_c < fin_periodo:
                        fin_efectivo = f_fin_c
                except ValueError:
                    pass

            # Días trabajados
            if inicio_efectivo > fin_efectivo:
                dias_trabajados = 0
            else:
                dias_trabajados = (fin_efectivo - inicio_efectivo).days + 1

            # Limitar a máximo los días del ciclo
            dias_trabajados = max(0, min(dias_trabajados, dias_totales_periodo))
            es_anio_completo = (dias_trabajados >= dias_totales_periodo)

            # 4. Sumar total de salarios ordinarios pagados y registrados en TransaccionesPagoPlanilla
            # en el período (01/12/año-1 a 30/11/año)
            f_inicio_str = inicio_periodo.isoformat()
            f_fin_str = fin_periodo.isoformat()

            query = """
            SELECT t.*, p.descripcion AS periodo_nombre, p.salario_neto_total, p.saldo_pendiente, p.estado AS periodo_estado
            FROM transacciones_pago_planilla t
            JOIN periodos_planilla p ON p.id = t.periodo_planilla_id
            WHERE t.empleado_id = ?
              AND t.fecha_pago >= ?
              AND t.fecha_pago <= ?
            ORDER BY t.fecha_pago ASC, t.id ASC
            """
            tx_rows = c.execute(query, (idEmpleado, f_inicio_str, f_fin_str)).fetchall()

            total_salario_acumulado = Decimal("0.00")
            transacciones_info = []

            for r in tx_rows:
                monto_tx = a_decimal(r["monto"])
                total_salario_acumulado += monto_tx
                transacciones_info.append({
                    "id": r["id"],
                    "periodo_id": r["periodo_planilla_id"],
                    "periodo_nombre": r["periodo_nombre"],
                    "monto": monto_tx,
                    "fecha_pago": r["fecha_pago"],
                    "concepto": r["concepto"],
                    "metodo_pago": r["metodo_pago"],
                    "referencia": r["referencia"],
                    "registrado_por": r["registrado_por"],
                    "periodo_estado": r["periodo_estado"],
                })

            # Si no hay transacciones en la nueva tabla pero sí en la tabla planilla antigua, sumar también
            if not transacciones_info:
                tabla_antigua_existe = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='planilla'").fetchone()
                if tabla_antigua_existe:
                    query_antigua = """
                    SELECT * FROM planilla
                    WHERE empleado_id = ? AND date(fecha) >= date(?) AND date(fecha) <= date(?)
                    ORDER BY fecha ASC
                    """
                    filas_antiguas = c.execute(query_antigua, (idEmpleado, f_inicio_str, f_fin_str)).fetchall()
                    for fa in filas_antiguas:
                        monto_antiguo = a_decimal(fa["salario_base"])
                        total_salario_acumulado += monto_antiguo
                        transacciones_info.append({
                            "id": fa["id"],
                            "periodo_id": None,
                            "periodo_nombre": f"Planilla Histórica {fa['fecha'][:10]}",
                            "monto": monto_antiguo,
                            "fecha_pago": fa["fecha"][:10],
                            "concepto": "Salario Ordinario (Registro Histórico)",
                            "metodo_pago": "Planilla",
                            "referencia": f"PL-{fa['id']}",
                            "registrado_por": "Sistema Histórico",
                            "periodo_estado": "pagado_completo",
                        })

            # 5. Cálculo del Décimo Tercer Mes (Aguinaldo)
            # FÓRMULA SOLICITADA EN EL REQUERIMIENTO:
            # Si no hay un año completo, calcule el proporcional: (TotalSalarioDevengado / 365) * DiasTrabajados
            dias_divisor = Decimal(str(dias_totales_periodo))  # 365
            dias_factor = Decimal(str(dias_trabajados))

            if es_anio_completo:
                # Año completo = 1 mes de salario ordinario pactado (Art. 93 Ley 185)
                # Si total acumulado / 12 es representativo, se puede usar salario base pactado
                aguinaldo_solicitado = salario_base_mensual
            else:
                if total_salario_acumulado > Decimal("0.00") and dias_trabajados > 0:
                    aguinaldo_solicitado = ((total_salario_acumulado / dias_divisor) * dias_factor).quantize(
                        CENTAVO, rounding=ROUND_HALF_UP
                    )
                else:
                    aguinaldo_solicitado = Decimal("0.00")

            # FÓRMULAS OFICIALES LEY 185 (NICARAGUA):
            # A) Proporcional por acumulación devengada en el año (1/12 de los salarios ordinarios devengados):
            aguinaldo_ley_185_acumulado = (total_salario_acumulado / Decimal("12.00")).quantize(
                CENTAVO, rounding=ROUND_HALF_UP
            )

            # B) Proporcional por días sobre el salario ordinario pactado:
            aguinaldo_ley_185_dias = ((salario_base_mensual / dias_divisor) * dias_factor).quantize(
                CENTAVO, rounding=ROUND_HALF_UP
            )

            # Determinación del valor a pagar:
            # Aplicamos la fórmula solicitada formalmente por el requerimiento
            aguinaldo_a_pagar = aguinaldo_solicitado

            # 6. Estado de los pagos del colaborador
            if not transacciones_info:
                estado_pagos = "Sin pagos registrados en el año fiscal."
            else:
                ultima_tx = transacciones_info[-1]
                fecha_ult = ultima_tx["fecha_pago"]
                monto_ult = ultima_tx["monto"]
                
                # Revisar si hay períodos parciales
                periodos_incompletos = c.execute(
                    "SELECT * FROM periodos_planilla WHERE empleado_id = ? AND anio = ? AND estado != 'pagado_completo'",
                    (idEmpleado, añoActual)
                ).fetchall()

                if periodos_incompletos:
                    p_inc = periodos_incompletos[0]
                    saldo_p = a_decimal(p_inc["saldo_pendiente"])
                    total_p = a_decimal(p_inc["salario_neto_total"])
                    estado_pagos = (
                        f"Pago parcial registrado el {fecha_ult} (Abono: C$ {monto_ult:,.2f}). "
                        f"Período {p_inc['descripcion']}: Pendiente C$ {saldo_p:,.2f} de C$ {total_p:,.2f}."
                    )
                else:
                    estado_pagos = f"Pagos al día. Último pago registrado el {fecha_ult} por C$ {monto_ult:,.2f}."

            return ResultadoAguinaldo(
                empleado_id=idEmpleado,
                nombre_empleado=nombre_completo,
                salario_base_mensual=salario_base_mensual,
                anio_fiscal=añoActual,
                fecha_inicio_periodo=f_inicio_str,
                fecha_fin_periodo=f_fin_str,
                fecha_exigible_pago=fecha_exigible,
                dias_totales_anio=dias_totales_periodo,
                dias_trabajados=dias_trabajados,
                es_anio_completo=es_anio_completo,
                total_salario_acumulado=total_salario_acumulado,
                aguinaldo_formula_solicitada=aguinaldo_solicitado,
                aguinaldo_ley_185_acumulado=aguinaldo_ley_185_acumulado,
                aguinaldo_ley_185_dias=aguinaldo_ley_185_dias,
                aguinaldo_calculado=aguinaldo_a_pagar,
                estado_pagos=estado_pagos,
                transacciones_incluidas=transacciones_info,
            )
        finally:
            if gestor_propio:
                c.close()


# Función de conveniencia para invocar directamente según requerimiento:
def CalcularAguinaldo(idEmpleado: int, añoActual: int, conn: Optional[sqlite3.Connection] = None) -> ResultadoAguinaldo:
    """Función global solicitada en las especificaciones del sistema."""
    gestor = GestorPlanillaDiferida()
    return gestor.CalcularAguinaldo(idEmpleado, añoActual, conn=conn)
