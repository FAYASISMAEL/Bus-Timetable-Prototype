import io
import uuid
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont
from pymongo import MongoClient

from backend import config
from backend.database.connection import get_database
from backend.main import app
from backend.services.ocr_service import ocr_status
from backend.utils.errors import AppError


@pytest.fixture
def live_api(tmp_path, monkeypatch):
    mongo = MongoClient(config.MONGODB_URI, serverSelectionTimeoutMS=2000)
    try:
        mongo.admin.command('ping')
    except Exception:
        mongo.close()
        pytest.skip('Real MongoDB is unavailable; integration checks were not run.')
    name = 'smart_timetable_test_' + uuid.uuid4().hex
    db = mongo[name]
    monkeypatch.setattr(config, 'UPLOAD_DIR', tmp_path)
    app.dependency_overrides[get_database] = lambda: db
    try:
        # Keep the module's shared Mongo client alive between tests.
        client = TestClient(app, raise_server_exceptions=False)
        yield client, db
        client.close()
    finally:
        app.dependency_overrides.clear()
        mongo.drop_database(name)
        mongo.close()


def image_bytes():
    image = Image.new('RGB', (1500, 600), 'white')
    draw = ImageDraw.Draw(image)
    font_paths = ['C:/Windows/Fonts/arial.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/System/Library/Fonts/Supplemental/Arial.ttf']
    font = next((ImageFont.truetype(p, 44) for p in font_paths if Path(p).exists()), ImageFont.load_default(size=44))
    for index, cells in enumerate([('Sl. No.', 'Destination', 'Timing'), ('1', 'Ernakulam', '06:30'), ('2', 'Aluva', '07:10'), ('3', 'Thrissur', '08:30')]):
        for x, cell in zip((70, 350, 1100), cells):
            draw.text((x, 50 + 110 * index), cell, font=font, fill='black')
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    return stream.getvalue()


def test_database_unavailable_is_safe():
    def unavailable():
        raise AppError(503, 'database_unavailable', 'MongoDB is currently unavailable.')
    app.dependency_overrides[get_database] = unavailable
    try:
        response = TestClient(app).get('/api/documents')
        assert response.status_code == 503
        assert response.json()['error']['code'] == 'database_unavailable'
    finally:
        app.dependency_overrides.clear()


def test_cors_and_upload_body_limit():
    client = TestClient(app)
    response = client.options('/api/upload', headers={'Origin': 'http://localhost:5173', 'Access-Control-Request-Method': 'POST'})
    assert response.headers['access-control-allow-origin'] == 'http://localhost:5173'
    response = client.options('/api/upload', headers={'Origin': 'https://untrusted.example', 'Access-Control-Request-Method': 'POST'})
    assert 'access-control-allow-origin' not in response.headers
    response = client.post('/api/upload', content=b'', headers={'Content-Length': str(config.MAX_UPLOAD_BYTES + 100000)})
    assert response.status_code == 413


def test_vercel_upload_preflight_and_error_response_cors(monkeypatch):
    origin = 'https://bus-timetable-prototype-ry6l-ten.vercel.app'
    from fastapi.middleware.cors import CORSMiddleware
    middleware = next(item for item in app.user_middleware if item.cls is CORSMiddleware)
    # Exercise the real upload route and middleware without depending on a local .env.
    try:
        with monkeypatch.context() as context:
            context.setitem(middleware.kwargs, 'allow_origins', [origin])
            context.setitem(app.dependency_overrides, get_database, lambda: None)
            app.middleware_stack = None
            client = TestClient(app)
            response = client.options('/api/upload', headers={
                'Origin': origin, 'Access-Control-Request-Method': 'POST',
                'Access-Control-Request-Headers': 'content-type'})
            assert response.status_code == 200
            assert response.headers['access-control-allow-origin'] == origin
            response = client.post('/api/upload', headers={'Origin': origin})
            assert response.status_code == 422
            assert response.headers['access-control-allow-origin'] == origin
            denied = client.options('/api/upload', headers={
                'Origin': 'https://another-project.vercel.app', 'Access-Control-Request-Method': 'POST'})
            assert denied.status_code == 400 and 'access-control-allow-origin' not in denied.headers
            client.close()
    finally:
        app.middleware_stack = None


@pytest.mark.integration
def test_upload_validation_and_cleanup(live_api):
    client, db = live_api
    cases = [('bad.txt', b'hello', 'text/plain', 415), ('empty.png', b'', 'image/png', 422),
             ('bad.png', b'broken', 'image/png', 422), ('bad.pdf', b'%PDF-1.0\nbroken', 'application/pdf', 422),
             ('bad.jpg', image_bytes(), 'image/jpeg', 415)]
    for name, payload, mime, status in cases:
        response = client.post('/api/upload', files={'file': (name, payload, mime)})
        assert response.status_code == status, response.text
        assert 'error' in response.json()
    assert not list(config.UPLOAD_DIR.glob('staging-*'))
    assert db.documents.count_documents({}) == 0
    assert client.get('/api/documents/not-an-id').status_code == 400


