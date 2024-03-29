import roax.context as context
import roax.schema as s
import unittest

from base64 import b64encode
from datetime import datetime
from io import BytesIO
from roax.resource import Resource, Unauthorized, operation
from roax.security import SecurityRequirement
from roax.wsgi import App, HTTPBasicSecurityScheme
from tempfile import TemporaryDirectory
from webob import Request


class TestSecurityRequirement(SecurityRequirement):
    def __init__(self, scheme):
        self.scheme = scheme
    def authorize(self):
        ctx = context.last(context="auth")
        if not ctx or ctx["role"] != "god":
            raise Unauthorized

class TestSecurityScheme(HTTPBasicSecurityScheme):
    def authenticate(self, user_id, password):
        if user_id == "sparky" and password == "punkydoodle":
            return {"user_id": user_id, "role": "god"}

_scheme = TestSecurityScheme("WallyWorld")

http1 = TestSecurityRequirement(_scheme)

_r1_schema = s.dict(
    properties = {
        "id": s.str(),
        "foo": s.int(),
        "bar": s.bool(),
        "dt": s.datetime(),
    },
    required = {"id", "foo", "bar"},
)

class _Resource1(Resource):
    
    schema = _r1_schema
    
    @operation(
        params = {"id": _r1_schema.properties["id"], "_body": _r1_schema},
        returns = s.dict({"id": _r1_schema.properties["id"]}),
        security = [],
    )
    def create(self, id, _body):
        return {"id": id}

    @operation(
        params = {"id": _r1_schema.properties["id"], "_body": _r1_schema},
        security = [],
    )
    def update(self, id, _body):
        return

    @operation(
        type = "action",
        params = {},
        returns = s.str(format="raw"),
        security = [http1]
    )
    def foo(self):
        return "foo_success"

    @operation(
        type = "action",
        params = {"uuid": s.uuid()},
        security = [http1],
    )
    def validate_uuid(self, uuid):
        pass

    @operation(
        type = "action",
        params = {"_body": s.reader()},
        returns = s.reader(),
        security = [],
    )
    def echo(self, _body):
        return BytesIO(_body.read())

    @operation(
        type = "query",
        params = {"optional": s.str()},
        returns = s.str(),
        security = [],
    )
    def optional(self, optional="default"):
        return optional


app = App("/", "Title", "1.0")
app.register_resource("/r1", _Resource1())


class TestWSGI(unittest.TestCase):

    def test_create(self):
        request = Request.blank("/r1?id=id1")
        request.method = "POST"
        request.json = {"id": "id1", "foo": 1, "bar": True, "dt": _r1_schema.properties["dt"].json_encode(datetime.now())}
        response = request.get_response(app)
        result = response.json
        self.assertEqual(result, {"id": "id1"})
        self.assertEqual(response.status_code, 200)  # OK

    def test_update(self):
        request = Request.blank("/r1?id=id2")
        request.method = "PUT"
        request.json = {"id": "id2", "foo": 123, "bar": False}
        response = request.get_response(app)
        self.assertEqual(response.status_code, 204)  # No Content

    def test_http_req(self):
        request = Request.blank("/r1/foo")
        request.method = "POST"
        request.authorization = ("Basic", b64encode(b"sparky:punkydoodle").decode())
        response = request.get_response(app)
        self.assertEqual(response.status_code, 200)  # OK
        self.assertEqual(response.text, "foo_success")

    def test_http_validation_vs_auth_failure(self):
        request = Request.blank("/r1/validate_uuid?uuid=not-a-uuid")
        request.method = "POST"
        response = request.get_response(app)
        self.assertEqual(response.status_code, 401)  # authorization should trump validation

    def test_echo(self):
        value = b"This is an echo test."
        request = Request.blank("/r1/echo")
        request.method = "POST"
        request.body = value
        response = request.get_response(app)
        self.assertEqual(response.body, value)

    def test_static_dir(self):
        foo = "<html><body>Foo</body></html>"
        bar = b"binary"
        with TemporaryDirectory() as td:
            with open("{}/foo.html".format(td), "w") as f:
                f.write(foo)
            with open("{}/bar.bin".format(td), "wb") as f:
                f.write(bar)
            a = App("/", "Title", "1.0")
            a.register_static("/static", td, [])
            request = Request.blank("/static/foo.html")
            response = request.get_response(a)
            self.assertEqual(response.body, foo.encode())
            request = Request.blank("/static/bar.bin")
            response = request.get_response(a)
            self.assertEqual(response.body, bar)
            self.assertEqual(response.content_type, "application/octet-stream")

    def test_static_dir_index(self):
        index = "<html><body>Index</body></html>"
        with TemporaryDirectory() as td:
            with open("{}/index.html".format(td), "w") as f:
                f.write(index)
            a = App("/", "Title", "1.0")
            a.register_static("/static", td, [])
            for path in ["/static/", "/static/index.html"]:
                request = Request.blank(path)
                response = request.get_response(a)
                self.assertEqual(response.body, index.encode())
                self.assertEqual(response.content_type, "text/html")

    def test_static_file(self):
        bar = b"binary"
        with TemporaryDirectory() as td:
            filename = "{}/bar.bin".format(td)
            with open("{}/bar.bin".format(td), "wb") as f:
                f.write(bar)
            a = App("/", "Title", "1.0")
            a.register_static(filename, filename, [])
            request = Request.blank(filename)
            response = request.get_response(a)
            self.assertEqual(response.body, bar)

    def test_optional_omit(self):
        request = Request.blank("/r1/optional")
        request.method = "GET"
        response = request.get_response(app)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body.decode(), "default")

    def test_optional_submit(self):
        request = Request.blank("/r1/optional?optional=foo")
        request.method = "GET"
        response = request.get_response(app)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body.decode(), "foo")


if __name__ == "__main__":
    unittest.main()
