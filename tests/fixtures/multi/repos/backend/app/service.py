"""Backend service for the multi-repo fixture."""


class Service:
    """A trivial service with one operation."""

    def handle(self, request: dict) -> dict:
        """Handle a request and echo its payload."""
        return {"ok": True, "echo": request}


def build_service() -> Service:
    return Service()
