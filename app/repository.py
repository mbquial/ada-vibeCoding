"""Repositorio en memoria (fake de C5), protegido frente a carreras concurrentes."""
from datetime import datetime, timezone
from threading import RLock
from app.models import Pedido

class PedidoRepository:
    def __init__(self):
        self._pedidos: dict[str, Pedido] = {}
        self._por_solicitud: dict[str, list[str]] = {}
        self._auditoria: list[dict] = []
        self._lock = RLock()

    def obtener_por_solicitud(self, solicitud_id: str) -> list[Pedido] | None:
        with self._lock:
            ids = self._por_solicitud.get(solicitud_id)
            return [self._pedidos[i].model_copy(deep=True) for i in ids] if ids is not None else None

    def guardar_lote_con_resultado(self, solicitud_id: str, pedidos: list[Pedido]) -> tuple[list[Pedido], bool]:
        """Guarda el lote atómicamente. El booleano indica si esta llamada lo creó."""
        with self._lock:
            existentes = self._por_solicitud.get(solicitud_id)
            if existentes is not None:
                return [self._pedidos[i].model_copy(deep=True) for i in existentes], False
            for pedido in pedidos:
                self._pedidos[pedido.pedido_id] = pedido.model_copy(deep=True)
            self._por_solicitud[solicitud_id] = [p.pedido_id for p in pedidos]
            return [p.model_copy(deep=True) for p in pedidos], True

    def guardar_lote(self, solicitud_id: str, pedidos: list[Pedido]) -> list[Pedido]:
        """Compatibilidad con la interfaz previa del repositorio."""
        guardados, _ = self.guardar_lote_con_resultado(solicitud_id, pedidos)
        return guardados

    def obtener(self, pedido_id: str) -> Pedido | None:
        with self._lock:
            pedido = self._pedidos.get(pedido_id)
            return pedido.model_copy(deep=True) if pedido else None

    def actualizar_estado(self, pedido: Pedido, actor: str, anterior: str, detalle: str | None = None) -> Pedido:
        """Persiste el estado y registra auditoría UTC en la misma sección crítica."""
        with self._lock:
            self._pedidos[pedido.pedido_id] = pedido.model_copy(deep=True)
            self._auditoria.append({
                "id_pedido": pedido.pedido_id,
                "actor": actor,
                "fecha_hora": datetime.now(timezone.utc),
                "estado_anterior": str(anterior),
                "estado_nuevo": str(pedido.estado.value if hasattr(pedido.estado, "value") else pedido.estado),
                "detalle": detalle,
            })
            return pedido.model_copy(deep=True)

    def auditoria(self) -> list[dict]:
        with self._lock:
            return [dict(x) for x in self._auditoria]
