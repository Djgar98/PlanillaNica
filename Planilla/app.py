import math
import os
import re
import secrets
import sqlite3
from datetime import date
from functools import wraps
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database import calcular_planilla_completa, get_db, init_db, obtener_empleados_con_ultimo_pago, obtener_historial_empleado, obtener_planillas_por_mes, registrar_movimiento

CEDULA_RE = re.compile(r"^\d{3}-\d{6}-\d{4}[A-Za-z]$")
INSS_RE = re.compile(r"^\d{7}-\d$")


def cargar_env_local():
    """Carga variables simples desde .env sin reemplazar las del sistema."""
    archivo_env = Path(__file__).resolve().parent / ".env"
    if not archivo_env.is_file():
        return
    for linea in archivo_env.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip("'\""))


cargar_env_local()
app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("PLANILLA_SECRET_KEY"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("PLANILLA_COOKIE_SECURE", "false").lower() == "true",
)
if not app.config["SECRET_KEY"]:
    raise RuntimeError("Define PLANILLA_SECRET_KEY antes de iniciar la aplicación.")


@app.template_filter("moneda")
def formato_moneda(valor):
    if valor is None or valor == "":
        return "C$ 0.00"
    return f"C$ {float(valor):,.2f}"


@app.context_processor
def inyectar_token_csrf():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return {"csrf_token": token}


@app.before_request
def validar_csrf():
    with get_db() as conn:
        categorias = conn.execute("SELECT * FROM categorias WHERE activo = 1 ORDER BY nombre").fetchall()
    if request.method == "POST":
        token, token_sesion = request.form.get("csrf_token", ""), session.get("csrf_token", "")
        if not token_sesion or not secrets.compare_digest(token, token_sesion):
            abort(400, "El formulario expiró o es inválido. Vuelve a intentarlo.")


def requiere_login(vista):
    @wraps(vista)
    def vista_protegida(*args, **kwargs):
        if "usuario" not in session:
            return redirect(url_for("login"))
        return vista(*args, **kwargs)
    return vista_protegida


def requiere_rol(*roles):
    def decorador(vista):
        @wraps(vista)
        def vista_protegida(*args, **kwargs):
            if "usuario" not in session:
                return redirect(url_for("login"))
            if session.get("rol") not in roles:
                abort(403, "No tienes permiso para realizar esta operación.")
            return vista(*args, **kwargs)
        return vista_protegida
    return decorador


def numero_positivo(valor, campo, permite_cero=True):
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        raise ValueError(f"{campo} debe ser un número válido.")
    if not math.isfinite(numero) or numero < 0 or (numero == 0 and not permite_cero):
        minimo = "mayor que cero" if not permite_cero else "igual o mayor que cero"
        raise ValueError(f"{campo} debe ser {minimo}.")
    return round(numero, 2)


def datos_empleado_formulario(formulario, empleado_id=None):
    datos = {
        "cedula": formulario.get("cedula", "").strip().upper(),
        "primer_nombre": formulario.get("primer_nombre", "").strip(),
        "segundo_nombre": formulario.get("segundo_nombre", "").strip(),
        "primer_apellido": formulario.get("primer_apellido", "").strip(),
        "segundo_apellido": formulario.get("segundo_apellido", "").strip(),
        "cargo_id": formulario.get("cargo_id", "").strip(),
        "numero_inss": formulario.get("numero_inss", "").strip(),
        "departamento": formulario.get("departamento", "").strip(),
        "fecha_ingreso": formulario.get("fecha_ingreso", "").strip()
    }
    # Compute full name for backwards compatibility
    partes_nombre = [datos["primer_nombre"], datos["segundo_nombre"], datos["primer_apellido"], datos["segundo_apellido"]]
    datos["nombre"] = " ".join(p for p in partes_nombre if p).strip()
    
    # Validate required fields
    if not CEDULA_RE.fullmatch(datos["cedula"]):
        raise ValueError("La cédula debe tener el formato 000-000000-0000X.")
    if not datos["primer_nombre"] or not datos["primer_apellido"] or not datos["cargo_id"]:
        raise ValueError("Los nombres y el cargo son obligatorios.")
    if not datos["primer_nombre"] or not datos["primer_apellido"] or not formulario.get("cargo_id") or not formulario.get("departamento_id"):
        raise ValueError("Cédula, Primer Nombre, Primer Apellido, Cargo y Departamento son obligatorios.")
        
    datos["nombre"] = " ".join(filter(None, [datos["primer_nombre"], datos["segundo_nombre"], datos["primer_apellido"], datos["segundo_apellido"]]))
    datos["cargo_id"] = int(formulario.get("cargo_id"))
    datos["cargo"] = "" # Backwards compatibility
    datos["departamento_id"] = int(formulario.get("departamento_id"))
    datos["departamento"] = "" # Backwards compatibility o para migración
    
    if datos["numero_inss"] and not INSS_RE.fullmatch(datos["numero_inss"]):
        raise ValueError("El número INSS debe tener el formato 1234567-8.")
    if datos["fecha_ingreso"]:
        try:
            date.fromisoformat(datos["fecha_ingreso"])
        except ValueError:
            raise ValueError("La fecha de ingreso no es válida.")
            
    datos["salario_base"] = numero_positivo(formulario.get("salario_base"), "El salario base", False)
    if empleado_id is not None:
        datos["id"] = empleado_id
    return datos


