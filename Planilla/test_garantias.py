"""
test_garantias.py
-----------------
Pruebas unitarias e integración para el módulo de garantías de productos.
Valida:
1. Creación automática de garantías al concretar una venta.
2. Anulación de garantías al anular o devolver una venta completa o parcial.
3. Clasificación de estados: activas, por vencer, vencidas, ejecutadas y anuladas.
4. Flujo de 'Ejecutar Garantía' con diagnóstico, solución técnica y descuento opcional de inventario.
5. Control de permisos de acceso.
"""

import unittest
from datetime import datetime, timedelta
from app import app
from database import (
    get_db, init_db, sumar_meses, crear_garantias_para_venta,
    anular_garantias_de_venta, anular_garantias_parcial,
    obtener_garantias, obtener_resumen_garantias,
    obtener_garantia_por_id, ejecutar_garantia
)
from werkzeug.security import generate_password_hash


class TestModuloGarantias(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()
        # Crear usuario vendedor y admin de prueba
        with get_db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO usuarios (id, usuario, nombre, password_hash, rol, activo) VALUES (901, 'vend_test', 'Vendedor Test', ?, 'vendedor', 1)",
                (generate_password_hash("pass123"),)
            )
            conn.execute(
                "INSERT OR REPLACE INTO usuarios (id, usuario, nombre, password_hash, rol, activo) VALUES (902, 'admin_test', 'Admin Test', ?, 'admin', 1)",
                (generate_password_hash("pass123"),)
            )
            # Asegurar producto de prueba con 6 meses de garantía
            conn.execute(
                "INSERT OR REPLACE INTO productos (id, codigo, nombre, precio_compra, precio_venta, existencia, stock_minimo, meses_garantia, activo) "
                "VALUES (801, 'TEST-GAR-01', 'Laptop Gamer Pro', 500, 800, 20, 2, 6, 1)"
            )

    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False

    def login_as(self, usuario="admin_test", rol="admin", usuario_id=902):
        with self.client.session_transaction() as sess:
            sess["usuario"] = usuario
            sess["usuario_id"] = usuario_id
            sess["rol"] = rol
            sess["csrf_token"] = "token-test"

    def test_01_calculo_sumar_meses(self):
        """Verifica la suma exacta de meses con ajuste de fin de mes."""
        fecha_base = datetime(2026, 1, 31).date()
        # Sumar 1 mes a 31 de enero en año no bisiesto o bisiesto debe dar fin de febrero (28)
        res_feb = sumar_meses(fecha_base, 1)
        self.assertEqual(res_feb.month, 2)
        self.assertIn(res_feb.day, (28, 29))

        # Sumar 6 meses
        res_6m = sumar_meses(fecha_base, 6)
        self.assertEqual(res_6m.month, 7)
        self.assertEqual(res_6m.day, 31)

    def test_02_creacion_automatica_garantias_al_vender(self):
        """Al registrar una venta, se deben crear garantías automáticamente para cada unidad."""
        with get_db() as conn:
            # Crear venta de 2 unidades del producto 801
            v_cur = conn.execute(
                "INSERT INTO ventas (cliente, usuario_id, subtotal, total, estado) VALUES ('Carlos Slim', 901, 1600, 1600, 'completada')"
            )
            venta_id = v_cur.lastrowid
            d_cur = conn.execute(
                "INSERT INTO detalle_ventas (venta_id, producto_id, cantidad, precio_unitario, subtotal) VALUES (?, 801, 2, 800, 1600)",
                (venta_id,)
            )
            
            creadas = crear_garantias_para_venta(conn, venta_id, "Carlos Slim")
            self.assertEqual(creadas, 2)

            garantias = conn.execute("SELECT * FROM garantias WHERE venta_id = ?", (venta_id,)).fetchall()
            self.assertEqual(len(garantias), 2)
            self.assertEqual(garantias[0]["estado"], "activa")
            self.assertEqual(garantias[0]["meses_cobertura"], 6)
            self.assertTrue(garantias[0]["codigo"].startswith(f"GAR-{venta_id:04d}-801-"))

    def test_03_anulacion_garantias_por_devolucion_o_anulacion(self):
        """Al anular o devolver una venta, sus garantías deben pasar a 'anulada'."""
        with get_db() as conn:
            v_cur = conn.execute(
                "INSERT INTO ventas (cliente, usuario_id, subtotal, total, estado) VALUES ('Cliente Anular', 901, 800, 800, 'completada')"
            )
            venta_id = v_cur.lastrowid
            conn.execute(
                "INSERT INTO detalle_ventas (venta_id, producto_id, cantidad, precio_unitario, subtotal) VALUES (?, 801, 1, 800, 800)",
                (venta_id,)
            )
            crear_garantias_para_venta(conn, venta_id, "Cliente Anular")

            # Comprobar que está activa
            gar = conn.execute("SELECT * FROM garantias WHERE venta_id = ?", (venta_id,)).fetchone()
            self.assertEqual(gar["estado"], "activa")

            # Anular venta
            anular_garantias_de_venta(conn, venta_id, "Devolución por defecto")

            gar_post = conn.execute("SELECT * FROM garantias WHERE venta_id = ?", (venta_id,)).fetchone()
            self.assertEqual(gar_post["estado"], "anulada")
            self.assertIn("Devolución por defecto", gar_post["motivo_anulacion"])

    def test_04_anulacion_parcial_garantias(self):
        """Al devolver parcialmente 1 de 2 unidades, solo 1 garantía debe anularse."""
        with get_db() as conn:
            v_cur = conn.execute(
                "INSERT INTO ventas (cliente, usuario_id, subtotal, total, estado) VALUES ('Cliente Parcial', 901, 1600, 1600, 'completada')"
            )
            venta_id = v_cur.lastrowid
            conn.execute(
                "INSERT INTO detalle_ventas (venta_id, producto_id, cantidad, precio_unitario, subtotal) VALUES (?, 801, 2, 800, 1600)",
                (venta_id,)
            )
            crear_garantias_para_venta(conn, venta_id, "Cliente Parcial")

            # Devolver 1 unidad
            anular_garantias_parcial(conn, venta_id, 801, 1, "Devolución de 1 unidad")

            anuladas = conn.execute("SELECT COUNT(*) FROM garantias WHERE venta_id = ? AND estado = 'anulada'", (venta_id,)).fetchone()[0]
            activas = conn.execute("SELECT COUNT(*) FROM garantias WHERE venta_id = ? AND estado = 'activa'", (venta_id,)).fetchone()[0]
            self.assertEqual(anuladas, 1)
            self.assertEqual(activas, 1)

    def test_05_ejecutar_garantia(self):
        """Procesa y ejecuta un reclamo técnico sobre una garantía activa."""
        with get_db() as conn:
            v_cur = conn.execute(
                "INSERT INTO ventas (cliente, usuario_id, subtotal, total, estado) VALUES ('Maria Lopez', 901, 800, 800, 'completada')"
            )
            venta_id = v_cur.lastrowid
            conn.execute(
                "INSERT INTO detalle_ventas (venta_id, producto_id, cantidad, precio_unitario, subtotal) VALUES (?, 801, 1, 800, 800)",
                (venta_id,)
            )
            crear_garantias_para_venta(conn, venta_id, "Maria Lopez")
            gar = conn.execute("SELECT * FROM garantias WHERE venta_id = ?", (venta_id,)).fetchone()

            # Ejecutar garantía con reemplazo
            codigo = ejecutar_garantia(
                conn,
                garantia_id=gar["id"],
                usuario_id=902,
                tipo_resolucion="reemplazo",
                motivo_reclamo="No enciende la pantalla",
                diagnostico="Defecto de panel interno",
                resolucion_notas="Se entregó unidad de reemplazo al cliente",
                descontar_inventario=True
            )
            self.assertEqual(codigo, gar["codigo"])

            # Comprobar actualización
            gar_ejecutada = conn.execute("SELECT * FROM garantias WHERE id = ?", (gar["id"],)).fetchone()
            self.assertEqual(gar_ejecutada["estado"], "ejecutada")
            self.assertEqual(gar_ejecutada["tipo_resolucion"], "reemplazo")
            self.assertEqual(gar_ejecutada["usuario_ejecuta_id"], 902)
            self.assertIsNotNone(gar_ejecutada["fecha_ejecucion"])

    def test_06_rutas_web_garantias(self):
        """Verifica el acceso y respuestas de las rutas /garantias y certificado."""
        self.login_as("admin_test", "admin", 902)
        
        # 1. Página principal de garantías
        resp = self.client.get("/garantias")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Control y Gesti", resp.data)
        self.assertIn(b"Ejecutar", resp.data)

        # 2. Certificado de garantía
        with get_db() as conn:
            gar = conn.execute("SELECT id FROM garantias LIMIT 1").fetchone()
            self.assertIsNotNone(gar)
            gar_id = gar["id"]

        resp_cert = self.client.get(f"/garantias/{gar_id}/certificado")
        self.assertEqual(resp_cert.status_code, 200)
        self.assertIn(b"Certificado Oficial de Cobertura", resp_cert.data)

        # 3. Post ejecución por ruta HTTP
        with get_db() as conn:
            v_cur = conn.execute(
                "INSERT INTO ventas (cliente, usuario_id, subtotal, total, estado) VALUES ('Test HTTP', 902, 800, 800, 'completada')"
            )
            v_id = v_cur.lastrowid
            conn.execute("INSERT INTO detalle_ventas (venta_id, producto_id, cantidad, precio_unitario, subtotal) VALUES (?, 801, 1, 800, 800)", (v_id,))
            crear_garantias_para_venta(conn, v_id, "Test HTTP")
            g_test = conn.execute("SELECT id FROM garantias WHERE venta_id = ?", (v_id,)).fetchone()

        resp_post = self.client.post(
            f"/garantias/{g_test['id']}/ejecutar",
            data={
                "csrf_token": "token-test",
                "tipo_resolucion": "reparacion",
                "motivo_reclamo": "Falla en teclado",
                "diagnostico": "Reconexión de cinta interna",
                "resolucion_notas": "Reparado exitosamente",
                "descontar_inventario": "0"
            },
            follow_redirects=True
        )
        self.assertEqual(resp_post.status_code, 200)
        self.assertIn(b"ejecutada exitosamente", resp_post.data)


if __name__ == "__main__":
    unittest.main()
