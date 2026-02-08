FROM python:3.9-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# تثبيت الحزم (Chrome, Xvfb, Xclip, Sqlite3)
RUN apt-get update && apt-get install -y \
    wget gnupg unzip xvfb xclip scrot sqlite3 \
    libgconf-2-4 libnss3 libxi6 libgdk-pixbuf2.0-0 libgtk-3-0 libxss1 libasound2 \
    fonts-liberation libappindicator3-1 xdg-utils \
    fonts-arphic-ukai fonts-arphic-uming fonts-ipafont-mincho fonts-ipafont-gothic fonts-unfonts-core \
    && rm -rf /var/lib/apt/lists/*

# تثبيت Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update && apt-get install -y google-chrome-stable

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 5000

ENTRYPOINT ["/entrypoint.sh"]