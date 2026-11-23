# ModuRelay

Configure **ModuRelay** in Model Providers with your gateway API key.
The default base URL is `https://ai.zhihengxiangyu.com`; root URLs and URLs
already ending in `/v1` use the same API root. Credentials are independent of
OpenAI and other providers. `MODURELAY_API_KEY` and `MODURELAY_BASE_URL` can
also be supplied through the existing permitted environment fallback.

Models are discovered from the key's `GET /v1/models` catalog, with no static
model whitelist. Enable the desired models in settings. Chat, reasoning,
vision and tools use the existing Language Model / Agent components; vectors
use Embedding Model. Gateway capability annotations take precedence over
name hints. Unannotated aliases remain usable with an explicit endpoint.

Use **ModuRelay Request** for images, audio, video, reranking, Responses or
other gateway APIs. Select a model, enter a prompt, and choose the endpoint
when Auto cannot identify an unannotated alias. JSON Body supplies arbitrary
API parameters; the selected model ID is preserved. POST returns the gateway
JSON unchanged inside `result`. For asynchronous APIs, pass the returned job
ID to a second component with method GET and the job endpoint. Binary results
include `content_type` and `content_base64`.

Native Anthropic requests can use `/messages`; the component adds the protocol
version. For Gemini use `/v1beta/models/{model}:generateContent` with `contents`
in JSON Body, or use Prompt for a text request. The placeholder uses the selected
model and prevents the path from overriding it. Explicit versioned paths such as
`/api/v3/contents/generations/tasks` retain their gateway route.
Other native model actions, including `:embedContent` and `:predict`, accept their
native JSON Body without adding a redundant top-level model field.

Multipart Files accepts Data with fields such as:
`{"file": {"filename": "speech.wav", "content_base64": "...", "content_type": "audio/wav"}}`.
This supports uploaded audio and image edit inputs without reading arbitrary
server paths. Multipart form fields come from JSON Body.

A listed model must still be supported by the key's group, upstream account,
and selected API. Discovery cannot guarantee upstream availability or billing
permissions. Credential validation only reads the model list and never
generates a completion. Realtime WebSocket sessions are not workflow outputs;
use the gateway's HTTP endpoints for workflow requests.

