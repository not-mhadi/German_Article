from http.server import BaseHTTPRequestHandler
import json
import requests
from bs4 import BeautifulSoup
import re
import base64
import datetime

# ── TEXT EXTRACTION ────────────────────────────────────────────────

def extract_text_from_pdf(pdf_b64):
    """Extract text from base64-encoded PDF using PyMuPDF."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise Exception("PDF support not available. Please install pymupdf.")

    pdf_bytes = base64.b64decode(pdf_b64)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    pages = []
    for page in doc:
        text = page.get_text("text")
        # Clean up the text
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.strip()
        if len(text) > 50:
            pages.append(text)
    doc.close()

    if not pages:
        raise Exception("Could not extract any text from the PDF. Make sure it contains selectable text (not a scanned image).")

    full_text = "\n\n".join(pages)
    # Limit to ~8000 chars to stay within token limits
    if len(full_text) > 8000:
        full_text = full_text[:8000] + "\n\n[Text truncated for processing...]"

    return full_text

def scrape_url(url):
    """Scrape text content from any URL using smart extraction."""
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'de,en;q=0.9',
    }

    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')

    # Remove noise elements
    for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'header',
                               'aside', 'form', 'iframe', 'noscript', 'ads',
                               'advertisement', 'cookie', 'popup']):
        tag.decompose()
    for tag in soup.find_all(class_=re.compile(r'(nav|menu|footer|header|sidebar|ad|cookie|popup|banner|social)', re.I)):
        tag.decompose()

    # Try known article selectors first
    article_selectors = [
        'article',
        '[role="main"]',
        'main',
        '.article-body', '.article-content', '.post-content',
        '.entry-content', '.story-body', '.content-body',
        '#article-body', '#content', '#main-content',
    ]
    content = None
    for sel in article_selectors:
        el = soup.select_one(sel)
        if el and len(el.get_text(strip=True)) > 300:
            content = el
            break

    # Fallback: find the div/section with the most paragraph text
    if not content:
        candidates = []
        for el in soup.find_all(['div', 'section', 'main']):
            paras = el.find_all('p')
            text = ' '.join(p.get_text(strip=True) for p in paras)
            if len(text) > 200:
                candidates.append((len(text), el))
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            content = candidates[0][1]

    if not content:
        raise Exception("Could not find readable content on this page. Try a different URL.")

    # Extract clean paragraphs
    paras = []
    for p in content.find_all(['p', 'h1', 'h2', 'h3']):
        text = p.get_text(separator=' ', strip=True)
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) > 30:
            paras.append(text)

    if not paras:
        # Fallback to all text
        raw = content.get_text(separator='\n', strip=True)
        paras = [line.strip() for line in raw.split('\n') if len(line.strip()) > 30]

    if not paras:
        raise Exception("No readable text found at this URL.")

    # Get title
    title = ''
    if soup.find('h1'):
        title = soup.find('h1').get_text(strip=True)
    elif soup.find('title'):
        title = soup.find('title').get_text(strip=True)
    title = title or 'Untitled'

    full_text = '\n\n'.join(paras)
    if len(full_text) > 8000:
        full_text = full_text[:8000] + "\n\n[Content truncated for processing...]"

    return title, full_text

# ── AI LESSON GENERATION ───────────────────────────────────────────

def generate_ai_lesson(title, content, api_key, source_lang='de'):
    """Generate lesson. source_lang: 'de' for German content, 'auto' to detect."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    system_prompt = """You are an expert German language teacher creating interactive learning materials.
Process the provided text into a structured German learning lesson.

If the text is not in German, translate it to German first, then create the lesson from the German version.

Output ONLY valid JSON in this exact structure:
{
  "title": "English translation of the title",
  "summary": "Brief 2-3 sentence summary in English",
  "content": [
    {
      "sentence_number": 1,
      "german_sentence": "German sentence (original or translated).",
      "english_translation": "Accurate English translation.",
      "word_meanings": { "GermanWord": "English meaning" },
      "grammar_notes": "Optional grammar note"
    }
  ],
  "vocabulary_highlights": [
    { "word": "german_word", "translation": "English meaning", "usage_example": "Example sentence in German" }
  ],
  "quiz": [
    {
      "question": "Comprehension question in German?",
      "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
      "correct_answer": "Option 1",
      "explanation": "Why this is correct"
    }
  ]
}

Rules:
- Process EVERY sentence sequentially, do not skip any
- Include key words in word_meanings, strip punctuation from keys
- Create 5-7 varied quiz questions in German
- vocabulary_highlights should contain 6-10 important words with usage examples"""

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

    response = requests.post(url, headers=headers, json=payload, timeout=90)

    if response.status_code == 401:
        raise Exception("invalid_api_key: Your Groq API key is invalid or expired.")
    if response.status_code == 429:
        raise Exception("rate_limit: Too many requests. Please wait a moment and try again.")
    if response.status_code != 200:
        raise Exception(f"groq_error_{response.status_code}: {response.text[:200]}")

    return response.json()['choices'][0]['message']['content']

# ── HANDLER ────────────────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length))

            api_key = body.get('api_key', '').strip()
            if not api_key:
                self._respond(400, {'success': False, 'error': 'API key is required'})
                return

            mode = body.get('mode', '')  # 'pdf' or 'url'

            if mode == 'pdf':
                pdf_b64 = body.get('pdf_data', '')
                filename = body.get('filename', 'document.pdf')
                if not pdf_b64:
                    self._respond(400, {'success': False, 'error': 'No PDF data provided'})
                    return
                raw_text = extract_text_from_pdf(pdf_b64)
                title = filename.replace('.pdf', '').replace('_', ' ').replace('-', ' ')
                source_url = f"PDF: {filename}"
                content = raw_text

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

            if len(content.strip()) < 100:
                raise Exception("Not enough text content found. Please try a different source.")

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
        self._cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