@pytest.mark.integration
def test_real_upload_ocr_edit_save_export_reprocess_delete(live_api):
    client, db = live_api
    if not ocr_status()['ready']:
        pytest.skip('Both real eng and mal Tesseract packs are required for this test.')
    response = client.post('/api/upload', files={'file': ('../../schedule.png', image_bytes(), 'image/png')})
    assert response.status_code == 201, response.text
    document = response.json()
    assert document['original_filename'] == 'schedule.png'
    assert client.get(f"/api/documents/{document['_id']}/source").status_code == 200
    response = client.post(f"/api/process/{document['_id']}")
    assert response.status_code == 201, response.text
    timetable = response.json()
    assert any(row['timing'] == '06:30' for row in timetable['entries']), timetable
    assert 'Aluva' in timetable['raw_ocr_text']
    payload = {key: timetable[key] for key in ['entries', 'revision']}
    payload['entries'][0].update(destination='ആലുവ', reviewed=True)
    response = client.put(f"/api/timetables/{timetable['_id']}", json=payload)
    assert response.status_code == 200, response.text
    assert response.json()['revision'] == 2
    assert response.json()['entries'][0]['destination'] == 'ആലുവ'
    assert client.put(f"/api/timetables/{timetable['_id']}", json=payload).status_code == 409
    exported = client.get(f"/api/timetables/{timetable['_id']}/export/json")
    assert exported.json()['entries'][0]['destination'] == 'ആലുവ'
    csv = client.get(f"/api/timetables/{timetable['_id']}/export/csv")
    assert csv.content.startswith(b'\xef\xbb\xbf')
    assert 'ആലുവ' in csv.content.decode('utf-8-sig')
    again = client.post(f"/api/process/{document['_id']}")
    assert again.status_code == 201
    assert again.json()['_id'] != timetable['_id']
    assert client.get(f"/api/timetables/{timetable['_id']}").json()['status'] == 'saved'
    assert client.delete(f"/api/timetables/{again.json()['_id']}").status_code == 200
    assert client.delete(f"/api/documents/{document['_id']}").status_code == 200
    assert db.timetables.count_documents({}) == 0
    assert not list(config.UPLOAD_DIR.iterdir())


@pytest.mark.integration
def test_pdf_pages_and_password_rejection(live_api):
    client, db = live_api
    with pymupdf.open() as pdf:
        for _ in range(2):
            page = pdf.new_page(width=750, height=300)
            page.insert_image(page.rect, stream=image_bytes())
        data = pdf.tobytes()
        encrypted = pdf.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw='secret', owner_pw='owner')
    response = client.post('/api/upload', files={'file': ('locked.pdf', encrypted, 'application/pdf')})
    assert response.status_code == 422
    response = client.post('/api/upload', files={'file': ('two-pages.pdf', data, 'application/pdf')})
    assert response.status_code == 201, response.text
    document_id = response.json()['_id']
    assert response.json()['page_count'] == 2
    if ocr_status()['ready']:
        result = client.post(f'/api/process/{document_id}')
        assert result.status_code == 201, result.text
        assert {row['page'] for row in result.json()['entries']} == {1, 2}
    else:
        assert client.post(f'/api/process/{document_id}').status_code == 503


@pytest.mark.integration
def test_real_malayalam_glyph_recognition(live_api, monkeypatch):
    monkeypatch.setattr(config, "OCR_LANGUAGE", "eng+mal")
    client, _ = live_api
    if not ocr_status()['ready']:
        pytest.skip('Both Tesseract language packs are required.')
    fonts = [Path('C:/Windows/Fonts/Nirmala.ttc'),
             Path('/usr/share/fonts/truetype/noto/NotoSansMalayalam-Regular.ttf')]
    font = next((path for path in fonts if path.exists()), None)
    if font is None:
        pytest.skip('A Malayalam font is required to render the real OCR fixture.')
    # MuPDF HTML uses HarfBuzz shaping, so conjuncts render correctly even if
    # the platform's Pillow build has no libraqm support.
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=700, height=240)
        page.insert_htmlbox(page.rect, '<table><tr><td>Sl. No.</td><td>Destination</td><td>Timing</td></tr><tr><td>1</td><td>ആലുവ</td><td>07:10</td></tr><tr><td>2</td><td>Aluva</td><td>08:30</td></tr></table>',
                            css=f"@font-face {{font-family: mal; src: url('{font.name}');}} body {{font-family: mal; font-size: 24px; margin: 20px;}}",
                            archive=pymupdf.Archive(str(font.parent)))
        payload = page.get_pixmap(matrix=pymupdf.Matrix(2, 2)).tobytes('png')
    response = client.post('/api/upload', files={'file': ('malayalam.png', payload, 'image/png')})
    assert response.status_code == 201, response.text
    result = client.post(f"/api/process/{response.json()['_id']}")
    assert result.status_code == 201, result.text
    assert 'ആലുവ' in result.json()['raw_ocr_text'], result.json()['raw_ocr_text']
    assert any(row['timing'] == '07:10' for row in result.json()['entries'])
