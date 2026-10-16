"""
test_payroll_module.py
======================
Suite completa de pruebas unitarias y de integración para el módulo de planilla:
- Precisión decimal fija (evitar errores de coma flotante).
- Modelado de Entidades (Empleado, Contrato, PeriodoPlanilla, TransaccionPagoPlanilla).
- Registro de pagos diferidos/parciales múltiples para un mismo período.
- Validación estricta que impide registrar pagos que excedan el saldo pendiente.
- Cálculo de Aguinaldo / Décimo Tercer Mes (Ley 185 Nicaragua) para Rosita, Franco y Marlene.
"""

import unittest
from decimal import Decimal
from datetime import date
import sqlite3
from pathlib import Path
import os

from payroll_module import (
    GestorPlanillaDiferida,
    CalcularAguinaldo,
    a_decimal,
    Empleado,
    Contrato,
    PeriodoPlanilla,
    TransaccionPagoPlanilla,
)

TEST_DB_PATH = Path(__file__).resolve().parent / "test_planilla_temp.db"


class TestPayrollModule(unittest.TestCase):

    def setUp(self):
        """Crea una base de datos aislada para pruebas."""
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()
        self.gestor = GestorPlanillaDiferida(db_path=TEST_DB_PATH)
        self.conn = self.gestor.get_connection()
        
        # Crear esquema base de empleados y usuarios
        self.conn.execute("""
        CREATE TABLE empleados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cedula TEXT UNIQUE NOT NULL,
            nombre TEXT NOT NULL,
            primer_nombre TEXT,
            segundo_nombre TEXT,
            primer_apellido TEXT,
            segundo_apellido TEXT,
            cargo TEXT NOT NULL DEFAULT 'Administrador',
            cargo_id INTEGER DEFAULT 1,
            numero_inss TEXT,
            departamento TEXT,
            fecha_ingreso TEXT,
            salario_base REAL DEFAULT 0.0,
            activo INTEGER DEFAULT 1
        );
        """)
        self.conn.execute("""
        CREATE TABLE usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            nombre TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            rol TEXT DEFAULT 'admin',
            activo INTEGER DEFAULT 1
        );
        """)
        self.conn.execute("INSERT INTO usuarios (id, usuario, nombre, password_hash, rol) VALUES (1, 'admin', 'Administrador', 'hash', 'admin');")
        self.conn.commit()

        # Asegurar esquema de contratos, períodos y transacciones
        self.gestor.asegurar_esquema(self.conn)

    def tearDown(self):
        self.conn.close()
        if TEST_DB_PATH.exists():
            try:
                TEST_DB_PATH.unlink()
            except PermissionError:
                pass

    def test_01_precision_decimal_monetaria(self):
        """Verifica que a_decimal maneje correctamente números, redondeo y nulos."""
        self.assertEqual(a_decimal(100.555), Decimal("100.56"))
        self.assertEqual(a_decimal("5000.00"), Decimal("5000.00"))
        self.assertEqual(a_decimal(None), Decimal("0.00"))
        self.assertEqual(a_decimal(0), Decimal("0.00"))
        # Operaciones financieras sin error de punto flotante
        total = Decimal("0.00")
        for _ in range(10):
            total += a_decimal("0.10")
        self.assertEqual(total, Decimal("1.00"))

    def test_02_contrato_y_periodo_creacion(self):
        """Verifica la formalización de contratos y apertura de períodos."""
        self.conn.execute(
            "INSERT INTO empleados (cedula, nombre, cargo, fecha_ingreso, salario_base) VALUES ('001-000000-0001A', 'Pedro Gomez', 'Ventas', '2026-01-01', 10000.0)"
        )
        self.conn.commit()
        emp_id = 1

        contrato = self.gestor.registrar_o_actualizar_contrato(
            empleado_id=emp_id,
            salario_base=Decimal("10000.00"),
            tipo_contrato="Indeterminado",
            fecha_inicio="2026-01-01",
            conn=self.conn
        )
        self.assertIsNotNone(contrato.id)
        self.assertEqual(contrato.salario_base, Decimal("10000.00"))

        periodo = self.gestor.obtener_o_crear_periodo(empleado_id=emp_id, anio=2026, mes=1, conn=self.conn)
        self.assertEqual(periodo.descripcion, "Planilla Enero 2026")
        self.assertEqual(periodo.salario_base_pactado, Decimal("10000.00"))
        self.assertEqual(periodo.total_pagado, Decimal("0.00"))
        self.assertEqual(periodo.estado, "pendiente")
        self.assertGreater(periodo.salario_neto_total, Decimal("0.00"))
        self.assertEqual(periodo.saldo_pendiente, periodo.salario_neto_total)

    def test_03_bloqueo_de_sobrepago(self):
        """Valida que el sistema rechace montos que excedan el saldo pendiente."""
        self.conn.execute(
            "INSERT INTO empleados (cedula, nombre, cargo, fecha_ingreso, salario_base) VALUES ('001-000000-0002B', 'Ana Ruiz', 'Bodega', '2026-02-01', 10000.0)"
        )
        self.conn.commit()
        emp_id = 1

        periodo = self.gestor.obtener_o_crear_periodo(empleado_id=emp_id, anio=2026, mes=2, salario_base_manual=Decimal("10000.00"), conn=self.conn)
        saldo_inicial = periodo.saldo_pendiente

        # Intentar pagar saldo + 1 NIO debe fallar
        monto_excesivo = saldo_inicial + Decimal("1.00")
        with self.assertRaises(ValueError) as ctx:
            self.gestor.registrar_pago_diferido(
                empleado_id=emp_id,
                periodo_planilla_id=periodo.id,
                monto=monto_excesivo,
                fecha_pago="2026-02-05",
                conn=self.conn
            )
        self.assertIn("excede el saldo pendiente", str(ctx.exception))

    def test_04_multiples_abonos_y_cambio_de_estado(self):
        """Valida N transacciones de pago para un mismo período y su liquidación completa."""
        self.conn.execute(
            "INSERT INTO empleados (cedula, nombre, cargo, fecha_ingreso, salario_base) VALUES ('001-000000-0003C', 'Carlos Silva', 'TI', '2026-03-01', 12000.0)"
        )
        self.conn.commit()
        emp_id = 1

        periodo = self.gestor.obtener_o_crear_periodo(empleado_id=emp_id, anio=2026, mes=3, salario_base_manual=Decimal("12000.00"), conn=self.conn)
        neto_total = periodo.salario_neto_total

        # Abono 1: Quincena 1
        abono1_monto = Decimal("5000.00")
        tx1 = self.gestor.registrar_pago_diferido(
            empleado_id=emp_id,
            periodo_planilla_id=periodo.id,
            monto=abono1_monto,
            fecha_pago="2026-03-15",
            concepto="Abono Quincena 1",
            conn=self.conn
        )
        self.assertEqual(tx1.monto, abono1_monto)

        row_p1 = self.conn.execute("SELECT * FROM periodos_planilla WHERE id = ?", (periodo.id,)).fetchone()
        self.assertEqual(row_p1["estado"], "pago_parcial")
        self.assertEqual(a_decimal(row_p1["total_pagado"]), abono1_monto)
        self.assertEqual(a_decimal(row_p1["saldo_pendiente"]), neto_total - abono1_monto)

        # Abono 2: Quincena 2 (liquidación restante)
        abono2_monto = neto_total - abono1_monto
        tx2 = self.gestor.registrar_pago_diferido(
            empleado_id=emp_id,
            periodo_planilla_id=periodo.id,
            monto=abono2_monto,
            fecha_pago="2026-03-30",
            concepto="Abono Quincena 2 (Liquidación)",
            conn=self.conn
        )
        self.assertEqual(tx2.monto, abono2_monto)

        row_p2 = self.conn.execute("SELECT * FROM periodos_planilla WHERE id = ?", (periodo.id,)).fetchone()
        self.assertEqual(row_p2["estado"], "pagado_completo")
        self.assertEqual(a_decimal(row_p2["total_pagado"]), neto_total)
        self.assertEqual(a_decimal(row_p2["saldo_pendiente"]), Decimal("0.00"))

        # Intentar abonar en período saldado debe fallar
        with self.assertRaises(ValueError):
            self.gestor.registrar_pago_diferido(
                empleado_id=emp_id,
                periodo_planilla_id=periodo.id,
                monto=Decimal("100.00"),
                fecha_pago="2026-03-31",
                conn=self.conn
            )

    def test_05_casos_de_prueba_rosita_franco_marlene(self):
        """
        Verifica el cálculo de Aguinaldo para los 3 casos de prueba del requerimiento:
        - Rosita: Salario 10,000, Pago 5,000 el 01/02/2026 (Año 2026, 303 días).
        - Franco: Salario 12,000, Pago 6,000 el 01/06/2026 (Año 2026, 183 días).
        - Marlene: Salario 15,000, Pago 7,500 el 01/11/2025 (Año 2025, 30 días).
        """
        # 1. Rosita
        self.conn.execute(
            "INSERT INTO empleados (id, cedula, nombre, cargo, fecha_ingreso, salario_base) VALUES (10, '001-010290-0001R', 'Rosita García', 'Admin', '2026-02-01', 10000.0)"
        )
        self.gestor.registrar_o_actualizar_contrato(10, Decimal("10000.00"), fecha_inicio="2026-02-01", conn=self.conn)
        p_rosita = self.gestor.obtener_o_crear_periodo(10, 2026, 2, Decimal("10000.00"), conn=self.conn)
        self.gestor.registrar_pago_diferido(10, p_rosita.id, Decimal("5000.00"), "2026-02-01", "Primer abono", conn=self.conn)

        res_rosita = self.gestor.CalcularAguinaldo(10, 2026, conn=self.conn)
        self.assertEqual(res_rosita.dias_trabajados, 303)
        self.assertEqual(res_rosita.total_salario_acumulado, Decimal("5000.00"))
        # (5000 / 365) * 303 = 4150.68
        self.assertEqual(res_rosita.aguinaldo_formula_solicitada, Decimal("4150.68"))
        self.assertEqual(res_rosita.aguinaldo_ley_185_acumulado, Decimal("416.67"))
        self.assertIn("Pago parcial registrado el 2026-02-01", res_rosita.estado_pagos)

        # 2. Franco
        self.conn.execute(
            "INSERT INTO empleados (id, cedula, nombre, cargo, fecha_ingreso, salario_base) VALUES (20, '001-150692-0002F', 'Franco Martínez', 'Admin', '2026-06-01', 12000.0)"
        )
        self.gestor.registrar_o_actualizar_contrato(20, Decimal("12000.00"), fecha_inicio="2026-06-01", conn=self.conn)
        p_franco = self.gestor.obtener_o_crear_periodo(20, 2026, 6, Decimal("12000.00"), conn=self.conn)
        self.gestor.registrar_pago_diferido(20, p_franco.id, Decimal("6000.00"), "2026-06-01", "Primer abono", conn=self.conn)

        res_franco = self.gestor.CalcularAguinaldo(20, 2026, conn=self.conn)
        self.assertEqual(res_franco.dias_trabajados, 183)
        self.assertEqual(res_franco.total_salario_acumulado, Decimal("6000.00"))
        # (6000 / 365) * 183 = 3008.22
        self.assertEqual(res_franco.aguinaldo_formula_solicitada, Decimal("3008.22"))
        self.assertEqual(res_franco.aguinaldo_ley_185_acumulado, Decimal("500.00"))
        self.assertIn("Pago parcial registrado el 2026-06-01", res_franco.estado_pagos)

        # 3. Marlene
        self.conn.execute(
            "INSERT INTO empleados (id, cedula, nombre, cargo, fecha_ingreso, salario_base) VALUES (30, '001-201188-0003M', 'Marlene López', 'Admin', '2025-11-01', 15000.0)"
        )
        self.gestor.registrar_o_actualizar_contrato(30, Decimal("15000.00"), fecha_inicio="2025-11-01", conn=self.conn)
        p_marlene = self.gestor.obtener_o_crear_periodo(30, 2025, 11, Decimal("15000.00"), conn=self.conn)
        self.gestor.registrar_pago_diferido(30, p_marlene.id, Decimal("7500.00"), "2025-11-01", "Primer abono", conn=self.conn)

        res_marlene = self.gestor.CalcularAguinaldo(30, 2025, conn=self.conn)
        self.assertEqual(res_marlene.dias_trabajados, 30)
        self.assertEqual(res_marlene.total_salario_acumulado, Decimal("7500.00"))
        # (7500 / 365) * 30 = 616.44
        self.assertEqual(res_marlene.aguinaldo_formula_solicitada, Decimal("616.44"))
        self.assertEqual(res_marlene.aguinaldo_ley_185_acumulado, Decimal("625.00"))
        self.assertIn("Pago parcial registrado el 2025-11-01", res_marlene.estado_pagos)

    def test_06_aguinaldo_anio_completo(self):
        """Verifica que un empleado con año completo (365 días) reciba su mes completo de salario base."""
        self.conn.execute(
            "INSERT INTO empleados (id, cedula, nombre, cargo, fecha_ingreso, salario_base) VALUES (40, '001-010190-0004Z', 'Empleado Antiguo', 'Admin', '2024-01-01', 20000.0)"
        )
        self.conn.commit()
        res_completo = self.gestor.CalcularAguinaldo(40, 2026, conn=self.conn)
        self.assertEqual(res_completo.dias_trabajados, 365)
        self.assertTrue(res_completo.es_anio_completo)
        self.assertEqual(res_completo.aguinaldo_formula_solicitada, Decimal("20000.00"))


if __name__ == "__main__":
    unittest.main()
