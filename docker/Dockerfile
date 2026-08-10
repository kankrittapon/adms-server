FROM python:3.12-slim

WORKDIR /app
COPY app/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY app/main.py ./main.py

CMD ["python", "main.py"]
