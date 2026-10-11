"""Casos de uso de C4."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.models import (
    ConfirmacionAlistamiento, EstadoPedido, EventoEstado, ItemPedido,
    Pedido, SolicitudPedido,
)
from app.repository import PedidoRepository
from app.publishers import FakeC6Disponibilidad, FakeEventPublisher
from app.state_machine import TransicionInvalida, validar_transicion


class SolicitudInvalida(ValueError):
    pass


class PedidoNoEncontrado(LookupError):
    pass


class ServicioPedidos:
    def __init__(
        self,
        repositorio: PedidoRepository,
        disponibilidad: FakeC6Disponibilidad,
        publicador: FakeEventPublisher,
        reloj=None,
    ):
        self.repositorio = repositorio
        self.disponibilidad = disponibilidad
        self.publicador = publicador
        self.reloj = reloj or (lambda: datetime.now(timezone.utc))

    def crear(self, solicitud: SolicitudPedido) -> tuple[list[Pedido], bool]:
        # Reenvíos comunes se resuelven antes de consultar C6. El repositorio también
        # resuelve atómicamente carreras entre solicitudes concurrentes.
        existentes = self.repositorio.obtener_por_solicitud(solicitud.solicitud_id)
        if existentes is not None:
            return existentes, True
        if not solicitud.consentimiento:
            raise SolicitudInvalida("Se requiere consentimiento para procesar el pedido.")

        stock = self.disponibilidad.consultar(solicitud.items)
        disponibles = [i for i in solicitud.items if stock[i.medicamento_id]]
        faltantes = [i for i in solicitud.items if not stock[i.medicamento_id]]
        ahora = self.reloj()  # Reloj del servidor; la solicitud no acepta fechas de cliente.
        if ahora.tzinfo is None or ahora.utcoffset() is None:
            # Los relojes inyectados en pruebas deben representar hora del servidor;
            # si son naive, se interpretan explícitamente como UTC.
            ahora = ahora.replace(tzinfo=timezone.utc)
        else:
            ahora = ahora.astimezone(timezone.utc)

        pedidos: list[Pedido] = []
        if disponibles:
            pedidos.append(self._nuevo_pedido(solicitud, disponibles, stock, ahora, "inmediato", EstadoPedido.LISTO))
        if faltantes:
            pedidos.append(self._nuevo_pedido(solicitud, faltantes, stock, ahora, "pendiente", EstadoPedido.PENDIENTE))

        # La operación atómica indica quién ganó la carrera y, por tanto, quién publica.
        guardados, creados = self.repositorio.guardar_lote_con_resultado(solicitud.solicitud_id, pedidos)
        if not creados:
            return guardados, True

        for pedido in guardados:
            if pedido.tipo == "inmediato":
                self.publicador.publicar("C8", "solicitar_despacho", pedido.model_dump(mode="json"))
            self.publicador.publicar("C12", "pedido_creado", pedido.model_dump(mode="json"))
            self.publicador.publicar("C15", "pedido_creado", pedido.model_dump(mode="json"))
        return guardados, False

    @staticmethod
    def _nuevo_pedido(solicitud, items, stock, ahora, tipo, estado):
        limite = ahora + timedelta(hours=48) if tipo == "pendiente" else None
        return Pedido(
            pedido_id=str(uuid4()),
            solicitud_id=solicitud.solicitud_id,
            tipo=tipo,
            items=[ItemPedido(medicamento_id=i.medicamento_id, cantidad=i.cantidad,
                              disponible=stock[i.medicamento_id]) for i in items],
            direccion=solicitud.direccion,
            franja=solicitud.franja,
            estado=estado,
            registrado_en=ahora,
            fecha_limite=limite,
            documento=solicitud.documento,
            formula=solicitud.formula,
            consentimiento=solicitud.consentimiento,
        )

    def confirmar_alistamiento(self, pedido_id: str, datos: ConfirmacionAlistamiento) -> Pedido:
        pedido = self._obtener(pedido_id)
        if pedido.tipo != "pendiente":
            raise TransicionInvalida("La confirmación de alistamiento solo aplica a pendientes.")
        # En un sistema real C6 se volvería a consultar antes de confirmar.
        validar_transicion(EstadoPedido(pedido.estado), EstadoPedido.LISTO)
        anterior = pedido.estado.value if hasattr(pedido.estado, "value") else pedido.estado
        pedido.estado = EstadoPedido.LISTO
        actualizado = self.repositorio.actualizar_estado(pedido, datos.actor, anterior, "Alistamiento confirmado")
        self.publicar_cambio(actualizado, datos.actor, anterior)
        self.publicador.publicar("C8", "solicitar_despacho", actualizado.model_dump(mode="json"))
        return actualizado

    def aplicar_evento(self, evento: EventoEstado) -> Pedido:
        pedido = self._obtener(evento.pedido_id)
        actual = EstadoPedido(pedido.estado)
        validar_transicion(actual, evento.nuevo_estado)
        anterior = actual.value
        pedido.estado = evento.nuevo_estado
        actualizado = self.repositorio.actualizar_estado(pedido, evento.actor, anterior, evento.detalle)
        self.publicar_cambio(actualizado, evento.actor, anterior)
        return actualizado

    def cancelar(self, pedido_id: str, actor: str) -> Pedido:
        pedido = self._obtener(pedido_id)
        return self.aplicar_evento(EventoEstado(
            pedido_id=pedido_id, nuevo_estado=EstadoPedido.CANCELADO, actor=actor
        ))

    def publicar_cambio(self, pedido: Pedido, actor: str, anterior: str):
        payload = {
            "pedido_id": pedido.pedido_id,
            "solicitud_id": pedido.solicitud_id,
            "estado_anterior": anterior,
            "estado_nuevo": pedido.estado.value if hasattr(pedido.estado, "value") else pedido.estado,
            "actor": actor,
        }
        self.publicador.publicar("C12", "cambio_estado", payload)
        self.publicador.publicar("C15", "cambio_estado", payload)

    def _obtener(self, pedido_id: str) -> Pedido:
        pedido = self.repositorio.obtener(pedido_id)
        if not pedido:
            raise PedidoNoEncontrado(pedido_id)
        return pedido
