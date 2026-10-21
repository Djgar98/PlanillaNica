import unittest
from app import app
from database import get_db, init_db
from werkzeug.security import generate_password_hash

class TestRolesIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        # Seed test users for each role if they don't exist
        test_users = [
            ("user_admin", "admin"),
            ("user_rrhh", "rrhh"),
            ("user_vendedor", "vendedor"),
            ("user_bodega", "bodega"),
            ("user_contabilidad", "contabilidad"),
            ("user_compras", "compras"),
            ("user_supervisor", "supervisor"),
            ("user_auditor", "auditor"),
        ]
        with get_db() as conn:
            for username, rol in test_users:
                conn.execute(
                    "INSERT OR REPLACE INTO usuarios (usuario, nombre, password_hash, rol, activo) VALUES (?, ?, ?, ?, 1)",
                    (username, f"Usuario {rol.upper()}", generate_password_hash("password123"), rol)
                )

    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False

    def login_as(self, username, rol):
        with self.client.session_transaction() as sess:
            sess["usuario"] = username
            sess["usuario_id"] = 999
            sess["rol"] = rol
            sess["csrf_token"] = "test-token"

    def test_admin_has_full_access(self):
        self.login_as("user_admin", "admin")
        resp = self.client.get("/usuarios")
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get("/inventario")
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get("/ventas")
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get("/reportes/ventas")
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get("/reportes/planilla-mensual")
        self.assertEqual(resp.status_code, 200)

    def test_rrhh_permissions_and_restrictions(self):
        self.login_as("user_rrhh", "rrhh")
        # RRHH can access employees and payroll
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get("/reportes/planilla-mensual")
        self.assertEqual(resp.status_code, 200)
        # RRHH CANNOT access user management
        resp = self.client.get("/usuarios")
        self.assertEqual(resp.status_code, 403)
        # RRHH CANNOT create sales
        resp = self.client.get("/ventas/nueva")
        self.assertEqual(resp.status_code, 403)
        # RRHH CANNOT modify inventory
        resp = self.client.get("/inventario/nuevo")
        self.assertEqual(resp.status_code, 403)

    def test_vendedor_permissions_and_restrictions(self):
        self.login_as("user_vendedor", "vendedor")
        # Vendedor can access sales and new sale
        resp = self.client.get("/ventas")
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get("/ventas/nueva")
        self.assertEqual(resp.status_code, 200)
        # Vendedor CANNOT access user management
        resp = self.client.get("/usuarios")
        self.assertEqual(resp.status_code, 403)
        # Vendedor CANNOT access employee management
        resp = self.client.get("/empleado/nuevo")
        self.assertEqual(resp.status_code, 403)
        # Vendedor CANNOT create inventory products
        resp = self.client.get("/inventario/nuevo")
        self.assertEqual(resp.status_code, 403)

    def test_bodega_permissions_and_restrictions(self):
        self.login_as("user_bodega", "bodega")
        # Bodega can view inventory and kardex
        resp = self.client.get("/inventario")
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get("/kardex")
        self.assertEqual(resp.status_code, 200)
        # Bodega CANNOT create sales
        resp = self.client.get("/ventas/nueva")
        self.assertEqual(resp.status_code, 403)
        # Bodega CANNOT manage users
        resp = self.client.get("/usuarios")
        self.assertEqual(resp.status_code, 403)
        # Bodega CANNOT manage product catalog (compras/admin does this)
        resp = self.client.get("/inventario/nuevo")
        self.assertEqual(resp.status_code, 403)

    def test_contabilidad_permissions_and_restrictions(self):
        self.login_as("user_contabilidad", "contabilidad")
        # Contabilidad index and redirection
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.headers["Location"].endswith("/contabilidad"))
        resp = self.client.get("/contabilidad")
        self.assertEqual(resp.status_code, 200)
        # Contabilidad can view sales, payroll report, and sales report
        resp = self.client.get("/ventas")
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get("/reportes/ventas")
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get("/reportes/planilla-mensual")
        self.assertEqual(resp.status_code, 200)
        # Contabilidad CANNOT manage users
        resp = self.client.get("/usuarios")
        self.assertEqual(resp.status_code, 403)
        # Contabilidad CANNOT create sales
        resp = self.client.get("/ventas/nueva")
        self.assertEqual(resp.status_code, 403)
        # Contabilidad CANNOT create products
        resp = self.client.get("/inventario/nuevo")
        self.assertEqual(resp.status_code, 403)

    def test_compras_permissions_and_restrictions(self):
        self.login_as("user_compras", "compras")
        # Compras can manage products and categories
        resp = self.client.get("/inventario")
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get("/inventario/nuevo")
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get("/categorias")
        self.assertEqual(resp.status_code, 200)
        # Compras CANNOT manage users
        resp = self.client.get("/usuarios")
        self.assertEqual(resp.status_code, 403)
        # Compras CANNOT create sales
        resp = self.client.get("/ventas/nueva")
        self.assertEqual(resp.status_code, 403)

    def test_supervisor_permissions_and_restrictions(self):
        self.login_as("user_supervisor", "supervisor")
        # Supervisor can view sales, inventory, requests, reports
        resp = self.client.get("/ventas")
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get("/solicitudes")
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get("/reportes/ventas")
        self.assertEqual(resp.status_code, 200)
        # Supervisor CANNOT manage users
        resp = self.client.get("/usuarios")
        self.assertEqual(resp.status_code, 403)
        # Supervisor CANNOT create sales
        resp = self.client.get("/ventas/nueva")
        self.assertEqual(resp.status_code, 403)

    def test_auditor_permissions_and_restrictions(self):
        self.login_as("user_auditor", "auditor")
        # Auditor has transversal read-only access
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get("/inventario")
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get("/ventas")
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get("/reportes/ventas")
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get("/reportes/planilla-mensual")
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get("/kardex")
        self.assertEqual(resp.status_code, 200)
        # Auditor CANNOT mutate data
        resp = self.client.get("/usuarios")
        self.assertEqual(resp.status_code, 403)
        resp = self.client.get("/inventario/nuevo")
        self.assertEqual(resp.status_code, 403)
        resp = self.client.get("/ventas/nueva")
        self.assertEqual(resp.status_code, 403)
        resp = self.client.get("/empleado/nuevo")
        self.assertEqual(resp.status_code, 403)

if __name__ == "__main__":
    unittest.main()
