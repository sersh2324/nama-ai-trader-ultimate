import os

import requests


OPPORTUNITY_PROMPT = (
    "اشرح بالعربية للمبتدئ في ثلاث جمل اتجاه السيناريو، شرط التأكيد وإلغاء الفكرة. "
    "اعتمد فقط على الوقائع المُرسلة. لا تخترع أسعارًا أو أخبارًا أو احتمالات نجاح. "
    "لا تطلب تنفيذ صفقة ولا تغير أي مستوى."
)


def explain_opportunity(facts, *, prompt=OPPORTUNITY_PROMPT):
    key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("NAMA_OPENAI_MODEL")
    if not key or not model:
        return None
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": facts},
            ],
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]