init_db()
with get_db() as conn:
    admin_usuario = os.environ.get("PLANILLA_ADMIN_USER")
    admin_hash = os.environ.get("PLANILLA_ADMIN_PASSWORD_HASH")
    existe = conn.execute("SELECT 1 FROM usuarios WHERE usuario = ?", (admin_usuario,)).fetchone() if admin_usuario else None
    if admin_usuario and admin_hash and not existe:
        conn.execute("INSERT INTO usuarios (usuario, nombre, password_hash, rol) VALUES (?, ?, ?, 'admin')", (admin_usuario, "Administrador", admin_hash))


@app.route("/login", methods=["GET", "POST"])
def login():
    if "usuario" in session:
        return redirigir_segun_rol(session.get("rol"))
        
    with get_db() as conn:
        categorias = conn.execute("SELECT * FROM categorias WHERE activo = 1 ORDER BY nombre").fetchall()
        
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        with get_db() as conn:
            cuenta = conn.execute("SELECT * FROM usuarios WHERE usuario = ? AND activo = 1", (usuario,)).fetchone()
            
        if cuenta and check_password_hash(cuenta["password_hash"], request.form.get("password", "")):
            session.clear()
            session.update(
                usuario=cuenta["usuario"], 
                usuario_id=cuenta["id"], 
                rol=cuenta["rol"], 
                csrf_token=secrets.token_urlsafe(32)
            )
            # Redirección dinámica según el rol del usuario que entra
            return redirigir_segun_rol(cuenta["rol"])
        else:
            flash("Credenciales incorrectas.", "danger")
            
    return render_template("login.html")

# Función que redirige al usuario directo a su módulo correspondiente
def redirigir_segun_rol(rol):
    if rol == "vendedor":
        return redirect(url_for("ventas"))
    elif rol == "bodega":
        return redirect(url_for("inventario"))
    elif rol in ("admin", "rrhh"):
        return redirect(url_for("index"))
    return redirect(url_for("ventas"))


@app.route("/logout", methods=["POST"])
@requiere_login
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@requiere_rol("admin", "rrhh")
def index():
    fecha_desde, fecha_hasta = request.args.get("fecha_desde", ""), request.args.get("fecha_hasta", "")
    try:
        if fecha_desde: date.fromisoformat(fecha_desde)
        if fecha_hasta: date.fromisoformat(fecha_hasta)
        if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta: raise ValueError
    except ValueError:
        flash("El rango de fechas no es válido.", "warning")
        fecha_desde = fecha_hasta = ""
    return render_template("index.html", empleados=obtener_empleados_con_ultimo_pago(fecha_desde or None, fecha_hasta or None), fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, mes_actual=date.today().strftime("%Y-%m"))


@app.route("/reportes/planilla-mensual")
@requiere_rol("admin", "rrhh")
def reporte_planilla_mensual():
    mes = request.args.get("mes", date.today().strftime("%Y-%m"))
    try:
        fecha_mes = date.fromisoformat(f"{mes}-01")
        if fecha_mes.strftime("%Y-%m") != mes:
            raise ValueError
    except ValueError:
        abort(400, "El mes debe tener el formato YYYY-MM.")
    planillas = obtener_planillas_por_mes(mes)
    totales = {
        "salario_bruto": sum(p["salario_bruto"] for p in planillas),
        "inss_laboral": sum(p["inss_laboral"] for p in planillas),
        "ir_laboral": sum(p["ir_laboral"] for p in planillas),
        "inss_patronal": sum(p["inss_patronal"] for p in planillas),
        "salario_neto": sum(p["salario_neto"] for p in planillas),
    }
    return render_template("reporte_planilla_mensual.html", mes=mes, planillas=planillas, totales=totales)


@app.route("/empleado/nuevo", methods=["GET", "POST"])
@requiere_rol("admin", "rrhh")
def nuevo_empleado():
    with get_db() as conn:
        cargos = conn.execute("SELECT * FROM cargos WHERE activo = 1 ORDER BY nombre").fetchall()
        departamentos = conn.execute("SELECT * FROM departamentos WHERE activo = 1 ORDER BY nombre").fetchall()
        
    if request.method == "POST":
        try:
            empleado = datos_empleado_formulario(request.form)
            with get_db() as conn:
                conn.execute("""INSERT INTO empleados (cedula, nombre, primer_nombre, segundo_nombre, primer_apellido, segundo_apellido, cargo_id, cargo, numero_inss, departamento, departamento_id, fecha_ingreso, salario_base)
                             VALUES (:cedula, :nombre, :primer_nombre, :segundo_nombre, :primer_apellido, :segundo_apellido, :cargo_id, :cargo, :numero_inss, :departamento, :departamento_id, :fecha_ingreso, :salario_base)""", empleado)
            flash("Empleado registrado exitosamente.", "success")
            return redirect(url_for("index"))
        except ValueError as error:
            flash(str(error), "danger")
        except sqlite3.IntegrityError as error:
            if "cedula" in str(error):
                flash("La cédula ya está registrada.", "danger")
            else:
                flash(f"Error de base de datos: {error}", "danger")
    return render_template("form_empleado.html", empleado=dict(request.form) if request.method == "POST" else None, cargos=cargos, departamentos=departamentos)


