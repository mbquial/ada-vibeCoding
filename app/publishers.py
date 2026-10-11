"""Publicador simulado para C8, C12 y C15."""
from typing import Any


class FakeEventPublisher:
    def __init__(self):
        self.events: list[dict[str, Any]] = []

    def publicar(self, destino: str, tipo: str, payload: dict) -> None:
        # En producción: outbox transaccional + broker (p. ej. RabbitMQ/Kafka).
        self.events.append({"destino": destino, "tipo": tipo, "payload": payload})


class FakeC6Disponibilidad:
    """Fake de C6: mapa medicamento_id -> stock disponible."""
    def __init__(self, stock: dict[str, int] | None = None):
        self.stock = stock or {}

    def consultar(self, items) -> dict[str, bool]:
        return {item.medicamento_id: self.stock.get(item.medicamento_id, 0) >= item.cantidad for item in items}
