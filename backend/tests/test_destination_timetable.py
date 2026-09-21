import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pymupdf
import pytest

from backend import config
from backend.services.image_processor import remove_table_grid
from backend.services.ocr_service import extract_tokens, ocr_status
from backend.services.pdf_processor import detect_pdf_mode, extract_pdf_pages
from backend.services.timetable_parser import parse_destination_timetable
from backend.tests.test_api import live_api

SAMPLE = Path(__file__).resolve().parents[1] / 'uploads/6ab0e5cd1bdf536b2bc5f00a.pdf'
EXPECTED = [('Thrissur', '06:30'), ('Aluva', '07:15'), ('Ernakulam', '07:45'),
            ('Angamaly', '08:10'), ('Chalakudy', '08:40'), ('Kottayam', '09:15'),
            ('Thrissur', '10:00'), ('Alappuzha', '10:45'), ('Kakkanad', '11:30'),
            ('Ernakulam', '12:15'), ('Thrissur', '13:00'), ('Aluva', '13:45'),
            ('Angamaly', '14:30'), ('Chalakudy', '15:15'), ('Kottayam', '16:00'),
            ('Ernakulam', '16:45'), ('Thrissur', '17:20'), ('Aluva', '18:00'),
            ('Kakkanad', '18:45'), ('Ernakulam', '19:30')]
FIXTURES = Path(__file__).parent / 'fixtures'


def word(text, x, y, page=1, width=None, confidence=95):
    return {'text': text, 'page': page, 'confidence': confidence,
            'bounding_box': {'left': x, 'top': y, 'width': width or len(text) * 5, 'height': 10}}


def headers(label='Sl. No.', y=20, page=1):
    return [word(label, 30, y, page), word('Destination', 130, y, page), word('Timing', 400, y, page)]


def parse(words, count=1, **kwargs):
    return parse_destination_timetable(words, [{'page': i, 'width': 600, 'mode': 'DIRECT_TEXT', 'text': ''}
                                              for i in range(1, count + 1)], **kwargs)


@pytest.mark.parametrize('label', ['Sl. No.', 'Sl No', 'S.No', 'SI No', 'Serial No'])
def test_headers_and_coordinate_sorting(label):
    words = [word('Ignore this route - heading', 30, 0)] + headers(label)
    words += [word('2', 30, 60), word('ALUVA', 130, 61), word('7.15', 400, 59),
              word('1', 30, 90), word('Ernakulam', 130, 89), word('6:30', 400, 90)]
    result = parse(list(reversed(words)))
    assert [(e['sl_no'], e['destination'], e['timing']) for e in result['entries']] == [(1, 'Ernakulam', '06:30'), (2, 'ALUVA', '07:15')]
    assert all(not e['needs_review'] for e in result['entries'])
    assert result['origin'] is result['route_name'] is result['destination_route'] is None


@pytest.mark.parametrize('label', ['Bus Stop', 'Stop', 'Stop Name', 'Bus Stop Name'])
def test_stop_header_aliases_with_separate_words(label):
    words = [word('Sl.', 30, 20), word('No.', 50, 20), word('Time', 400, 20)]
    x = 130
    for part in label.split():
        words.append(word(part, x, 20))
        x += len(part) * 5 + 5
    words += [word('35', 30, 40), word('Kizhakkambalam', 130, 40), word('Market', 205, 40), word('05:41', 400, 40)]
    result = parse(words)
    assert not result['needs_review']
    assert result['entries'][0]['destination'] == 'Kizhakkambalam Market'
    assert result['entries'][0]['timing'] == '05:41'


def test_explicit_note_is_retained_as_source_but_not_an_empty_entry():
    words = headers() + [word('1', 30, 40), word('Aluva', 130, 40), word('06:18', 400, 40),
                         word('Note:', 10, 70), word('Check with operator.', 130, 70)]
    result = parse(words)
    assert len(result['entries']) == 1 and not result['needs_review']
    assert result['unparsed_lines'][0]['kind'] == 'source_note'
    assert result['unparsed_lines'][0]['text'] == 'Note: Check with operator.'
    # A cell beginning with Note: must never cause its anchored row to disappear.
    result = parse(headers() + [word('1', 30, 40), word('Note:', 130, 40), word('06:18', 400, 40)])
    assert len(result['entries']) == 1 and result['entries'][0]['destination'] == 'Note:'


