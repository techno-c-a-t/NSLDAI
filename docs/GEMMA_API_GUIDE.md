# Управление процессом мышления (Thinking Process) в моделях Gemma 4

Официальная документация Google:
👉 [Запустите Gemma с помощью Gemini API](https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api?hl=ru)

---

## 1. Концепция мышления (Thinking) в Gemma 4

Модели **Gemma 4** (`gemma-4-31b-it`, `gemma-4-26b-a4b-it`) используют внутренний процесс мышления (*thinking process*), оптимизирующий многоэтапные рассуждения в логически сложных задачах.

По умолчанию в Gemini API этот параметр включен (**`high`**). При активном мышлении модель генерирует скрытые цепочки рассуждений, что приводит к:
1. Заметному увеличению задержки ответа (latency).
2. Повышенному расходу токенов.
3. Риску утечки служебных англоязычных мета-инструкций или внутренних размышлений в текст ответа пользователя.

В проекте **NSLDAI (Фантом)** для моделей Gemma мышление **принудительно отключено на 100%** во всех сценариях (диалоги, классификатор Gatekeeper, извлечение досье, суммаризация голосовых сообщений).

---

## 2. Управление уровнем мышления через API

Уровень мышления строго контролируется через следующие параметры:

| Режим | Значение `thinking_level` | Описание |
| :--- | :--- | :--- |
| **Выключено (100% OFF)** | `"minimal"` | Отключает мыслительный процесс, обеспечивает максимальную скорость и лаконичный ответ. |
| **Включено (ON)** | `"high"` | Активирует глубокие многоэтапные рассуждения. |

> ⚠️ **Важно:** Модели Gemma 4 поддерживают строго `"minimal"` и `"high"`. Значения вроде `"low"` или `"medium"` не поддерживаются спецификацией Gemma 4 и могут приводить к сбоям или игнорированию параметра.

---

## 3. Примеры реализации

### Python SDK (`google-genai`)
```python
from google import genai
from google.genai import types

client = genai.Client()

# Полное отключение thinking:
response = client.models.generate_content(
    model="gemma-4-26b-a4b-it",
    contents="Привет, Фантом!",
    config=types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level="minimal")
    ),
)
print(response.text)
```

### Google OpenAI-compatible API (используется в проекте NSLDAI)
Эндпоинт: `https://generativelanguage.googleapis.com/v1beta/openai/chat/completions`

В OpenAI-совместимом слое Google API параметр транслируется через `reasoning_effort`:
```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_GEMINI_API_KEY",
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    default_headers={"x-goog-api-key": "YOUR_GEMINI_API_KEY"}
)

response = client.chat.completions.create(
    model="gemma-4-31b-it",
    messages=[{"role": "user", "content": "Привет, Фантом!"}],
    reasoning_effort="minimal",  # 👈 Гарантированное отключение thinking
    temperature=0.95,
    max_tokens=3000
)
print(response.choices[0].message.content)
```

### Прямой REST JSON API
```json
POST https://generativelanguage.googleapis.com/v1beta/models/gemma-4-26b-a4b-it:generateContent
{
  "contents": [
    {
      "parts": [{"text": "Привет, Фантом!"}]
    }
  ],
  "generationConfig": {
    "thinkingConfig": {
      "thinkingLevel": "minimal"
    }
  }
}
```

---

## 4. Архитектурное правило в кодовой базе NSLDAI

В файле [`modules/ai_service.py`](file:///home/technocat/Документы/Projects/NSLDAI/modules/ai_service.py):
- При вызове моделей, содержащих `gemma` в имени, параметр `reasoning_effort` **автоматически выставляется в `"minimal"`**, если вызывающий код явно не указал иное.
- При запросе через OpenAI-совместимый клиент передается:
  ```python
  kwargs["reasoning_effort"] = "minimal"
  ```
- Значения `"off"`, `"none"`, `"disable"`, `"0"` автоматически нормализуются в `"minimal"`.
