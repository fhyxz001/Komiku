FROM python:3.11-slim

WORKDIR /app

COPY app.py .
COPY static static/

EXPOSE 8080

ENV MANGA_DIR=/vol1/1000/Manga
ENV HOST=0.0.0.0
ENV PORT=8080

CMD ["python", "app.py"]
