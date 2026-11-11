"""API clients must not receive login HTML or HTML error pages."""
import importlib.util
import unittest
from pathlib import Path

from flask import Flask, jsonify, redirect

_SPEC = importlib.util.spec_from_file_location(
    "api_json_errors",
    Path(__file__).resolve().parents[1] / "utils" / "api_json_errors.py",
)
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
rewrite_api_html_response = _MODULE.rewrite_api_html_response


def _app():
    app = Flask(__name__)
    app.config["PROPAGATE_EXCEPTIONS"] = False

    @app.after_request
    def _rewrite_with_path(response):
        from flask import request
        return rewrite_api_html_response(request.path, response)

    @app.route("/api/ok")
    def ok():
        return jsonify({"success": True, "data": []})

    @app.route("/api/needs-login")
    def needs_login():
        return redirect("/login")

    @app.route("/api/boom")
    def boom():
        raise RuntimeError("database unavailable")

    @app.route("/login")
    def login_page():
        return "<!DOCTYPE html><html><title>Sign In</title><body>Sign In</body></html>", 200

    @app.route("/api/html-login")
    def html_login():
        return "<!DOCTYPE html><html><title>Sign In</title><body class=\"login-page\">Sign In</body></html>", 200

    @app.route("/api/forbidden.json")
    def forbidden_json():
        return jsonify({"success": False, "error": "Admin access required"}), 403

    @app.route("/api/missing.json")
    def missing_json():
        return jsonify({"success": False, "error": "Purchase request not found"}), 404

    @app.route("/api/failed.json")
    def failed_json():
        return jsonify({"success": False, "error": "database unavailable"}), 500

    @app.route("/api/forbidden.html")
    def forbidden_html():
        body = "<!DOCTYPE html><html><title>Forbidden</title><body>Sign In at /login</body></html>"
        return body, 403

    @app.route("/api/missing.html")
    def missing_html():
        return "<!DOCTYPE html><html><title>Not Found</title><body>/login</body></html>", 404

    @app.route("/api/failed.html")
    def failed_html():
        body = "<!DOCTYPE html><html><title>Error</title><body>redirect('/login') Sign In</body></html>"
        return body, 500

    @app.route("/php/getOrdersByStatus.php")
    def php_json():
        return jsonify({"success": False, "error": "Not authenticated"}), 401

    @app.route("/logout")
    def logout():
        return redirect("/login")

    @app.route("/admin/procurement")
    def page():
        return "<!DOCTYPE html><html><title>Procurement</title></html>", 200

    return app


class ApiJsonErrorTests(unittest.TestCase):
    def setUp(self):
        self.client = _app().test_client()

    def test_json_success_is_unchanged(self):
        response = self.client.get("/api/ok")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["success"], True)

    def test_login_redirect_becomes_json_401(self):
        response = self.client.get("/api/needs-login")
        self.assertEqual(response.status_code, 401)
        body = response.get_json()
        self.assertEqual(body["success"], False)
        self.assertIn("Session expired", body["error"])
        self.assertFalse((response.get_data(as_text=True) or "").lstrip().startswith("<"))

    def test_unhandled_api_exception_is_json(self):
        response = self.client.get("/api/boom")
        self.assertEqual(response.status_code, 500)
        body = response.get_json()
        self.assertIsNotNone(body)
        self.assertEqual(body["success"], False)
        self.assertNotIn("<!DOCTYPE", response.get_data(as_text=True))

    def test_api_login_html_becomes_json_401(self):
        response = self.client.get("/api/html-login")
        self.assertEqual(response.status_code, 401)
        self.assertIn("Session expired", response.get_json()["error"])

    def test_json_403_stays_permission_error(self):
        response = self.client.get("/api/forbidden.json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "Admin access required")

    def test_json_404_stays_original_error(self):
        response = self.client.get("/api/missing.json")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"], "Purchase request not found")

    def test_json_500_stays_original_error(self):
        response = self.client.get("/api/failed.json")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json()["error"], "database unavailable")

    def test_html_403_is_not_session_expired(self):
        response = self.client.get("/api/forbidden.html")
        self.assertEqual(response.status_code, 403)
        body = response.get_json()
        self.assertIn("permission", body["error"].lower())
        self.assertNotIn("Session expired", body["error"])

    def test_html_404_names_missing_endpoint(self):
        response = self.client.get("/api/missing.html")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"], "API endpoint not found.")

    def test_html_500_is_not_session_expired(self):
        response = self.client.get("/api/failed.html")
        self.assertEqual(response.status_code, 500)
        body = response.get_json()
        self.assertNotIn("Session expired", body["error"])
        self.assertNotIn("<!DOCTYPE", response.get_data(as_text=True))

    def test_php_json_401_keeps_original_body(self):
        response = self.client.get("/php/getOrdersByStatus.php")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"], "Not authenticated")

    def test_page_logout_redirect_stays_redirect(self):
        response = self.client.get("/logout")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers.get("Location", ""))

    def test_html_pages_stay_html(self):
        response = self.client.get("/admin/procurement")
        self.assertEqual(response.status_code, 200)
        self.assertIn("<!DOCTYPE html>", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
