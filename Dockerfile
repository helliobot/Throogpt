# आधार के रूप में आधिकारिक Python इमेज
FROM python:3.11-slim

# वर्किंग डायरेक्टरी सेट करें
WORKDIR /app

# प्रोजेक्ट फाइल्स कॉपी करें
COPY . .

# डिपेंडेंसीज़ इंस्टॉल करें
RUN pip install --no-cache-dir -r requirements.txt

# SQLite डेटाबेस के लिए डायरेक्टरी बनाएँ
RUN mkdir -p /app/data

# पर्यावरण चर सेट करें (Choreo द्वारा ओवरराइड किया जाएगा)
ENV BOT_TOKEN=${BOT_TOKEN}

# बॉट चलाएँ
CMD ["python", "bot.py"]
