import unittest

from fastapi.testclient import TestClient

from backend.main import app


class TestHealthEndpoint(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health_ok(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "ok", "service": "TraceUPI API"},
        )

    def test_health_rejects_unknown_fields_in_response_model(self) -> None:
        payload = self.client.get("/health").json()
        self.assertEqual(set(payload.keys()), {"status", "service"})


if __name__ == "__main__":
    unittest.main()
