from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.api import app, get_service
from app.models import (
    ConfirmacionAlistamiento, EstadoPedido, EventoEstado, ItemSolicitud,
    SolicitudPedido,
)
from app.publishers import FakeC6Disponibilidad, FakeEventPublisher
from app.repository import PedidoRepository
from app.service import ServicioPedidos
from app.state_machine import TransicionInvalida, validar_transicion


@pytest.fixture
def setup_service():
    repo = PedidoRepository()
    c6 = FakeC6Disponibilidad({"A": 10, "B": 0})
    events = FakeEventPublisher()
    now = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
    service = ServicioPedidos(repo, c6, events, reloj=lambda: now)
    return service, repo, events, now


def solicitud(items, solicitud_id="sol-1", consentimiento=True):
    return SolicitudPedido(
        solicitud_id=solicitud_id,
        documento="DOC-123",
        formula="FORM-456",
        items=items,
        direccion="Calle 1 # 2-3",
        franja="14:00-16:00",
        consentimiento=consentimiento,
    )


def test_ca_c4_01_todo_disponible_crea_listo_y_envia_c8(setup_service):
    service, _, events, _ = setup_service
    pedidos, idempotente = service.crear(solicitud([ItemSolicitud(medicamento_id="A", cantidad=2)]))
    assert idempotente is False
    assert len(pedidos) == 1
    assert pedidos[0].estado == EstadoPedido.LISTO
    assert any(e["destino"] == "C8" and e["tipo"] == "solicitar_despacho" for e in events.events)


def test_ca_c4_02_mixto_separa_inmediato_y_pendiente_con_48h(setup_service):
    service, _, _, now = setup_service
    pedidos, _ = service.crear(solicitud([
        ItemSolicitud(medicamento_id="A", cantidad=1),
        ItemSolicitud(medicamento_id="B", cantidad=1),
    ]))
    inmediato = next(p for p in pedidos if p.tipo == "inmediato")
    pendiente = next(p for p in pedidos if p.tipo == "pendiente")
    assert inmediato.estado == EstadoPedido.LISTO
    assert pendiente.estado == EstadoPedido.PENDIENTE
    assert pendiente.registrado_en.tzinfo is not None
    assert pendiente.registrado_en.utcoffset() == timedelta(0)
    assert pendiente.registrado_en == now
    assert pendiente.fecha_limite == pendiente.registrado_en + timedelta(hours=48)


def test_ca_c4_03_alistamiento_pasa_a_listo(setup_service):
    service, _, events, _ = setup_service
    pedidos, _ = service.crear(solicitud([ItemSolicitud(medicamento_id="B", cantidad=1)]))
    actualizado = service.confirmar_alistamiento(pedidos[0].pedido_id, ConfirmacionAlistamiento(actor="aux-1"))
    assert actualizado.estado == EstadoPedido.LISTO
    assert any(e["destino"] == "C8" and e["tipo"] == "solicitar_despacho" for e in events.events)


def test_idempotencia_primera_crea_y_publica_segunda_reutiliza_sin_eventos(setup_service):
    service, repo, events, _ = setup_service
    req = solicitud([ItemSolicitud(medicamento_id="A", cantidad=1)])

    primera, idem_primera = service.crear(req)
    eventos_primera = len(events.events)
    assert idem_primera is False
    assert len(primera) == 1
    assert eventos_primera == 3  # C8, C12 y C15
    assert repo.obtener_por_solicitud(req.solicitud_id) is not None

    segunda, idem_segunda = service.crear(req)
    assert idem_segunda is True
    assert [p.model_dump(mode="json") for p in segunda] == [p.model_dump(mode="json") for p in primera]
    assert len(events.events) == eventos_primera
    assert len(repo.obtener_por_solicitud(req.solicitud_id)) == 1


def test_transicion_invalida_mensaje_espanol_sin_comillas():
    with pytest.raises(TransicionInvalida) as exc:
        validar_transicion(EstadoPedido.ENTREGADO, EstadoPedido.EN_RUTA)
    assert str(exc.value) == "Transición no permitida: de Entregado a En ruta"


def test_cancelar_en_ruta_es_rechazado_sin_auditoria(setup_service):
    service, repo, _, _ = setup_service
    pedido = service.crear(solicitud([ItemSolicitud(medicamento_id="A", cantidad=1)]))[0][0]
    service.aplicar_evento(EventoEstado(pedido_id=pedido.pedido_id, nuevo_estado=EstadoPedido.ASIGNADO, actor="sistema"))
    service.aplicar_evento(EventoEstado(pedido_id=pedido.pedido_id, nuevo_estado=EstadoPedido.EN_RUTA, actor="sistema"))
    auditoria_antes = len(repo.auditoria())
    with pytest.raises(TransicionInvalida, match="Transición no permitida: de En ruta a Cancelado"):
        service.cancelar(pedido.pedido_id, "operador")
    assert len(repo.auditoria()) == auditoria_antes