def test_perumbavoor_pdf_all_66_rows_and_repeated_bus_stop_headers():
    with patch.object(pymupdf.Page, 'get_pixmap', side_effect=AssertionError('Do not OCR this digital PDF')):
        pages = list(extract_pdf_pages(FIXTURES / 'perumbavoor-to-aluva.pdf'))
    result = parse_destination_timetable([word for page in pages for word in page['tokens']], pages)
    expected = json.loads((FIXTURES / 'perumbavoor-to-aluva.expected.json').read_text(encoding='utf-8'))
    assert [{key: row[key] for key in ('sl_no', 'destination', 'timing')} for row in result['entries']] == expected
    assert [row['sl_no'] for row in result['entries']] == list(range(1, 67))
    assert [sum(row['page'] == page for row in result['entries']) for page in (1, 2)] == [34, 32]
    assert all(len(page['headers']) == 1 for page in pages)
    assert result['extraction_method'] == 'DIRECT_TEXT' and not result['needs_review']
    assert result['warnings'] == [] and len(result['unparsed_lines']) == 1
    assert result['route_name'] is result['origin'] is result['destination_route'] is None


@pytest.mark.integration
def test_perumbavoor_upload_process_and_export(live_api):
    client, _ = live_api
    response = client.post('/api/upload', files={'file': ('Perumbavoor_to_Aluva_All_Stops.pdf',
                           (FIXTURES / 'perumbavoor-to-aluva.pdf').read_bytes(), 'application/pdf')})
    assert response.status_code == 201, response.text
    with patch('backend.services.processing.extract_tokens', side_effect=AssertionError('No OCR')):
        response = client.post(f"/api/process/{response.json()['_id']}")
    assert response.status_code == 201, response.text
    timetable = response.json()
    assert len(timetable['entries']) == 66 and not timetable['needs_review']
    assert timetable['entries'][36]['destination'] == 'Twenty 20 Nagar'
    assert timetable['entries'][36]['timing'] == '05:43'
    assert timetable['entries'][62]['destination'] == 'Aluva KSRTC'
    assert timetable['entries'][62]['timing'] == '06:15'
    exported = client.get(f"/api/timetables/{timetable['_id']}/export/json").json()
    assert exported['entries'] == timetable['entries']


def test_missing_cells_never_borrow_from_neighbor_and_keep_raw_boxes():
    words = headers() + [word('1', 30, 40), word('Ernakulam', 130, 40),
                         word('2', 30, 60), word('Aluva', 130, 60), word('8:30 PM', 400, 60),
                         word('3', 30, 80), word('25:90', 400, 80)]
    entries = parse(words)['entries']
    assert entries[0]['timing'] is None and entries[0]['needs_review']
    assert entries[1]['timing'] == '20:30' and not entries[1]['needs_review']
    assert entries[2]['destination'] == '' and entries[2]['timing'] is None
    assert entries[2]['original_time'] == '25:90'
    assert entries[0]['source_words'] and entries[0]['bounding_box']['top'] == 40


def test_wrong_columns_are_never_reinterpreted():
    entries = parse(headers() + [word('1', 30, 40), word('06:30', 130, 40), word('Ernakulam', 400, 40)])['entries']
    assert entries[0]['destination'] == '06:30'
    assert entries[0]['timing'] is None and entries[0]['needs_review']


def test_duplicate_anchors_and_rows_are_flagged_including_across_pages():
    words = headers() + [word('1', 30, 40), word('Aluva', 130, 40), word('06:30', 400, 40)]
    words += headers(page=2) + [word('1', 30, 40, 2), word('Aluva', 130, 40, 2), word('06:30', 400, 40, 2)]
    for entry in parse(words, count=2)['entries']:
        assert 'Duplicate row anchor' in entry['issues'] and 'Duplicate row' in entry['issues']


def test_repeated_headers_and_missing_or_damaged_headers():
    words = headers() + [word('1', 30, 40), word('Aluva', 130, 40), word('6:30', 400, 40)]
    words += headers(y=60) + [word('2', 30, 80), word('Thrissur', 130, 80), word('7:30', 400, 80)]
    assert len(parse(words)['entries']) == 2
    entries = parse(words[3:6])['entries']
    assert entries[0]['destination'] == '' and entries[0]['timing'] is None
    assert entries[0]['raw_text'] == '1 Aluva 6:30' and entries[0]['needs_review']
    entries = parse(headers() + [word('?', 30, 40), word('Aluva', 130, 40), word('6:30', 400, 40)])['entries']
    assert entries[0]['sl_no'] is None and entries[0]['needs_review']
    assert entries[0]['destination'] == '' and entries[0]['timing'] is None
    assert entries[0]['raw_text'] == '? Aluva 6:30'


def test_y_tolerance_does_not_shift_off_row_time(caplog):
    words = headers() + [word('1', 30, 40), word('Ernakulam', 130, 40), word('06:30', 400, 47)]
    with caplog.at_level('INFO'):
        result = parse(words, y_tolerance=3, debug=True)
    assert result['entries'][0]['timing'] is None
    assert result['entries'][1]['sl_no'] is None and result['entries'][1]['timing'] is None
    assert 'SL: 1 DESTINATION: Ernakulam TIME: None' in caplog.text
    assert result['entries'][1]['source_words'][0]['text'] == '06:30'


