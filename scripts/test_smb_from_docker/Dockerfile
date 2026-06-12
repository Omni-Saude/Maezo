FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir smbprotocol

COPY test_smb_write.py .

CMD ["python", "test_smb_write.py"]
