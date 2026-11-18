from app.ingestion.vimeo import pick_smallest_rendition
from app.ingestion.wordpress import extract_vimeo_ids


def test_vimeo_block_embed():
    html = '<!-- wp:embed {"url":"https://vimeo.com/123456789"} -->\n<figure>https://vimeo.com/123456789</figure>'
    assert extract_vimeo_ids(html) == ["123456789"]


def test_vimeo_iframe_and_private_hash():
    html = '<iframe src="https://player.vimeo.com/video/987654321?h=abc123&badge=0"></iframe>'
    assert extract_vimeo_ids(html) == ["987654321"]


def test_multiple_videos_in_order():
    html = 'https://player.vimeo.com/video/111111111 text https://vimeo.com/222222222'
    assert extract_vimeo_ids(html) == ["111111111", "222222222"]


def test_no_video():
    assert extract_vimeo_ids("<p>Solo texto</p>") == []
    assert extract_vimeo_ids('<script src="https://player.vimeo.com/api/player.js"></script>') == []


def test_smallest_rendition():
    downloads = [
        {"quality": "hd", "size": 900, "link": "https://x/hd"},
        {"quality": "sd", "size": 200, "link": "https://x/sd"},
        {"quality": "source", "size": 5000, "link": "https://x/src"},
    ]
    assert pick_smallest_rendition(downloads)["link"] == "https://x/sd"
    assert pick_smallest_rendition([]) is None
