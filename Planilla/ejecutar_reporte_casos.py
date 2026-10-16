"""
ejecutar_reporte_casos.py
=========================
Script de inicialización y ejecución de casos de prueba para el módulo de planilla:
- Rosita (Salario Base 10,000 NIO, Pago Parcial 5,000 NIO el 01/02/2026)
- Franco (Salario Base 12,000 NIO, Pago Parcial 6,000 NIO el 01/06/2026)
- Marlene (Salario Base 15,000 NIO, Pago Parcial 7,500 NIO el 01/11/2025)

Ejecuta CalcularAguinaldo para cada colaborador y genera el informe requerido
con todas las columnas solicitadas y desglose legal según Ley 185 de Nicaragua.
"""

import sys
from decimal import Decimal
from datetime import date
from pathlib import Path

# Configurar stdout para evitar errores en Windows cp1252
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Asegurar importación del módulo local
sys.path.insert(0, str(Path(__file__).resolve().parent))

from payroll_module import GestorPlanillaDiferida, CalcularAguinaldo, a_decimal


def configurar_casos_de_prueba(gestor: GestorPlanillaDiferida):
    """Inserta o actualiza los empleados, contratos, períodos y pagos de prueba."""
    conn = gestor.get_connection()
    try:
        gestor.asegurar_esquema(conn)

        # Definición de los casos de prueba solicitados
        casos = [
            {
                "cedula": "001-010290-0001R",
                "primer_nombre": "Rosita",
                "primer_apellido": "García",
                "nombre": "Rosita García",
                "salario_base": Decimal("10000.00"),
                "fecha_ingreso": "2026-02-01",
                "anio_periodo": 2026,
                "mes_periodo": 2,
                "anio_fiscal_aguinaldo": 2026,
                "pago_monto": Decimal("5000.00"),
                "pago_fecha": "2026-02-01",
                "concepto": "Primer abono parcial (Quincena 1)",
                "referencia": "TRANSF-ROS-001",
            },
            {
                "cedula": "001-150692-0002F",
                "primer_nombre": "Franco",
                "primer_apellido": "Martínez",
                "nombre": "Franco Martínez",
                "salario_base": Decimal("12000.00"),
                "fecha_ingreso": "2026-06-01",
                "anio_periodo": 2026,
                "mes_periodo": 6,
                "anio_fiscal_aguinaldo": 2026,
                "pago_monto": Decimal("6000.00"),
                "pago_fecha": "2026-06-01",
                "concepto": "Primer abono parcial (Quincena 1)",
                "referencia": "TRANSF-FRA-001",
            },
            {
                "cedula": "001-201188-0003M",
                "primer_nombre": "Marlene",
                "primer_apellido": "López",
                "nombre": "Marlene López",
                "salario_base": Decimal("15000.00"),
                "fecha_ingreso": "2025-11-01",
                "anio_periodo": 2025,
                "mes_periodo": 11,
                "anio_fiscal_aguinaldo": 2025,
                "pago_monto": Decimal("7500.00"),
                "pago_fecha": "2025-11-01",
                "concepto": "Primer abono parcial (Quincena 1)",
                "referencia": "TRANSF-MAR-001",
            },
        ]

        empleados_procesados = []

        for caso in casos:
            # 1. Crear o actualizar empleado
            row_emp = conn.execute("SELECT id FROM empleados WHERE cedula = ?", (caso["cedula"],)).fetchone()
            if row_emp:
                emp_id = row_emp["id"]
                conn.execute("""
                UPDATE empleados
                SET nombre = ?, primer_nombre = ?, primer_apellido = ?, cargo = 'Administrador', cargo_id = 1, fecha_ingreso = ?, salario_base = ?, activo = 1
                WHERE id = ?
                """, (caso["nombre"], caso["primer_nombre"], caso["primer_apellido"], caso["fecha_ingreso"], float(caso["salario_base"]), emp_id))
            else:
                cursor = conn.execute("""
                INSERT INTO empleados (cedula, nombre, primer_nombre, primer_apellido, cargo, cargo_id, fecha_ingreso, salario_base, activo)
                VALUES (?, ?, ?, ?, 'Administrador', 1, ?, ?, 1)
                """, (caso["cedula"], caso["nombre"], caso["primer_nombre"], caso["primer_apellido"], caso["fecha_ingreso"], float(caso["salario_base"])))
                emp_id = cursor.lastrowid

            conn.commit()

            # 2. Registrar Contrato Laboral
            contrato = gestor.registrar_o_actualizar_contrato(
                empleado_id=emp_id,
                salario_base=caso["salario_base"],
                tipo_contrato="Indeterminado",
                fecha_inicio=caso["fecha_ingreso"],
                observaciones=f"Contrato formalizado de {caso['nombre']} por C$ {caso['salario_base']:,.2f}/mes",
                conn=conn
            )

            # 3. Obtener o crear PeriodoPlanilla
            periodo = gestor.obtener_o_crear_periodo(
                empleado_id=emp_id,
                anio=caso["anio_periodo"],
                mes=caso["mes_periodo"],
                salario_base_manual=caso["salario_base"],
                conn=conn
            )

            # 4. Registrar Transacción de Pago Parcial (si no existe ya para evitar duplicados)
            tx_existente = conn.execute(
                "SELECT id FROM transacciones_pago_planilla WHERE periodo_planilla_id = ? AND referencia = ?",
                (periodo.id, caso["referencia"])
            ).fetchone()

            if not tx_existente:
                # Limpiar cualquier pago previo en este periodo para este test
                conn.execute("DELETE FROM transacciones_pago_planilla WHERE periodo_planilla_id = ?", (periodo.id,))
                conn.execute(
                    "UPDATE periodos_planilla SET total_pagado = 0, saldo_pendiente = salario_neto_total, estado = 'pendiente' WHERE id = ?",
                    (periodo.id,)
                )
                conn.commit()

                tx = gestor.registrar_pago_diferido(
                    empleado_id=emp_id,
                    periodo_planilla_id=periodo.id,
                    monto=caso["pago_monto"],
                    fecha_pago=caso["pago_fecha"],
                    concepto=caso["concepto"],
                    metodo_pago="Transferencia",
                    referencia=caso["referencia"],
                    notas="Primer abono registrado en prueba inicial",
                    usuario_id=1,
                    registrado_por="Admin Nómina",
                    conn=conn
                )

            empleados_procesados.append({
                "empleado_id": emp_id,
                "nombre": caso["nombre"],
                "anio_fiscal": caso["anio_fiscal_aguinaldo"]
            })

        conn.commit()
        return empleados_procesados
    finally:
        conn.close()


