# app/blueprints/partners.py
"""
Blueprint Módulo 4: Catastro de Socios, Medidores y Sectores.
Rutas HTML + API JSON para DataTables / Modales AJAX.

CAMBIOS RESPECTO A LA VERSIÓN ANTERIOR:
-----------------------------------------
FIX 1: Ruta duplicada /create → sectors_create movida a /sectors/create
FIX 2: Filtro de usuarios invertido (mostraba vinculados, debe mostrar libres)
FIX 3: validate_user_id accedía partner_profile como objeto (es dynamic query)
FIX 4: change_meter_route ahora acepta JSON además de form-encoded
FIX 5: sectors_create y sectors_edit retornan JSON para llamadas AJAX
FIX 6: sectors_create y sectors_edit validan CSRF correctamente
"""

from datetime import date
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, jsonify, current_app
)
from flask_login import login_required, current_user
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from app import db
from app.models.partner import Partner, Meter, Sector, PartnerStatus, MeterStatus
from app.models.user import User, ROLE_LABELS
from app.services.partner_service import (
    get_partner_by_id, search_partners, create_partner, update_partner,
    change_meter, get_meters_available_for_install,
    get_admin_stats, get_socio_portal_data,
    get_sectores_activos, create_sector, get_sector_by_id,
    ValidationError, BusinessRuleError, NotFoundError, PartnerServiceError
)
from app.services.auth_service import permission_required

# ──────────────────────────────────────────────────────────────
# FORMS (WTForms) - Validación Servidor + CSRF
# ──────────────────────────────────────────────────────────────
from flask_wtf import FlaskForm
from wtforms import (
    StringField, TextAreaField, SelectField, DateField,
    IntegerField, FloatField, HiddenField, BooleanField
)
from wtforms.validators import (
    DataRequired, Optional, Length, Email, NumberRange,
    ValidationError as WTFormsValidationError
)
from app.services.rut_validator import clean_rut, validate_rut, format_rut


