import google.generativeai as genai
import os

# Sem vlož svůj API klíč, nebo se ujisti, že ho máš v proměnných prostředí
genai.configure(api_key="AIzaSyBIMS6bG-BJXVbikWy53ar0hwR7spnU1BA")

# Pokud používáš st.secrets v aplikaci, můžeš klíč vytáhnout z ní,
# nebo ho pro tento test vlož natvrdo výše.

print("Dostupné modely pro generování textu:")
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(m.name)