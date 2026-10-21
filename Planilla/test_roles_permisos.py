"""
test_roles_permisos.py
----------------------
Pruebas unitarias para validar la implementación de la matriz de roles y permisos.
"""

import unittest
from roles_permisos import (
    ROLES, ROLES_INFO, PERMISOS, PERMISOS_POR_ROL,
    tiene_permiso, obtener_permisos_rol
)


class TestRolesPermisos(unittest.TestCase):

    def test_todos_los_roles_definidos(self):
        esperados = {"admin", "rrhh", "vendedor", "bodega", "contabilidad", "compras", "supervisor", "auditor"}
        self.assertEqual(set(ROLES), esperados)
        self.assertEqual(set(ROLES_INFO.keys()), esperados)

    def test_admin_acceso_total(self):
        for permiso in PERMISOS:
            self.assertTrue(tiene_permiso("admin", permiso), f"Admin debe tener {permiso}")

    def test_rrhh_permisos(self):
        # Permisos que debe tener
        self.assertTrue(tiene_permiso("rrhh", "consultar_empleados"))
        self.assertTrue(tiene_permiso("rrhh", "gestionar_empleados"))
        self.assertTrue(tiene_permiso("rrhh", "consultar_planilla"))
        self.assertTrue(tiene_permiso("rrhh", "procesar_planilla"))
        self.assertTrue(tiene_permiso("rrhh", "consultar_reportes_planilla"))
        
        # Restricciones
        self.assertFalse(tiene_permiso("rrhh", "gestionar_usuarios"))
        self.assertFalse(tiene_permiso("rrhh", "crear_ventas"))
        self.assertFalse(tiene_permiso("rrhh", "consultar_inventario"))
        self.assertFalse(tiene_permiso("rrhh", "gestionar_productos"))

    def test_vendedor_permisos(self):
        self.assertTrue(tiene_permiso("vendedor", "consultar_productos"))
        self.assertTrue(tiene_permiso("vendedor", "crear_ventas"))
        self.assertTrue(tiene_permiso("vendedor", "consultar_ventas_propias"))
        self.assertTrue(tiene_permiso("vendedor", "solicitar_anulacion"))
        
        # Restricciones
        self.assertFalse(tiene_permiso("vendedor", "consultar_todas_ventas"))
        self.assertFalse(tiene_permiso("vendedor", "resolver_solicitudes"))
        self.assertFalse(tiene_permiso("vendedor", "gestionar_productos"))
        self.assertFalse(tiene_permiso("vendedor", "consultar_planilla"))

    def test_bodega_permisos(self):
        self.assertTrue(tiene_permiso("bodega", "consultar_productos"))
        self.assertTrue(tiene_permiso("bodega", "consultar_inventario"))
        self.assertTrue(tiene_permiso("bodega", "registrar_entradas"))
        self.assertTrue(tiene_permiso("bodega", "ajustar_existencias"))
        self.assertTrue(tiene_permiso("bodega", "consultar_reportes_inventario"))
        
        # Restricciones
        self.assertFalse(tiene_permiso("bodega", "gestionar_productos"))
        self.assertFalse(tiene_permiso("bodega", "crear_ventas"))
        self.assertFalse(tiene_permiso("bodega", "resolver_solicitudes"))
        self.assertFalse(tiene_permiso("bodega", "consultar_planilla"))

    def test_contabilidad_permisos(self):
        self.assertTrue(tiene_permiso("contabilidad", "consultar_planilla"))
        self.assertTrue(tiene_permiso("contabilidad", "consultar_reportes_planilla"))
        self.assertTrue(tiene_permiso("contabilidad", "consultar_ventas_propias"))
        self.assertTrue(tiene_permiso("contabilidad", "consultar_todas_ventas"))
        self.assertTrue(tiene_permiso("contabilidad", "consultar_reportes_ventas"))
        self.assertTrue(tiene_permiso("contabilidad", "consultar_reportes_financieros"))
        
        # Restricciones
        self.assertFalse(tiene_permiso("contabilidad", "procesar_planilla"))
        self.assertFalse(tiene_permiso("contabilidad", "gestionar_empleados"))
        self.assertFalse(tiene_permiso("contabilidad", "crear_ventas"))
        self.assertFalse(tiene_permiso("contabilidad", "gestionar_productos"))

    def test_compras_permisos(self):
        self.assertTrue(tiene_permiso("compras", "consultar_productos"))
        self.assertTrue(tiene_permiso("compras", "gestionar_productos"))
        self.assertTrue(tiene_permiso("compras", "gestionar_categorias"))
        self.assertTrue(tiene_permiso("compras", "consultar_inventario"))
        self.assertTrue(tiene_permiso("compras", "registrar_entradas"))
        self.assertTrue(tiene_permiso("compras", "consultar_reportes_inventario"))
        
        # Restricciones
        self.assertFalse(tiene_permiso("compras", "ajustar_existencias"))
        self.assertFalse(tiene_permiso("compras", "crear_ventas"))
        self.assertFalse(tiene_permiso("compras", "consultar_planilla"))

    def test_supervisor_permisos(self):
        self.assertTrue(tiene_permiso("supervisor", "consultar_empleados"))
        self.assertTrue(tiene_permiso("supervisor", "consultar_planilla"))
        self.assertTrue(tiene_permiso("supervisor", "consultar_reportes_planilla"))
        self.assertTrue(tiene_permiso("supervisor", "consultar_productos"))
        self.assertTrue(tiene_permiso("supervisor", "consultar_inventario"))
        self.assertTrue(tiene_permiso("supervisor", "consultar_reportes_inventario"))
        self.assertTrue(tiene_permiso("supervisor", "consultar_ventas_propias"))
        self.assertTrue(tiene_permiso("supervisor", "consultar_todas_ventas"))
        self.assertTrue(tiene_permiso("supervisor", "resolver_solicitudes"))
        self.assertTrue(tiene_permiso("supervisor", "consultar_reportes_ventas"))
        self.assertTrue(tiene_permiso("supervisor", "consultar_reportes_financieros"))
        
        # Restricciones
        self.assertFalse(tiene_permiso("supervisor", "gestionar_usuarios"))
        self.assertFalse(tiene_permiso("supervisor", "gestionar_empleados"))
        self.assertFalse(tiene_permiso("supervisor", "procesar_planilla"))
        self.assertFalse(tiene_permiso("supervisor", "crear_ventas"))
        self.assertFalse(tiene_permiso("supervisor", "ajustar_existencias"))

    def test_auditor_permisos(self):
        self.assertTrue(tiene_permiso("auditor", "consultar_empleados"))
        self.assertTrue(tiene_permiso("auditor", "consultar_planilla"))
        self.assertTrue(tiene_permiso("auditor", "consultar_reportes_planilla"))
        self.assertTrue(tiene_permiso("auditor", "consultar_productos"))
        self.assertTrue(tiene_permiso("auditor", "consultar_inventario"))
        self.assertTrue(tiene_permiso("auditor", "consultar_reportes_inventario"))
        self.assertTrue(tiene_permiso("auditor", "consultar_ventas_propias"))
        self.assertTrue(tiene_permiso("auditor", "consultar_todas_ventas"))
        self.assertTrue(tiene_permiso("auditor", "consultar_reportes_ventas"))
        self.assertTrue(tiene_permiso("auditor", "consultar_reportes_financieros"))
        self.assertTrue(tiene_permiso("auditor", "consultar_reportes_auditoria"))
        
        # Restricciones (solo lectura)
        self.assertFalse(tiene_permiso("auditor", "gestionar_usuarios"))
        self.assertFalse(tiene_permiso("auditor", "gestionar_empleados"))
        self.assertFalse(tiene_permiso("auditor", "procesar_planilla"))
        self.assertFalse(tiene_permiso("auditor", "crear_ventas"))
        self.assertFalse(tiene_permiso("auditor", "resolver_solicitudes"))
        self.assertFalse(tiene_permiso("auditor", "gestionar_productos"))
        self.assertFalse(tiene_permiso("auditor", "registrar_entradas"))
        self.assertFalse(tiene_permiso("auditor", "ajustar_existencias"))


if __name__ == "__main__":
    unittest.main()
