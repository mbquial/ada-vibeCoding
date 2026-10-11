"""Máquina de estados centralizada mediante una tabla explícita."""
from app.models import EstadoPedido

TRANSICIONES_VALIDAS = {
    EstadoPedido.CREADO: {EstadoPedido.PENDIENTE, EstadoPedido.LISTO, EstadoPedido.CANCELADO},
    EstadoPedido.PENDIENTE: {EstadoPedido.LISTO, EstadoPedido.CANCELADO},
    EstadoPedido.LISTO: {EstadoPedido.ASIGNADO, EstadoPedido.CANCELADO},
    EstadoPedido.ASIGNADO: {EstadoPedido.EN_RUTA, EstadoPedido.CANCELADO},
    EstadoPedido.EN_RUTA: {EstadoPedido.ENTREGADO, EstadoPedido.FALLIDO},
    EstadoPedido.ENTREGADO: set(),
    EstadoPedido.FALLIDO: set(),
    EstadoPedido.CANCELADO: set(),
}

class TransicionInvalida(ValueError):
    """Se intentó una transición no declarada en TRANSICIONES_VALIDAS."""

def validar_transicion(actual: EstadoPedido, nuevo: EstadoPedido) -> None:
    """Lanza un error en español con nombres de estado sin comillas adicionales."""
    actual = EstadoPedido(actual)
    nuevo = EstadoPedido(nuevo)
    if nuevo not in TRANSICIONES_VALIDAS[actual]:
        raise TransicionInvalida(
            f"Transición no permitida: de {actual.value} a {nuevo.value}"
        )
