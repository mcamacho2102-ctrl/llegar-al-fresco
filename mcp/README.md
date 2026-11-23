# Servidor MCP · Llegar al fresco

Conecta un asistente de IA (Claude Desktop, VS Code, Cursor…) con la aplicación. Las respuestas salen de los datos abiertos y del motor de rutas, no de la memoria del modelo. Solo necesita Python 3.9 o posterior, sin dependencias.

| Herramienta | Qué responde |
|---|---|
| `buscar_lugar` | Direcciones y destinos de los registros de la Comunidad: centros de salud, centros de día, farmacias y bibliotecas |
| `ruta_con_descansos` | Ruta más corta frente a la ruta que nunca supera X m sin banco, con paradas, sol, pendiente y fuentes |
| `bancos_prioritarios` | Dónde poner un banco nuevo para que más portales lleguen a un destino |
| `municipios_prioritarios` | Clasificación de los 179 municipios (solo datos de la Comunidad) |
| `impacto_madrid` | Cifra de impacto por distrito y sensibilidad |

## Configuración en Claude Desktop

*Ajustes → Desarrollador → Editar configuración*:

```json
{
  "mcpServers": {
    "llegar-al-fresco": {
      "command": "python3",
      "args": ["/ruta/a/llegar-al-fresco/mcp/servidor.py"],
      "env": { "LLEGAR_URL": "http://127.0.0.1:8768" }
    }
  }
}
```

`LLEGAR_URL` puede apuntar a la demo pública. Para probarlo sin cliente: `python3 mcp/probar.py`.

## Guion de demo (30 segundos)

1. «Mi madre tiene 82 años y no puede andar más de 150 metros sin sentarse. ¿Cómo va de Plaza de la Virgen de la Paloma 1 a la Biblioteca Pedro Salinas el 1 de julio a las 14:00?»
   → El asistente llama a `ruta_con_descansos` y explica la ruta, en qué banco parar y cuántos minutos irá al sol.
2. «Soy técnica del ayuntamiento. ¿Dónde pondrías un banco para mejorar ese acceso?» → `bancos_prioritarios`.
3. «¿Qué municipios de la Comunidad deberían ser los siguientes?» → `municipios_prioritarios`.
