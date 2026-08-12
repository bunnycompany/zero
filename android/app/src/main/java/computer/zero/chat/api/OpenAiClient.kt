package computer.zero.chat.api

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.withContext
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import okhttp3.Call
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

@Serializable
data class ChatMessage(val role: String, val content: String)

@Serializable
data class ChatRequest(
    val model: String,
    val messages: List<ChatMessage>,
    val stream: Boolean = true,
    val temperature: Double = 0.7,
    // reasoning models can spend their entire budget thinking; cap it so a
    // chat reply on a small machine stays minutes-not-hours bounded
    @SerialName("max_tokens") val maxTokens: Int = 4096,
)

@Serializable
data class StreamDelta(
    val content: String? = null,
    val role: String? = null,
    val reasoning: String? = null,
    // the danger.plus gateway's dialect for the same thing
    @SerialName("reasoning_content") val reasoningContent: String? = null,
)

@Serializable
data class StreamChoice(val delta: StreamDelta? = null, @SerialName("finish_reason") val finishReason: String? = null)

@Serializable
data class StreamChunk(val choices: List<StreamChoice> = emptyList())

@Serializable
data class ModelInfo(val id: String)

@Serializable
data class ModelsResponse(val data: List<ModelInfo> = emptyList())

sealed class StreamEvent {
    data class Token(val text: String) : StreamEvent()
    data class Reasoning(val text: String) : StreamEvent()
    data object Done : StreamEvent()
    data class Error(val message: String) : StreamEvent()
}

/**
 * Minimal client for any OpenAI-compatible /v1 endpoint (mlx_lm.server,
 * LM Studio, Ollama, ...). Deliberately tolerant: malformed stream chunks
 * are skipped, never fatal — a family member's chat must not crash because
 * a server hiccuped mid-token.
 */
class OpenAiClient(
    private val baseUrl: String,
    private val apiKey: String? = null,
) {
    // encodeDefaults: kotlinx omits properties equal to their defaults unless
    // told otherwise — which silently dropped stream/temperature/max_tokens
    // and turned every request non-streaming. Hard-won line; do not remove.
    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    private val http = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS) // streaming: no read deadline
        .build()

    private fun request(path: String) = Request.Builder()
        .url(baseUrl.trimEnd('/') + path)
        .apply { apiKey?.takeIf { it.isNotBlank() }?.let { header("Authorization", "Bearer $it") } }

    suspend fun listModels(): Result<List<String>> = withContext(Dispatchers.IO) {
        runCatching {
            http.newCall(request("/models").get().build()).execute().use { resp ->
                if (!resp.isSuccessful) error("HTTP ${resp.code} from /models")
                val body = resp.body?.string() ?: error("empty response")
                json.decodeFromString<ModelsResponse>(body).data.map { it.id }
            }
        }
    }

    fun streamChat(model: String, history: List<ChatMessage>, temperature: Double): Flow<StreamEvent> =
        callbackFlow {
            val payload = json.encodeToString(
                ChatRequest.serializer(),
                ChatRequest(model = model, messages = history, temperature = temperature),
            )
            val call: Call = http.newCall(
                request("/chat/completions")
                    .post(payload.toRequestBody("application/json".toMediaType()))
                    .build()
            )
            try {
                call.execute().use { resp ->
                    if (!resp.isSuccessful) {
                        val detail = resp.body?.string()?.take(200) ?: ""
                        trySend(StreamEvent.Error("HTTP ${resp.code} $detail"))
                        return@use
                    }
                    val source = resp.body?.source() ?: run {
                        trySend(StreamEvent.Error("empty response body"))
                        return@use
                    }
                    while (!source.exhausted()) {
                        val line = source.readUtf8Line() ?: break
                        if (!line.startsWith("data:")) continue
                        val data = line.removePrefix("data:").trim()
                        if (data == "[DONE]") break
                        val chunk = runCatching {
                            json.decodeFromString<StreamChunk>(data)
                        }.getOrNull() ?: continue // tolerate malformed chunks
                        chunk.choices.firstOrNull()?.delta?.let { delta ->
                            (delta.reasoning ?: delta.reasoningContent)?.takeIf { it.isNotEmpty() }
                                ?.let { trySend(StreamEvent.Reasoning(it)) }
                            delta.content?.takeIf { it.isNotEmpty() }
                                ?.let { trySend(StreamEvent.Token(it)) }
                        }
                    }
                    trySend(StreamEvent.Done)
                }
            } catch (e: Exception) {
                trySend(StreamEvent.Error(e.message ?: e.javaClass.simpleName))
            } finally {
                close()
            }
            awaitClose { call.cancel() }
        }.flowOn(Dispatchers.IO)
}
