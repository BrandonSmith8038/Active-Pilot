FROM python:3.12-slim
RUN pip install --no-cache-dir tzdata
WORKDIR /app
COPY app.py dashboard.html logo.png icon.png favicon.ico ./
ENV PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 8100
CMD ["python", "app.py"]
