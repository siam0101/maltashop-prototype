# MaltaShop Prototype

A small prototype of the MaltaShop "place an order" flow, built for Unit 5:
Service-Oriented Architecture and Microservices Fundamentals.

It has two services, each with its own data store:

- **Order service** (FastAPI + PostgreSQL) accepts orders over REST and
  publishes an `OrderPlaced` event.
- **Notification service** (FastAPI + SQLite) consumes `OrderPlaced` from
  RabbitMQ and records a customer notification.

## Status

Work in progress. Run instructions will be added as the services are built.

## Environment variables

Copy the template and adjust if needed:

```bash
cp .env.example .env
```

The variables are described in `.env.example`.