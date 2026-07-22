"""
Módulo 2 – Blueprint de Autenticación, Usuarios y Permisos.
Rutas: login, logout, recuperación de clave y administración de usuarios.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models.user import (
    User, ROLE_DEFAULTS, ROLE_LABELS,
    ALL_MODULES, MODULE_LABELS,
)
from app.services.rut_validator import clean_rut, validate_rut, format_rut
from app.services.auth_service import permission_required

auth_bp = Blueprint('auth', __name__, template_folder='../templates/auth')


# ── LOGIN ──────────────────────────────────────────────────

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Página y procesamiento de inicio de sesión."""

    # ── Si ya está autenticado, mostrar panel de sesión activa ──
    if current_user.is_authenticated:
        return render_template(
            'auth/login.html',
            session_active=True,
            user=current_user,
        )

    if request.method == 'POST':
        rut_raw = request.form.get('rut', '').strip()
        password = request.form.get('password', '')

        # Limpiar RUT
        rut = clean_rut(rut_raw)

        # Validar formato
        if not validate_rut(rut):
            flash('El RUT ingresado no es válido.', 'error')
            return render_template('auth/login.html', rut=rut_raw, session_active=False)

        # Generar variantes para buscar
        rut_formatted = format_rut(rut)
        rut_dashed = rut[:-1] + '-' + rut[-1]
        rut_plain = rut

        # Buscar por cualquier formato
        user = User.query.filter(
            (User.rut == rut_formatted) |
            (User.rut == rut_dashed) |
            (User.rut == rut_plain)
        ).first()

        if user is None or not user.check_password(password):
            flash('RUT o contraseña incorrectos.', 'error')
            return render_template('auth/login.html', rut=rut_raw, session_active=False)

        if not user.is_active:
            flash('Su cuenta se encuentra desactivada. Contacte al administrador.', 'error')
            return render_template('auth/login.html', rut=rut_raw, session_active=False)

        # Normalizar RUT almacenado
        if user.rut != rut_formatted:
            user.rut = rut_formatted
            db.session.commit()

        # Iniciar sesión
        login_user(user, remember=True)
        flash(f'Bienvenido, {user.nombre}.', 'success')

        # Redirigir según destino o rol
        next_page = request.args.get('next')
        if next_page and _is_safe_url(next_page):
            return redirect(next_page)
        return _redirect_by_role()

    return render_template('auth/login.html', session_active=False)


@auth_bp.route('/logout')
@login_required
def logout():
    """Cierra la sesión del usuario."""
    logout_user()
    flash('Sesión cerrada correctamente.', 'success')
    return redirect(url_for('dashboard.index'))


# ── RECUPERACIÓN DE CLAVE ──────────────────────────────────

@auth_bp.route('/recover', methods=['GET', 'POST'])
def recover_password():
    """Página de recuperación de clave por RUT o correo."""
    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()

        if not identifier:
            flash('Ingrese su RUT o correo electrónico.', 'error')
            return render_template('auth/recover_password.html')

        # Buscar por RUT o email
        user = None
        if '@' in identifier:
            user = User.query.filter_by(email=identifier.lower()).first()
        else:
            rut = clean_rut(identifier)
            if validate_rut(rut):
                rut_fmt = format_rut(rut)
                rut_dashed = rut[:-1] + '-' + rut[-1]
                user = User.query.filter(
                    (User.rut == rut_fmt) |
                    (User.rut == rut_dashed) |
                    (User.rut == rut)
                ).first()

        if user:
            import secrets
            temp_password = secrets.token_urlsafe(8)
            user.set_password(temp_password)
            db.session.commit()
            flash(
                f'Clave temporal generada para {format_rut(clean_rut(user.rut))}: '
                f'"{temp_password}". Inicie sesión y cámbiela de inmediato.',
                'success',
            )
            return redirect(url_for('auth.login'))

        flash(
            'Si el RUT o correo está registrado, recibirá instrucciones '
            'de recuperación.',
            'success',
        )
        return redirect(url_for('auth.login'))

    return render_template('auth/recover_password.html')


# ── ADMINISTRACIÓN DE USUARIOS ─────────────────────────────

@auth_bp.route('/users')
@login_required
@permission_required('auth', 2)
def users_admin():
    """Panel de administración de usuarios y permisos."""
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template(
        'auth/users_admin.html',
        users=users,
        role_labels=ROLE_LABELS,
        module_labels=MODULE_LABELS,
        all_modules=ALL_MODULES,
        role_defaults=ROLE_DEFAULTS,
    )