class PartnerForm(FlaskForm):
    """Formulario Crear/Editar Socio."""
    id = HiddenField()
    rut = StringField('RUT', validators=[DataRequired(), Length(max=12)],
                      render_kw={"placeholder": "12.345.678-9", "class": "form-control"})
    nombre = StringField('Nombre / Razón Social', validators=[DataRequired(), Length(max=150)],
                         render_kw={"class": "form-control"})
    nombre_fantasia = StringField('Nombre Fantasía', validators=[Optional(), Length(max=150)],
                                  render_kw={"class": "form-control"})
    direccion = StringField('Dirección', validators=[DataRequired(), Length(max=250)],
                            render_kw={"class": "form-control"})
    numero = StringField('Número', validators=[Optional(), Length(max=10)],
                         render_kw={"class": "form-control"})
    complemento = StringField('Complemento (Depto/Block)', validators=[Optional(), Length(max=100)],
                              render_kw={"class": "form-control"})
    sector_id = SelectField('Sector', coerce=int, validators=[Optional()],
                            render_kw={"class": "form-select"})
    latitud = FloatField('Latitud', validators=[Optional(), NumberRange(-90, 90)],
                         render_kw={"class": "form-control", "step": "any"})
    longitud = FloatField('Longitud', validators=[Optional(), NumberRange(-180, 180)],
                          render_kw={"class": "form-control", "step": "any"})
    referencia_ubicacion = TextAreaField('Referencia Ubicación', validators=[Optional()],
                                         render_kw={"class": "form-control", "rows": 2})
    telefono = StringField('Teléfono', validators=[Optional(), Length(max=20)],
                           render_kw={"class": "form-control"})
    celular = StringField('Celular', validators=[Optional(), Length(max=20)],
                          render_kw={"class": "form-control"})
    email = StringField('Email', validators=[Optional(), Email(), Length(max=120)],
                        render_kw={"class": "form-control", "type": "email"})
    estado = SelectField('Estado',
                         choices=[(s.value, s.name.capitalize()) for s in PartnerStatus],
                         validators=[DataRequired()], render_kw={"class": "form-select"})
    fecha_ingreso = DateField('Fecha Ingreso', format='%Y-%m-%d', validators=[Optional()],
                              render_kw={"class": "form-control", "type": "date"})
    tipo_conexion = SelectField('Tipo Conexión',
                                choices=[('domiciliaria', 'Domiciliaria'),
                                         ('industrial', 'Industrial'),
                                         ('agrícola', 'Agrícola'),
                                         ('otra', 'Otra')],
                                validators=[DataRequired()],
                                render_kw={"class": "form-select"})
    diametro_empalme = StringField('Diámetro Empalme (mm)', validators=[Optional(), Length(max=10)],
                                   render_kw={"class": "form-control"})
    observaciones = TextAreaField('Observaciones', validators=[Optional()],
                                  render_kw={"class": "form-control", "rows": 3})
    user_id = SelectField('Usuario Portal (Opcional)', coerce=int, validators=[Optional()],
                          render_kw={"class": "form-select"})
    motivo_baja = TextAreaField('Motivo Baja / Corte', validators=[Optional()],
                                render_kw={"class": "form-control", "rows": 2})

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Sectores activos para el dropdown
        self.sector_id.choices = [(0, '-- Sin Sector --')] + [
            (s.id, s.nombre) for s in get_sectores_activos()
        ]

        # ── FIX 2 ──────────────────────────────────────────
        # ANTES: User.query.filter(User.partner_profile.any(), User.is_active == True)
        #        → Seleccionaba usuarios que YA TENÍAN socio vinculado
        # AHORA: ~User.partner_profile.any()
        #        → Selecciona usuarios SIN socio vinculado (libres para vincular)
        # ¿Por qué? El dropdown muestra candidatos a vincular. Si ya tienen socio,
        # no tiene sentido ofrecerlos aquí.
        # ───────────────────────────────────────────────────
        users_free = User.query.filter(
            ~User.partner_profile.any(),
            User.is_active == True
        ).order_by(User.nombre)
        self.user_id.choices = [(0, '-- Sin vincular --')] + [
            (u.id, f"{u.nombre} ({u.rut})") for u in users_free
        ]

    def validate_rut(self, field):
        if not field.data:
            return
        cleaned = clean_rut(field.data)
        if not validate_rut(cleaned):
            raise WTFormsValidationError("RUT inválido (dígito verificador incorrecto)")
        partner_id = int(self.id.data) if self.id.data else None
        existing = Partner.query.filter(Partner.rut == format_rut(cleaned))
        if partner_id:
            existing = existing.filter(Partner.id != partner_id)
        if existing.first():
            raise WTFormsValidationError("Este RUT ya está registrado en otro socio.")

    def validate_user_id(self, field):
        # ── FIX 3 ──────────────────────────────────────────
        # ANTES: if user.partner_profile and (not self.id.data or ...)
        #        → user.partner_profile es un objeto Query (lazy='dynamic'),
        #          SIEMPRE es truthy aunque no tenga resultados.
        #        → Además, acceder .id sobre un Query lanza AttributeError.
        # AHORA: Se usa .first() para obtener el Partner real o None.
        # ¿Por qué? El backref 'partner_profile' en Partner.user_id es
        # lazy='dynamic' (definido por la relación 1:1 con unique=True).
        # Un query dynamic siempre evalúa como True; hay que ejecutar
        # .first() para saber si realmente existe un Partner vinculado.
        # ───────────────────────────────────────────────────
        if field.data and field.data != 0:
            user = User.query.get(field.data)
            if not user:
                raise WTFormsValidationError("Usuario no encontrado.")
            existing_partner = user.partner_profile.first()
            if existing_partner:
                # Si estamos editando, permitir que sea el mismo socio
                if not self.id.data or existing_partner.id != int(self.id.data):
                    raise WTFormsValidationError("Este usuario ya tiene un socio asociado.")