@app.route("/empleado/editar/<int:id>", methods=["GET", "POST"])
@requiere_rol("admin", "rrhh")
def editar_empleado(id):
    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        empleado_actual = conn.execute("SELECT * FROM empleados WHERE id = ?", (id,)).fetchone()
        cargos = conn.execute("SELECT * FROM cargos WHERE activo = 1 ORDER BY nombre").fetchall()
        departamentos = conn.execute("SELECT * FROM departamentos WHERE activo = 1 ORDER BY nombre").fetchall()
        
    if empleado_actual is None: abort(404)
    
    # We must format empleado_actual into a standard dict to prevent issues
    empleado_dict = dict(empleado_actual)
    if request.method == "POST":
        try:
            empleado = datos_empleado_formulario(request.form)
            empleado["id"] = id
            with get_db() as conn:
                conn.execute("""UPDATE empleados SET cedula=:cedula, nombre=:nombre, primer_nombre=:primer_nombre, segundo_nombre=:segundo_nombre, primer_apellido=:primer_apellido, segundo_apellido=:segundo_apellido, cargo_id=:cargo_id, cargo=:cargo, numero_inss=:numero_inss,
                             departamento=:departamento, departamento_id=:departamento_id, fecha_ingreso=:fecha_ingreso, salario_base=:salario_base WHERE id=:id""", empleado)
            flash("Datos del empleado actualizados.", "success")
            return redirect(url_for("index"))
        except ValueError as error:
            flash(str(error), "danger")
        except sqlite3.IntegrityError as error:
            if "cedula" in str(error):
                flash("La cédula ya existe en otro registro.", "danger")
            else:
                flash(f"Error de base de datos: {error}", "danger")
            # If error, prefill with user input
            empleado_dict.update(request.form)
            
    return render_template("form_empleado.html", empleado=empleado_dict, cargos=cargos, departamentos=departamentos)


@app.route("/empleado/estado/<int:id>/<int:nuevo_estado>", methods=["POST"])
@requiere_rol("admin", "rrhh")
def cambiar_estado_empleado(id, nuevo_estado):
    if nuevo_estado not in (0, 1): abort(400, "Estado de empleado inválido.")
    with get_db() as conn:
        resultado = conn.execute("UPDATE empleados SET activo = ? WHERE id = ?", (nuevo_estado, id))
    if resultado.rowcount == 0: abort(404)
    flash("Estado del empleado actualizado.", "info")
    return redirect(url_for("index"))


@app.route("/empleado/historial/<int:empleado_id>")
@requiere_rol("admin", "rrhh")
def historial_empleado(empleado_id):
    with get_db() as conn:
        empleado = conn.execute("SELECT * FROM empleados WHERE id = ?", (empleado_id,)).fetchone()
    if empleado is None: abort(404)
    return render_template("historial_empleado.html", empleado=empleado, planillas=obtener_historial_empleado(empleado_id))


@app.route("/empleado/<int:empleado_id>/reporte")
@requiere_rol("admin", "rrhh")
def reporte_historial_empleado(empleado_id):
    """Genera un reporte imprimible del historial y acumulados del colaborador."""
    with get_db() as conn:
        empleado = conn.execute("SELECT * FROM empleados WHERE id = ?", (empleado_id,)).fetchone()
    if empleado is None:
        abort(404)
    planillas = obtener_historial_empleado(empleado_id)
    totales = {
        "salario_base": sum(p["salario_base"] for p in planillas),
        "pago_horas_extras": sum(p["pago_horas_extras"] for p in planillas),
        "salario_bruto": sum(p["salario_bruto"] for p in planillas),
        "inss_laboral": sum(p["inss_laboral"] for p in planillas),
        "ir_laboral": sum(p["ir_laboral"] for p in planillas),
        "inss_patronal": sum(p["inss_patronal"] for p in planillas),
        "salario_neto": sum(p["salario_neto"] for p in planillas),
    }
    return render_template("reporte_historial.html", empleado=empleado, planillas=planillas, totales=totales)


@app.route("/planilla/<int:planilla_id>/recibo")
@requiere_rol("admin", "rrhh")
def recibo_planilla(planilla_id):
    """Muestra un comprobante imprimible de un pago ya registrado."""
    with get_db() as conn:
        planilla = conn.execute("""SELECT p.*, e.nombre, e.cedula, e.cargo, e.numero_inss, e.departamento
            FROM planilla p JOIN empleados e ON e.id = p.empleado_id WHERE p.id = ?""", (planilla_id,)).fetchone()
    if planilla is None:
        abort(404)
    return render_template("recibo_planilla.html", planilla=planilla)


