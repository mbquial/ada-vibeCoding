"""API REST de C4 y dependencias reemplazables en pruebas."""
from fastapi import Depends, FastAPI, HTTPException, Header
from app.models import SolicitudPedido, PedidoCreado, EventoEstado, ConfirmacionAlistamiento, Pedido
from app.repository import PedidoRepository
from app.publishers import FakeC6Disponibilidad, FakeEventPublisher
from app.service import ServicioPedidos, SolicitudInvalida, PedidoNoEncontrado
from app.state_machine import TransicionInvalida

app = FastAPI(title="Servicio de Pedidos y Pendientes (C4)", version="1.0.0")

_repo = PedidoRepository()
_c6 = FakeC6Disponibilidad({"MED-001": 100, "MED-002": 100})
_eventos = FakeEventPublisher()
_servicio = ServicioPedidos(_repo, _c6, _eventos)


def get_service() -> ServicioPedidos:
    return _servicio


def require_role(x_role: str = Header(default="operador")) -> str:
    # Demo: en producción, validar JWT/OIDC y roles contra identidad corporativa.
    if x_role not in {"operador", "auxiliar", "admin", "sistema"}:
        raise HTTPException(status_code=403, detail="Rol no autorizado")
    return x_role


@app.post("/solicitudes", response_model=PedidoCreado, status_code=201)
def crear_solicitud(
    solicitud: SolicitudPedido,
    actor: str = Depends(require_role),
    servicio: ServicioPedidos = Depends(get_service),
):
    try:
        pedidos, idempotente = servicio.crear(solicitud)
        return PedidoCreado(solicitud_id=solicitud.solicitud_id, pedidos=pedidos, idempotente=idempotente)
    except SolicitudInvalida as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/pedidos/{pedido_id}/alistamiento", response_model=Pedido)
def confirmar_alistamiento(
    pedido_id: str,
    datos: ConfirmacionAlistamiento,
    rol: str = Depends(require_role),
    servicio: ServicioPedidos = Depends(get_service),
):
    if rol not in {"auxiliar", "admin"}:
        raise HTTPException(status_code=403, detail="Solo auxiliar o admin puede confirmar alistamiento")
    try:
        return servicio.confirmar_alistamiento(pedido_id, datos)
    except PedidoNoEncontrado as exc:
        raise HTTPException(status_code=404, detail="Pedido no encontrado") from exc
    except TransicionInvalida as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/eventos/estado", response_model=Pedido)
def recibir_evento(
    evento: EventoEstado,
    rol: str = Depends(require_role),
    servicio: ServicioPedidos = Depends(get_service),
):
    try:
        return servicio.aplicar_evento(evento)
    except PedidoNoEncontrado as exc:
        raise HTTPException(status_code=404, detail="Pedido no encontrado") from exc
    except TransicionInvalida as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/pedidos/{pedido_id}/cancelar", response_model=Pedido)
def cancelar_pedido(
    pedido_id: str,
    actor: str = Header(default="operador", alias="X-Actor"),
    rol: str = Depends(require_role),
    servicio: ServicioPedidos = Depends(get_service),
):
    try:
        return servicio.cancelar(pedido_id, actor)
    except PedidoNoEncontrado as exc:
        raise HTTPException(status_code=404, detail="Pedido no encontrado") from exc
    except TransicionInvalida as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/pedidos/{pedido_id}", response_model=Pedido)
def obtener_pedido(pedido_id: str, rol: str = Depends(require_role), servicio: ServicioPedidos = Depends(get_service)):
    pedido = servicio.repositorio.obtener(pedido_id)
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return pedido


@app.get("/health")
def health():
    return {"status": "ok"}
