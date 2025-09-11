from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

response = client.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=[
        {"role": "system", "content": "Eres un astronauta."},
        {"role": "user", "content": "Dime el nombre de los primermos planetas del sistema solar."}
    ],
    max_tokens=50
)

print(response.choices[0].message.content.strip())
