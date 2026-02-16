import requests
from bs4 import BeautifulSoup
import random
import os
import json
import re
import xml.etree.ElementTree as ET
from openai import OpenAI
from dotenv import load_dotenv 

# Load the API key from your .env file
load_dotenv() 

client = OpenAI(
    api_key=os.environ.get("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1" 
)

def get_random_article_url():
    """Fetches valid article links reliably using the official RSS feed."""
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
    """
    Robustly scrapes the FULL article from Nachrichtenleicht INCLUDING dictionary.
    
    Article structure:
    1. Intro paragraph in <p class="article-header-description">
    2. Main content in <div class="article-details-text"> elements
    3. Dictionary section with <h3 class="teaser-word-title"> and <p class="teaser-word-description">
    """
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    response = requests.get(article_url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Extract Title
    title_tag = soup.find('h1')
    if not title_tag:
        title_tag = soup.find('h2')
    title = title_tag.get_text(strip=True) if title_tag else "No Title Found"
    
    content_lines = []
    
    # 1. Get the intro/teaser paragraph
    intro_para = soup.find('p', class_='article-header-description')
    if intro_para:
        intro_text = intro_para.get_text(strip=True)
        if intro_text and len(intro_text) > 20:
            content_lines.append(intro_text)
            print(f"✓ Found intro paragraph ({len(intro_text)} chars)")
    
    # 2. Get all main article content divs
    article_content_divs = soup.find_all('div', class_='article-details-text')
    for div in article_content_divs:
        text = div.get_text(strip=True)
        if text and len(text) > 20:
            content_lines.append(text)
    
    print(f"✓ Found {len(article_content_divs)} main content paragraphs")
    
    # 3. Get dictionary definitions (Wörter-Buch)
    dictionary_entries = []
    word_titles = soup.find_all('h3', class_='teaser-word-title')
    word_descriptions = soup.find_all('p', class_='teaser-word-description')
    
    # Match titles with descriptions
    for title_elem, desc_elem in zip(word_titles, word_descriptions):
        word = title_elem.get_text(strip=True)
        definition = desc_elem.get_text(strip=True)
        if word and definition:
            # Add as a definition entry
            dictionary_entries.append(f"{word}: {definition}")
    
    print(f"✓ Found {len(dictionary_entries)} dictionary entries")
    
    # Combine: main article + dictionary
    all_content = content_lines + dictionary_entries
    content = " ".join(all_content)
    
    # Clean up whitespace
    content = re.sub(r'\s+', ' ', content).strip()
    
    print(f"✓ Total: {len(all_content)} sections, {len(content)} characters")
    
    return title, content

def generate_ai_lesson(title, content):
    """Enhanced AI prompt with better structure and instructions."""
    
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

# --- Main Execution Flow ---
if __name__ == "__main__":
    try:
        print("🔍 Fetching random German article...")
        random_url = get_random_article_url()
        print(f"✓ Selected: {random_url}\n")
        
        print("📰 Scraping article content...")
        title, content = scrape_article_text(random_url)
        
        # Display preview
        preview_length = min(400, len(content))
        print(f"\n--- ARTICLE PREVIEW ---")
        print(f"Title: {title}")
        print(f"Content: {content[:preview_length]}...")
        if len(content) > preview_length:
            print(f"... (and {len(content) - preview_length} more characters)")
        print(f"Total characters: {len(content)}")
        print("------------------------\n")
        
        if len(content) < 200:
            print("⚠️  Warning: Article content seems too short. Trying again...")
            raise Exception(f"Content too short - only got {len(content)} characters")
        
        print("🤖 Sending to AI for translation and analysis...")
        print("⏳ This may take 30-60 seconds for complete processing...\n")
        
        lesson_json_string = generate_ai_lesson(title, content)
        lesson_data = json.loads(lesson_json_string)
        
        # Validation
        sentences_count = len(lesson_data.get('content', []))
        quiz_count = len(lesson_data.get('quiz', []))
        
        print("✅ SUCCESS!\n")
        print(f"📊 Results:")
        print(f"   • Sentences processed: {sentences_count}")
        print(f"   • Quiz questions: {quiz_count}")
        print(f"   • Vocabulary items: {len(lesson_data.get('vocabulary_highlights', []))}")
        
        # Save with metadata
        output_data = {
            "source_url": random_url,
            "generated_at": __import__('datetime').datetime.now().isoformat(),
            **lesson_data
        }
        
        with open('lesson_data.json', 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 Saved to 'lesson_data.json'")
        print(f"🌐 Open 'index.html' in your browser to view the lesson!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nTroubleshooting:")
        print("  1. Check your GROQ_API_KEY in .env file")
        print("  2. Ensure you have internet connection")
        print("  3. Try running the script again")