class MeterChangeForm(FlaskForm):
    """Formulario modal Cambio de Medidor."""
    partner_id = HiddenField(validators=[DataRequired()])
    old_meter_id = HiddenField(validators=[DataRequired()])
    new_meter_serie = SelectField('Nuevo Medidor (Nº Serie)', coerce=str,
                                  validators=[DataRequired()],
                                  render_kw={"class": "form-select"})
    lectura_salida = IntegerField('Lectura Salida (Medidor Antiguo)',
                                  validators=[DataRequired(), NumberRange(min=0)],
                                  render_kw={"class": "form-control", "min": 0})
    lectura_entrada = IntegerField('Lectura Entrada (Medidor Nuevo)',
                                   validators=[DataRequired(), NumberRange(min=0)],
                                   render_kw={"class": "form-control", "min": 0})
    fecha_cambio = DateField('Fecha Cambio', format='%Y-%m-%d',
                             validators=[DataRequired()],
                             default=date.today,
                             render_kw={"class": "form-control", "type": "date"})
    observaciones = TextAreaField('Observaciones', validators=[Optional()],
                                  render_kw={"class": "form-control", "rows": 2})

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        meters = get_meters_available_for_install()
        self.new_meter_serie.choices = [
            (m.numero_serie, f"{m.numero_serie} ({m.marca or 'S/M'} - {m.modelo or 'S/M'})")
            for m in meters
        ]


class SectorForm(FlaskForm):
    """Formulario simple Sector."""
    id = HiddenField()
    codigo = StringField('Código', validators=[DataRequired(), Length(max=20)],
                         render_kw={"class": "form-control", "placeholder": "SEC-01"})
    nombre = StringField('Nombre', validators=[DataRequired(), Length(max=100)],
                         render_kw={"class": "form-control"})
    descripcion = TextAreaField('Descripción', validators=[Optional()],
                                render_kw={"class": "form-control", "rows": 2})
    orden_lectura = IntegerField('Orden Lectura', validators=[Optional(), NumberRange(min=0)],
                                 default=0, render_kw={"class": "form-control"})
    activo = BooleanField('Activo', default=True)


# ──────────────────────────────────────────────────────────────
# BLUEPRINT
# ──────────────────────────────────────────────────────────────
bp = Blueprint('partners', __name__, url_prefix='/partners')


# ══════════════════════════════════════════════════════════════
# LISTADO PRINCIPAL (HTML + DataTables AJAX)
# ══════════════════════════════════════════════════════════════

@bp.route('/')
@login_required
@permission_required('partners', 1)
def index():
    """Vista principal: Tabla de Socios (DataTables server-side)."""
    sectores = get_sectores_activos()
    estados = [(s.value, s.name.capitalize()) for s in PartnerStatus]
    return render_template('partners/index.html', sectores=sectores, estados=estados)


