from fastapi import FastAPI

app = FastAPI(title="MaltaShop Order Service", version="0.1.0")


@app.get("/health")
def health():
    """Used by Docker (and later Kubernetes) to check the service is alive."""
    return {"status": "ok", "service": "order-service"}