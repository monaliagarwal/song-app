FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python manage.py collectstatic --noinput
EXPOSE $PORT
CMD daphne moodtune.asgi:application --port $PORT --bind 0.0.0.0
