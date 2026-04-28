# Runner Server (Compiler/Terminal)

Bu klasör Flutter uygulamasının “Compiler” moduna çıktı sağlayan sandbox runner’ıdır.

## Gereksinimler
- Docker (zorunlu)
- Python 3.11+ (önerilir)

## Çalıştırma

```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

## Endpoint
- `POST /run`
  - body: `{ languageId, code, stdin?, timeLimitMs?, memoryLimitMb? }`
  - response: `{ stdout, stderr, exitCode, durationMs, didTimeout, hint? }`

## Notlar
- `matlab` dili **Octave** ile çalıştırılır.
- `sql` şu an MVP: sorguyu sadece ekrana basar.

