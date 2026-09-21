# 💼 Sistema de Gestión de Planilla y Nómina (Nicaragua)

Aplicación web desarrollada en **Python (Flask)** y **SQLite** para la administración de expedientes laborales y el cálculo automatizado de retenciones y contribuciones de ley en Nicaragua (INSS, IR e INSS Patronal).

---

## 🚀 Características Principales

* **Autenticación de Usuarios:** Control de acceso seguro mediante sesión para administradores de nómina.
* **Gestión de Colaboradores (CRUD):** Registro, edición y desactivación (borrado lógico) de expedientes laborales.
* **Validaciones y Máscaras en Tiempo Real:**
  * Cédula de identidad nicaragüense (`000-000000-0000X`).
  * Número de asegurado INSS (`1234567-8`).
  * Formato monetario automático en Córdobas (`C$ 0.00`).
* **Cálculo Automatizado de Nómina (Legislación de Nicaragua):**
  * **INSS Laboral:** 7% sobre el Salario Bruto.
  * **IR Laboral:** Retención mensual calculada sobre la tarifa progresiva anual (Art. 52 - LCT).
  * **INSS Patronal Dinámico:** Tasa adaptativa según la cantidad de empleados activos (21.5% para < 50 colaboradores y 22.5% para ≥ 50 colaboradores).
  * **Horas Extraordinarias:** Liquidación con recargo doble (100%) sobre la hora ordinaria (`Salario Base / 240 * 2`).
* **Historial y Reportes:**
  * Búsqueda y filtrado de pagos por rango de fechas (`Desde` / `Hasta`).
  * Desglose completo e individual de recibos de pago por trabajador.
* **Resiliencia de Base de Datos:** Modo WAL (`PRAGMA journal_mode=WAL`) en SQLite para evitar bloqueos por concurrencia y captura de excepciones para evitar duplicidad de cédulas.

---

## 🛠️ Tecnologías Utilizadas

* **Backend:** Python 3.x, Flask.
* **Base de Datos:** SQLite 3 (con conector nativo `sqlite3`).
* **Frontend:** HTML5, CSS3, JavaScript (ES6), Bootstrap 5, Bootstrap Icons.
* **Tipografía:** Google Fonts (Inter).

---

## 📂 Estructura del Proyecto

```text
Planilla/
│
├── static/
│   ├── css/
│   │   └── style.css          # Estilos globales y temas visuales
│   └── js/
│       ├── main.js            # Confirmaciones globales y utilidades UI
│       └── form_empleado.js   # Máscaras de entrada en cliente
│
├── templates/
│   ├── login.html             # Pantalla de inicio de sesión
│   ├── index.html             # Dashboard principal y listado de colaboradores
│   ├── form_empleado.html     # Formulario de creación/edición de expedientes
│   ├── form_planilla.html     # Formulario para procesar el cálculo de pago
│   └── historial_empleado.html # Vista detallada de recibos históricos
│
├── app.py                     # Rutas y controladores de Flask
├── database.py                # Conexiones, esquemas y lógica tributaria
└── planilla_ni.db             # Archivo de base de datos SQLite


-------------------------------------------------------------------------------------------------------------------
## ⚙️ Pasos para Levantar el Proyecto

### 1. Activar el Entorno Virtual (`.venv`)

Abre la terminal en la carpeta raíz del proyecto y ejecuta el comando según tu consola:

* **En PowerShell:**
  ```powershell
  .\.venv\Scripts\Activate.ps1

  ```DOS
  .venv\Scripts\activate

 ```En Git Bash / Terminal de VS Code:
  source .venv/Scripts/activate

### 2. Instalar Dependencias

    pip install -r requirements.txt

### 3. Entrar a la Carpeta del Código y Ejecutar
    cd Planilla
    python app.py

------------------------------------------------------------------------------------------------------    

🔑 Credenciales de Acceso
Ingresa estas credenciales en la pantalla de inicio de sesión (login):

Usuario: admin

Contraseña: 123456
## Configuración segura

Las credenciales ya no están incluidas en el código. Antes de iniciar la aplicación,
define las variables de entorno documentadas en `Planilla/.env.example`.

En PowerShell puedes crear una clave y un hash de contraseña así:

```powershell
$env:PLANILLA_SECRET_KEY = python -c "import secrets; print(secrets.token_urlsafe(32))"
$env:PLANILLA_ADMIN_USER = "admin"
$env:PLANILLA_ADMIN_PASSWORD_HASH = python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('CambiaEstaClave'))"
$env:PLANILLA_COOKIE_SECURE = "false"
```

Para producción usa HTTPS, configura `PLANILLA_COOKIE_SECURE=true` y deja `FLASK_DEBUG=false`.
