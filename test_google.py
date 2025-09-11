import os
from google.cloud import vision

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "clave_google.json"

client = vision.ImageAnnotatorClient()

with open("manzana.jpg", "rb") as img_file:  # cambia por la ruta de tu imagen
    content = img_file.read()

image = vision.Image(content=content)
response = client.label_detection(image=image)

for label in response.label_annotations:
    print(label.description, label.score)