def imprimir_informe_de_prueba():
    """Ejecuta la función CalcularAguinaldo para los 3 empleados y genera el informe consolidado."""
    gestor = GestorPlanillaDiferida()
    datos_empleados = configurar_casos_de_prueba(gestor)

    print("\n" + "=" * 105)
    print(" S I S T E M A   D E   N Ó M I N A   ( N I C A R A G U A ) - L E Y   1 8 5 ")
    print(" INFORME DE PRUEBA: REGISTRO DE PAGOS PARCIALES Y CÁLCULO DE AGUINALDO (DÉCIMO TERCER MES)")
    print("=" * 105)

    resultados = []
    for item in datos_empleados:
        resultado = gestor.CalcularAguinaldo(idEmpleado=item["empleado_id"], añoActual=item["anio_fiscal"])
        resultados.append(resultado)

    # Imprimir Tabla Resumen Principal
    encabezados = [
        "Nombre Empleado",
        "Salario Base",
        "Año Fiscal",
        "Días Trab.",
        "Total Acumulado",
        "Aguinaldo Solicitado",
        "Aguinaldo Ley 185 (1/12)",
    ]

    print(f"\n{encabezados[0]:<18} | {encabezados[1]:<14} | {encabezados[2]:<10} | {encabezados[3]:<10} | {encabezados[4]:<16} | {encabezados[5]:<20} | {encabezados[6]:<18}")
    print("-" * 118)

    for r in resultados:
        sal_base_fmt = f"C$ {r.salario_base_mensual:,.2f}"
        total_acum_fmt = f"C$ {r.total_salario_acumulado:,.2f}"
        ag_solic_fmt = f"C$ {r.aguinaldo_formula_solicitada:,.2f}"
        ag_ley_fmt = f"C$ {r.aguinaldo_ley_185_acumulado:,.2f}"
        dias_fmt = f"{r.dias_trabajados}/{r.dias_totales_anio}"

        print(
            f"{r.nombre_empleado:<18} | {sal_base_fmt:<14} | {r.anio_fiscal:<10} | {dias_fmt:<10} | "
            f"{total_acum_fmt:<16} | {ag_solic_fmt:<20} | {ag_ley_fmt:<18}"
        )

    print("-" * 118)

    # Imprimir Detalle Individual por Empleado
    print("\n" + "=" * 105)
    print(" DETALLE INDIVIDUAL DE CASOS DE PRUEBA Y AUDITORÍA DE PAGOS")
    print("=" * 105)

    for i, r in enumerate(resultados, 1):
        print(f"\n[CASO #{i}] EMPLEADO: {r.nombre_empleado.upper()}")
        print("-" * 65)
        print(f" * Salario Base Pactado:            C$ {r.salario_base_mensual:,.2f} / mes")
        print(f" * Año Fiscal de Cálculo:           {r.anio_fiscal}")
        print(f" * Período Legal de Cómputo:        {r.fecha_inicio_periodo} al {r.fecha_fin_periodo}")
        print(f" * Días Totales del Ciclo:          {r.dias_totales_anio} días")
        print(f" * Días Trabajados por el Empleado: {r.dias_trabajados} días ({'Año Completo' if r.es_anio_completo else 'Período Proporcional'})")
        print(f" * Total Salario Acumulado:         C$ {r.total_salario_acumulado:,.2f} (según pagos registrados)")
        print(f" * Aguinaldo a Pagar (Fórmula req): C$ {r.aguinaldo_formula_solicitada:,.2f}")
        print(f"   |-- Fórmula aplicada:            (TotalDevengado / 365) * DíasTrabajados")
        print(f"                                    (C$ {r.total_salario_acumulado:,.2f} / {r.dias_totales_anio}) * {r.dias_trabajados}")
        print(f" * Aguinaldo Ley 185 (Acum/12):     C$ {r.aguinaldo_ley_185_acumulado:,.2f}")
        print(f" * Aguinaldo Ley 185 (Base/365*D):  C$ {r.aguinaldo_ley_185_dias:,.2f}")
        print(f" * Fecha Exigible de Pago:          {r.fecha_exigible_pago} (Código del Trabajo Art. 96)")
        print(f" * Estado Actual de los Pagos:      {r.estado_pagos}")
        
        print(" * Historial de Transacciones Registradas en el Período:")
        if r.transacciones_incluidas:
            for tx in r.transacciones_incluidas:
                print(
                    f"   - Fecha: {tx['fecha_pago']} | Monto: C$ {tx['monto']:,.2f} | "
                    f"Ref: {tx['referencia']} | Registrado por: {tx['registrado_por']} | "
                    f"Concepto: {tx['concepto']}"
                )
        else:
            print("   - No hay transacciones registradas.")

    print("\n" + "=" * 105)
    print(" PRUEBAS DE VALIDACIÓN DE REGLAS DE NEGOCIO:")
    print("=" * 105)

    # 1. Probar validación de exceso de pago sobre el saldo pendiente
    print("\n[VALIDACIÓN 1] Intento de sobrepago (Monto superior al saldo pendiente):")
    conn = gestor.get_connection()
    try:
        emp_rosita = conn.execute("SELECT id FROM empleados WHERE nombre LIKE '%Rosita%'").fetchone()
        periodo_rosita = conn.execute("SELECT * FROM periodos_planilla WHERE empleado_id = ?", (emp_rosita["id"],)).fetchone()
        saldo_actual = a_decimal(periodo_rosita["saldo_pendiente"])
        print(f" -> Saldo pendiente de Rosita en período {periodo_rosita['descripcion']}: C$ {saldo_actual:,.2f}")
        monto_invalido = saldo_actual + Decimal("1000.00")
        print(f" -> Intentando registrar pago de C$ {monto_invalido:,.2f} (excede el saldo por C$ 1,000.00)...")
        
        try:
            gestor.registrar_pago_diferido(
                empleado_id=emp_rosita["id"],
                periodo_planilla_id=periodo_rosita["id"],
                monto=monto_invalido,
                fecha_pago="2026-02-15",
                concepto="Intento de sobrepago",
                conn=conn
            )
            print(" ❌ ERROR: El sistema permitió el sobrepago (Falló la validación).")
        except ValueError as ex:
            print(f" ✔ CORRECTO: El sistema bloqueó el sobrepago exitosamente.")
            print(f"   Mensaje capturado: {ex}")

        # 2. Probar pago complementario exitoso (segundo abono para completar el mes)
        print("\n[VALIDACIÓN 2] Registro de segundo abono para completar el mes (N pagos por período):")
        monto_segundo_abono = saldo_actual
        print(f" -> Registrando abono complementario exacto de C$ {monto_segundo_abono:,.2f}...")
        tx2 = gestor.registrar_pago_diferido(
            empleado_id=emp_rosita["id"],
            periodo_planilla_id=periodo_rosita["id"],
            monto=monto_segundo_abono,
            fecha_pago="2026-02-15",
            concepto="Segundo abono (Quincena 2 - Finiquito de mes)",
            metodo_pago="Transferencia",
            referencia="TRANSF-ROS-002",
            usuario_id=1,
            registrado_por="Admin Nómina",
            conn=conn
        )
        periodo_actualizado = conn.execute("SELECT * FROM periodos_planilla WHERE id = ?", (periodo_rosita["id"],)).fetchone()
        print(f" ✔ Abono registrado exitosamente. ID Transacción: {tx2.id}")
        print(f" -> Nuevo Total Pagado: C$ {periodo_actualizado['total_pagado']:,.2f}")
        print(f" -> Nuevo Saldo Pendiente: C$ {periodo_actualizado['saldo_pendiente']:,.2f}")
        print(f" -> Nuevo Estado del Período: '{periodo_actualizado['estado']}' (esperado: 'pagado_completo')")

        # Recalcular aguinaldo con el mes completado
        res_rosita_completo = gestor.CalcularAguinaldo(idEmpleado=emp_rosita["id"], añoActual=2026, conn=conn)
        print(f" -> Recálculo de Aguinaldo de Rosita con mes de febrero saldado al 100%:")
        print(f"    • Total Acumulado: C$ {res_rosita_completo.total_salario_acumulado:,.2f}")
        print(f"    • Aguinaldo Solicitado: C$ {res_rosita_completo.aguinaldo_formula_solicitada:,.2f}")
        print(f"    • Aguinaldo Ley 185 (Acum/12): C$ {res_rosita_completo.aguinaldo_ley_185_acumulado:,.2f}")
        print(f"    • Estado de Pagos: {res_rosita_completo.estado_pagos}")

        # Restaurar al estado inicial de 1 solo abono parcial para que coincida exactamente con el caso de prueba base
        conn.execute("DELETE FROM transacciones_pago_planilla WHERE id = ?", (tx2.id,))
        conn.execute(
            "UPDATE periodos_planilla SET total_pagado = 5000.0, saldo_pendiente = (salario_neto_total - 5000.0), estado = 'pago_parcial' WHERE id = ?",
            (periodo_rosita["id"],)
        )
        conn.commit()
        print("\n -> Estado de prueba restablecido al abono parcial inicial para consistencia.")

    finally:
        conn.close()

    print("\n" + "=" * 105)
    print(" INFORME GENERADO SATISFACTORIAMENTE.")
    print("=" * 105 + "\n")


if __name__ == "__main__":
    imprimir_informe_de_prueba()
