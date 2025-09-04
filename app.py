from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from sqlalchemy import text, desc, and_
from datetime import datetime, date, time
from werkzeug.utils import secure_filename
import os
import urllib.parse
import logging
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
from threading import Thread
import smtplib
import time as time_module
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import ssl
import requests

# Configuración básica de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', '7a3e8b1f45c9d2e6a7b4c8f3e1d9a2b5c7e3f8a1d4b9e6c2a5f8e3b1d7c9a4e6')

# Configuración de la base de datos Railway
app.config['SQLALCHEMY_DATABASE_URI'] = (
    'mysql+pymysql://root:VHYZwwkmTYmGQAfwKiQGBwHAlpZcesIQ@gondola.proxy.rlwy.net:24406/railway'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configuración de correo Mailgun - USAR VARIABLES DE ENTORNO
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.mailgun.org')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'False').lower() == 'true'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'corporativovb@sandboxa92ea0efebee474b934033418f510063.mailgun.org')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'corporativovbdb2025@gmail.com')
app.config['MAIL_TIMEOUT'] = 30
app.config['MAIL_DEBUG'] = False

# Configuración para subida de archivos (DESHABILITADA para Railway)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

# Crear directorio de uploads si no existe (solo para desarrollo local)
if os.environ.get('RAILWAY_ENVIRONMENT') is None:
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
mail = Mail(app)

# === Modelos ===

class Fecha(db.Model):
    __tablename__ = 'Fechas'
    idFechas = db.Column(db.Integer, primary_key=True)
    Fecha = db.Column(db.Date)

class Hora(db.Model):
    __tablename__ = 'Hora'
    idHora = db.Column(db.Integer, primary_key=True)
    Hora = db.Column(db.Time, nullable=False, unique=True)

class Prospecto(db.Model):
    __tablename__ = 'Prospecto'
    idProspecto = db.Column(db.Integer, primary_key=True)
    Tipo_Prospecto = db.Column(db.String(45))

class Pais(db.Model):
    __tablename__ = 'Pais'
    idPais = db.Column(db.Integer, primary_key=True, autoincrement=True)
    pais = db.Column(db.String(45))

class Cliente(db.Model):
    __tablename__ = 'Cliente'
    idCliente = db.Column(db.Integer, primary_key=True, autoincrement=True)
    Nombre = db.Column(db.String(45), nullable=False)
    Apellido_P = db.Column(db.String(45), nullable=False)
    Apellido_M = db.Column(db.String(45))
    Telefono = db.Column(db.String(45), nullable=False)
    Email = db.Column(db.String(45), nullable=False)
    Prospecto_idProspecto = db.Column(db.Integer, default=1)
    Pais_idPais = db.Column(db.Integer, default=1)

class Reunion(db.Model):
    __tablename__ = 'Reuniones'
    id_r = db.Column(db.Integer, primary_key=True, autoincrement=True)
    cliente = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    fecha = db.Column(db.Date, nullable=False)
    hora = db.Column(db.Time, nullable=False)
    enlace_zoom = db.Column(db.String(255), nullable=False, default='https://us06web.zoom.us/j/81971641072')

class Paquete(db.Model):
    __tablename__ = 'Paquete'
    idPaquete = db.Column(db.Integer, primary_key=True, autoincrement=True)
    Nombre = db.Column(db.String(100), nullable=False)
    Destino = db.Column(db.String(100), nullable=False)
    Calificacion = db.Column(db.Float, default=0.0)
    Promocion = db.Column(db.String(100), default="")
    Precio = db.Column(db.Float, nullable=False)
    Imagen = db.Column(db.String(255))
    Fecha_Inicio = db.Column(db.Date)
    Fecha_Final = db.Column(db.Date)

class Jefe(db.Model):
    __tablename__ = 'jefe'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    usuario = db.Column(db.String(50))
    contraseña = db.Column(db.String(255))

# === Funciones de utilidad ===

def limpiar_fechas_antiguas():
    """Elimina automáticamente las fechas anteriores al día actual"""
    try:
        hoy = date.today()
        num_eliminadas = db.session.execute(
            text("DELETE FROM Fechas WHERE Fecha < :hoy"),
            {'hoy': hoy}
        ).rowcount
        db.session.commit()
        logger.info(f"Se eliminaron {num_eliminadas} fechas antiguas")
        return num_eliminadas
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al limpiar fechas antiguas: {e}")
        return 0

def limpieza_automatica_mexico():
    """Ejecuta la limpieza de fechas a las 00:00 hora de México"""
    try:
        # Obtener la hora actual en zona horaria de México
        zona_mexico = pytz.timezone('America/Mexico_City')
        ahora_mexico = datetime.now(zona_mexico)
        
        logger.info(f"⏰ Verificando limpieza programada. Hora en México: {ahora_mexico.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Ejecutar limpieza solo entre 00:00 and 00:05 hora de México
        if ahora_mexico.hour == 0 and ahora_mexico.minute <= 5:
            num_eliminadas = limpiar_fechas_antiguas()
            logger.info(f"✅ Limpieza automática completada. Fechas eliminadas: {num_eliminadas}")
            return num_eliminadas
        else:
            logger.info("🕒 No es hora de limpieza automática")
            return 0
            
    except Exception as e:
        logger.error(f"❌ Error en limpieza automática: {e}")
        return 0

def allowed_file(filename):
    """Verifica si la extensión del archivo está permitida"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def convert_google_drive_url(url):
    """Convierte un enlace de Google Drive a un enlace directo de imagen"""
    if not url or 'drive.google.com' not in url:
        return url
    
    if 'uc?id=' in url:
        file_id = url.split('uc?id=')[1].split('&')[0]
        return f"https://drive.google.com/thumbnail?id={file_id}&sz=w1000"
    
    if 'file/d/' in url:
        parts = url.split('/')
        try:
            file_id_index = parts.index('d') + 1
            if file_id_index < len(parts):
                file_id = parts[file_id_index]
                return f"https://drive.google.com/thumbnail?id={file_id}&sz=w1000"
        except (ValueError, IndexError):
            pass
    
    return url

def enviar_correo(destinatario, asunto, cuerpo):
    """Función para enviar emails usando Mailgun API (más confiable que SMTP)"""
    try:
        # Configuración de Mailgun API
        mailgun_domain = os.environ.get('MAILGUN_DOMAIN', 'sandboxa92ea0efebee474b934033418f510063.mailgun.org')
        mailgun_api_key = os.environ.get('MAILGUN_API_KEY', '')
        
        if not mailgun_api_key:
            logger.error("❌ API Key de Mailgun no configurado")
            # Guardar en log para no perder los emails
            with open('emails_pendientes.log', 'a') as f:
                f.write(f"{datetime.now()}|{destinatario}|{asunto}|{cuerpo[:200]}...\n")
            return False
        
        # Preparar la solicitud a la API de Mailgun
        url = f"https://api.mailgun.net/v3/{mailgun_domain}/messages"
        auth = ("api", mailgun_api_key)
        
        data = {
            "from": f"Corporativo Vicente Blas <mailgun@{mailgun_domain}>",
            "to": destinatario,
            "subject": asunto,
            "text": cuerpo
        }
        
        # Enviar la solicitud
        response = requests.post(
            url, 
            auth=auth, 
            data=data,
            timeout=30
        )
        
        if response.status_code == 200:
            logger.info("✅ Correo enviado exitosamente via Mailgun API")
            return True
        else:
            logger.error(f"❌ Error Mailgun API: {response.status_code} - {response.text}")
            # Guardar en log para recuperar después
            with open('emails_fallidos.log', 'a') as f:
                f.write(f"{datetime.now()}|{destinatario}|{asunto}|API Error: {response.status_code}\n")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error enviando correo via API: {str(e)}")
        # Guardar en log para recuperar después
        with open('emails_fallidos.log', 'a') as f:
            f.write(f"{datetime.now()}|{destinatario}|{asunto}|Exception: {str(e)}\n")
        return False

def enviar_correo_async(app, destinatario, asunto, cuerpo):
    """Envía correos en segundo plano"""
    with app.app_context():
        return enviar_correo(destinatario, asunto, cuerpo)

# ✅ FILTRO CORREGIDO
@app.template_filter('ensure_public_image')
def ensure_public_image_filter(image_path):
    if not image_path:
        return "https://via.placeholder.com/300x180"
    
    if image_path.startswith(('http://', 'https://')):
        return image_path
    
    if 'drive.google.com' in image_path:
        return image_path
    
    return "https://via.placeholder.com/300x180"

# === Configuración del programador de tareas ===
scheduler = BackgroundScheduler()
scheduler.add_job(func=limpieza_automatica_mexico, trigger='cron', hour='*', minute=0)
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

# === Endpoint de diagnóstico de email ===
@app.route('/debug-email')
def debug_email():
    """Endpoint completo para debuguear email"""
    try:
        # Mostrar configuración actual (ocultando password)
        config = {
            'MAIL_SERVER': app.config.get('MAIL_SERVER'),
            'MAIL_PORT': app.config.get('MAIL_PORT'),
            'MAIL_USE_TLS': app.config.get('MAIL_USE_TLS'),
            'MAIL_USERNAME': app.config.get('MAIL_USERNAME'),
            'MAIL_PASSWORD_SET': bool(app.config.get('MAIL_PASSWORD')),
            'MAIL_DEFAULT_SENDER': app.config.get('MAIL_DEFAULT_SENDER'),
            'RAILWAY_ENVIRONMENT': os.environ.get('RAILWAY_ENVIRONMENT'),
            'MAILGUN_API_KEY_SET': bool(os.environ.get('MAILGUN_API_KEY')),
            'MAILGUN_DOMAIN': os.environ.get('MAILGUN_DOMAIN')
        }
        
        # Test de envío de correo de prueba
        email_status = ""
        try:
            resultado = enviar_correo(
                'corporativovbdb2025@gmail.com',
                '✅ Test Email from Railway',
                'This is a test email from your Railway app using Mailgun API'
            )
            if resultado:
                email_status = "✅ Email de prueba enviado exitosamente"
            else:
                email_status = "❌ Error enviando email"
        except Exception as email_error:
            email_status = f"❌ Error enviando email: {email_error}"
        
        return jsonify({
            'status': 'diagnostic_complete',
            'email_test': email_status,
            'config': config
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e),
            'config': {
                'MAIL_SERVER': app.config.get('MAIL_SERVER'),
                'MAIL_PORT': app.config.get('MAIL_PORT'),
                'MAIL_USE_TLS': app.config.get('MAIL_USE_TLS'),
                'MAIL_USERNAME': app.config.get('MAIL_USERNAME'),
                'MAIL_PASSWORD_SET': bool(app.config.get('MAIL_PASSWORD')),
                'MAIL_DEFAULT_SENDER': app.config.get('MAIL_DEFAULT_SENDER'),
                'MAILGUN_API_KEY_SET': bool(os.environ.get('MAILGUN_API_KEY')),
                'MAILGUN_DOMAIN': os.environ.get('MAILGUN_DOMAIN')
            }
        }), 500

# === Endpoints de Fechas ===

@app.route('/api/fechas/count')
def contar_fechas():
    count = db.session.execute(text("SELECT COUNT(*) FROM Fechas")).scalar()
    return jsonify({'count': count})

@app.route('/api/fechas/proximas')
def fechas_proximas():
    hoy = date.today()
    fechas = Fecha.query.filter(Fecha.Fecha >= hoy).order_by(Fecha.Fecha).limit(5).all()
    return jsonify([{
        'idFechas': f.idFechas,
        'Fecha': f.Fecha.strftime('%Y-%m-%d')
    } for f in fechas])

@app.route('/api/fechas', methods=['GET'])
def listar_fechas():
    fechas = Fecha.query.order_by(Fecha.Fecha).all()
    return jsonify([{
        'idFechas': f.idFechas,
        'Fecha': f.Fecha.strftime('%Y-%m-%d')
    } for f in fechas])

@app.route('/api/fechas', methods=['POST'])
def crear_fecha():
    data = request.get_json()
    try:
        fecha_input = datetime.strptime(data['Fecha'], '%Y-%m-%d').date()
        
        fecha_existente = Fecha.query.filter_by(Fecha=fecha_input).first()
        if fecha_existente:
            return jsonify({
                'success': False, 
                'message': 'Esta fecha ya existe en el sistema',
                'duplicado': True
            }), 400
            
        nueva_fecha = Fecha(Fecha=fecha_input)
        db.session.add(nueva_fecha)
        db.session.commit()
        return jsonify({
            'success': True, 
            'message': 'Fecha creada correctamente',
            'nuevaFecha': {
                'idFechas': nueva_fecha.idFechas,
                'Fecha': nueva_fecha.Fecha.strftime('%Y-%m-%d')
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/api/fechas/<int:id>', methods=['PUT'])
def actualizar_fecha(id):
    fecha = Fecha.query.get_or_404(id)
    data = request.get_json()
    try:
        nueva_fecha_input = datetime.strptime(data['Fecha'], '%Y-%m-%d').date()
        
        fecha_existente = Fecha.query.filter(
            and_(
                Fecha.Fecha == nueva_fecha_input,
                Fecha.idFechas != id
            )
        ).first()
        
        if fecha_existente:
            return jsonify({
                'success': False, 
                'message': 'Esta fecha ya existe en el sistema',
                'duplicado': True
            }), 400
            
        fecha.Fecha = nueva_fecha_input
        db.session.commit()
        return jsonify({
            'success': True, 
            'message': 'Fecha actualizada correctamente',
            'fechaActualizada': {
                'idFechas': fecha.idFechas,
                'Fecha': fecha.Fecha.strftime('%Y-%m-%d')
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/api/fechas/<int:id>', methods=['DELETE'])
def eliminar_fecha(id):
    fecha = Fecha.query.get_or_404(id)
    try:
        db.session.delete(fecha)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Fecha eliminada correctamente'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/api/fechas/limpiar-antiguas', methods=['POST'])
def limpiar_fechas_antiguas_endpoint():
    try:
        num_eliminadas = limpiar_fechas_antiguas()
        return jsonify({
            'success': True,
            'message': 'Fechas antiguas eliminadas correctamente',
            'fechas_eliminadas': num_eliminadas
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error al limpiar fechas antiguas: {str(e)}'
        }), 500

# === Endpoints de Horas ===

@app.route('/api/horas/count')
def contar_horas():
    count = Hora.query.count()
    return jsonify({'count': count})

@app.route('/api/horas/recientes')
def horas_recientes():
    horas = Hora.query.order_by(desc(Hora.idHora)).limit(5).all()
    return jsonify([{
        'idHora': h.idHora,
        'Hora': h.Hora.strftime('%H:%M')
    } for h in horas])

@app.route('/api/horas', methods=['GET'])
def listar_horas():
    horas = Hora.query.order_by(Hora.Hora).all()
    return jsonify([{
        'idHora': h.idHora,
        'Hora': h.Hora.strftime('%H:%M')
    } for h in horas])

@app.route('/api/horas', methods=['POST'])
def crear_hora():
    data = request.get_json()
    try:
        hora_str = data['Hora']
        hora_obj = datetime.strptime(hora_str, '%H:%M').time()
        
        hora_existente = Hora.query.filter_by(Hora=hora_obj).first()
        if hora_existente:
            return jsonify({
                'success': False, 
                'message': 'Esta hora ya existe en el sistema',
                'duplicado': True
            }), 400
            
        nueva_hora = Hora(Hora=hora_obj)
        db.session.add(nueva_hora)
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Hora creada correctamente',
            'nuevaHora': {
                'idHora': nueva_hora.idHora,
                'Hora': nueva_hora.Hora.strftime('%H:%M')
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/api/horas/<int:id>', methods=['PUT'])
def actualizar_hora(id):
    hora = Hora.query.get_or_404(id)
    data = request.get_json()
    try:
        nueva_hora_str = data['Hora']
        nueva_hora_obj = datetime.strptime(nueva_hora_str, '%H:%M').time()
        
        hora_existente = Hora.query.filter(
            and_(
                Hora.Hora == nueva_hora_obj,
                Hora.idHora != id
            )
        ).first()
        
        if hora_existente:
            return jsonify({
                'success': False, 
                'message': 'Esta hora ya existe en el sistema',
                'duplicado': True
            }), 400
            
        hora.Hora = nueva_hora_obj
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Hora actualizada correctamente',
            'horaActualizada': {
                'idHora': hora.idHora,
                'Hora': hora.Hora.strftime('%H:%M')
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/api/horas/<int:id>', methods=['DELETE'])
def eliminar_hora(id):
    hora = Hora.query.get_or_404(id)
    try:
        db.session.delete(hora)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Hora eliminada correctamente'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400

# === Endpoints de Clientes ===

@app.route('/api/clientes/count')
def contar_clientes():
    count = Cliente.query.count()
    return jsonify({'count': count})

@app.route('/api/clientes/recientes')
def clientes_recientes():
    clientes = db.session.query(Cliente, Prospecto).join(
        Prospecto, Cliente.Prospecto_idProspecto == Prospecto.idProspecto
    ).order_by(desc(Cliente.idCliente)).limit(5).all()
    
    return jsonify([{
        'id': c.Cliente.idCliente,
        'nombre': c.Cliente.Nombre,
        'apellido_p': c.Cliente.Apellido_P,
        'apellido_m': c.Cliente.Apellido_M,
        'email': c.Cliente.Email,
        'tipo_prospecto': c.Prospecto.Tipo_Prospecto
    } for c in clientes])

@app.route('/api/clientes', methods=['GET'])
def listar_clientes():
    clientes = db.session.query(Cliente, Prospecto).join(
        Prospecto, Cliente.Prospecto_idProspecto == Prospecto.idProspecto
    ).order_by(Cliente.idCliente).all()
    
    return jsonify([{
        'idCliente': c.Cliente.idCliente,
        'Nombre': c.Cliente.Nombre,
        'Apellido_P': c.Cliente.Apellido_P,
        'Apellido_M': c.Cliente.Apellido_M,
        'Telefono': c.Cliente.Telefono,
        'Email': c.Cliente.Email,
        'Tipo_Prospecto': c.Prospecto.Tipo_Prospecto
    } for c in clientes])

@app.route('/api/clientes', methods=['POST'])
def crear_cliente():
    data = request.get_json()
    try:
        tipo_cliente = data.get('tipo', 'interesado')
        prospecto_id = 2 if tipo_cliente == 'cotizador' else 1
            
        nuevo_cliente = Cliente(
            Nombre=data['Nombre'],
            Apellido_P=data['Apellido_P'],
            Apellido_M=data.get('Apellido_M', ''),
            Telefono=data['Telefono'],
            Email=data['Email'],
            Prospecto_idProspecto=prospecto_id,
            Pais_idPais=1
        )
        db.session.add(nuevo_cliente)
        db.session.commit()
        
        prospecto = Prospecto.query.get(prospecto_id)
        
        return jsonify({
            'success': True, 
            'message': 'Cliente creada correctamente',
            'nuevoCliente': {
                'idCliente': nuevo_cliente.idCliente,
                'Nombre': nuevo_cliente.Nombre,
                'Apellido_P': nuevo_cliente.Apellido_P,
                'Apellido_M': nuevo_cliente.Apellido_M,
                'Telefono': nuevo_cliente.Telefono,
                'Email': nuevo_cliente.Email,
                'tipo': tipo_cliente,
                'Tipo_Prospecto': prospecto.Tipo_Prospecto if prospecto else tipo_cliente
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/api/clientes/<int:id>', methods=['PUT'])
def actualizar_cliente(id):
    cliente = Cliente.query.get_or_404(id)
    data = request.get_json()
    try:
        tipo_cliente = data.get('tipo', 'interesado')
        prospecto_id = 2 if tipo_cliente == 'cotizador' else 1
            
        cliente.Nombre = data['Nombre']
        cliente.Apellido_P = data['Apellido_P']
        cliente.Apellido_M = data.get('Apellido_M', '')
        cliente.Telefono = data['Telefono']
        cliente.Email = data['Email']
        cliente.Prospecto_idProspecto = prospecto_id
        
        db.session.commit()
        
        prospecto = Prospecto.query.get(prospecto_id)
        
        return jsonify({
            'success': True, 
            'message': 'Cliente actualizada correctamente',
            'clienteActualizado': {
                'idCliente': cliente.idCliente,
                'Nombre': cliente.Nombre,
                'Apellido_P': cliente.Apellido_P,
                'Apellido_M': cliente.Apellido_M,
                'Telefono': cliente.Telefono,
                'Email': cliente.Email,
                'tipo': tipo_cliente,
                'Tipo_Prospecto': prospecto.Tipo_Prospecto if prospecto else tipo_cliente
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/api/clientes/<int:id>', methods=['DELETE'])
def eliminar_cliente(id):
    cliente = Cliente.query.get_or_404(id)
    try:
        db.session.delete(cliente)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Cliente eliminada correctamente'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400

# === Endpoints para Reuniones ===

@app.route('/api/reuniones', methods=['GET'])
def listar_reuniones():
    try:
        reuniones = Reunion.query.order_by(Reunion.fecha, Reunion.hora).all()
        return jsonify([{
            'id_r': r.id_r,
            'cliente': r.cliente,
            'email': r.email,
            'fecha': r.fecha.strftime('%Y-%m-%d'),
            'hora': r.hora.strftime('%H:%M'),
            'fecha_formateada': r.fecha.strftime('%d/%m/%Y'),
            'hora_formateada': r.hora.strftime('%I:%M %p'),
            'enlace_zoom': r.enlace_zoom
        } for r in reuniones])
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error al obtener reuniones: {str(e)}'
        }), 500

@app.route('/api/reuniones/<int:id>', methods=['DELETE'])
def eliminar_reunion(id):
    reunion = Reunion.query.get_or_404(id)
    try:
        db.session.delete(reunion)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Reunión eliminada correctamente'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400

# === Endpoint para Invitaciones Zoom ===

@app.route('/api/enviar-invitacion-zoom', methods=['POST'])
def enviar_invitacion_zoom():
    try:
        data = request.json
        
        required_fields = ['email', 'nombre', 'subject', 'message', 'fecha', 'hora']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({
                    'success': False,
                    'message': f'El campo {field} es requerido'
                }), 400

        try:
            fecha_obj = datetime.strptime(data['fecha'], '%Y-%m-%d').date()
            hora_obj = datetime.strptime(data['hora'], '%H:%M').time()
        except ValueError as e:
            return jsonify({
                'success': False,
                'message': f'Formato de fecha/hora inválido: {str(e)}'
            }), 400

        nueva_reunion = Reunion(
            cliente=data['nombre'],
            email=data['email'],
            fecha=fecha_obj,
            hora=hora_obj,
            enlace_zoom='https://us06web.zoom.us/j/81971641072'
        )
        
        db.session.add(nueva_reunion)
        db.session.commit()

        # Enviar correo al cliente (async)
        try:
            thread = Thread(target=enviar_correo_async, args=(app, data['email'], data['subject'], data['message']))
            thread.start()
        except Exception as mail_error:
            logger.error(f"Error al programar correo: {mail_error}")

        # Enviar copia al administrador (async)
        try:
            cuerpo_admin = f"""Se envió invitación a Zoom a:

Nombre: {data['nombre']}
Email: {data['email']}

Mensaje enviado:
{data['message']}
"""
            thread = Thread(target=enviar_correo_async, args=(app, 'corporativovbdb2025@gmail.com', f"Copia: {data['subject']}", cuerpo_admin))
            thread.start()
        except Exception:
            pass

        return jsonify({
            'success': True,
            'message': 'Reunión agendada e invitación enviada correctamente',
            'reunion_id': nueva_reunion.id_r
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error al agendar reunión: {str(e)}'
        }), 500

# === Rutas principales ===

@app.route('/')
def home():
    try:
        db.session.execute(text('SELECT 1'))
        return render_template('index.html')
    except Exception as e:
        return f'❌ Error al conectar a la base de datos: {e}'

@app.route('/log.html')
def log():
    fecha = request.args.get('fecha')
    hora = request.args.get('hora')
    return render_template('log.html', fecha=fecha, hora=hora)

@app.route('/paquetes')
def mostrar_paquetes():
    try:
        paquetes = Paquete.query.all()
        return render_template('muestra.html', paquetes=paquetes)
    except Exception as e:
        return f'❌ Error al obtener paquetes: {e}'

@app.route('/api/fechas')
def get_fechas():
    try:
        fechas = Fecha.query.all()
        eventos = [{
            "start": f.Fecha.strftime("%Y-%m-%d"),
            "allDay": True,
            "display": "background",
            "color": "green",
            "idFechas": f.idFechas
        } for f in fechas]
        return jsonify(eventos)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/horas/<int:id_fecha>')
def get_horas(id_fecha):
    try:
        horas = Hora.query.all()
        horas_lista = [{"idHora": h.idHora, "hora": h.Hora.strftime("%H:%M:%S")} for h in horas]
        return jsonify(horas_lista)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/guardar_cliente', methods=['POST'])
def guardar_cliente():
    logger.info("🔵🔵🔵 INICIANDO guardar_cliente 🔵🔵🔵")
    logger.info(f"Form data: {dict(request.form)}")
    
    try:
        nombre = request.form['nombre']
        apellidoP = request.form['apellidoP']
        apellidoM = request.form.get('apellidoM', '')
        telefono = request.form['telefono']
        email = request.form['email']
        pais_nombre = request.form['pais']
        tipo_cliente = request.form['tipo']

        fecha = request.form.get('fecha')
        hora = request.form.get('hora')

        logger.info(f"📋 Datos recibidos: {nombre} {apellidoP}, tipo: {tipo_cliente}, fecha: {fecha}, hora: {hora}")

        prospecto = Prospecto.query.filter_by(Tipo_Prospecto=tipo_cliente).first()
        if not prospecto:
            logger.error(f"❌ Tipo de prospecto '{tipo_cliente}' no encontrado.")
            return f"❌ Tipo de prospecto '{tipo_cliente}' no encontrado."

        pais_existente = Pais.query.filter_by(pais=pais_nombre).first()
        if not pais_existente:
            nuevo_pais = Pais(pais=pais_nombre)
            db.session.add(nuevo_pais)
            db.session.commit()
            pais_id = nuevo_pais.idPais
        else:
            pais_id = pais_existente.idPais

        nuevo_cliente = Cliente(
            Nombre=nombre,
            Apellido_P=apellidoP,
            Apellido_M=apellidoM,
            Telefono=telefono,
            Email=email,
            Prospecto_idProspecto=prospecto.idProspecto,
            Pais_idPais=pais_id
        )

        db.session.add(nuevo_cliente)
        db.session.commit()

        logger.info(f"✅ Cliente guardado exitosamente: ID {nuevo_cliente.idCliente}")

        if tipo_cliente.lower() == "cotizador":
            cuerpo_mensaje_cliente = f"""
Hola {nombre},

Gracias por tu interés en nuestros paquetes de viaje. Te mantendremos informado sobre 
nuevos paquetes, promociones y ofertas especiales que puedan ser de tu interés.

Pronto recibirás información sobre nuestros destinos y paquetes disponibles.

¡Esperamos poder ayudarte a planificar tu próximo viaje!

Equipo Corporativo Vicente Blas SAS DE CV
            """

            cuerpo_mensaje_admin = f"""
Nuevo cliente interesado en paquetes registrado en el sistema:

Nombre: {nombre} {apellidoP} {apellidoM}
📞 Teléfono: {telefono}
📧 Email: {email}
🌎 País: {pais_nombre}
👤 Tipo de prospecto: {tipo_cliente}

Este cliente está interesado en recibir información sobre paquetes de viaje.
            """

            # Enviar correos en segundo plano
            try:
                thread = Thread(target=enviar_correo_async, args=(app, email, "✅ Registro exitoso - Información de paquetes", cuerpo_mensaje_cliente))
                thread.start()
            except Exception as mail_error:
                logger.error(f"Error al programar correo cliente: {mail_error}")

            try:
                thread = Thread(target=enviar_correo_async, args=(app, 'corporativovbdb2025@gmail.com', f"📦 Nuevo cliente interesado en paquetes: {nombre} {apellidoP}", cuerpo_mensaje_admin))
                thread.start()
            except Exception as mail_error:
                logger.error(f"Error al programar correo admin: {mail_error}")

            return redirect(url_for('mostrar_paquetes'))

        elif tipo_cliente.lower() == "interesado en crear tu agencia":
            if not fecha or not hora:
                logger.error("❌ Fecha y hora requeridas para reuniones")
                return "❌ Fecha y hora son requeridas para agendar reunión", 400

            try:
                fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
            except ValueError as e:
                logger.error(f"❌ Formato de fecha inválido: {fecha}. Error: {str(e)}")
                return f"❌ Formato de fecha inválido: {fecha}", 400
            
            try:
                hora_obj = datetime.strptime(hora, '%H:%M').time()
            except ValueError:
                try:
                    hora_obj = datetime.strptime(hora, '%H:%M:%S').time()
                except ValueError as e:
                    logger.error(f"❌ Formato de hora no válido: {hora}. Error: {str(e)}")
                    return f"❌ Formato de hora no válido: {hora}", 400
            
            nueva_reunion = Reunion(
                cliente=f"{nombre} {apellidoP} {apellidoM}".strip(),
                email=email,
                fecha=fecha_obj,
                hora=hora_obj,
                enlace_zoom='https://us06web.zoom.us/j/81971641072'
            )
            db.session.add(nueva_reunion)
            db.session.commit()

            cuerpo_mensaje = f"""
Hola {nombre},

Gracias por registrarte a nuestra sesión informativa para agentes de viajes con Vicente Blas Benitez.
El día
📅 Fecha: {fecha}
⏰ Hora: {hora}
🔗 Enlace de Zoom: https://us06web.zoom.us/j/81971641072

¡Nos vemos pronto!

Equipo Corporativo Vicente Blas SAS DE CV
            """

            # Enviar correos en segundo plano
            try:
                thread = Thread(target=enviar_correo_async, args=(app, email, "✅ Confirmación de tu sesión informativa", cuerpo_mensaje))
                thread.start()
            except Exception as mail_error:
                logger.error(f"Error al programar correo confirmación: {mail_error}")

            try:
                cuerpo_interno = f"""
Nuevo cliente registrado en el sistema:

Nombre: {nombre} {apellidoP} {apellidoM}
📞 Teléfono: {telefono}
📧 Email: {email}
🌎 País: {pais_nombre}
👤 Tipo de prospecto: {tipo_cliente}

{cuerpo_mensaje}
                """
                thread = Thread(target=enviar_correo_async, args=(app, 'corporativovbdb2025@gmail.com', f"📩 Nuevo registro de cliente: {nombre} {apellidoP}", cuerpo_interno))
                thread.start()
            except Exception as mail_error:
                logger.error(f"Error al programar correo interno: {mail_error}")

            return redirect(url_for('envio', cliente_id=nuevo_cliente.idCliente, fecha=fecha, hora=hora))

        return redirect(url_for('home'))

    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ ERROR en guardar_cliente: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return f"❌ Error al guardar cliente: {e}"

@app.route('/inicio')
def inicio():
    return render_template('inicio.html')

@app.route('/validar_admin', methods=['POST'])
def validar_admin():
    usuario = request.form['usuario']
    contraseña = request.form['contraseña']

    jefe = Jefe.query.filter_by(usuario=usuario, contraseña=contraseña).first()

    if jefe:
        return redirect(url_for('interfaz_admin'))
    else:
        error = "❌ Usuario o contraseña incorrectos. Intenta de nuevo."
        return render_template('inicio.html', error=error)

@app.route('/interfaz_admin')
def interfaz_admin():
    return render_template('interfaz_admin.html')

@app.route('/envio')
def envio():
    cliente_id = request.args.get('cliente_id')
    fecha = request.args.get('fecha')
    hora = request.args.get('hora')

    if not cliente_id:
        return "Cliente ID no proporcionado", 400

    cliente = Cliente.query.filter_by(idCliente=cliente_id).first()
    if not cliente:
        return "Cliente no encontrado", 404

    pais_obj = Pais.query.filter_by(idPais=cliente.Pais_idPais).first()
    prospecto_obj = Prospecto.query.filter_by(idProspecto=cliente.Prospecto_idProspecto).first()

    enlace_zoom = "https://us06web.zoom.us/j/81971641072"
    tipo = prospecto_obj.Tipo_Prospecto if prospecto_obj else ''

    return render_template('envio.html',
                           nombre=cliente.Nombre,
                           apellidoP=cliente.Apellido_P,
                           apellidoM=cliente.Apellido_M if cliente.Apellido_M else '',
                           telefono=cliente.Telefono,
                           email=cliente.Email,
                           pais=pais_obj.pais if pais_obj else '',
                           tipo=tipo,
                           fecha=fecha,
                           hora=hora,
                           enlace_zoom=enlace_zoom)

# === Vistas administración ===

@app.route('/admin/fechas')
def admin_fechas():
    return render_template('fechas.html')

@app.route('/admin/horas')
def admin_horas():
    return render_template('horas.html')

@app.route('/admin/clientes')
def admin_clientes():
    return render_template('clientes.html')

# === Gestión de paquetes ===

@app.route('/Pack')
def pack():
    try:
        paquetes = Paquete.query.order_by(Paquete.Fecha_Inicio).all()
        clientes = Cliente.query.order_by(Cliente.Nombre).all()
        return render_template('Pack.html', paquetes=paquetes, clientes=clientes)
    except Exception as e:
        return f"❌ Error al cargar Pack.html: {e}"

@app.route('/form_paquete')
def form_paquete():
    return render_template('form_paquete.html')

@app.route('/paquete/nuevo', methods=['GET', 'POST'])
def nuevo_paquete():
    if request.method == 'POST':
        try:
            nombre = request.form['nombre']
            calificacion = request.form['calificacion']
            promocion = request.form['promocion']
            destino = request.form['destino']
            precio_str = request.form['precio']
            fecha_inicio = request.form['fecha_inicio']
            fecha_final = request.form['fecha_final']

            imagen_url = request.form.get('imagen_url', '')
            imagen_drive = request.form.get('imagen_drive', '')
            imagen = ''

            if imagen_drive:
                imagen = convert_google_drive_url(imagen_drive)
            elif imagen_url:
                imagen = imagen_url

            try:
                precio = float(precio_str.replace(',', '').replace('$', '').strip())
            except ValueError:
                flash('Formato de precio inválido', 'error')
                return render_template('form_paquete.html', paquete=None)

            try:
                fecha_inicio_obj = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
                fecha_final_obj = datetime.strptime(fecha_final, '%Y-%m-%d').date()
            except ValueError as e:
                flash(f'Formato de fecha inválido: {str(e)}', 'error')
                return render_template('form_paquete.html', paquete=None)

            nuevo = Paquete(
                Nombre=nombre,
                Calificacion=float(calificacion) if calificacion else 0.0,
                Promocion=promocion,
                Imagen=imagen,
                Destino=destino,
                Precio=precio,
                Fecha_Inicio=fecha_inicio_obj,
                Fecha_Final=fecha_final_obj
            )
            
            db.session.add(nuevo)
            db.session.commit()
            flash('Paquete creado correctamente', 'success')
            return redirect(url_for('pack'))
            
        except Exception as e:
            db.session.rollback()
            return f"ERROR EN NUEVO_PAQUETE: {str(e)}<br>TYPE: {type(e).__name__}"
    
    return render_template('form_paquete.html', paquete=None)

@app.route('/paquete/editar/<int:id>', methods=['GET', 'POST'])
def editar_paquete(id):
    try:
        paquete = Paquete.query.get_or_404(id)
    except Exception as e:
        flash('Paquete no encontrado', 'error')
        return redirect(url_for('pack'))

    if request.method == 'POST':
        try:
            paquete.Nombre = request.form['nombre']
            
            try:
                paquete.Calificacion = float(request.form['calificacion']) if request.form['calificacion'] else 0.0
            except ValueError:
                flash('Formato de calificación inválido', 'error')
                return render_template('form_paquete.html', paquete=paquete)
                
            paquete.Promocion = request.form['promocion']
            paquete.Destino = request.form['destino']

            precio_str = request.form['precio']
            try:
                paquete.Precio = float(precio_str.replace(',', '').replace('$', '').strip())
            except ValueError:
                flash('Formato de precio inválido', 'error')
                return render_template('form_paquete.html', paquete=paquete)

            try:
                paquete.Fecha_Inicio = datetime.strptime(request.form['fecha_inicio'], '%Y-%m-%d').date()
                paquete.Fecha_Final = datetime.strptime(request.form['fecha_final'], '%Y-%m-%d').date()
            except ValueError as e:
                flash(f'Formato de fecha inválido: {str(e)}', 'error')
                return render_template('form_paquete.html', paquete=paquete)

            imagen_url = request.form.get('imagen_url', '')
            imagen_drive = request.form.get('imagen_drive', '')

            if imagen_drive:
                paquete.Imagen = convert_google_drive_url(imagen_drive)
            elif imagen_url:
                paquete.Imagen = imagen_url

            db.session.commit()
            flash('Paquete actualizado correctamente', 'success')
            return redirect(url_for('pack'))
            
        except Exception as e:
            db.session.rollback()
            return f"ERROR EN EDITAR_PAQUETE: {str(e)}<br>TYPE: {type(e).__name__}"
    
    return render_template('form_paquete.html', paquete=paquete)

@app.route('/eliminar_paquete/<int:id>', methods=['POST'])
def eliminar_paquete(id):
    paquete = Paquete.query.get_or_404(id)
    try:
        db.session.delete(paquete)
        db.session.commit()
        flash('Paquete eliminado correctamente', 'success')
        return redirect(url_for('pack'))
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar paquete: {e}', 'error')
        return redirect(url_for('pack'))

@app.route('/enviar_whatsapp', methods=['POST'])
def enviar_whatsapp():
    try:
        id_paquete = request.form.get('id_paquete')
        numeros = request.form.getlist('numeros')
        
        if not id_paquete or not numeros:
            flash('Datos incompletos', 'error')
            return redirect(url_for('mostrar_paquetes'))

        paquete = Paquete.query.get_or_404(id_paquete)
        clientes_seleccionados = Cliente.query.filter(Cliente.Telefono.in_(numeros)).all()
        
        mensaje = (
            f"Hola, tenemos un nuevo paquete:\n\n"
            f"Nombre: {paquete.Nombre}\n"
            f"Destino: {paquete.Destino}\n"
            f"Precio: {paquete.Precio}\n"
            f"Desde: {paquete.Fecha_Inicio.strftime('%d %b')} hasta {paquete.Fecha_Final.strftime('%d %b')}"
        )
        mensaje_encoded = urllib.parse.quote(mensaje)
        
        enlaces = []
        for cliente in clientes_seleccionados:
            telefono_limpio = ''.join(filter(str.isdigit, cliente.Telefono))
            if telefono_limpio:
                enlace_whatsapp = f'https://wa.me/{telefono_limpio}?text={mensaje_encoded}'
                enlaces.append({
                    'nombre': cliente.Nombre,
                    'numero': cliente.Telefono,
                    'enlace': enlace_whatsapp
                })
        
        return render_template('enlaces_whatsapp.html', 
                            paquete=paquete,
                            enlaces=enlaces)
    
    except Exception as e:
        flash(f'Error al generar enlaces: {str(e)}', 'error')
        return redirect(url_for('mostrar_paquetes'))

# Ruta para servir archivos subidos
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    if os.environ.get('RAILWAY_ENVIRONMENT'):
        return "Funcionalidad de subida de archivos no disponible en producción", 404
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Nuevos endpoints para testing
@app.route('/test-mailgun')
def test_mailgun():
    """Endpoint para probar Mailgun"""
    try:
        resultado = enviar_correo(
            'corporativovbdb2025@gmail.com',
            '🚀 Test Mailgun desde Railway',
            'Este es un email de prueba usando Mailgun API\n\n'
            f'📅 Hora: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n'
            f'🌐 Entorno: {os.environ.get("RAILWAY_ENVIRONMENT", "Desconocido")}'
        )
        
        return jsonify({
            'success': resultado,
            'message': '✅ Email enviado correctamente' if resultado else '❌ Error enviando email',
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/mailgun-config')
def mailgun_config():
    """Verificar configuración de Mailgun"""
    config = {
        'MAIL_SERVER': app.config.get('MAIL_SERVER'),
        'MAIL_PORT': app.config.get('MAIL_PORT'),
        'MAIL_USERNAME': app.config.get('MAIL_USERNAME'),
        'MAIL_PASSWORD_SET': bool(app.config.get('MAIL_PASSWORD')),
        'MAIL_USE_TLS': app.config.get('MAIL_USE_TLS'),
        'MAIL_DEFAULT_SENDER': app.config.get('MAIL_DEFAULT_SENDER'),
        'MAILGUN_API_KEY_SET': bool(os.environ.get('MAILGUN_API_KEY')),
        'MAILGUN_DOMAIN': os.environ.get('MAILGUN_DOMAIN')
    }
    return jsonify(config)

if __name__ == '__main__':
    app.secret_key = 'super_secret_key'
    app.run(debug=True)