def test_crossing_column_boundary_does_not_truncate_name():
    entry = parse(headers() + [word('1', 30, 40), word('Long destination', 130, 40, width=260), word('06:30', 400, 40)])['entries'][0]
    assert entry['destination'] == '' and entry['needs_review']
    assert 'Long destination' in entry['raw_text']


def test_page_modes_and_existing_pdf_no_render_or_ocr():
    assert detect_pdf_mode('', []) == 'OCR_FALLBACK'
    assert detect_pdf_mode('\ufffd\ufffd\ufffd', [word('\ufffd', 0, 0)]) == 'OCR_FALLBACK'
    if not SAMPLE.exists():
        pytest.skip('Local uploaded sample is absent.')
    with patch.object(pymupdf.Page, 'get_pixmap', side_effect=AssertionError('Digital PDF must not render')):
        pages = list(extract_pdf_pages(SAMPLE))
    result = parse_destination_timetable([w for page in pages for w in page['tokens']], pages)
    assert result['extraction_method'] == 'DIRECT_TEXT'
    assert [(e['destination'], e['timing']) for e in result['entries']] == EXPECTED
    assert [e['sl_no'] for e in result['entries']] == list(range(1, 21))


def test_english_ocr_does_not_require_malayalam(monkeypatch):
    monkeypatch.setattr('backend.services.ocr_service.ocr_status', lambda: {'ready': True, 'malayalam_available': False})
    with patch('backend.services.ocr_service.pytesseract.image_to_data', return_value={'text': []}) as engine:
        extract_tokens(np.full((40, 40), 255, dtype=np.uint8), 1)
    assert engine.call_args.kwargs['lang'] == 'eng'


def test_clean_page_is_not_grid_processed():
    gray = np.full((100, 100), 240, dtype=np.uint8)
    clean, changed = remove_table_grid(gray)
    assert not changed and np.array_equal(clean, gray)


@pytest.mark.integration
def test_existing_pdf_upload_edit_export_without_tesseract(live_api):
    client, _ = live_api
    if not SAMPLE.exists():
        pytest.skip('Local uploaded sample is absent.')
    uploaded = client.post('/api/upload', files={'file': ('existing.pdf', SAMPLE.read_bytes(), 'application/pdf')})
    assert uploaded.status_code == 201, uploaded.text
    with patch('backend.services.processing.extract_tokens', side_effect=AssertionError('OCR forbidden')):
        response = client.post(f"/api/process/{uploaded.json()['_id']}")
    assert response.status_code == 201, response.text
    result = response.json()
    assert [(e['destination'], e['timing']) for e in result['entries']] == EXPECTED
    assert result['extraction_method'] == 'DIRECT_TEXT' and result['pages'][0]['headers']
    assert result['route_name'] is result['origin'] is result['destination_route'] is None
    rows = list(reversed(result['entries']))
    rows[0]['timing'] = 'bad time'
    saved = client.put(f"/api/timetables/{result['_id']}", json={'entries': rows, 'revision': result['revision']})
    assert saved.status_code == 200, saved.text
    assert saved.json()['entries'][-1]['timing'] is None
    assert saved.json()['entries'][-1]['needs_review']
    assert [e['sl_no'] for e in saved.json()['entries']] == list(range(1, 21))
    assert saved.json()['entries'][2]['source_words'] == result['entries'][2]['source_words']
    exported = client.get(f"/api/timetables/{result['_id']}/export/csv")
    assert exported.text.lstrip('\ufeff').splitlines()[0] == 'destination,timing,confidence,needs_review,issues'


@pytest.mark.integration
def test_mixed_pdf_uses_english_ocr_only_for_scanned_page(live_api):
    client, _ = live_api
    if not SAMPLE.exists() or not ocr_status()['ready']:
        pytest.skip('Local PDF and English OCR are required.')
    with pymupdf.open(SAMPLE) as source, pymupdf.open() as mixed:
        mixed.insert_pdf(source)
        page = mixed.new_page(width=source[0].rect.width, height=source[0].rect.height)
        page.insert_image(page.rect, stream=source[0].get_pixmap(matrix=pymupdf.Matrix(3, 3)).tobytes('png'))
        data = mixed.tobytes()
    uploaded = client.post('/api/upload', files={'file': ('mixed.pdf', data, 'application/pdf')})
    with patch('backend.services.processing.extract_tokens', wraps=extract_tokens) as engine:
        response = client.post(f"/api/process/{uploaded.json()['_id']}")
    assert response.status_code == 201, response.text
    result = response.json()
    assert engine.call_count == 1 and engine.call_args.kwargs['language'] == 'eng'
    assert result['extraction_method'] == 'MIXED'
    assert [p['mode'] for p in result['pages']] == ['DIRECT_TEXT', 'OCR_FALLBACK']
    for page in (1, 2):
        assert [(e['destination'], e['timing']) for e in result['entries'] if e['page'] == page] == EXPECTED
