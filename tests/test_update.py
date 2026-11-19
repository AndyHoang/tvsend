from tvsend import update


class FakeContext:
    def __init__(self, cas):
        self.cas, self.loaded = cas, []

    def cert_store_stats(self):
        return {"x509_ca": self.cas}

    def load_verify_locations(self, cafile=None):
        self.loaded.append(cafile)


def test_system_certificates_are_used_when_python_has_none(tmp_path, monkeypatch):
    missing, present, later = tmp_path / "missing.pem", tmp_path / "cert.pem", tmp_path / "later.pem"
    present.write_text("")
    later.write_text("")
    ctx = FakeContext(cas=0)
    monkeypatch.setattr(update.ssl, "create_default_context", lambda: ctx)
    monkeypatch.setattr(update, "CA_FILES", (str(missing), str(present), str(later)))
    assert update.tls_context() is ctx
    assert ctx.loaded == [str(present)]


def test_python_certificates_are_left_alone(tmp_path, monkeypatch):
    present = tmp_path / "cert.pem"
    present.write_text("")
    ctx = FakeContext(cas=140)
    monkeypatch.setattr(update.ssl, "create_default_context", lambda: ctx)
    monkeypatch.setattr(update, "CA_FILES", (str(present),))
    assert update.tls_context() is ctx and ctx.loaded == []
