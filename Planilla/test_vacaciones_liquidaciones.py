import os
import unittest
import sqlite3
from datetime import datetime, date
from app import app
from database import (
    get_db,
    init_db,
    calcular_saldo_vacaciones,
    registrar_vacaciones_gozadas,
    obtener_historial_vacaciones,
    obtener_resumen_vacaciones_todos,
    calcular_antiguedad_detallada,
    calcular_liquidacion,
    guardar_liquidacion,
    obtener_liquidaciones,
    obtener_liquidacion_por_id
)

class TestVacacionesLiquidaciones(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        cls.client = app.test_client()

    def setUp(self):
        # Aseguramos tablas creadas
        init_db()

    def test_01_computo_saldo_vacaciones(self):
        """Verifica la fórmula legal de vacaciones (Art. 76 Ley 185: 2.5 días/mes o 30 días/año)."""
        with get_db() as conn:
            emp = conn.execute("SELECT id, fecha_ingreso FROM empleados WHERE activo = 1 LIMIT 1").fetchone()
            self.assertIsNotNone(emp, "Debe existir al menos un empleado de prueba")

            saldo = calcular_saldo_vacaciones(conn, emp["id"], fecha_corte="2026-10-30")
            self.assertGreater(saldo["dias_acumulados"], 0)
            self.assertGreaterEqual(saldo["dias_pendientes"], 0)
            self.assertEqual(saldo["dias_pendientes"], round(saldo["dias_acumulados"] - saldo["dias_gozados"], 2))

    def test_02_registrar_vacaciones_gozadas(self):
        """Verifica el registro de vacaciones tomadas y el descuento del saldo disponible."""
        with get_db() as conn:
            emp = conn.execute("SELECT id FROM empleados WHERE activo = 1 LIMIT 1").fetchone()
            emp_id = emp["id"]

            saldo_antes = calcular_saldo_vacaciones(conn, emp_id, fecha_corte="2026-10-30")
            dias_a_tomar = 2.0

            id_reg = registrar_vacaciones_gozadas(
                conn,
                empleado_id=emp_id,
                fecha_inicio="2026-10-15",
                fecha_fin="2026-10-16",
                dias_gozados=dias_a_tomar,
                observaciones="Prueba unitaria de vacaciones gozadas"
            )
            self.assertIsNotNone(id_reg)

            saldo_despues = calcular_saldo_vacaciones(conn, emp_id, fecha_corte="2026-10-30")
            self.assertAlmostEqual(saldo_despues["dias_gozados"], saldo_antes["dias_gozados"] + dias_a_tomar, places=2)

    def test_03_antiguedad_detallada(self):
        """Verifica cálculo exacto de años, meses y días de servicio."""
        f_ingreso = date(2023, 1, 15)
        f_salida = date(2026, 4, 20)
        anios, meses, dias, total_dias = calcular_antiguedad_detallada(f_ingreso, f_salida)

        self.assertEqual(anios, 3)
        self.assertEqual(meses, 3)
        self.assertEqual(dias, 5)
        self.assertGreater(total_dias, 1100)

    def test_04_liquidacion_por_despido(self):
        """Verifica liquidación por Despido: incluye indemnización Art. 45."""
        with get_db() as conn:
            # Crear empleado temporal con 2 años de servicio para cálculo predecible
            cursor = conn.execute("""
                INSERT INTO empleados (nombre, cedula, cargo, cargo_id, salario_base, fecha_ingreso, activo)
                VALUES ('Test Despido Colab', '001-150190-0001A', 'Analista', 1, 30000.0, '2024-01-01', 1)
            """)
            emp_id = cursor.lastrowid

            calc = calcular_liquidacion(
                conn,
                empleado_id=emp_id,
                fecha_salida="2026-01-01",
                motivo="despido",
                regimen="privada",
                dias_salario_pendiente=5,
                otras_deducciones=500.0,
                motivo_deducciones="Préstamo"
            )

            # Verificaciones:
            self.assertEqual(calc["motivo"], "despido")
            self.assertEqual(calc["salario_base_mensual"], 30000.0)
            self.assertEqual(calc["salario_diario"], 1000.0)
            
            # Salario pendiente (5 días = 5,000; INSS 7% = 350)
            self.assertEqual(calc["monto_salario_pendiente"], 5000.0)
            self.assertEqual(calc["inss_salario_pendiente"], 350.0)

            # Indemnización Art. 45: 2 años exactos = 2 meses = 60,000.0
            self.assertEqual(calc["aplica_indemnizacion"], 1)
            self.assertAlmostEqual(calc["meses_indemnizacion"], 2.0, places=1)
            self.assertAlmostEqual(calc["monto_indemnizacion"], 60000.0, delta=300.0)

            # Total bruto y deducciones
            self.assertGreater(calc["total_bruto"], 65000.0)
            self.assertEqual(calc["total_deducciones"], 350.0 + 500.0)
            self.assertEqual(calc["total_neto"], round(calc["total_bruto"] - 850.0, 2))

            # Limpiar
            conn.execute("DELETE FROM empleados WHERE id = ?", (emp_id,))

    def test_05_liquidacion_por_renuncia_privada(self):
        """Verifica liquidación por Renuncia en Sector Privado: Art. 45 es 0.00 pero conserva vacaciones y aguinaldo."""
        with get_db() as conn:
            cursor = conn.execute("""
                INSERT INTO empleados (nombre, cedula, cargo, cargo_id, salario_base, fecha_ingreso, activo)
                VALUES ('Test Renuncia Colab', '001-150190-0002B', 'Operador', 1, 20000.0, '2024-01-01', 1)
            """)
            emp_id = cursor.lastrowid

            calc = calcular_liquidacion(
                conn,
                empleado_id=emp_id,
                fecha_salida="2026-01-01",
                motivo="renuncia",
                regimen="privada",
                dias_salario_pendiente=0,
                otras_deducciones=0
            )

            # En renuncia privada NO aplica indemnización Art. 45
            self.assertEqual(calc["motivo"], "renuncia")
            self.assertEqual(calc["aplica_indemnizacion"], 0)
            self.assertEqual(calc["monto_indemnizacion"], 0.0)

            # Pero SÍ incluye vacaciones y aguinaldo acumulados
            self.assertGreater(calc["monto_vacaciones"], 0.0)
            self.assertGreater(calc["monto_aguinaldo"], 0.0)
            self.assertEqual(calc["total_neto"], calc["total_bruto"])

            # Limpiar
            conn.execute("DELETE FROM empleados WHERE id = ?", (emp_id,))

    def test_06_guardar_liquidacion_y_baja(self):
        """Verifica guardar liquidación formalmente y dar de baja al empleado."""
        with get_db() as conn:
            cursor = conn.execute("""
                INSERT INTO empleados (nombre, cedula, cargo, cargo_id, salario_base, fecha_ingreso, activo)
                VALUES ('Test Liquidar Final', '001-150190-0003C', 'Supervisor', 1, 15000.0, '2025-01-01', 1)
            """)
            emp_id = cursor.lastrowid

            calc = calcular_liquidacion(conn, emp_id, fecha_salida="2026-06-01", motivo="despido")
            liq_id, codigo = guardar_liquidacion(conn, calc, usuario_id=1, dar_de_baja=True)

            self.assertIsNotNone(liq_id)
            self.assertTrue(codigo.startswith("LIQ-"))

            # Verificar que el empleado fue desactivado
            emp = conn.execute("SELECT activo FROM empleados WHERE id = ?", (emp_id,)).fetchone()
            self.assertEqual(emp["activo"], 0)

            # Verificar consulta de liquidación guardada
            liq_row = obtener_liquidacion_por_id(conn, liq_id)
            self.assertIsNotNone(liq_row)
            self.assertEqual(liq_row["codigo"], codigo)
            self.assertEqual(liq_row["motivo"], "despido")

            # Limpiar
            conn.execute("DELETE FROM liquidaciones WHERE id = ?", (liq_id,))
            conn.execute("DELETE FROM empleados WHERE id = ?", (emp_id,))

    def test_07_rutas_web(self):
        """Verifica que las rutas GET y POST respondan adecuadamente con una sesión autenticada."""
        with self.client.session_transaction() as sess:
            sess["usuario_id"] = 1
            sess["usuario"] = "admin"
            sess["rol"] = "admin"
            sess["csrf_token"] = "test-token"

        # GET Vacaciones
        res_vac = self.client.get("/vacaciones")
        self.assertEqual(res_vac.status_code, 200)

        # GET Liquidaciones
        res_liq = self.client.get("/liquidaciones")
        self.assertEqual(res_liq.status_code, 200)

        # GET Nueva Liquidación
        res_nueva = self.client.get("/liquidaciones/nueva")
        self.assertEqual(res_nueva.status_code, 200)

        # AJAX calcular
        with get_db() as conn:
            emp = conn.execute("SELECT id FROM empleados WHERE activo = 1 LIMIT 1").fetchone()
            emp_id = emp["id"]

        res_ajax = self.client.post("/liquidaciones/calcular-ajax", data={
            "empleado_id": emp_id,
            "fecha_salida": "2026-10-30",
            "motivo": "despido",
            "regimen": "privada",
            "dias_salario_pendiente": "0",
            "otras_deducciones": "0"
        })
        self.assertEqual(res_ajax.status_code, 200)
        data = res_ajax.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("datos", data)
        self.assertIn("total_neto", data["datos"])

if __name__ == "__main__":
    unittest.main()