@bp.route('/api/list')
@login_required
@permission_required('partners', 1)
def api_list():
    """Endpoint DataTables: JSON paginado/filtrado."""
    draw = request.args.get('draw', 1, type=int)
    start = request.args.get('start', 0, type=int)
    length = request.args.get('length', 25, type=int)
    search_value = request.args.get('search[value]', '', type=str)

    estado = request.args.get('estado', '', type=str)
    sector_id = request.args.get('sector_id', 0, type=int)

    page = (start // length) + 1 if length else 1
    per_page = length

    estado_enum = PartnerStatus(estado) if estado else None
    sector_id_f = sector_id if sector_id != 0 else None

    try:
        partners, total = search_partners(
            term=search_value if search_value else None,
            estado=estado_enum,
            sector_id=sector_id_f,
            page=page,
            per_page=per_page,
            order_by='nombre',
            order_dir='asc'
        )
    except Exception as e:
        current_app.logger.error(f"Error api_list partners: {e}")
        return jsonify({
            'draw': draw, 'recordsTotal': 0,
            'recordsFiltered': 0, 'data': [], 'error': str(e)
        }), 500

    data = []
    for p in partners:
        meter_act = p.medidor_activo
        data.append({
            'id': p.id,
            'rut': p.rut,
            'nombre': p.nombre,
            'direccion': p.direccion_completa,
            'sector': p.sector_rel.nombre if p.sector_rel else None,
            'medidor': meter_act.numero_serie if meter_act else None,
            'estado': p.estado.name.capitalize(),
            'estado_raw': p.estado.value,
            'fecha_ingreso': p.fecha_ingreso.strftime('%d/%m/%Y') if p.fecha_ingreso else '-',
            # FIX 33: Se elimina el campo 'actions' del backend.
            # El HTML de los botones ahora se genera en el frontend (JS).
            # El backend solo envía datos puros.
        })

    return jsonify({
        'draw': draw,
        'recordsTotal': total,
        'recordsFiltered': total,
        'data': data
    })


# ══════════════════════════════════════════════════════════════
# CREAR SOCIO
# ══════════════════════════════════════════════════════════════

@bp.route('/create', methods=['GET', 'POST'])
@login_required
@permission_required('partners', 2)
def create():
    form = PartnerForm()
    if form.validate_on_submit():
        data = _form_to_partner_dict(form)
        try:
            partner = create_partner(data, current_user.id)
            flash(f'Socio "{partner.nombre}" creado correctamente (RUT: {partner.rut}).', 'success')
            # FIX 22: PRG pattern - redirect tras POST exitoso.
            # Esto ya existía, pero ahora es más importante porque
            # el FIX 20 previene re-submit del lado cliente,
            # y el redirect previene re-submit del lado servidor
            # (F5 del navegador no re-POSTea).
            return redirect(url_for('partners.detail', partner_id=partner.id))
        except ValidationError as e:
            flash(f'Error de validación: {e.message}', 'danger')
            if e.field and hasattr(form, e.field):
                getattr(form, e.field).errors.append(e.message)
        except PartnerServiceError as e:
            flash(f'Error: {e.message}', 'danger')
        except Exception as e:
            current_app.logger.exception("Error creando socio")
            flash('Error interno del servidor.', 'danger')

    return render_template('partners/form.html', form=form,
                           title='Nuevo Socio',
                           action_url=url_for('partners.create'))


# ══════════════════════════════════════════════════════════════
# EDITAR SOCIO
# ══════════════════════════════════════════════════════════════

@bp.route('/<int:partner_id>/edit', methods=['GET', 'POST'])
@login_required
@permission_required('partners', 2)
def edit(partner_id):
    partner = get_partner_by_id(partner_id, with_meters=False)
    form = PartnerForm(obj=partner)
    form.id.data = partner.id

    if partner.user_id:
        form.user_id.data = partner.user_id

    if form.validate_on_submit():
        data = _form_to_partner_dict(form)
        try:
            update_partner(partner_id, data, current_user.id)
            flash('Socio actualizado correctamente.', 'success')
            return redirect(url_for('partners.detail', partner_id=partner_id))
        except ValidationError as e:
            flash(f'Error de validación: {e.message}', 'danger')
            if e.field and hasattr(form, e.field):
                getattr(form, e.field).errors.append(e.message)
        except PartnerServiceError as e:
            flash(f'Error: {e.message}', 'danger')
        except Exception as e:
            current_app.logger.exception("Error editando socio")
            flash('Error interno del servidor.', 'danger')

    return render_template('partners/form.html', form=form, partner=partner,
                           title=f'Editar: {partner.nombre}',
                           action_url=url_for('partners.edit', partner_id=partner_id))


# ══════════════════════════════════════════════════════════════
# DETALLE SOCIO (Vista completa + Historial Medidores)
# ══════════════════════════════════════════════════════════════

@bp.route('/<int:partner_id>')
@login_required
@permission_required('partners', 1)
def detail(partner_id):
    partner = get_partner_by_id(partner_id, with_meters=True)

    # FIX 9: Cargar medidores como lista estática para el template
    meters_list = partner.meters.all()

    meter_form = MeterChangeForm()
    meter_form.partner_id.data = partner.id
    if partner.medidor_activo:
        meter_form.old_meter_id.data = partner.medidor_activo.id
        meter_form.lectura_salida.data = (
            partner.medidor_activo.ultima_lectura_valor
            or partner.medidor_activo.lectura_instalacion
        )

    return render_template('partners/detail.html',
                           partner=partner,
                           meter_form=meter_form,
                           meters_list=meters_list)  # ← nueva variable


# ══════════════════════════════════════════════════════════════
# CAMBIO DE MEDIDOR (AJAX POST desde Modal)
# ── FIX 4 ───────────────────────────────────────────────────
# ANTES: Usaba MeterChangeForm que solo lee request.form.
#        El modal Alpine.js enviaba Content-Type: application/json,
#        por lo que request.form llegaba vacío y el CSRF fallaba.
# AHORA: Detecta Content-Type. Si es JSON, parsea request.json
#        y llama directamente al service (sin WTForms).
#        Si es form-encoded, usa el form como antes.
# ¿Por qué? El modal usa Alpine.js + fetch con JSON porque necesita
# enviar datos estructurados desde el frontend. WTForms no puede
# parsear JSON body, solo form-encoded. La solución es tener dos
# caminos: JSON (modal AJAX) y form-encoded (fallback tradicional).
# ────────────────────────────────────────────────────────────

@bp.route('/change-meter', methods=['POST'])
@login_required
@permission_required('partners', 2)
def change_meter_route():
    # ── Camino A: JSON (desde modal Alpine.js) ──
    if request.is_json:
        data = request.get_json()

        # Validar campos requeridos manualmente (equivalente a WTForms)
        required = ['partner_id', 'new_meter_serie', 'lectura_salida',
                     'lectura_entrada', 'fecha_cambio']
        missing = [f for f in required if not data.get(f)]
        if missing:
            return jsonify({
                'success': False,
                'error': f'Campos requeridos faltantes: {", ".join(missing)}'
            }), 400

        try:
            old_m, new_m = change_meter(
                partner_id=int(data['partner_id']),
                new_meter_serie=data['new_meter_serie'],
                lectura_salida_antiguo=int(data['lectura_salida']),
                lectura_entrada_nuevo=int(data['lectura_entrada']),
                fecha_cambio=_parse_date(data['fecha_cambio']),
                user_id=current_user.id,
                observaciones=data.get('observaciones', '')
            )

            warn = ""
            if int(data['lectura_entrada']) < int(data['lectura_salida']):
                warn = (" ⚠️ La lectura de entrada es menor a la de salida; "
                        "verifique si el medidor nuevo parte en 0.")

            return jsonify({
                'success': True,
                'message': (f'Cambio realizado: Retirado {old_m.numero_serie} '
                            f'→ Instalado {new_m.numero_serie}.{warn}'),
                'new_meter_serie': new_m.numero_serie,
                'new_meter_id': new_m.id
            })

        except ValidationError as e:
            return jsonify({'success': False, 'error': e.message, 'field': e.field}), 400
        except BusinessRuleError as e:
            return jsonify({'success': False, 'error': e.message}), 400
        except PartnerServiceError as e:
            return jsonify({'success': False, 'error': e.message}), 400
        except Exception as e:
            current_app.logger.exception("Error en change_meter (JSON)")
            return jsonify({'success': False, 'error': 'Error interno del servidor'}), 500

    # ── Camino B: Form-encoded (fallback / form tradicional) ──
    form = MeterChangeForm()
    form.new_meter_serie.choices = [
        (m.numero_serie, m.numero_serie) for m in get_meters_available_for_install()
    ]

    if form.validate_on_submit():
        try:
            old_m, new_m = change_meter(
                partner_id=form.partner_id.data,
                new_meter_serie=form.new_meter_serie.data,
                lectura_salida_antiguo=form.lectura_salida.data,
                lectura_entrada_nuevo=form.lectura_entrada.data,
                fecha_cambio=form.fecha_cambio.data,
                user_id=current_user.id,
                observaciones=form.observaciones.data
            )

            warn = ""
            if form.lectura_entrada.data < form.lectura_salida.data:
                warn = (" ⚠️ La lectura de entrada es menor a la de salida; "
                        "verifique si el medidor nuevo parte en 0.")

            flash(f'Cambio realizado: Retirado {old_m.numero_serie} '
                  f'→ Instalado {new_m.numero_serie}.{warn}', 'success')
            return redirect(url_for('partners.detail',
                                    partner_id=form.partner_id.data))

        except ValidationError as e:
            flash(f'Error de validación: {e.message}', 'danger')
        except BusinessRuleError as e:
            flash(f'Error: {e.message}', 'danger')
        except PartnerServiceError as e:
            flash(f'Error: {e.message}', 'danger')
        except Exception as e:
            current_app.logger.exception("Error en change_meter (form)")
            flash('Error interno del servidor.', 'danger')

        return redirect(url_for('partners.detail',
                                partner_id=form.partner_id.data))

    errors = {field: errs[0] for field, errs in form.errors.items()}
    return jsonify({'success': False, 'error': 'Datos inválidos', 'errors': errors}), 400


# ══════════════════════════════════════════════════════════════
# API AUXILIARES (Select2 / Autocomplete)
# ══════════════════════════════════════════════════════════════

@bp.route('/api/search')
@login_required
@permission_required('partners', 1)
def api_search():
    """Autocomplete para selectores (ej. en Módulo Lecturas/Facturación)."""
    q = request.args.get('q', '', type=str)
    limit = request.args.get('limit', 10, type=int)

    if len(q) < 2:
        return jsonify({'results': []})

    partners, _ = search_partners(term=q, page=1, per_page=limit)
    results = [{
        'id': p.id,
        'text': f"{p.rut} - {p.nombre}",
        'rut': p.rut,
        'nombre': p.nombre,
        'direccion': p.direccion_completa,
        'medidor': p.medidor_activo.numero_serie if p.medidor_activo else None,
        'sector_id': p.sector_id
    } for p in partners]
    return jsonify({'results': results})


@bp.route('/api/meters/available')
@login_required
@permission_required('partners', 1)
def api_meters_available():
    """Medidores en bodega para modal cambio."""
    meters = get_meters_available_for_install()
    results = [{
        'id': m.id,
        'text': f"{m.numero_serie} ({m.marca or 'S/M'} {m.modelo or ''})",
        'serie': m.numero_serie,
        'marca': m.marca,
        'modelo': m.modelo,
        'diametro': m.diametro,
        'multiplicador': m.multiplicador
    } for m in meters]
    return jsonify({'results': results})


# ══════════════════════════════════════════════════════════════
# SECTORES (CRUD Simple dentro del mismo Blueprint)
# ── FIX 1 ───────────────────────────────────────────────────
# ANTES: @bp.route('/create') ← MISMA RUTA QUE create() de socios
#        Flask lanza AssertionError: ya existe un endpoint 'partners.create'
#        o, si no lanza error, una de las dos rutas queda inaccesible.
# AHORA: @bp.route('/sectors/create')
# ¿Por qué? Flask registra rutas por URL exacta por blueprint.
# Dos funciones con la misma URL causan conflicto. La URL correcta
# para crear un sector dentro del blueprint partners es /sectors/create.
# ────────────────────────────────────────────────────────────

@bp.route('/sectors')
@login_required
@permission_required('partners', 1)
def sectors_index():
    sectors = Sector.query.order_by(Sector.orden_lectura, Sector.nombre).all()
    form = SectorForm()
    return render_template('partners/sectors.html', sectors=sectors, form=form)


# ── FIX 5 ───────────────────────────────────────────────────
# ANTES: flash() + redirect() → El template sectors.html llama esta
#        ruta vía fetch() AJAX esperando JSON. Un redirect HTML
#        confunde al frontend: res.ok puede ser true (302→200)
#        pero res.json() falla porque el body es HTML.
# AHORA: Retorna JSON con success/message. Solo flash+redirect si
#        no es una llamada AJAX (fallback para forms tradicionales).
# ¿Por qué? El modal Alpine.js en sectors.html envía fetch() con
# Content-Type form-encoded y espera una respuesta JSON para mostrar
# toast y recargar. Compatibilidad dual: AJAX + form tradicional.
# ────────────────────────────────────────────────────────────

@bp.route('/sectors/create', methods=['POST'])
@login_required
@permission_required('partners', 2)
def sectors_create():
    form = SectorForm()
    if form.validate_on_submit():
        try:
            data = {
                'codigo': form.codigo.data,
                'nombre': form.nombre.data,
                'descripcion': form.descripcion.data,
                'orden_lectura': form.orden_lectura.data or 0
            }
            sector = create_sector(data, current_user.id)

            # Si es AJAX (fetch), devolver JSON
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                return jsonify({
                    'success': True,
                    'message': f'Sector "{sector.nombre}" creado.',
                    'sector': sector.to_dict()
                })

            # Si es form tradicional
            flash('Sector creado.', 'success')
            return redirect(url_for('partners.sectors_index'))

        except Exception as e:
            current_app.logger.exception("Error creando sector")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': str(e)}), 400
            flash(f'Error: {e}', 'danger')
    else:
        errors = {f: errs[0] for f, errs in form.errors.items()}
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'Datos inválidos', 'errors': errors}), 400
        for field, errs in form.errors.items():
            flash(f'{field}: {errs[0]}', 'danger')

    return redirect(url_for('partners.sectors_index'))


