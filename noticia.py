import os
import glob
import json
import time
import google.generativeai as genai

# --- CONFIGURACIÓN ---
# Como el script lo ejecuta GitHub desde la raíz del proyecto,
# las rutas se escriben directas:
CARPETA_TUITS = 'tuits'
CARPETA_NEWS = 'news'


def generar_noticia_con_modelo(modelo_nombre, contenido):
    """Intenta generar una noticia usando un modelo específico"""
    try:
        model = genai.GenerativeModel(modelo_nombre)

        # Prompt para Gemini (El "Periodista")
        prompt = f"""
        Actúa como un redactor de noticias digitales.
        Tengo este tuit crudo extraído de X (Twitter):

        "{contenido}"

        Tu tarea:
        1. Analiza el contenido.
        2. Redacta una noticia corta (Título + 2 párrafos máximo).
        3. Usa un tono informativo y neutral.
        4. Si el tuit es irrelevante o spam, escribe solo "IRRELEVANTE".
        """

        # Llamada a la API
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"⚠️ Error con modelo {modelo_nombre}: {e}")
        raise e


def main():
    # 1. APLICAR LA LLAVE (SEGURIDAD)
    # El script busca la llave en las variables de entorno que configuramos en el YAML.
    # No necesitas escribirla aquí, GitHub se la pasa invisiblemente.
    api_key = os.getenv('GEMINI_API_KEY')

    if not api_key:
        print("❌ ERROR CRÍTICO: No se encontró la GEMINI_API_KEY en el entorno.")
        print("   Asegúrate de haberla agregado en Settings -> Secrets en GitHub.")
        exit(1)

    # Configuramos Gemini
    genai.configure(api_key=api_key)

    # Lista de modelos a usar en orden de preferencia
    # Gemini 3 Pro es el más avanzado pero tiene límites estrictos en la versión gratuita
    # Gemini 2.5 Flash es más económico y veloz para tareas de texto
    modelos_a_usar = [
        'gemini-3-pro-preview', # Alternaitiva rápida y económica
        'gemini-2.5-pro'         # Modelo potente con menor cuota gratuita
    ]

    # 2. VERIFICAR CARPETAS
    if not os.path.exists(CARPETA_NEWS):
        os.makedirs(CARPETA_NEWS)
        print(f"📁 Carpeta '{CARPETA_NEWS}' creada automáticamente.")

    # 3. BUSCAR TUITS
    patron_busqueda = os.path.join(CARPETA_TUITS, "*.json")
    archivos_json = glob.glob(patron_busqueda)

    print(f"📂 Se encontraron {len(archivos_json)} tuits en la carpeta '{CARPETA_TUITS}'.")

    if len(archivos_json) == 0:
        print("ℹ️ No hay nada que procesar. Finalizando.")
        return

    # 4. PROCESAR CADA TUIT
    nuevas_noticias = 0

    for archivo in archivos_json:
        try:
            # Preparamos el nombre del archivo de salida
            nombre_archivo = os.path.basename(archivo) # ej: tuit_123.json
            nombre_base = os.path.splitext(nombre_archivo)[0]
            ruta_salida = os.path.join(CARPETA_NEWS, f"noticia_{nombre_base}.txt")

            # Si ya existe la noticia, no gastamos saldo de API
            if os.path.exists(ruta_salida):
                # print(f"⏩ Saltando {nombre_archivo}, ya fue procesado.")
                continue

            print(f"🤖 Generando noticia para: {nombre_archivo}...")

            # Leemos el tuit
            with open(archivo, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Intentamos obtener el texto, si falla usamos todo el json
                contenido = data.get('text', str(data))

            # Intentar generar contenido con los modelos en orden de preferencia
            texto_generado = None
            modelo_usado = None

            for modelo in modelos_a_usar:
                try:
                    print(f"   Intentando con modelo: {modelo}")
                    texto_generado = generar_noticia_con_modelo(modelo, contenido)
                    modelo_usado = modelo
                    print(f"   ✅ Éxito con modelo: {modelo}")
                    break  # Salir del bucle si tuvimos éxito
                except Exception as e:
                    if "429" in str(e) or "quota" in str(e).lower() or "rate limit" in str(e).lower():
                        print(f"   ⏰ Límite de cuota alcanzado para {modelo}, probando siguiente...")
                        continue  # Probar con el siguiente modelo
                    else:
                        print(f"   ❌ Error distinto de cuota con {modelo}: {e}")
                        continue  # Probar con el siguiente modelo

            if texto_generado is None:
                print(f"   ❌ No se pudo generar contenido con ningún modelo para {nombre_archivo}")
                continue

            # Guardamos el resultado
            with open(ruta_salida, "w", encoding="utf-8") as f:
                f.write(texto_generado)

            print(f"✅ Noticia guardada: {ruta_salida} (usando {modelo_usado})")
            nuevas_noticias += 1

            # Pausa de cortesía para la API (Rate Limit)
            time.sleep(2)

        except Exception as e:
            print(f"⚠️ Error procesando {archivo}: {e}")

    print(f"🏁 Proceso finalizado. Se generaron {nuevas_noticias} noticias nuevas.")

if __name__ == "__main__":
    main()