def test_cancelar_desde_estado_terminal_es_rechazado(setup_service):
    service, repo, _, _ = setup_service
    pedido = service.crear(solicitud([ItemSolicitud(medicamento_id="A", cantidad=1)]))[0][0]
    service.aplicar_evento(EventoEstado(pedido_id=pedido.pedido_id, nuevo_estado=EstadoPedido.ASIGNADO, actor="sistema"))
    service.aplicar_evento(EventoEstado(pedido_id=pedido.pedido_id, nuevo_estado=EstadoPedido.EN_RUTA, actor="sistema"))
    service.aplicar_evento(EventoEstado(pedido_id=pedido.pedido_id, nuevo_estado=EstadoPedido.ENTREGADO, actor="repartidor"))
    auditoria_antes = len(repo.auditoria())
    with pytest.raises(TransicionInvalida, match="Transición no permitida: de Entregado a Cancelado"):
        service.cancelar(pedido.pedido_id, "operador")
    assert len(repo.auditoria()) == auditoria_antes


def test_auditoria_valida_con_campos_y_utc_y_sin_registro_invalido(setup_service):
    service, repo, _, _ = setup_service
    pedido = service.crear(solicitud([ItemSolicitud(medicamento_id="A", cantidad=1)]))[0][0]
    actualizado = service.aplicar_evento(EventoEstado(
        pedido_id=pedido.pedido_id, nuevo_estado=EstadoPedido.ASIGNADO, actor="operador-7"
    ))
    registros = repo.auditoria()
    assert len(registros) == 1
    registro = registros[0]
    assert registro["id_pedido"] == pedido.pedido_id
    assert registro["estado_anterior"] == "Listo para despacho"
    assert registro["estado_nuevo"] == "Asignado"
    assert registro["actor"] == "operador-7"
    assert registro["fecha_hora"].tzinfo is not None
    assert registro["fecha_hora"].utcoffset() == timedelta(0)
    assert actualizado.estado == EstadoPedido.ASIGNADO

    with pytest.raises(TransicionInvalida):
        service.aplicar_evento(EventoEstado(
            pedido_id=pedido.pedido_id, nuevo_estado=EstadoPedido.CREADO, actor="operador-7"
        ))
    assert len(repo.auditoria()) == 1


def test_consentimiento_faltante_es_error(setup_service):
    service, _, _, _ = setup_service
    with pytest.raises(ValueError, match="Se requiere consentimiento"):
        service.crear(solicitud([ItemSolicitud(medicamento_id="A", cantidad=1)], consentimiento=False))


def test_pedido_inexistente_es_error(setup_service):
    service, _, _, _ = setup_service
    with pytest.raises(LookupError, match="pedido-no-existe"):
        service.aplicar_evento(EventoEstado(
            pedido_id="pedido-no-existe", nuevo_estado=EstadoPedido.ENTREGADO, actor="sistema"
        ))


def test_api_devuelve_409_y_mensaje_claro_para_transicion_invalida(setup_service):
    service, _, _, _ = setup_service
    pedido = service.crear(solicitud([ItemSolicitud(medicamento_id="A", cantidad=1)]))[0][0]
    service.aplicar_evento(EventoEstado(pedido_id=pedido.pedido_id, nuevo_estado=EstadoPedido.ASIGNADO, actor="sistema"))
    service.aplicar_evento(EventoEstado(pedido_id=pedido.pedido_id, nuevo_estado=EstadoPedido.EN_RUTA, actor="sistema"))
    app.dependency_overrides[get_service] = lambda: service
    try:
        client = TestClient(app)
        response = client.post("/eventos/estado", json={
            "pedido_id": pedido.pedido_id,
            "nuevo_estado": "Cancelado",
            "actor": "operador",
        }, headers={"X-Role": "operador"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 409
    assert response.json()["detail"] == "Transición no permitida: de En ruta a Cancelado"


def test_api_pedido_inexistente_devuelve_404(setup_service):
    service, _, _, _ = setup_service
    app.dependency_overrides[get_service] = lambda: service
    try:
        response = TestClient(app).post("/eventos/estado", json={
            "pedido_id": "desconocido", "nuevo_estado": "Entregado", "actor": "sistema"
        })
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 404
    assert response.json()["detail"] == "Pedido no encontrado"


def test_api_consentimiento_faltante_devuelve_422(setup_service):
    service, _, _, _ = setup_service
    app.dependency_overrides[get_service] = lambda: service
    try:
        response = TestClient(app).post("/solicitudes", json={
            "solicitud_id": "sin-consentimiento", "documento": "DOC", "formula": "FORM",
            "items": [{"medicamento_id": "A", "cantidad": 1}],
            "direccion": "Calle 1", "franja": "mañana", "consentimiento": False,
        })
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422
    assert response.json()["detail"] == "Se requiere consentimiento para procesar el pedido."


def test_idempotencia_bajo_concurrencia_publica_solo_una_vez():
    from concurrent.futures import ThreadPoolExecutor

    repo = PedidoRepository()
    events = FakeEventPublisher()
    service = ServicioPedidos(repo, FakeC6Disponibilidad({"A": 10}), events)
    req = solicitud([ItemSolicitud(medicamento_id="A", cantidad=1)], solicitud_id="concurrente")

    with ThreadPoolExecutor(max_workers=8) as pool:
        resultados = list(pool.map(lambda _: service.crear(req), range(8)))

    assert all(len(pedidos) == 1 for pedidos, _ in resultados)
    assert len({pedidos[0].pedido_id for pedidos, _ in resultados}) == 1
    assert sum(1 for _, idempotente in resultados if not idempotente) == 1
    assert len(events.events) == 3