@bp.route('/sectors/<int:sector_id>/edit', methods=['POST'])
@login_required
@permission_required('partners', 2)
def sectors_edit(sector_id):
    sector = get_sector_by_id(sector_id)
    form = SectorForm(obj=sector)
    if form.validate_on_submit():
        sector.codigo = form.codigo.data.strip().upper()
        sector.nombre = form.nombre.data.strip()
        sector.descripcion = form.descripcion.data
        sector.orden_lectura = form.orden_lectura.data or 0
        db.session.commit()

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True,
                'message': f'Sector "{sector.nombre}" actualizado.',
                'sector': sector.to_dict()
            })

        flash('Sector actualizado.', 'success')
    else:
        errors = {f: errs[0] for f, errs in form.errors.items()}
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'Datos inválidos', 'errors': errors}), 400
        for field, errs in form.errors.items():
            flash(f'{field}: {errs[0]}', 'danger')

    return redirect(url_for('partners.sectors_index'))


@bp.route('/sectors/<int:sector_id>/toggle', methods=['POST'])
@login_required
@permission_required('partners', 2)
def sectors_toggle(sector_id):
    sector = get_sector_by_id(sector_id)
    sector.activo = not sector.activo
    db.session.commit()
    return jsonify({'success': True, 'activo': sector.activo})


