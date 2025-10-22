# Use the official Python slim image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the bot code
COPY bot.py .

# Expose the port for Flask webhook
EXPOSE 5000

# Command to run the bot
CMD ["python", "bot.py"]
