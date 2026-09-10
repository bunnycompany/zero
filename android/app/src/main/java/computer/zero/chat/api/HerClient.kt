package computer.zero.chat.api

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

/**
 * Client for Her's LAN bridge (her/bridge.py on the Mac). Not a model API:
 * this talks to the agent — every message lands in the same command inbox a
 * keystroke at the Mac does, tagged as coming from this phone, which the
 * executor treats as untrusted (it can ask; it can never change the Mac).
 */
@Serializable
data class HerQuestion(val id: String, val text: String)

@Serializable
data class HerPresence(
    val line: String = "",
    val glance: String = "",
    val state: String = "idle",
    val question: HerQuestion? = null,
    val attention: Boolean = false,
    val level: String = "quiet",
)

@Serializable
data class HerAnswer(val text: String = "", val goal: String = "")

@Serializable
data class HerSnapshot(
    val alive: Boolean = false,
    val status: String = "idle",
    val mode: String = "shadow",
    val presence: HerPresence? = null,
    val answer: HerAnswer? = null,
    @kotlinx.serialization.SerialName("answer_ts") val answerTs: Double? = null,
    val name: String = "Her",
)

@Serializable
data class HerHealth(val her: Boolean = false, val name: String = "Her", val alive: Boolean = false,
                     @kotlinx.serialization.SerialName("pairing_open") val pairingOpen: Boolean = false)

@Serializable
data class PairResult(val device: String, val token: String, val name: String = "Her")

@Serializable
private data class PairBody(val code: String, val name: String, val kind: String)

@Serializable
private data class SayBody(val text: String, @kotlinx.serialization.SerialName("reply_to") val replyTo: String? = null)

@Serializable
private data class ErrorBody(val error: String = "")

class HerClient(private val baseUrl: String, private val token: String? = null) {
    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true; explicitNulls = false }
    private val http = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()
    private val media = "application/json; charset=utf-8".toMediaType()

    private fun req(path: String): Request.Builder {
        val b = Request.Builder().url(baseUrl.trimEnd('/') + path)
        if (token != null) b.header("Authorization", "Bearer $token")
        return b
    }

    private suspend inline fun <reified T> call(crossinline build: Request.Builder.() -> Request.Builder): Result<T> =
        withContext(Dispatchers.IO) {
            runCatching {
                http.newCall(build(req("")).build()).execute().use { resp ->
                    val body = resp.body?.string() ?: ""
                    if (!resp.isSuccessful) {
                        val msg = runCatching { json.decodeFromString<ErrorBody>(body).error }.getOrDefault("")
                        error(msg.ifEmpty { "HTTP ${resp.code}" })
                    }
                    json.decodeFromString<T>(body)
                }
            }
        }

    suspend fun health(): Result<HerHealth> = call { url(baseUrl.trimEnd('/') + "/health").get() }

    suspend fun pair(code: String, deviceName: String, kind: String = "phone"): Result<PairResult> = call {
        url(baseUrl.trimEnd('/') + "/pair")
            .post(json.encodeToString(PairBody(code.trim().uppercase(), deviceName, kind)).toRequestBody(media))
    }

    suspend fun presence(): Result<HerSnapshot> = call { url(baseUrl.trimEnd('/') + "/v1/presence").get() }

    suspend fun say(text: String, replyTo: String? = null): Result<Unit> =
        call<Map<String, kotlinx.serialization.json.JsonElement>> {
            url(baseUrl.trimEnd('/') + "/v1/say")
                .post(json.encodeToString(SayBody(text, replyTo)).toRequestBody(media))
        }.map { }
}
