# 🧪 Laboratorio 3 — Implementación de Componentes con Vibe Coding

## Componente seleccionado

**Servicio de Pedidos y Pendientes (C4)**

Este repositorio contiene el prototipo del componente seleccionado del mapa de
componentes. El servicio recibe solicitudes de pedidos, consulta la
disponibilidad de los medicamentos, crea pedidos inmediatos o pendientes y
notifica a los componentes dependientes.

## 📚 Entregable 1 — Prompt inicial usado en Vibe Coding

```text
Quiero que generes el código de un componente llamado: Servicio de Pedidos y Pendientes (C4)
Tipo: Servicio
Lenguaje/Framework preferido: Python con FastAPI (pruebas con pytest)

Especificación del componente:
- Propósito: gestionar el ciclo de vida de pedidos y pendientes de medicamentos y fijar el plazo de 48 h.

- Entradas: solicitud de C1 (documento, fórmula, ítems, dirección, franja, consentimiento), disponibilidad de C6 (stock por ítem), confirmación de alistamiento del auxiliar, eventos de C10 (entregada/fallida).

- Salidas: pedido con estado persistido (C5), solicitud a C8, eventos a C12 y C15.

- Reglas de negocio:
  1. Estados válidos: Creado, Pendiente, Listo para despacho, Asignado, En ruta, Entregado, Fallido, Cancelado. Solo se permiten transiciones válidas entre ellos.
  2. El reloj de 48 h inicia con la hora del servidor (no la del cliente). Fecha límite = registro + 48 h.
  3. Una solicitud mixta (ítems con y sin stock) se divide en una entrega inmediata y un pendiente.
  4. Cancelar solo es posible antes de "En ruta".
  5. Idempotencia por ID de solicitud: reenviar la misma solicitud no crea pedidos duplicados.

- Flujo principal:
  1) Valida la solicitud.
  2) Consulta disponibilidad a C6.
  3) Crea pedido(s) y plazo.
  4) Publica eventos a C8, C12 y C15.
  5) Actualiza el estado según eventos recibidos.

- RNF clave:
  - Rendimiento: crear pedido p95 ≤ 800 ms con 50 solicitudes concurrentes.
  - Seguridad: datos cifrados en reposo (AES-256), acceso por rol, cada cambio de estado queda auditado (quién, cuándo, estado anterior y nuevo).

- Criterios de aceptación:
  CA-C4-01: Dado una solicitud con todo disponible, cuando se procesa, entonces se crea pedido "Listo para despacho" y se envía a C8.
  CA-C4-02: Dado dos ítems con uno sin stock, cuando se procesa, entonces se crea entrega inmediata y pendiente con plazo de 48 h.
  CA-C4-03: Dado un pendiente ya disponible, cuando el auxiliar confirma el alistamiento, entonces pasa a "Listo para despacho" en ≤ 5 s.

Requerimientos adicionales para el código:
- Código modular y comentado (separar: modelos, máquina de estados, servicio, repositorio, endpoints, publicador de eventos).
- Buenas prácticas de FastAPI (Pydantic, inyección de dependencias, manejo de errores HTTP).
- C5, C6 y los consumidores de eventos deben ser interfaces simuladas (mocks/fakes) para poder probar C4 de forma aislada.
- Pruebas unitarias básicas con pytest que cubran los 3 criterios de aceptación y las transiciones inválidas.
- Documentación mínima (README corto con instrucciones de ejecución).
```

## 💻 Entregable 2 — Código generado

El código generado y adaptado se encuentra en:

- `app/api.py`: endpoints REST y dependencias.
- `app/service.py`: casos de uso del servicio C4.
- `app/models.py`: modelos de entrada y salida.
- `app/state_machine.py`: transiciones permitidas.
- `app/repository.py`: persistencia en memoria y auditoría.
- `app/publishers.py`: disponibilidad y publicación de eventos simuladas.
- `tests/test_service.py`: pruebas unitarias y de API.


## 🔁 Entregable 3 — Prompt refinado

```text
El código generado tiene un problema concreto de idempotencia y necesita completar la validación de reglas y pruebas. Corrígelo manteniendo la estructura modular actual de FastAPI, servicio, repositorio, máquina de estados y pruebas.

Hallazgos confirmados en el código actual:

1. La fecha límite del pedido pendiente ya se calcula con un reloj del servidor en UTC mediante datetime.now(timezone.utc) o el reloj inyectado. Conserva este comportamiento y asegúrate de que:
   - registrado_en tenga zona horaria UTC.
   - fecha_limite sea exactamente registrado_en + 48 horas.
   - ninguna fecha del cliente pueda modificar este cálculo.
   - exista una prueba que verifique explícitamente fecha_limite == registrado_en + timedelta(hours=48).

2. Corrige la idempotencia en ServicioPedidos.crear:
   - La primera solicitud con un solicitud_id nuevo debe crear los pedidos, devolver idempotente=false y publicar los eventos correspondientes.
   - Una segunda solicitud con el mismo solicitud_id debe devolver exactamente los pedidos ya creados, devolver idempotente=true y no crear nuevos pedidos ni publicar eventos duplicados.
   - Conserva la protección del repositorio ante solicitudes concurrentes.
   - Corrige la condición actual posterior a guardar_lote, porque actualmente trata incorrectamente la primera creación como si fuera idempotente y evita la publicación inicial de eventos.
   - Agrega o ajusta una prueba que compruebe tanto el resultado de la primera llamada como el de la segunda, incluido el número de eventos publicados.

3. Mantén la máquina de estados centralizada en una tabla explícita de transiciones válidas:
   - Rechaza cualquier salto de estado no declarado.
   - Devuelve un error HTTP 409 desde la API.
   - El mensaje debe estar en español y tener el formato claro:
     "Transición no permitida: de X a Y"
     Evita depender de representaciones con comillas adicionales.
   - Cancelar debe fallar desde "En ruta" y desde cualquier estado posterior, incluyendo "Entregado", "Fallido" o "Cancelado".
   - No permitas transiciones desde estados terminales.
   - Agrega pruebas para una transición inválida, para cancelar en "En ruta" y para cancelar desde al menos un estado terminal.

4. Conserva y completa la auditoría de cambios de estado:
   - Cada transición válida debe guardar un registro con:
     id_pedido, estado_anterior, estado_nuevo, actor y fecha/hora.
   - La fecha/hora de auditoría debe ser consciente de zona horaria y estar en UTC.
   - No debe generarse auditoría cuando una transición es rechazada.
   - Agrega una prueba que verifique el contenido del registro de auditoría después de una transición válida y que confirme que no se registra una transición inválida.

5. Completa las pruebas más allá del caso feliz:
   - idempotencia: primera creación y reenvío de la misma solicitud;
   - fecha límite del pendiente igual a registro + 48 horas;
   - transición inválida;
   - cancelación en "En ruta";
   - cancelación desde un estado terminal;
   - auditoría de cambios de estado;
   - respuesta HTTP 409 y mensaje en español para una transición inválida;
   - errores de pedido inexistente y consentimiento faltante, cuando corresponda.

6. Revisa todos los mensajes de error relacionados con estas reglas:
   - Deben estar en español.
   - Deben ser claros y consistentes.
   - Las transiciones inválidas deben usar exactamente el formato:
     "Transición no permitida: de X a Y"
   - No ocultes errores ni devuelvas respuestas exitosas como fallback.

7. Actualiza la documentación directamente relacionada en README.md para que describa el comportamiento real, especialmente:
   - idempotencia en la primera y segunda solicitud;
   - cálculo UTC de la fecha límite;
   - transiciones permitidas y cancelación bloqueada desde "En ruta";
   - auditoría de cada cambio de estado;
   - cobertura de pruebas agregada.

No cambies la arquitectura general ni ejecutes migraciones innecesarias. Implementa cambios quirúrgicos, conserva las interfaces existentes cuando sea posible y entrega también las pruebas actualizadas.
```

## 💭 Entregable 4 — Reflexión breve

### ¿Qué funcionó bien en el prompt?

