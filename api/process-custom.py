from http.server import BaseHTTPRequestHandler
import json
import requests
from bs4 import BeautifulSoup
import re
import base64
import datetime

# ── PDF EXTRACTION ─────────────────────────────────────────────────

def extract_text_from_pdf(pdf_b64):
    try:
        import fitz
    except ImportError:
        raise Exception("PDF support unavailable — pymupdf not installed.")

    pdf_bytes = base64.b64decode(pdf_b64)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    for page in doc:
        text = page.get_text("text")
        text = re.sub(r'\n{3,}', '\n\n', text).strip()
        if len(text) > 50:
            pages.append(text)
    doc.close()

    if not pages:
        raise Exception("No selectable text found in PDF. It may be a scanned image.")

    full_text = "\n\n".join(pages)
    if len(full_text) > 8000:
        full_text = full_text[:8000] + "\n\n[Truncated...]"
    return full_text

# ── URL SCRAPING — MULTI-STRATEGY ─────────────────────────────────

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'DNT': '1',
    'Cache-Control': 'max-age=0',
}

def try_jina_reader(url):
    """Use Jina AI's free r.jina.ai reader — handles JS-rendered pages."""
    jina_url = f"https://r.jina.ai/{url}"
    r = requests.get(jina_url, headers={'Accept': 'text/plain', 'User-Agent': 'Mozilla/5.0'}, timeout=20)
    if r.status_code != 200:
        return None, None
    text = r.text.strip()
    if len(text) < 200:
        return None, None

    # Jina returns markdown-like text — extract title from first # line
    lines = text.split('\n')
    title = ''
    content_lines = []
    for line in lines:
        stripped = line.strip()
        if not title and stripped.startswith('# '):
            title = stripped[2:].strip()
        elif stripped and not stripped.startswith('```') and not stripped.startswith('!['):
            # Skip image refs and code blocks, keep prose
            if not re.match(r'^(https?://|www\.)', stripped):
                content_lines.append(stripped)

    content = '\n'.join(content_lines)
    # Remove markdown formatting
    content = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', content)   # links
    content = re.sub(r'#{1,6}\s+', '', content)                   # headers
    content = re.sub(r'\*{1,2}([^*]+)\*{1,2}', r'\1', content)   # bold/italic
    content = re.sub(r'\n{3,}', '\n\n', content).strip()

    return title or 'Article', content

def try_direct_scrape(url):
    """Direct HTML fetch with broad extraction strategy."""
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()

    # Some sites return JSON with content embedded
    ct = r.headers.get('Content-Type', '')
    if 'json' in ct:
        data = r.json()
        text = json.dumps(data)
        return 'Article', text[:6000]

    soup = BeautifulSoup(r.text, 'html.parser')

    # ── Strategy 1: JSON-LD structured data (always rendered server-side) ──
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string or '')
            # Handle @graph arrays
            items = data.get('@graph', [data]) if isinstance(data, dict) else data
            if isinstance(items, dict):
                items = [items]
            for item in items:
                if item.get('@type') in ('Article', 'NewsArticle', 'WebPage', 'BlogPosting'):
                    body = item.get('articleBody') or item.get('description') or ''
                    headline = item.get('headline') or item.get('name') or ''
                    if len(body) > 200:
                        return headline, body[:8000]
        except Exception:
            pass

    # ── Strategy 2: OpenGraph / meta tags for short content ──
    og_title = soup.find('meta', property='og:title')
    og_desc = soup.find('meta', property='og:description')

    # ── Strategy 3: Remove noise, find biggest text block ──
    for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'head',
                               'aside', 'form', 'iframe', 'noscript']):
        tag.decompose()
    for tag in soup.find_all(class_=re.compile(
            r'(nav|menu|footer|header|sidebar|cookie|popup|banner|social|share|related|comment|ad-|widget|teaser(?!.*text))',
            re.I)):
        tag.decompose()

    # Broad selector list including common German news site patterns
    selectors = [
        # Generic semantic
        'article', '[role="main"]', 'main',
        # Common class patterns
        '.article-body', '.article-content', '.article__body', '.article__content',
        '.article__text', '.article-text',
        '.post-content', '.post-body', '.entry-content',
        '.story-body', '.story-content',
        '.content-body', '.page-content',
        '.text-content', '.main-content',
        # Deutschlandfunk / ARD patterns
        '.b-content-main', '.articleText', '.article-long-text',
        '[class*="ArticleBody"]', '[class*="article-body"]',
        '[class*="articleBody"]', '[class*="ArticleText"]',
        '[class*="content__text"]', '[class*="contentText"]',
        # Generic IDs
        '#article-body', '#content', '#main-content', '#main',
        # Data attributes
        '[data-module="articleBody"]', '[data-component="article-body"]',
    ]

    content_el = None
    for sel in selectors:
        try:
            el = soup.select_one(sel)
            if el and len(el.get_text(strip=True)) > 200:
                content_el = el
                break
        except Exception:
            continue

    # ── Strategy 4: Largest paragraph cluster ──
    if not content_el:
        best_score = 0
        for el in soup.find_all(['div', 'section', 'main', 'article']):
            paras = el.find_all('p')
            text = ' '.join(p.get_text(strip=True) for p in paras if len(p.get_text(strip=True)) > 20)
            score = len(text)
            if score > best_score:
                best_score = score
                content_el = el

    if not content_el or len(content_el.get_text(strip=True)) < 150:
        return None, None

    # Extract clean paragraphs
    paras = []
    for p in content_el.find_all(['p', 'h1', 'h2', 'h3', 'li']):
        text = p.get_text(separator=' ', strip=True)
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) > 25:
            paras.append(text)

    # Deduplicate adjacent duplicates
    seen = set()
    unique = []
    for p in paras:
        key = p[:60]
        if key not in seen:
            seen.add(key)
            unique.append(p)

    if not unique:
        return None, None

    title_tag = soup.find('h1') or (og_title and og_title.get('content')) or soup.find('title')
    if hasattr(title_tag, 'get_text'):
        title = title_tag.get_text(strip=True)
    elif isinstance(title_tag, str):
        title = title_tag
    else:
        title = 'Article'

    content = '\n\n'.join(unique)
    if len(content) > 8000:
        content = content[:8000] + "\n\n[Truncated...]"

    return title, content

