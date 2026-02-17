from http.server import BaseHTTPRequestHandler
import json
import requests
from bs4 import BeautifulSoup
import random
import re
import xml.etree.ElementTree as ET
from openai import OpenAI
import datetime

def get_random_article_url():
    rss_url = "https://www.nachrichtenleicht.de/nachrichtenleicht-nachrichten-100.rss"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    response = requests.get(rss_url, headers=headers, timeout=10)
    root = ET.fromstring(response.content)
    links = []
    for item in root.findall('.//item'):
        link = item.find('link')
        if link is not None and link.text:
            url = link.text
            if url.endswith('.html') and "-100.html" not in url and "podcast" not in url:
                links.append(url)
    if not links:
        raise Exception("Could not find any valid article links.")
    return random.choice(links)

def scrape_article_text(article_url):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    response = requests.get(article_url, headers=headers, timeout=10)
    soup = BeautifulSoup(response.text, 'html.parser')

    title_tag = soup.find('h1') or soup.find('h2')
    title = title_tag.get_text(strip=True) if title_tag else "No Title Found"

    content_lines = []

    intro_para = soup.find('p', class_='article-header-description')
    if intro_para:
        intro_text = intro_para.get_text(strip=True)
        if len(intro_text) > 20:
            content_lines.append(intro_text)

    for div in soup.find_all('div', class_='article-details-text'):
        text = div.get_text(strip=True)
        if len(text) > 20:
            content_lines.append(text)

    for title_elem, desc_elem in zip(
        soup.find_all('h3', class_='teaser-word-title'),
        soup.find_all('p', class_='teaser-word-description')
    ):
        word = title_elem.get_text(strip=True)
        definition = desc_elem.get_text(strip=True)
        if word and definition:
            content_lines.append(f"{word}: {definition}")

    content = " ".join(content_lines)
    content = re.sub(r'\s+', ' ', content).strip()
    return title, content

def generate_ai_lesson(title, content, api_key):
    client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")

    system_prompt = """You are an expert German language teacher creating interactive learning materials.
Process this German news article into a structured lesson.

Output ONLY valid JSON in this exact structure:
{
  "title": "English translation of the article title",
  "summary": "Brief 2-3 sentence summary in English",
  "content": [
    {
      "sentence_number": 1,
      "german_sentence": "Original German sentence.",
      "english_translation": "Accurate English translation.",
      "word_meanings": { "GermanWord": "English meaning" },
      "grammar_notes": "Optional grammar note"
    }
  ],
  "vocabulary_highlights": [
    { "word": "german_word", "translation": "English meaning", "usage_example": "Example sentence" }
  ],
  "quiz": [
    {
      "question": "Question in German?",
      "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
      "correct_answer": "Option 1",
      "explanation": "Why this is correct"
    }
  ]
}

Rules:
- Process EVERY sentence, number them sequentially
- Include ALL words in word_meanings, strip punctuation from keys
- Create 5-7 quiz questions in German
- Do not stop until the entire article is processed"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Title: {title}\n\nContent:\n{content}"}
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
        max_tokens=16000
    )
    return response.choices[0].message.content


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

            article_url = get_random_article_url()
            title, content = scrape_article_text(article_url)

            if len(content) < 200:
                raise Exception("Article content too short, please try again.")

            lesson_data = json.loads(generate_ai_lesson(title, content, api_key))

            self._respond(200, {
                'success': True,
                'data': {
                    'source_url': article_url,
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