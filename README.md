# NutriCart Backend - Grupo 12

Repositorio del backend oficial para el proyecto **NutriCart**, desarrollado con **Python y FastAPI**, encargado de gestionar perfiles de usuario, procesamiento de intenciones y la futura integración con el catálogo del supermercado.

---

## Prerrequisitos
* Tener instalado **Python** (versión 3.10 o superior recomendada).

---

## Instrucciones de Instalación y Ejecución (Windows)

Sigue estos pasos en tu terminal para levantar el servidor de desarrollo localmente utilizando un entorno virtual aislando las dependencias:

### 1. Clonar o abrir la carpeta del proyecto
Abre tu terminal (PowerShell o CMD) y posicionate en la carpeta raíz del backend:
```bash
cd Ruta/A/Tu/Carpeta/GPTI
```

### 2. Crear el Entorno Virtual (venv)
Crea un entorno virtual local ejecutando:
```bash
python -m venv venv
```

### 3. Activar el Entorno Virtual
Activa el entorno:
- Si usas CMD (Spimbolo del sistema):
```bash
venv\Scripts\activate.bat
```
- Si usas MAC:
```bash
source venv/bin/activate
```
(Sabrás que está activo porque aparecerá (venv) al inicio de tu línea de comandos).

### 4. Instalar las Dependencias
Con el entorno virtual activo, instala los paquetes requeridos:
- Con Windows:
```bash
python -m pip install -r requirements.txt
```
- Con MAC o Linux:
```bash
pip install -r requirements.txt
```

### 5. Configurar las Variables de Entorno (.env)
1. Crea un archivo llamado .env en la raíz del proyecto
2. Agrega la variable de conexión:
```bash
DATABASE_URL=postgresql://postgres.muqarojryuazjdhsavzb:TU_CONTRASEÑA@aws-0-us-east-2.pooler.supabase.com:5432/postgres
```
3. (Opcional) Configura los orígenes permitidos por CORS para el frontend, como lista separada por comas. Si no se define, el valor por defecto es `http://localhost:5173` (Vite):
```bash
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

### 6. Ejecutar el Servidor de Desarrollo
Inicia la aplicación FastAPI con recarga automática:
- Con Windows:
```bash
python -m uvicorn app.main:app --reload
```

- Con MAC o Linux:
```bash
uvicorn app.main:app --reload
```