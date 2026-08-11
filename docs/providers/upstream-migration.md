# Upstream Provider migration seam

The first migration step is deliberately adapter-only. Existing business
services remain the source of truth while `BuiltinProviderAdapter` normalizes
their input/output into the Provider Kernel contract.

| Existing service                                       | Provider kind | Capability          | Adapter boundary                  |
| ------------------------------------------------------ | ------------- | ------------------- | --------------------------------- |
| `workbench.integrations.llm.client.LlmClient.complete` | `llm`         | `completion`        | injected completion callable      |
| `workbench.audio.transcriber.Transcriber.transcribe`   | `asr`         | `transcription`     | injected transcript callable      |
| local TTS/HeyGen audio service                         | `tts`         | `speech.synthesize` | injected audio artifact callable  |
| HeyGen avatar client                                   | `avatar`      | `avatar.generate`   | injected video artifact callable  |
| `workbench.ocr.paddle_adapter.OcrEngine.recognize`     | `ocr`         | `text.extract`      | injected OCR result callable      |
| `workbench.video.render_service.PageRenderer.render`   | `renderer`    | `render.page`       | injected render artifact callable |

Only the six static `builtin-*` descriptors are accepted. The adapter rejects
absolute paths and returns content-addressed `artifact://sha256:...` references;
it never returns provider prompt text, API keys, cookies, or vendor SDK objects.
The next migration batch can inject the real callable behind each descriptor,
compare legacy/new outputs under a feature flag, and roll back without changing
project revisions.
