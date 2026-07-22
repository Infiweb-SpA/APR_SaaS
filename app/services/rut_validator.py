"""
Módulo 2 – Validación de RUT chileno.
Algoritmo módulo 11 para verificar dígito verificador.
"""

import re


def clean_rut(rut: str) -> str:
    """Elimina puntos, guion y espacios. Retorna solo dígitos + DV."""
    return re.sub(r'[^0-9kK]', '', rut).upper().strip()


def format_rut(rut: str) -> str:
    """
    Formatea un RUT limpio al formato XX.XXX.XXX-K.
    Si el RUT es inválido, retorna el valor original.
    """
    cleaned = clean_rut(rut)
    if len(cleaned) < 2:
        return rut

    body = cleaned[:-1]
    dv = cleaned[-1]

    # Agregar puntos de miles
    formatted = ''
    for i, digit in enumerate(reversed(body)):
        if i > 0 and i % 3 == 0:
            formatted = '.' + formatted
        formatted = digit + formatted

    return f'{formatted}-{dv}'


def calculate_dv(body: str) -> str:
    """
    Calcula el dígito verificador esperado para el cuerpo numérico del RUT.
    Algoritmo módulo 11 con factores 2,3,4,5,6,7 (cíclicos, derecha a izquierda).
    """
    total = 0
    factor = 2
    for digit in reversed(body):
        total += int(digit) * factor
        factor = factor + 1 if factor < 7 else 2

    remainder = total % 11
    result = 11 - remainder

    if result == 11:
        return '0'
    elif result == 10:
        return 'K'
    else:
        return str(result)


def validate_rut(rut: str) -> bool:
    """
    Valida un RUT chileno completo (cuerpo + dígito verificador).
    Acepta formatos: 12345678-9, 12.345.678-9, 123456789.
    Retorna True si el dígito verificador es correcto.
    """
    cleaned = clean_rut(rut)

    if len(cleaned) < 2:
        return False

    body = cleaned[:-1]
    dv = cleaned[-1]

    if not body.isdigit():
        return False

    if len(body) < 7 or len(body) > 8:
        return False

    expected = calculate_dv(body)
    return dv == expected