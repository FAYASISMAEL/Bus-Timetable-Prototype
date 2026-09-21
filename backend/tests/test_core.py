import re

import numpy as np
import pytest
from PIL import Image

from backend.services.image_processor import preprocess_image, read_image
from backend.services.ocr_service import tokens_to_lines
from backend.services.timetable_parser import normalize_time, parse_timetable
from backend.services.validator import normalize_stop, validate_stops
from backend.utils.errors import AppError
from backend.utils.files import inspect_upload, sanitize_filename, validate_filename
from backend.routes.timetables import spreadsheet_safe


@pytest.mark.parametrize('value,expected', [
    ('06:30', '06:30'), ('6:30', '06:30'), ('07.15', '07:15'), ('7.15', '07:15'),
    ('18:40', '18:40'), ('8:30 AM', '08:30'), ('08:30 PM', '20:30'),
    ('12:00 AM', '00:00'), ('12:00 PM', '12:00'), ('8:30 p.m.', '20:30'),
    ('24:00', None), ('12:60', None), ('00:30 AM', None), ('13:30 PM', None),
    ('18:40 junk', None), ('123:00', None), ('8:3', None),
])
def test_time_formats(value, expected):
    assert normalize_time(value) == expected


def test_text_without_geometry_never_infers_routes_or_rows():
    result = parse_timetable([{'text': 'ERNAKULAM - Thrissur 06:30', 'confidence': 90, 'page': 1}])
    assert result['route_name'] is None
    assert result['origin'] is None
    assert result['destination_route'] is None
    assert result['entries'] == []
    assert result['needs_review']
    assert 'ERNAKULAM' in result['raw_ocr_text']


def test_validation_never_drops_data_and_review_does_not_clear_invalidity():
    rows = [{'stop_name': '', 'time': '77:77', 'confidence': 40, 'reviewed': True},
            {'stop_name': 'Aluva', 'time': '06:30', 'confidence': 80},
            {'stop_name': 'ALUVA', 'time': '06:30', 'confidence': 60}]
    validated = validate_stops(rows)
    assert len(validated) == 3
    assert validated[0]['needs_review']
    assert 'Duplicate row' in validated[1]['issues']
    assert validated[1]['confidence_level'] == 'high'
    assert validated[2]['confidence_level'] == 'medium'
    assert normalize_stop('ആലുവ') == 'ആലുവ'


def test_filename_and_content_safety(tmp_path):
    assert sanitize_filename('../../folder\\evil.png') == 'evil.png'
    with pytest.raises(AppError):
        validate_filename('evil.exe', 'image/png')
    with pytest.raises(AppError):
        validate_filename('photo.png', 'application/pdf')
    path = tmp_path / 'wrong.png'
    Image.new('RGB', (100, 100), 'white').save(path, format='JPEG')
    with pytest.raises(AppError) as error:
        inspect_upload(path, '.png')
    assert error.value.code == 'type_mismatch'
    path.write_bytes(b'not an image')
    with pytest.raises(AppError):
        read_image(path)


def test_conservative_preprocessing():
    image = np.full((100, 200, 3), 255, dtype=np.uint8)
    result, metadata = preprocess_image(image)
    assert result.ndim == 2
    assert result.shape == (100, 200)
    assert metadata['deskew_degrees'] == 0


def test_geometry_grouping_preserves_pages_and_columns():
    tokens = [{'text': text, 'page': page, 'confidence': 90, 'bounding_box': {'left': x, 'top': 20, 'width': 30, 'height': 20}}
              for text, page, x in [('06:30', 1, 300), ('Aluva', 1, 10), ('Thrissur', 2, 10)]]
    lines = tokens_to_lines(tokens)
    assert lines[0]['text'] == 'Aluva 06:30'
    assert lines[1]['page'] == 2


@pytest.mark.parametrize('value', ['=1+1', '+cmd', '-cmd', '@sum(1)', '  =1+1'])
def test_csv_formula_safety(value):
    assert spreadsheet_safe(value).startswith("'")