@app.route("/agregar-planilla/<int:empleado_id>", methods=["GET", "POST"])
@requiere_rol("admin", "rrhh")
def agregar_planilla(empleado_id):
    with get_db() as conn:
        empleado = conn.execute("SELECT * FROM empleados WHERE id = ?", (empleado_id,)).fetchone()
    if empleado is None: abort(404)
    if not empleado["activo"]:
        flash("No se puede procesar una planilla para un empleado inactivo.", "warning")
        return redirect(url_for("index"))
    if request.method == "POST":
        try:
            salario_base = numero_positivo(request.form.get("salario_base"), "El salario base", False)
            horas_extras = numero_positivo(request.form.get("horas_extras", 0), "Las horas extras")
        except ValueError as error:
            flash(str(error), "danger")
            return render_template("form_planilla.html", empleado=empleado, valores=dict(request.form))
        res = calcular_planilla_completa(salario_base, horas_extras)
        with get_db() as conn:
            conn.execute("""INSERT INTO planilla (empleado_id, salario_base, horas_extras, pago_horas_extras, salario_bruto,
                         inss_laboral, inss_laboral_tasa, ir_laboral, inss_patronal, inss_patronal_tasa, salario_neto)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                         (empleado_id, res["salario_base"], res["horas_extras"], res["pago_horas_extras"], res["salario_bruto"],
                          res["inss_laboral"], res["inss_laboral_tasa"], res["ir_laboral"], res["inss_patronal"],
                          res["inss_patronal_tasa"], res["salario_neto"]))
        flash("Pago de planilla registrado exitosamente.", "success")
        return redirect(url_for("index"))
    return render_template("form_planilla.html", empleado=empleado, valores=None)


@app.route("/inventario")
@requiere_rol("admin", "bodega")
def inventario():
    incluir_inactivos = request.args.get("todos") == "1"
    with get_db() as conn:
        productos = conn.execute("SELECT p.*, c.nombre as categoria_nombre FROM productos p LEFT JOIN categorias c ON c.id=p.categoria_id " + ("" if incluir_inactivos else "WHERE p.activo = 1 ") + "ORDER BY p.activo DESC, p.nombre").fetchall()
        movimientos = conn.execute("""SELECT m.*, p.nombre AS producto, u.usuario FROM movimientos_inventario m
            JOIN productos p ON p.id=m.producto_id LEFT JOIN usuarios u ON u.id=m.usuario_id ORDER BY m.id DESC LIMIT 12""").fetchall()
    return render_template("inventario.html", productos=productos, movimientos=movimientos, incluir_inactivos=incluir_inactivos)


def datos_producto(formulario):
    datos = {k: formulario.get(k, "").strip() for k in ("codigo", "nombre", "descripcion")}
    datos["categoria_id"] = formulario.get("categoria_id") or 1
    datos["marca_id"] = formulario.get("marca_id") or 1
    datos["tipo_id"] = formulario.get("tipo_id") or 1
    if not datos["codigo"] or not datos["nombre"]:
        raise ValueError("Código y nombre son obligatorios.")
    datos["precio_compra"] = numero_positivo(formulario.get("precio_compra", 0), "El precio de compra")
    datos["precio_venta"] = numero_positivo(formulario.get("precio_venta"), "El precio de venta")
    datos["stock_minimo"] = int(numero_positivo(formulario.get("stock_minimo", 0), "El stock mínimo"))
    return datos


@app.route("/inventario/nuevo", methods=["GET", "POST"])
@requiere_rol("admin", "bodega")
def nuevo_producto():
    with get_db() as conn:
        categorias = conn.execute("SELECT * FROM categorias WHERE activo = 1 ORDER BY nombre").fetchall()
        marcas = conn.execute("SELECT * FROM marcas ORDER BY nombre").fetchall()
        tipos = conn.execute("SELECT * FROM tipos ORDER BY nombre").fetchall()
    if request.method == "POST":
        try:
            datos = datos_producto(request.form)
            inicial = int(numero_positivo(request.form.get("existencia", 0), "La existencia inicial"))
            with get_db() as conn:
                cursor = conn.execute("""INSERT INTO productos (codigo,nombre,descripcion,categoria_id,marca_id,tipo_id,precio_compra,precio_venta,existencia,stock_minimo)
                    VALUES (:codigo,:nombre,:descripcion,:categoria_id,:marca_id,:tipo_id,:precio_compra,:precio_venta,0,:stock_minimo)""", datos)
                if inicial:
                    registrar_movimiento(conn, cursor.lastrowid, "entrada", inicial, session["usuario_id"], "Alta de producto", "Existencia inicial")
            flash("Producto registrado correctamente.", "success")
            return redirect(url_for("inventario"))
        except (ValueError, sqlite3.IntegrityError) as error:
            flash("El código ya existe." if isinstance(error, sqlite3.IntegrityError) else str(error), "danger")
    return render_template("form_producto.html", producto=dict(request.form) if request.method == "POST" else None, categorias=categorias, marcas=marcas, tipos=tipos)


@app.route("/inventario/<int:producto_id>/editar", methods=["GET", "POST"])
@requiere_rol("admin", "bodega")
def editar_producto(producto_id):
    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        producto_row = conn.execute("SELECT * FROM productos WHERE id=?", (producto_id,)).fetchone()
        categorias = conn.execute("SELECT * FROM categorias WHERE activo = 1 ORDER BY nombre").fetchall()
        marcas = conn.execute("SELECT * FROM marcas ORDER BY nombre").fetchall()
        tipos = conn.execute("SELECT * FROM tipos ORDER BY nombre").fetchall()
    
    if producto_row is None: 
        abort(404)
        
    # CONVERSIÓN CRUCIAL: Convertimos la fila sqlite3.Row a un diccionario estándar para que funcione .get() en el HTML
    producto = dict(producto_row)

    if request.method == "POST":
        try:
            datos = datos_producto(request.form)
            datos["id"] = producto_id
            with get_db() as conn:
                conn.execute("""UPDATE productos SET codigo=:codigo, nombre=:nombre, descripcion=:descripcion, categoria_id=:categoria_id, marca_id=:marca_id, tipo_id=:tipo_id,
                    precio_compra=:precio_compra, precio_venta=:precio_venta, stock_minimo=:stock_minimo WHERE id=:id""", datos)
            flash("Producto actualizado.", "success")
            return redirect(url_for("inventario"))
        except (ValueError, sqlite3.IntegrityError) as error:
            flash("El código ya existe." if isinstance(error, sqlite3.IntegrityError) else str(error), "danger")
            # Si hay un error al validar, actualizamos el diccionario con lo que el usuario escribió
            producto.update(request.form)
            
    return render_template("form_producto.html", producto=producto, categorias=categorias, marcas=marcas, tipos=tipos)


@app.route("/inventario/<int:producto_id>/movimiento", methods=["POST"])
@requiere_rol("admin", "bodega")
def movimiento_producto(producto_id):
    try:
        cantidad = int(numero_positivo(request.form.get("cantidad"), "La cantidad", False))
        tipo = request.form.get("tipo")
        if tipo not in ("entrada", "ajuste"): raise ValueError("Tipo de movimiento inválido.")
        if tipo == "ajuste": cantidad = -cantidad
        with get_db() as conn:
            registrar_movimiento(conn, producto_id, tipo, cantidad, session["usuario_id"], nota=request.form.get("nota", "").strip())
        flash("Movimiento de inventario registrado.", "success")
    except ValueError as error:
        flash(str(error), "danger")
    return redirect(url_for("inventario"))


@app.route("/inventario/<int:producto_id>/estado/<int:estado>", methods=["POST"])
@requiere_rol("admin", "bodega")
def estado_producto(producto_id, estado):
    if estado not in (0, 1): abort(400)
    with get_db() as conn:
        resultado = conn.execute("UPDATE productos SET activo=? WHERE id=?", (estado, producto_id))
    if not resultado.rowcount: abort(404)
    flash("Producto actualizado.", "info")
    return redirect(url_for("inventario"))



@app.route("/ventas")
@requiere_rol("admin", "vendedor", "bodega")
def ventas():
    with get_db() as conn:
        ventas_lista = conn.execute("""SELECT v.*, u.usuario, COUNT(d.id) AS lineas FROM ventas v JOIN usuarios u ON u.id=v.usuario_id
            LEFT JOIN detalle_ventas d ON d.venta_id=v.id GROUP BY v.id ORDER BY v.id DESC""").fetchall()
    return render_template("ventas.html", ventas=ventas_lista)


@app.route("/ventas/nueva", methods=["GET", "POST"])
@requiere_rol("admin", "vendedor", "bodega")
def nueva_venta():
    with get_db() as conn:
        productos = conn.execute("SELECT * FROM productos WHERE activo=1 AND existencia>0 ORDER BY nombre").fetchall()
    if request.method == "POST":
        try:
            acumulado = {}
            for producto_id, cantidad in zip(request.form.getlist("producto_id"), request.form.getlist("cantidad")):
                if producto_id and cantidad:
                    pid, cant = int(producto_id), int(numero_positivo(cantidad, "La cantidad", False))
                    acumulado[pid] = acumulado.get(pid, 0) + cant
            if not acumulado: raise ValueError("Agrega al menos un producto a la venta.")
            with get_db() as conn:
                lineas, total = [], 0
                for pid, cant in acumulado.items():
                    producto = conn.execute("SELECT * FROM productos WHERE id=? AND activo=1", (pid,)).fetchone()
                    if producto is None: raise ValueError("Uno de los productos ya no está disponible.")
                    if producto["existencia"] < cant: raise ValueError(f"Stock insuficiente para {producto['nombre']}.")
                    subtotal = round(producto["precio_venta"] * cant, 2); total += subtotal
                    lineas.append((pid, cant, producto["precio_venta"], subtotal))
                cursor = conn.execute("INSERT INTO ventas (cliente,usuario_id,subtotal,total) VALUES (?,?,?,?)", (request.form.get("cliente", "").strip(), session["usuario_id"], total, total))
                for pid, cant, precio, subtotal in lineas:
                    conn.execute("INSERT INTO detalle_ventas (venta_id,producto_id,cantidad,precio_unitario,subtotal) VALUES (?,?,?,?,?)", (cursor.lastrowid,pid,cant,precio,subtotal))
                    registrar_movimiento(conn, pid, "venta", -cant, session["usuario_id"], f"Venta #{cursor.lastrowid}")
            flash("Venta registrada correctamente.", "success")
            return redirect(url_for("detalle_venta", venta_id=cursor.lastrowid))
        except (ValueError, sqlite3.Error) as error:
            flash(str(error), "danger")
    return render_template("form_venta.html", productos=productos)


@app.route("/ventas/<int:venta_id>")
@requiere_rol("admin", "vendedor", "bodega")
def detalle_venta(venta_id):
    with get_db() as conn:
        venta = conn.execute("SELECT v.*,u.usuario FROM ventas v JOIN usuarios u ON u.id=v.usuario_id WHERE v.id=?", (venta_id,)).fetchone()
        detalles = conn.execute("SELECT d.*,p.nombre,p.codigo FROM detalle_ventas d JOIN productos p ON p.id=d.producto_id WHERE d.venta_id=?", (venta_id,)).fetchall()
    if venta is None: abort(404)
    return render_template("detalle_venta.html", venta=venta, detalles=detalles)


@app.route("/ventas/<int:venta_id>/ticket")
@requiere_rol("admin", "vendedor", "bodega")
def ticket_venta(venta_id):
    with get_db() as conn:
        venta = conn.execute("SELECT v.*, u.usuario FROM ventas v JOIN usuarios u ON u.id=v.usuario_id WHERE v.id=?", (venta_id,)).fetchone()
        detalles = conn.execute("SELECT d.*, p.nombre, p.codigo FROM detalle_ventas d JOIN productos p ON p.id=d.producto_id WHERE d.venta_id=?", (venta_id,)).fetchall()
    if venta is None:
        abort(404)
    return render_template("ticket_venta.html", venta=venta, detalles=detalles)


@app.route("/ventas/<int:venta_id>/anular", methods=["POST"])
@requiere_rol("admin")
def anular_venta(venta_id):
    accion = request.form.get("accion")
    if accion not in ("anulada", "devuelta"): abort(400)
    try:
        with get_db() as conn:
            venta = conn.execute("SELECT * FROM ventas WHERE id=?", (venta_id,)).fetchone()
            if venta is None: abort(404)
            if venta["estado"] != "completada": raise ValueError("La venta ya fue procesada anteriormente.")
            detalles = conn.execute("SELECT * FROM detalle_ventas WHERE venta_id=?", (venta_id,)).fetchall()
            tipo = "anulacion" if accion == "anulada" else "devolucion"
            for detalle in detalles:
                registrar_movimiento(conn, detalle["producto_id"], tipo, detalle["cantidad"], session["usuario_id"], f"Venta #{venta_id}", request.form.get("motivo", "").strip())
            conn.execute("UPDATE ventas SET estado=?, motivo_anulacion=? WHERE id=?", (accion, request.form.get("motivo", "").strip(), venta_id))
        flash("La venta fue " + ("anulada" if accion == "anulada" else "devuelta") + " y el inventario se restauró.", "success")
    except ValueError as error: flash(str(error), "danger")
    return redirect(url_for("detalle_venta", venta_id=venta_id))


@app.route("/ventas/<int:venta_id>/devolucion_parcial", methods=["POST"])
@requiere_rol("admin", "bodega")
def devolucion_parcial(venta_id):
    producto_id = request.form.get("producto_id", type=int)
    cantidad = request.form.get("cantidad", type=int)
    motivo = request.form.get("motivo", "").strip()

    if not producto_id or not cantidad or cantidad <= 0:
        flash("Datos de devolución inválidos.", "danger")
        return redirect(url_for("detalle_venta", venta_id=venta_id))
    
    with get_db() as conn:
        venta = conn.execute("SELECT * FROM ventas WHERE id=?", (venta_id,)).fetchone()
        if not venta or venta["estado"] != "completada":
            flash("La venta no está disponible para devolución parcial.", "danger")
            return redirect(url_for("detalle_venta", venta_id=venta_id))
            
        detalle = conn.execute("SELECT * FROM detalle_ventas WHERE venta_id=? AND producto_id=?", (venta_id, producto_id)).fetchone()
        if not detalle or detalle["cantidad"] < cantidad:
            flash("La cantidad a devolver excede lo vendido o el producto no está en la venta.", "danger")
            return redirect(url_for("detalle_venta", venta_id=venta_id))
            
        # Reingreso al inventario
        registrar_movimiento(conn, producto_id, "devolucion", cantidad, session["usuario_id"], f"Venta #{venta_id} (Parcial)", motivo)
        
        # Actualizar detalle
        nueva_cantidad = detalle["cantidad"] - cantidad
        if nueva_cantidad > 0:
            nuevo_subtotal = nueva_cantidad * detalle["precio_unitario"]
            conn.execute("UPDATE detalle_ventas SET cantidad=?, subtotal=? WHERE id=?", (nueva_cantidad, nuevo_subtotal, detalle["id"]))
        else:
            conn.execute("DELETE FROM detalle_ventas WHERE id=?", (detalle["id"],))
            
        # Actualizar total de la venta
        nuevo_total_row = conn.execute("SELECT SUM(subtotal) as total FROM detalle_ventas WHERE venta_id=?", (venta_id,)).fetchone()
        nuevo_total = nuevo_total_row["total"] if nuevo_total_row["total"] is not None else 0
        
        if nuevo_total <= 0:
            conn.execute("UPDATE ventas SET estado='devuelta', motivo_anulacion=?, subtotal=0, total=0 WHERE id=?", (motivo or "Devolución total por partes", venta_id))
        else:
            conn.execute("UPDATE ventas SET subtotal=?, total=? WHERE id=?", (nuevo_total, nuevo_total, venta_id))
            
        flash(f"Devolución parcial de {cantidad} unidad(es) registrada.", "success")
        
    return redirect(url_for("detalle_venta", venta_id=venta_id))


@app.route("/usuarios", methods=["GET", "POST"])
@requiere_rol("admin", "rrhh")
def usuarios():
    if request.method == "POST":
        usuario, nombre, password, rol, empleado_id = (request.form.get(k, "").strip() for k in ("usuario", "nombre", "password", "rol", "empleado_id"))
        empleado_id = empleado_id if empleado_id else None
        try:
            if not usuario or not nombre or len(password) < 6: raise ValueError("Usuario, nombre y una contraseña de 6 caracteres son obligatorios.")
            if rol not in ("admin", "vendedor", "rrhh", "bodega"): raise ValueError("Rol inválido.")
            with get_db() as conn: conn.execute("INSERT INTO usuarios (usuario,nombre,password_hash,rol,empleado_id) VALUES (?,?,?,?,?)", (usuario,nombre,generate_password_hash(password),rol,empleado_id))
            flash("Usuario creado.", "success")
            return redirect(url_for("usuarios"))
        except (ValueError, sqlite3.IntegrityError) as error: flash("El usuario ya existe." if isinstance(error, sqlite3.IntegrityError) else str(error), "danger")
    with get_db() as conn: lista = conn.execute("SELECT u.id,u.usuario,u.nombre,u.rol,u.activo,u.creado_en,e.nombre as empleado_nombre FROM usuarios u LEFT JOIN empleados e ON e.id=u.empleado_id ORDER BY u.nombre").fetchall()
    with get_db() as conn:
        empleados = conn.execute("SELECT id, nombre, cedula FROM empleados WHERE activo=1").fetchall()
    return render_template("usuarios.html", usuarios=lista, empleados=empleados)


@app.route("/usuarios/<int:usuario_id>/estado/<int:estado>", methods=["POST"])
@requiere_rol("admin", "rrhh")
def estado_usuario(usuario_id, estado):
    if estado not in (0, 1) or usuario_id == session["usuario_id"]: abort(400, "No puedes cambiar tu propio acceso.")
    with get_db() as conn: resultado = conn.execute("UPDATE usuarios SET activo=? WHERE id=?", (estado, usuario_id))
    if not resultado.rowcount: abort(404)
    flash("Acceso de usuario actualizado.", "info")
    return redirect(url_for("usuarios"))

@app.route("/usuarios/<int:usuario_id>/rol", methods=["POST"])
@requiere_rol("admin", "rrhh")
def cambiar_rol_usuario(usuario_id):
    nuevo_rol = request.form.get("rol")
    if nuevo_rol not in ("admin", "vendedor", "rrhh", "bodega"):
        abort(400, "Rol inválido.")
    with get_db() as conn:
        conn.execute("UPDATE usuarios SET rol=? WHERE id=?", (nuevo_rol, usuario_id))
    flash("Rol de usuario actualizado correctamente.", "success")
    return redirect(url_for("usuarios"))

@app.route("/usuarios/<int:usuario_id>/password", methods=["POST"])
@requiere_rol("admin", "rrhh")
def cambiar_password_usuario(usuario_id):
    nueva_password = request.form.get("password", "")
    if len(nueva_password) < 6:
        flash("La contraseña debe tener al menos 6 caracteres.", "danger")
        return redirect(url_for("usuarios"))
    
    password_hash = generate_password_hash(nueva_password)
    with get_db() as conn:
        conn.execute("UPDATE usuarios SET password_hash=? WHERE id=?", (password_hash, usuario_id))
    flash("Contraseña actualizada exitosamente.", "success")
    return redirect(url_for("usuarios"))



@app.route("/catalogo/<tipo>", methods=["GET", "POST"])
@requiere_rol("admin", "rrhh", "bodega")
def catalogo(tipo):
    tablas = {
        "marcas": "Marcas",
        "tipos": "Tipos",
        "cargos": "Cargos",
        "departamentos": "Departamentos"
    }
    if tipo not in tablas:
        abort(404)
        
    titulo = tablas[tipo]
    
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        if not nombre:
            flash("El nombre es requerido.", "danger")
        else:
            try:
                with get_db() as conn:
                    conn.execute(f"INSERT INTO {tipo} (nombre) VALUES (?)", (nombre,))
                flash(f"Registro en {titulo} creado con éxito.", "success")
            except sqlite3.IntegrityError:
                flash("Ese nombre ya existe.", "danger")
        return redirect(url_for('catalogo', tipo=tipo))
        
    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        items = conn.execute(f"SELECT * FROM {tipo} ORDER BY nombre").fetchall()
        
    return render_template("catalogo.html", titulo=titulo, items=items, tipo_url=tipo)

@app.route("/catalogo/<tipo>/<int:item_id>/estado/<int:estado>", methods=["POST"])
@requiere_rol("admin", "rrhh", "bodega")
def estado_catalogo(tipo, item_id, estado):
    tablas = ["marcas", "tipos", "cargos", "departamentos"]
    if tipo not in tablas or estado not in (0, 1):
        abort(400)
    with get_db() as conn:
        conn.execute(f"UPDATE {tipo} SET activo = ? WHERE id = ?", (estado, item_id))
    flash("Estado actualizado.", "success")
    return redirect(url_for('catalogo', tipo=tipo))

@app.route("/categorias", methods=["GET", "POST"])
@requiere_rol("admin", "bodega")
def categorias():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        if not nombre:
            flash("El nombre es obligatorio.", "danger")
        else:
            try:
                with get_db() as conn:
                    conn.execute("INSERT INTO categorias (nombre) VALUES (?)", (nombre,))
                flash("Categoría creada.", "success")
            except sqlite3.IntegrityError:
                flash("La categoría ya existe.", "danger")
        return redirect(url_for("categorias"))
    with get_db() as conn:
        lista = conn.execute("SELECT * FROM categorias ORDER BY nombre").fetchall()
    return render_template("categorias.html", categorias=lista)

@app.route("/categorias/<int:cat_id>/estado/<int:estado>", methods=["POST"])
@requiere_rol("admin", "bodega")
def estado_categoria(cat_id, estado):
    with get_db() as conn:
        conn.execute("UPDATE categorias SET activo=? WHERE id=?", (estado, cat_id))
    flash("Estado actualizado.", "info")
    return redirect(url_for("categorias"))

@app.route("/kardex")
@requiere_rol("admin", "bodega")
def kardex_lista():
    with get_db() as conn:
        productos = conn.execute("SELECT p.id, p.codigo, p.nombre, p.existencia FROM productos p ORDER BY p.nombre").fetchall()
    return render_template("kardex_lista.html", productos=productos)

@app.route("/kardex/<int:producto_id>")
@requiere_rol("admin", "bodega")
def kardex_producto(producto_id):
    with get_db() as conn:
        producto = conn.execute("SELECT * FROM productos WHERE id=?", (producto_id,)).fetchone()
        if not producto: abort(404)
        movs = conn.execute("SELECT m.*, u.usuario FROM movimientos_inventario m LEFT JOIN usuarios u ON u.id=m.usuario_id WHERE m.producto_id=? ORDER BY m.id ASC", (producto_id,)).fetchall()
    return render_template("kardex_detalle.html", producto=producto, movimientos=movs)

@app.route("/solicitudes")
@requiere_rol("admin", "bodega", "vendedor")
def solicitudes():
    with get_db() as conn:
        if session.get("rol") == "vendedor":
            lista = conn.execute("SELECT s.*, v.fecha as venta_fecha, v.total, u.usuario FROM solicitudes_anulacion s JOIN ventas v ON v.id=s.venta_id JOIN usuarios u ON u.id=s.usuario_solicita_id WHERE s.usuario_solicita_id=? ORDER BY s.id DESC", (session["usuario_id"],)).fetchall()
        else:
            lista = conn.execute("SELECT s.*, v.fecha as venta_fecha, v.total, u.usuario FROM solicitudes_anulacion s JOIN ventas v ON v.id=s.venta_id JOIN usuarios u ON u.id=s.usuario_solicita_id ORDER BY s.id DESC").fetchall()
    return render_template("solicitudes.html", solicitudes=lista)

@app.route("/ventas/<int:venta_id>/solicitar_anulacion", methods=["POST"])
@requiere_rol("admin", "vendedor")
def solicitar_anulacion(venta_id):
    tipo = request.form.get("tipo") # anulacion o devolucion
    motivo = request.form.get("motivo", "").strip()
    
    if not motivo:
        flash("El motivo es requerido.", "danger")
        return redirect(url_for("detalle_venta", venta_id=venta_id))
        
    if tipo not in ("anulacion", "devolucion"):
        flash("Tipo de solicitud inválido.", "danger")
        return redirect(url_for("detalle_venta", venta_id=venta_id))
        
    with get_db() as conn:
        venta = conn.execute("SELECT * FROM ventas WHERE id=?", (venta_id,)).fetchone()
        if not venta or venta["estado"] != "completada":
            flash("Venta inválida o ya procesada.", "danger")
            return redirect(url_for("detalle_venta", venta_id=venta_id))
            
        # Registramos únicamente la solicitud sin romper la restricción CHECK de la venta
        conn.execute("INSERT INTO solicitudes_anulacion (venta_id, tipo, usuario_solicita_id, motivo) VALUES (?,?,?,?)", 
                     (venta_id, tipo, session["usuario_id"], motivo))
    
    flash("Solicitud enviada a bodega/administración.", "success")
    return redirect(url_for("detalle_venta", venta_id=venta_id))

@app.route("/solicitudes/<int:solicitud_id>/resolver", methods=["POST"])
@requiere_rol("admin", "bodega")
def resolver_solicitud(solicitud_id):
    accion = request.form.get("accion") # aprobar o rechazar
    from database import registrar_movimiento
    from datetime import datetime
    
    try:
        with get_db() as conn:
            sol = conn.execute("SELECT * FROM solicitudes_anulacion WHERE id=? AND estado='pendiente'", (solicitud_id,)).fetchone()
            if not sol:
                raise ValueError("Solicitud no encontrada o ya resuelta.")
                
            venta_id = sol["venta_id"]
            if accion == "aprobar":
                # Reingresar stock
                detalles = conn.execute("SELECT * FROM detalle_ventas WHERE venta_id=?", (venta_id,)).fetchall()
                for detalle in detalles:
                    registrar_movimiento(conn, detalle["producto_id"], sol["tipo"], detalle["cantidad"], session["usuario_id"], f"Venta #{venta_id} ({sol['tipo']})", sol["motivo"])
                
                estado_final = "anulada" if sol["tipo"] == "anulacion" else "devuelta"
                conn.execute("UPDATE ventas SET estado=? WHERE id=?", (estado_final, venta_id))
                conn.execute("UPDATE solicitudes_anulacion SET estado='aprobada', usuario_autoriza_id=?, fecha_resolucion=CURRENT_TIMESTAMP WHERE id=?", (session["usuario_id"], solicitud_id))
                flash("Solicitud aprobada y stock restaurado.", "success")
            else:
                conn.execute("UPDATE ventas SET estado='completada' WHERE id=?", (venta_id,))
                conn.execute("UPDATE solicitudes_anulacion SET estado='rechazada', usuario_autoriza_id=?, fecha_resolucion=CURRENT_TIMESTAMP WHERE id=?", (session["usuario_id"], solicitud_id))
                flash("Solicitud rechazada.", "info")
    except ValueError as e:
        flash(str(e), "danger")
        
    return redirect(url_for("solicitudes"))


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")
