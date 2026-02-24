FROM python:3.9-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# 1. تثبيت الحزم (أضفنا fluxbox)
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    xvfb \
    xclip \
    xsel \
    scrot \
    gnome-screenshot \
    xdotool \
    x11vnc \
    novnc \
    websockify \
    sqlite3 \
    procps \
    python3-tk \
    python3-dev \
    fluxbox \
    fonts-liberation \
    fonts-arphic-ukai \
    fonts-arphic-uming \
    fonts-ipafont-mincho \
    fonts-ipafont-gothic \
    fonts-unfonts-core \
    fontconfig \
    libnss3 \
    libxss1 \
    libasound2 \
    libgbm1 \
    libgtk-3-0 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# 2. تثبيت Chrome
RUN wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get update \
    && apt-get install -y ./google-chrome-stable_current_amd64.deb \
    && rm google-chrome-stable_current_amd64.deb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 5000

ENTRYPOINT ["/entrypoint.sh"]