"""
Módulo 2 – Servicio de Autenticación.
Decorador @permission_required y utilidades de sesión.
"""

from functools import wraps
from flask import flash, redirect, url_for, request
from flask_login import current_user


def permission_required(module: str, min_level: int = 1):
    """
    Decorador que valida si el usuario autenticado tiene
    al menos min_level de permiso en el módulo indicado.

    Uso:
        @permission_required('readings', 2)
        def capture_readings():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Verificar autenticación
            if not current_user.is_authenticated:
                flash('Debe iniciar sesión para acceder.', 'warning')
                return redirect(url_for('auth.login', next=request.url))

            # Verificar nivel de permiso
            if not current_user.has_permission(module, min_level):
                flash(
                    'No tiene permisos suficientes para acceder a esta sección.',
                    'error',
                )
                return redirect(url_for('dashboard.index'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator