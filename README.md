# MaltaShop Prototype

A working prototype of the MaltaShop "place an order" flow, built for Unit 5: Service-Oriented Architecture and Microservices Fundamentals (Learn Key Institute, Malta Campus).

It shows how MaltaShop's checkout could be split out of the PHP monolith into independent services that own their own data and talk through events instead of shared tables.

## What the system does

1. A client sends `POST /orders` to the **Order service**.
2. The Order service saves the order in its own **PostgreSQL** database with status `PENDING`.
3. It publishes an `OrderPlaced` event to **RabbitMQ** (topic exchange `maltashop.events`, routing key `order.placed`).
4. The **Notification service** consumes the event from its own queue and records a customer notification in its own **SQLite** database.

The two services never call each other directly. If the Notification service is down, orders still go through and the events wait in the queue.

```
Client
  |  POST /orders  (Idempotency-Key, X-Correlation-ID)
  v
Order service (FastAPI) ----> PostgreSQL (orders)
  |
  |  OrderPlaced event
  v
RabbitMQ  exchange: maltashop.events
  |  queue: notification.order-placed   (failed messages -> notification.order-placed.dlq)
  v
Notification service (FastAPI) ----> SQLite (notifications, processed_events)
```

## Features demonstrated

- Database per service (PostgreSQL for orders, SQLite for notifications)
- Asynchronous publish-subscribe messaging through RabbitMQ
- Idempotent order creation using an `Idempotency-Key` header
- Idempotent event handling using a `processed_events` table
- Dead-letter queue for messages that fail processing
- Structured JSON logs with a correlation ID carried across both services
- Separate liveness (`/health`) and readiness (`/ready`) endpoints
- Multi-stage Docker builds running as a non-root user, with health checks
- Unit, component and contract tests, plus a CI pipeline with an integration smoke test

## Prerequisites

- Docker Desktop (with Docker Compose v2)
- Git

## How to run

```bash
git clone https://github.com/siam0101/maltashop-prototype.git
cd maltashop-prototype
cp .env.example .env
docker compose up --build
```

On Windows PowerShell, use `copy .env.example .env` instead of `cp`.

Wait until the logs show `Order service started` and `Listening for events`, then open:

| What | URL |
|---|---|
| Order service API docs | http://localhost:8000/docs |
| Notification list | http://localhost:8001/notifications |
| Notification readiness | http://localhost:8001/ready |
| RabbitMQ dashboard (login from `.env`) | http://localhost:15672 |

To place an order from the command line:

```bash
curl -X POST http://localhost:8000/orders \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: demo-001" \
  -d '{"customer_id":"cust-1001","product_id":"prod-55","quantity":2,"unit_price":49.99}'
```

Sending the same request again with the same `Idempotency-Key` returns the original order with status 200 instead of creating a second one.

To stop everything, press `Ctrl + C`, or run `docker compose down`. Add `-v` to also delete the stored data.

## Environment variables

These are read from `.env` by Docker Compose. Copy `.env.example` to get started. The real `.env` file is not committed.

| Variable | Used by | Purpose | Example |
|---|---|---|---|
| `ORDER_DB_USER` | order-db, order-service | PostgreSQL user | `order_user` |
| `ORDER_DB_PASSWORD` | order-db, order-service | PostgreSQL password | `order_pass` |
| `ORDER_DB_NAME` | order-db, order-service | PostgreSQL database name | `orders` |
| `RABBITMQ_USER` | rabbitmq, both services | RabbitMQ user | `maltashop` |
| `RABBITMQ_PASSWORD` | rabbitmq, both services | RabbitMQ password | `maltashop` |
| `NOTIFICATION_DB_PATH` | notification-service | Path of the SQLite file inside the container | `/data/notifications.db` |
| `LOG_LEVEL` | both services | Minimum log level | `INFO` |

Compose builds these service-level variables from the ones above:

| Variable | Service | Purpose |
|---|---|---|
| `DATABASE_URL` | order-service | SQLAlchemy connection string for PostgreSQL |
| `RABBITMQ_URL` | both services | AMQP connection string for RabbitMQ |
| `SERVICE_NAME` | both services | Name written into every log line |

## Running the tests

The tests run inside a Python 3.12 container, so nothing needs installing locally:

```bash
docker run --rm -v ${PWD}:/repo -w /repo/order-service python:3.12-slim sh -c "pip install -q -r requirements-dev.txt && python -m pytest -v"
docker run --rm -v ${PWD}:/repo -w /repo/notification-service python:3.12-slim sh -c "pip install -q -r requirements-dev.txt && python -m pytest -v"
```

`contracts/order_placed.json` defines the shape of the `OrderPlaced` event. The Order service tests check that what it publishes matches the contract, and the Notification service tests check that it can handle it.

## CI pipeline

`.github/workflows/ci.yml` runs on every push and pull request to `main`:

1. **Test**: unit, component and contract tests for both services, in parallel
2. **Build**: one Docker image per service, tagged with the commit SHA and pushed to GitHub Container Registry on `main`
3. **Smoke test**: starts the full system with Docker Compose, places an order and checks that the notification arrives

## Project structure

```
maltashop-prototype/
├── .github/workflows/ci.yml
├── contracts/order_placed.json
├── order-service/
│   ├── app/            main.py, db.py, events.py, logging_config.py
│   ├── tests/          test_orders.py
│   ├── Dockerfile
│   ├── requirements.txt
│   └── requirements-dev.txt
├── notification-service/
│   ├── app/            main.py, db.py, consumer.py, logging_config.py
│   ├── tests/          test_consumer.py
│   ├── Dockerfile
│   ├── requirements.txt
│   └── requirements-dev.txt
├── docker-compose.yml
└── .env.example
```

## Known limitations

This is a prototype, not production code.

- Payment and Inventory services are not built. The order stays `PENDING`, where the full saga would confirm or cancel it.
- The order is saved and then the event is published as two separate steps. If RabbitMQ is down at that moment, the event is lost. A transactional outbox would close this gap.
- There is no API gateway or authentication yet.
- Credentials live in `.env` for local use only. Production would use a secrets manager.
- The smoke test rebuilds the images instead of pulling the exact images pushed in the build stage.