def scrape_url(url):
    """Try multiple strategies, use whatever works first."""
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    errors = []

    # Strategy A: Direct scrape (fastest, works for most sites)
    try:
        title, content = try_direct_scrape(url)
        if title and content and len(content) > 150:
            return title, content
        errors.append("Direct scrape: insufficient content")
    except Exception as e:
        errors.append(f"Direct scrape: {str(e)[:80]}")

    # Strategy B: Jina reader (handles JS-rendered / paywalled sites)
    try:
        title, content = try_jina_reader(url)
        if title and content and len(content) > 150:
            return title, content
        errors.append("Jina reader: insufficient content")
    except Exception as e:
        errors.append(f"Jina reader: {str(e)[:80]}")

    raise Exception(
        f"Could not extract readable content from this URL.\n"
        f"The site may require JavaScript or block scrapers.\n"
        f"Try copying the article text and using PDF upload instead.\n"
        f"Details: {' | '.join(errors)}"
    )

# ── AI LESSON GENERATION ───────────────────────────────────────────

def generate_ai_lesson(title, content, api_key):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    system_prompt = """You are an expert German language teacher creating interactive learning materials.

Process the provided text into a structured German learning lesson.
If the text is not in German, translate it to German first, then create the lesson.

Output ONLY valid JSON:
{
  "title": "English translation of the title",
  "summary": "2-3 sentence English summary",
  "content": [
    {
      "sentence_number": 1,
      "german_sentence": "German sentence.",
      "english_translation": "English translation.",
      "word_meanings": { "GermanWord": "English meaning" },
      "grammar_notes": "Optional grammar note"
    }
  ],
  "vocabulary_highlights": [
    { "word": "german_word", "translation": "English meaning", "usage_example": "Example in German" }
  ],
  "quiz": [
    {
      "question": "Question in German?",
      "options": ["A", "B", "C", "D"],
      "correct_answer": "A",
      "explanation": "Why A is correct"
    }
  ]
}

Rules:
- Process ALL sentences sequentially, number them
- Include key words in word_meanings, strip punctuation from keys
- 5-7 quiz questions in German
- 6-10 vocabulary highlights"""

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Title: {title}\n\nContent:\n{content}"}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.3,
        "max_tokens": 16000
    }

    r = requests.post(url, headers=headers, json=payload, timeout=90)

    if r.status_code == 401:
        raise Exception("invalid_api_key: Your Groq API key is invalid or expired.")
    if r.status_code == 429:
        raise Exception("rate_limit: Too many requests. Please wait and try again.")
    if r.status_code != 200:
        raise Exception(f"groq_error_{r.status_code}: {r.text[:200]}")

    return r.json()['choices'][0]['message']['content']

# ── HANDLER ────────────────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length))
            api_key = body.get('api_key', '').strip()

            if not api_key:
                self._respond(400, {'success': False, 'error': 'API key is required'})
                return

            mode = body.get('mode', '')

            if mode == 'pdf':
                pdf_b64 = body.get('pdf_data', '')
                filename = body.get('filename', 'document.pdf')
                if not pdf_b64:
                    self._respond(400, {'success': False, 'error': 'No PDF data provided'})
                    return
                content = extract_text_from_pdf(pdf_b64)
                title = filename.replace('.pdf', '').replace('_', ' ').replace('-', ' ')
                source_url = f"PDF: {filename}"

            elif mode == 'url':
                url_input = body.get('url', '').strip()
                if not url_input:
                    self._respond(400, {'success': False, 'error': 'No URL provided'})
                    return
                title, content = scrape_url(url_input)
                source_url = url_input

            else:
                self._respond(400, {'success': False, 'error': f'Unknown mode: {mode}'})
                return

            if not content or len(content.strip()) < 100:
                raise Exception("Not enough text found. Try a different source.")

            lesson_data = json.loads(generate_ai_lesson(title, content, api_key))

            self._respond(200, {
                'success': True,
                'data': {
                    'source_url': source_url,
                    'generated_at': datetime.datetime.now().isoformat(),
                    **lesson_data
                }
            })

        except Exception as e:
            self._respond(500, {'success': False, 'error': str(e)})

    def _respond(self, status, data):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self._cors()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')