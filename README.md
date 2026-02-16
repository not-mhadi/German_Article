# Deutsche Lernwerkstatt 🇩🇪

Learn German through real news articles with AI-powered translations and interactive quizzes.

## ✨ Features

- 🎨 **Dark Mode UI** - Beautiful, minimalist interface
- 🔐 **Bring Your Own API Key** - Use your free Groq API key
- 📚 **Real News Articles** - From Nachrichtenleicht (simplified German)
- 💬 **Word-by-Word Translations** - Understand every word
- 🎯 **Interactive Quizzes** - Test your comprehension
- 🌐 **Deploy on Vercel** - Free hosting, no server needed

## 🚀 Quick Deploy to Vercel

1. **Get a Groq API Key** (free)
   - Go to https://console.groq.com/
   - Sign up
   - Create an API key

2. **Deploy to Vercel**
   ```bash
   # Push to GitHub
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin YOUR_GITHUB_REPO
   git push -u origin main
   
   # Deploy on Vercel
   # Go to vercel.com/new
   # Import your GitHub repo
   # Click Deploy
   ```

3. **Done!** Share your app URL

## 📁 Project Structure

```
deutsche-lernwerkstatt/
├── api/
│   └── generate-lesson.py    # Serverless function
├── index.html                 # Frontend UI
├── vercel.json               # Vercel config
├── requirements.txt          # Python dependencies
└── VERCEL_DEPLOY.md          # Detailed deployment guide
```

## 🎯 How to Use

1. Visit your deployed app
2. Enter your Groq API key (optional: save it in browser)
3. Click "Generate New Lesson"
4. Wait ~30-60 seconds
5. Start learning!

## 🛠️ Tech Stack

- **Frontend**: Vanilla HTML/CSS/JS
- **Backend**: Python Serverless Functions (Vercel)
- **AI**: Groq API (Llama 3.3 70B)
- **Scraping**: BeautifulSoup4
- **Hosting**: Vercel (free tier)

## 🔐 Privacy & Security

- **No API keys stored on server** - Users provide their own
- **Optional browser storage** - LocalStorage for convenience
- **HTTPS by default** - Encrypted connections
- **No database** - Stateless serverless architecture

## 💰 Cost

### Completely Free!

- **Vercel**: Free tier (100GB bandwidth/month)
- **Groq API**: Free tier (7,000 requests/day)
- **No hidden costs**: Zero ongoing expenses

## 📖 Full Documentation

- See `VERCEL_DEPLOY.md` for detailed deployment instructions
- Includes troubleshooting, monitoring, and best practices

## 🐛 Troubleshooting

### App not working?
- Check your Groq API key is correct
- Make sure you have internet connection
- Try generating a different lesson

### Deployment failed?
- Check `requirements.txt` has all dependencies
- Verify `vercel.json` configuration
- See `VERCEL_DEPLOY.md` for detailed help

## 🎓 Educational Use

This app is for educational purposes only. News article content © Nachrichtenleicht/Deutschlandfunk.

## 📝 License

MIT License - Feel free to use and modify!

## 🙏 Credits

- **News Source**: [Nachrichtenleicht](https://www.nachrichtenleicht.de/)
- **AI Model**: Groq (Llama 3.3 70B)
- **Fonts**: Google Fonts (Inter)

---

**Viel Erfolg beim Deutschlernen! Good luck learning German!** 🎓✨