@auth_bp.route('/users/new', methods=['POST'])
@login_required
@permission_required('auth', 2)
def user_create():
    """Crea un nuevo usuario."""
    rut_raw = request.form.get('rut', '').strip()
    nombre = request.form.get('nombre', '').strip()
    email = request.form.get('email', '').strip().lower()
    role = request.form.get('role', 'socio')
    password = request.form.get('password', '')

    # Validaciones
    errors = []
    rut = clean_rut(rut_raw)

    if not validate_rut(rut):
        errors.append('El RUT ingresado no es válido.')
    if not nombre:
        errors.append('El nombre es obligatorio.')
    if not email or '@' not in email:
        errors.append('El correo electrónico no es válido.')
    if role not in ROLE_DEFAULTS:
        errors.append('El rol seleccionado no es válido.')
    if len(password) < 6:
        errors.append('La contraseña debe tener al menos 6 caracteres.')

    rut_fmt = format_rut(rut)

    # Verificar unicidad (buscar en todos los formatos)
    rut_dashed = rut[:-1] + '-' + rut[-1]
    existing = User.query.filter(
        (User.rut == rut_fmt) |
        (User.rut == rut_dashed) |
        (User.rut == rut)
    ).first()
    if existing:
        errors.append(f'Ya existe un usuario con RUT {rut_fmt}.')
    if User.query.filter_by(email=email).first():
        errors.append(f'Ya existe un usuario con correo {email}.')

    if errors:
        for e in errors:
            flash(e, 'error')
        return redirect(url_for('auth.users_admin'))

    user = User(
        rut=rut_fmt,
        nombre=nombre,
        email=email,
        role=role,
        permissions=ROLE_DEFAULTS[role].copy(),
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    flash(f'Usuario {nombre} ({rut_fmt}) creado exitosamente.', 'success')
    return redirect(url_for('auth.users_admin'))


@auth_bp.route('/users/<int:user_id>/permissions', methods=['POST'])
@login_required
@permission_required('auth', 2)
def user_update_permissions(user_id):
    """Actualiza los permisos individuales de un usuario."""
    user = User.query.get_or_404(user_id)

    new_permissions = {}
    for module in ALL_MODULES:
        level = request.form.get(f'perm_{module}', '0')
        try:
            new_permissions[module] = int(level)
        except (ValueError, TypeError):
            new_permissions[module] = 0

    user.permissions = new_permissions
    db.session.commit()

    flash(f'Permisos de {user.nombre} actualizados correctamente.', 'success')
    return redirect(url_for('auth.users_admin'))


@auth_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@login_required
@permission_required('auth', 2)
def user_toggle(user_id):
    """Activa o desactiva un usuario."""
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash('No puede desactivar su propia cuenta.', 'error')
        return redirect(url_for('auth.users_admin'))

    user.is_active = not user.is_active
    db.session.commit()

    estado = 'activado' if user.is_active else 'desactivado'
    flash(f'Usuario {user.nombre} {estado} correctamente.', 'success')
    return redirect(url_for('auth.users_admin'))


@auth_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@permission_required('auth', 2)
def user_reset_password(user_id):
    """Genera una nueva clave temporal para un usuario."""
    user = User.query.get_or_404(user_id)

    import secrets
    temp_password = secrets.token_urlsafe(8)
    user.set_password(temp_password)
    db.session.commit()

    flash(
        f'Clave temporal de {user.nombre}: "{temp_password}". '
        f'Comuníquesela al usuario.',
        'success',
    )
    return redirect(url_for('auth.users_admin'))


@auth_bp.route('/users/<int:user_id>/role', methods=['POST'])
@login_required
@permission_required('auth', 2)
def user_update_role(user_id):
    """Actualiza el rol de un usuario y aplica permisos por defecto."""
    user = User.query.get_or_404(user_id)
    new_role = request.form.get('role', user.role)

    if new_role not in ROLE_DEFAULTS:
        flash('Rol inválido.', 'error')
        return redirect(url_for('auth.users_admin'))

    user.role = new_role
    user.apply_role_defaults()
    db.session.commit()

    flash(
        f'Rol de {user.nombre} cambiado a '
        f'"{ROLE_LABELS.get(new_role, new_role)}" con permisos por defecto.',
        'success',
    )
    return redirect(url_for('auth.users_admin'))


# ── Utilidad interna ───────────────────────────────────────

def _is_safe_url(target: str) -> bool:
    """Verifica que la URL de redirección sea segura (mismo host)."""
    from urllib.parse import urlparse, urljoin
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return (
        test_url.scheme in ('http', 'https')
        and ref_url.netloc == test_url.netloc
    )

# ── Redirección según rol ──────────────────────────────────

def _redirect_by_role():
    """
    Redirige al usuario según su rol después del login:
    - Admin (auth >= 2)     → Panel de administración (Módulo 3)
    - Staff (cualquier permiso admin >= 1) → Panel de administración
    - Socios y otros        → Portal personal (Módulo 3)
    """
    # Admin con acceso a gestión de usuarios → panel admin
    if current_user.has_permission('auth', 2):
        return redirect(url_for('main.admin_dashboard'))

    # Staff con algún permiso de lectura o escritura → panel admin
    if (current_user.has_permission('partners', 1) or
            current_user.has_permission('readings', 1) or
            current_user.has_permission('billing', 1) or
            current_user.has_permission('pos', 1) or
            current_user.has_permission('reports', 1)):
        return redirect(url_for('main.admin_dashboard'))

    # Socio → portal personal
    return redirect(url_for('main.socio_portal'))