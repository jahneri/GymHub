FROM python:3.11-slim
WORKDIR /app
<<<<<<< HEAD
# Install gcc and libs for PyAudio (portaudio) and Postgres (libpq)
RUN apt-get update && apt-get install -y gcc portaudio19-dev libpq-dev && rm -rf /var/lib/apt/lists/*
=======
RUN apt-get update && apt-get install -y gcc portaudio19-dev && rm -rf /var/lib/apt/lists/*
>>>>>>> d38c103
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