```text
Pegar la especificación completa de C4 en el prompt, con las reglas de negocio numeradas y los tres criterios de aceptación literales, produjo una base de código alineada con lo pedido. La separación modular que solicité (modelos, máquina de estados, servicio, repositorio, endpoints y publicador de eventos) se respetó y dejó una estructura clara y fácil de revisar. Pedir C5, C6 y los consumidores de eventos como interfaces simuladas permitió probar C4 de forma aislada. Además, la IA generó pruebas ligadas a los criterios de aceptación, lo que facilitó la validación de la Parte D. Varias reglas ya quedaron bien resueltas desde el primer intento, como el cálculo de la fecha límite con reloj del servidor en UTC y la tabla explícita de transiciones.
```

### ¿Qué tuve que mejorar?

```text
Al revisar el código encontré que la idempotencia estaba mal implementada: la condición posterior a guardar_lote trataba la primera creación como si fuera un reenvío, por lo que no se publicaban los eventos iniciales. Mi prompt original pedía “no crear duplicados”, pero no definía el comportamiento esperado en cada caso (primera llamada: idempotente=false y eventos publicados; segunda llamada: mismos pedidos, idempotente=true y sin eventos nuevos). También faltaban detalles que había dejado ambiguos: el formato exacto del mensaje de error (“Transición no permitida: de X a Y”), el código HTTP 409, el bloqueo de transiciones desde estados terminales, la auditoría solo en transiciones válidas y pruebas más allá del caso feliz. En el prompt refinado señalé los hallazgos concretos del código, indiqué qué conservar y qué corregir, y pedí cambios quirúrgicos sin alterar la arquitectura, además de actualizar el README para reflejar el comportamiento real.
```

### ¿Qué aprendí sobre cómo guiar a la IA para programar?

```text
Aprendí que el código generado hay que revisarlo y probarlo, no asumir que es correcto: un error sutil como el de la idempotencia solo apareció al leer la lógica y contrastarla con los criterios de aceptación. Un buen prompt define con precisión entradas, salidas, reglas de negocio, RNF y comportamientos esperados en cada escenario, incluidos los casos límite y los mensajes de error. Las instrucciones de refinamiento funcionan mejor cuando son puntuales: describir el problema observado, el resultado esperado y qué no tocar. También aprendí a ser honesto sobre los límites: los RNF como el cifrado AES-256 o el p95 ≤ 800 ms con 50 solicitudes concurrentes no se pueden demostrar con un prototipo en memoria ni con pruebas unitarias, y es mejor documentarlos como pendientes que afirmar que se cumplen. En conjunto, la IA acelera la generación, pero la calidad final depende de qué tan claro especifico, valido e itero.
```

## 🚀 Ejecución del proyecto

### Requisitos

- Python 3.
- Dependencias de `requirements.txt`.

### Instalación

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
```

### Iniciar la API

```bash
uvicorn app.api:app --reload
```

Documentación interactiva: <http://127.0.0.1:8000/docs>

### Ejecutar las pruebas

```bash
pytest -q
```

La suite cubre los criterios de aceptación, idempotencia, conteo de eventos,
plazo UTC de 48 horas, transiciones inválidas, cancelación en ruta y desde
estados terminales, auditoría, HTTP 409/404/422 y consentimiento faltante.

## 📋 Ejemplo de solicitud

```json
{
  "solicitud_id": "C1-0001",
  "documento": "DOC-123",
  "formula": "FORM-456",
  "items": [
    {"medicamento_id": "MED-001", "cantidad": 1},
    {"medicamento_id": "MED-002", "cantidad": 2}
  ],
  "direccion": "Calle 10 # 20-30",
  "franja": "14:00-16:00",
  "consentimiento": true
}
```

## ⚠️ Límites del prototipo

- `PedidoRepository` y `FakeEventPublisher` usan memoria; los datos se pierden
  al reiniciar. En producción se recomienda una base de datos con restricción
  única para `solicitud_id`, un patrón *transactional outbox* y coordinación
  de concurrencia distribuida. El bloqueo actual protege dentro de un solo
  proceso.
- `X-Role` es una simulación de autorización. En producción debe sustituirse
  por autenticación JWT/OIDC y autorización real.
- El cifrado AES-256 en reposo no se implementa en este fake; debe configurarse
  y verificarse en la base de datos/almacenamiento y en la gestión de claves.
- El cumplimiento de p95 ≤ 800 ms con 50 solicitudes concurrentes debe medirse
  con pruebas de carga en el entorno objetivo; no se puede inferir de las
  pruebas unitarias.
