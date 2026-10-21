"""
roles_permisos.py
-----------------
Módulo centralizado de definición y control de roles y permisos del sistema.
Basado estrictamente en el documento oficial:
"Definición de roles de usuario y permisos - Aplicación de gestión de planilla, ventas e inventario"
Universidad Nacional Héroes de San José de las Mulas (UNHSJM).

Define los 8 roles y las 21 capacidades de la matriz comparativa de permisos.
"""

from typing import Set, Dict, Any

# Lista canónica de los 8 roles definidos en el sistema
ROLES = (
    "admin",
    "rrhh",
    "vendedor",
    "bodega",
    "contabilidad",
    "compras",
    "supervisor",
    "auditor",
)

# Metadatos descriptivos de los roles para UI (badges, iconos y descripción)
ROLES_INFO: Dict[str, Dict[str, Any]] = {
    "admin": {
        "codigo": "admin",
        "nombre": "Administrador",
        "badge": "danger",
        "icono": "bi-shield-lock-fill",
        "emoji": "🛡️",
        "descripcion": "Responsable del acceso y la administración global. Dispone de acceso transversal a todos los módulos.",
    },
    "rrhh": {
        "codigo": "rrhh",
        "nombre": "Recursos Humanos",
        "badge": "success",
        "icono": "bi-people-fill",
        "emoji": "👥",
        "descripcion": "Responsable de la información laboral y salarial. Gestiona colaboradores y procesa planilla.",
    },
    "vendedor": {
        "codigo": "vendedor",
        "nombre": "Vendedor",
        "badge": "primary",
        "icono": "bi-cart-fill",
        "emoji": "🛒",
        "descripcion": "Usuario operativo de ventas. Consulta productos, registra ventas propias y solicita anulaciones.",
    },
    "bodega": {
        "codigo": "bodega",
        "nombre": "Bodega",
        "badge": "secondary",
        "icono": "bi-box-seam-fill",
        "emoji": "📦",
        "descripcion": "Responsable del control de existencias físicas. Registra entradas y ajustes de inventario.",
    },
    "contabilidad": {
        "codigo": "contabilidad",
        "nombre": "Contabilidad",
        "badge": "info",
        "icono": "bi-cash-coin",
        "emoji": "💰",
        "descripcion": "Usuario de consulta financiera. Examina ventas, planillas y reportes financieros sin modificar datos.",
    },
    "compras": {
        "codigo": "compras",
        "nombre": "Compras",
        "badge": "warning",
        "icono": "bi-bag-check-fill",
        "emoji": "🛍️",
        "descripcion": "Responsable del catálogo y las entradas. Gestiona productos, categorías y recepciones de stock.",
    },
    "supervisor": {
        "codigo": "supervisor",
        "nombre": "Supervisor",
        "badge": "dark",
        "icono": "bi-clipboard-check-fill",
        "emoji": "📋",
        "descripcion": "Responsable de supervisión y control. Resuelve solicitudes y consulta operaciones y reportes.",
    },
    "auditor": {
        "codigo": "auditor",
        "nombre": "Auditor",
        "badge": "secondary",
        "icono": "bi-search",
        "emoji": "🔍",
        "descripcion": "Usuario de revisión sin modificación. Supervisa trazabilidad, kardex y reportes de auditoría.",
    },
}

# Las 21 funcionalidades definidas en la Matriz Comparativa (Páginas 7 y 8)
PERMISOS = (
    "gestionar_usuarios",
    "consultar_empleados",
    "gestionar_empleados",
    "consultar_planilla",
    "procesar_planilla",
    "consultar_reportes_planilla",
    "consultar_productos",
    "gestionar_productos",
    "gestionar_categorias",
    "consultar_inventario",
    "registrar_entradas",
    "ajustar_existencias",
    "consultar_reportes_inventario",
    "crear_ventas",
    "consultar_ventas_propias",
    "consultar_todas_ventas",
    "solicitar_anulacion",
    "resolver_solicitudes",
    "consultar_reportes_ventas",
    "consultar_reportes_financieros",
    "consultar_reportes_auditoria",
)

# Matriz exacta de asignación de capacidades por rol
PERMISOS_POR_ROL: Dict[str, Set[str]] = {
    # Administrador: Comodín de acceso total
    "admin": {
        "*"
    },
    # Recursos Humanos (RRHH): Gestión laboral y salarial
    "rrhh": {
        "consultar_empleados",
        "gestionar_empleados",
        "consultar_planilla",
        "procesar_planilla",
        "consultar_reportes_planilla",
    },
    # Vendedor: Operaciones de venta propia
    "vendedor": {
        "consultar_productos",
        "crear_ventas",
        "consultar_ventas_propias",
        "solicitar_anulacion",
    },
    # Bodega: Control de existencias físicas
    "bodega": {
        "consultar_productos",
        "consultar_inventario",
        "registrar_entradas",
        "ajustar_existencias",
        "consultar_reportes_inventario",
    },
    # Contabilidad: Consulta financiera
    "contabilidad": {
        "consultar_planilla",
        "consultar_reportes_planilla",
        "consultar_ventas_propias",
        "consultar_todas_ventas",
        "consultar_reportes_ventas",
        "consultar_reportes_financieros",
    },
    # Compras: Catálogo y recepción de mercancías
    "compras": {
        "consultar_productos",
        "gestionar_productos",
        "gestionar_categorias",
        "consultar_inventario",
        "registrar_entradas",
        "consultar_reportes_inventario",
    },
    # Supervisor: Consulta integral y resolución de solicitudes
    "supervisor": {
        "consultar_empleados",
        "consultar_planilla",
        "consultar_reportes_planilla",
        "consultar_productos",
        "consultar_inventario",
        "consultar_reportes_inventario",
        "consultar_ventas_propias",
        "consultar_todas_ventas",
        "resolver_solicitudes",
        "consultar_reportes_ventas",
        "consultar_reportes_financieros",
    },
    # Auditor: Consulta transversal sin privilegios de modificación
    "auditor": {
        "consultar_empleados",
        "consultar_planilla",
        "consultar_reportes_planilla",
        "consultar_productos",
        "consultar_inventario",
        "consultar_reportes_inventario",
        "consultar_ventas_propias",
        "consultar_todas_ventas",
        "consultar_reportes_ventas",
        "consultar_reportes_financieros",
        "consultar_reportes_auditoria",
    },
}


def tiene_permiso(rol: str, permiso: str) -> bool:
    """
    Verifica si un rol tiene otorgado un permiso específico.
    El rol 'admin' dispone del comodín '*' que otorga acceso total.
    """
    if not rol:
        return False
    if rol == "admin":
        return True
    permisos_rol = PERMISOS_POR_ROL.get(rol, set())
    if "*" in permisos_rol:
        return True
    return permiso in permisos_rol


def obtener_permisos_rol(rol: str) -> Set[str]:
    """Retorna el conjunto de permisos correspondiente a un rol."""
    if not rol:
        return set()
    if rol == "admin":
        return set(PERMISOS)
    return set(PERMISOS_POR_ROL.get(rol, set()))
