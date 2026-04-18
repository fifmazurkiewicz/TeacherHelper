# modules/graphics — generator grafik

## Odpowiedzialność

Grafiki sceniczne, kostiumy, rekwizyty, plakaty, zaproszenia; styl przyjazny dzieciom.

## Formaty

PNG, JPG, PDF, SVG.

## Adaptery zewnętrzne

DALL-E, Stable Diffusion, Midjourney (każdy za osobnym adapterem implementującym wspólny port `ImageGeneratorPort`).

## Zasady

- Prompt budowany z kontekstu projektu (opcjonalnie z **core/file-context**).
- Zapis wyniku przez **core/files** + trigger indeksowania dla opisu obrazu (vision).
- Moduł uruchamiany przez tool call `generate_graphics`.
