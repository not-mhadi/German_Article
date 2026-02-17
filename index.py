import json
import requests
from bs4 import BeautifulSoup
import random
import re
import xml.etree.ElementTree as ET
from openai import OpenAI

def get_random_article_url():
    """Fetches valid article links from RSS feed."""
    rss_url = "https://www.nachrichtenleicht.de/nachrichtenleicht-nachrichten-100.rss"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    response = requests.get(rss_url, headers=headers)
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
    """Scrapes the full article including dictionary."""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    response = requests.get(article_url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Extract Title
    title_tag = soup.find('h1')
    if not title_tag:
        title_tag = soup.find('h2')
    title = title_tag.get_text(strip=True) if title_tag else "No Title Found"
    
    content_lines = []
    
    # 1. Get intro paragraph
    intro_para = soup.find('p', class_='article-header-description')
    if intro_para:
        intro_text = intro_para.get_text(strip=True)
        if intro_text and len(intro_text) > 20:
            content_lines.append(intro_text)
    
    # 2. Get main article content
    article_content_divs = soup.find_all('div', class_='article-details-text')
    for div in article_content_divs:
        text = div.get_text(strip=True)
        if text and len(text) > 20:
            content_lines.append(text)
    
    # 3. Get dictionary entries
    dictionary_entries = []
    word_titles = soup.find_all('h3', class_='teaser-word-title')
    word_descriptions = soup.find_all('p', class_='teaser-word-description')
    
    for title_elem, desc_elem in zip(word_titles, word_descriptions):
        word = title_elem.get_text(strip=True)
        definition = desc_elem.get_text(strip=True)
        if word and definition:
            dictionary_entries.append(f"{word}: {definition}")
    
    # Combine all content
    all_content = content_lines + dictionary_entries
    content = " ".join(all_content)
    content = re.sub(r'\s+', ' ', content).strip()
    
    return title, content

def generate_ai_lesson(title, content, api_key):
    """Generates lesson using AI with user's API key."""
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1"
    )
    
    system_prompt = """You are an expert German language teacher creating interactive learning materials.

Your task is to process a German news article and create a comprehensive learning experience.

CRITICAL REQUIREMENTS:
1. Process EVERY sentence from start to finish - do not skip or summarize
2. Number sentences sequentially to track your progress
3. Provide word-by-word translations for vocabulary building
4. Create engaging, varied quiz questions

Output ONLY valid JSON in this exact structure:
{
  "title": "English translation of the article title",
  "summary": "Brief 2-3 sentence summary in English of what the article is about",
  "content": [
    {
      "sentence_number": 1,
      "german_sentence": "Original German sentence.",
      "english_translation": "Accurate English translation.",
      "word_meanings": {
        "German_word_1": "English meaning",
        "German_word_2": "English meaning"
      },
      "grammar_notes": "Optional: Brief note about important grammar in this sentence"
    }
  ],
  "vocabulary_highlights": [
    {
      "word": "important_German_word",
      "translation": "English meaning",
      "usage_example": "Short German example sentence"
    }
  ],
  "quiz": [
    {
      "question": "Comprehension question in German",
      "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
      "correct_answer": "Option 1",
      "explanation": "Brief explanation of why this is correct"
    }
  ]
}

WORD MEANINGS RULES:
- Strip ALL punctuation from German words (keys)
- Include EVERY word including articles (der, die, das)
- For verbs, provide infinitive form if conjugated
- Keep meanings concise (1-3 words max)

QUIZ REQUIREMENTS:
- Create 5-7 varied questions
- Mix question types: factual recall, inference, vocabulary, grammar
- Make all options plausible
- Questions should be in German, options in German
- Add helpful explanations

Process the entire article systematically. Do not stop until complete."""

    user_prompt = f"Title: {title}\n\nArticle Content:\n{content}"

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
        max_tokens=16000
    )
    
    return response.choices[0].message.content

def handler(event, context):
    """Vercel serverless function handler."""
    
    # Handle CORS preflight
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            },
            'body': ''
        }
    
    try:
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        api_key = body.get('api_key')
        
        if not api_key:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'success': False,
                    'error': 'API key is required'
                })
            }
        
        # Get random article
        article_url = get_random_article_url()
        
        # Scrape article
        title, content = scrape_article_text(article_url)
        
        if len(content) < 200:
            raise Exception("Content too short")
        
        # Generate lesson
        lesson_json_string = generate_ai_lesson(title, content, api_key)
        lesson_data = json.loads(lesson_json_string)
        
        # Add metadata
        import datetime
        output_data = {
            "source_url": article_url,
            "generated_at": datetime.datetime.now().isoformat(),
            **lesson_data
        }
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'success': True,
                'data': output_data
            })
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'success': False,
                'error': str(e)
            })
        }