# ──────────────────────────────────────────────────────────────
# HELPERS PRIVADOS
# ──────────────────────────────────────────────────────────────

def _form_to_partner_dict(form: PartnerForm) -> dict:
    """Convierte Form -> Dict compatible con Service Layer."""
    def clean(v):
        return v.strip() if isinstance(v, str) else v

    data = {
        'rut': clean(form.rut.data),
        'nombre': clean(form.nombre.data),
        'nombre_fantasia': clean(form.nombre_fantasia.data),
        'direccion': clean(form.direccion.data),
        'numero': clean(form.numero.data),
        'complemento': clean(form.complemento.data),
        'sector_id': form.sector_id.data if form.sector_id.data != 0 else None,
        'latitud': form.latitud.data,
        'longitud': form.longitud.data,
        'referencia_ubicacion': clean(form.referencia_ubicacion.data),
        'telefono': clean(form.telefono.data),
        'celular': clean(form.celular.data),
        'email': clean(form.email.data).lower() if form.email.data else None,
        'estado': form.estado.data,
        'fecha_ingreso': form.fecha_ingreso.data,
        'tipo_conexion': form.tipo_conexion.data,
        'diametro_empalme': clean(form.diametro_empalme.data),
        'observaciones': clean(form.observaciones.data),
        'motivo_baja': clean(form.motivo_baja.data),
    }
    if form.user_id.data and form.user_id.data != 0:
        data['user_id'] = form.user_id.data
    return data


def _parse_date(val) -> date:
    """Helper seguro para parsear fechas desde JSON strings."""
    if not val:
        return date.today()
    try:
        if isinstance(val, date):
            return val
        return date.fromisoformat(str(val))
    except (ValueError, TypeError):
        return date.today()